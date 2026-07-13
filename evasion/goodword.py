#!/usr/bin/env python3
"""
GoodWord Evasion Attack
========================
Evade text classifiers (spam filters, content moderation) by inserting
benign tokens that shift the classifier's decision.

Techniques:
  - White-box: extract GoodWords from model internals (Naive Bayes feature_log_prob_)
  - Black-box: discover effective words via 3-phase adaptive querying
  - Evaluation: evasion rate measurement with increasing word count

Works against any classifier that combines word features additively
(Naive Bayes, logistic regression, linear SVMs).

Usage:
    python goodword.py --mode whitebox --model spam_model.pkl --vectorizer vec.pkl
    python goodword.py --mode blackbox --target http://target/api/classify --budget 1000
    python goodword.py --mode evaluate --model spam_model.pkl --vectorizer vec.pkl --spam-file spam.txt
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False

try:
    import joblib
    _HAS_JOBLIB = True
except ImportError:
    _HAS_JOBLIB = False

try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    import urllib.request
    _HTTP = "urllib"


# ============================================================
# WHITE-BOX: EXTRACT GOODWORDS FROM MODEL
# ============================================================

def extract_goodwords(classifier, vectorizer, top_n=100):
    """
    Extract GoodWords from a Naive Bayes classifier.

    GoodWords are tokens with high P(word|ham) / P(word|spam) ratio.
    Adding them to spam messages shifts the posterior toward ham.

    Args:
        classifier: trained MultinomialNB with feature_log_prob_
        vectorizer: fitted CountVectorizer/TfidfVectorizer
        top_n: number of top words to return

    Returns:
        list of (word, goodness_score, ham_prob, spam_prob)
    """
    feature_names = vectorizer.get_feature_names_out()
    ham_log_probs = classifier.feature_log_prob_[0]   # P(w|ham)
    spam_log_probs = classifier.feature_log_prob_[1]  # P(w|spam)

    goodness_scores = []
    for i, word in enumerate(feature_names):
        ham_prob = np.exp(ham_log_probs[i])
        spam_prob = np.exp(spam_log_probs[i])
        goodness = ham_prob / (spam_prob + 1e-10)
        goodness_scores.append((word, goodness, ham_prob, spam_prob))

    goodness_scores.sort(key=lambda x: x[1], reverse=True)
    return goodness_scores[:top_n]


def augment_message(message, words):
    """Append GoodWords to a message."""
    if words:
        return message + " " + " ".join(words)
    return message


def whitebox_attack(classifier, vectorizer, spam_messages, top_n=100,
                    test_counts=None, verbose=True):
    """
    White-box GoodWord attack: extract words and evaluate evasion.

    Args:
        classifier: trained Naive Bayes model
        vectorizer: fitted vectorizer
        spam_messages: list of spam messages to evade
        top_n: number of GoodWords to extract
        test_counts: list of word counts to test (default: [0,5,10,15,20])

    Returns:
        (goodwords, results_dict)
    """
    if test_counts is None:
        test_counts = [0, 5, 10, 15, 20]

    goodwords = extract_goodwords(classifier, vectorizer, top_n)

    if verbose:
        print(f"[*] Top 10 GoodWords:")
        for word, score, hp, sp in goodwords[:10]:
            print(f"    {word:15s} | goodness: {score:8.2f} | "
                  f"ham_p: {hp:.4f} | spam_p: {sp:.4f}")

    results = {}
    for num_words in test_counts:
        selected = [w for w, _, _, _ in goodwords[:num_words]]
        evaded = 0
        for message in spam_messages:
            augmented = augment_message(message, selected)
            vec = vectorizer.transform([augmented])
            prob = classifier.predict_proba(vec)[0]
            if prob[0] > prob[1]:  # ham_prob > spam_prob
                evaded += 1
        rate = 100 * evaded / max(len(spam_messages), 1)
        results[num_words] = rate
        if verbose:
            print(f"    Words: {num_words:3d} | Evasion: {rate:.2f}%")

    return goodwords, results


# ============================================================
# BLACK-BOX: 3-PHASE ADAPTIVE DISCOVERY
# ============================================================

def query_classifier(target_url, text, body_template=None, label_key="label",
                     prob_key="spam_probability"):
    """Query a remote classifier API. Returns (label, spam_probability)."""
    headers = {"Content-Type": "application/json"}
    if body_template:
        body = body_template.replace("{{PAYLOAD}}", text.replace('"', '\\"'))
    else:
        body = json.dumps({"message": text})

    if _HTTP == "httpx":
        client = httpx.Client(timeout=30, verify=False)
        resp = client.post(target_url, content=body.encode(), headers=headers)
        data = resp.json()
    else:
        req = urllib.request.Request(target_url, body.encode(), headers)
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())

    label = data.get(label_key, data.get("prediction", "unknown"))
    prob = data.get(prob_key, data.get("confidence", data.get("probability", 0.5)))
    return label, float(prob)


def build_candidate_vocabulary(ham_messages, min_freq=2):
    """Build candidate GoodWord vocabulary from known ham messages."""
    word_freq = defaultdict(int)
    for msg in ham_messages:
        for word in set(msg.lower().split()):
            word = word.strip(".,!?;:'\"()[]{}").strip()
            if len(word) >= 2:
                word_freq[word] += 1
    return [w for w, f in word_freq.items() if f >= min_freq]


def three_phase_discovery(spam_messages, candidate_words, predict_fn,
                          budget=1000, verbose=True):
    """
    3-phase black-box GoodWord discovery.

    Phase 1 (40%): Exploration — test wide, identify candidates with ε-greedy
    Phase 2 (40%): Exploitation — refine scores on top candidates
    Phase 3 (20%): Combinations — find synergistic word pairs/triplets

    Args:
        spam_messages: list of spam messages to test against
        candidate_words: list of candidate words to evaluate
        predict_fn: function(text) -> (label, spam_probability)
        budget: total query budget

    Returns:
        (ranked_words, best_combinations, queries_used)
    """
    exploration_budget = int(budget * 0.4)
    exploitation_budget = int(budget * 0.4)
    combination_budget = budget - exploration_budget - exploitation_budget

    # Word scoring via exponential moving average
    word_scores = {w: 0.0 for w in candidate_words}
    word_counts = {w: 0 for w in candidate_words}
    alpha = 0.3  # EMA smoothing
    queries_used = 0

    # --- Phase 1: Exploration ---
    if verbose:
        print(f"\n[Phase 1] Exploration ({exploration_budget} queries)")

    exploration_rate = 0.2
    while queries_used < exploration_budget and candidate_words:
        test_message = random.choice(spam_messages)
        word = _epsilon_greedy_select(word_scores, candidate_words, exploration_rate)

        # Baseline probability
        _, prob_orig = predict_fn(test_message)
        queries_used += 1

        # Augmented probability
        augmented = test_message + " " + word
        _, prob_aug = predict_fn(augmented)
        queries_used += 1

        # Impact = reduction in spam probability
        impact = prob_orig - prob_aug
        _update_score(word_scores, word_counts, word, impact, alpha)

        if queries_used % 50 == 0 and verbose:
            top3 = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"    queries={queries_used} top3={[(w, f'{s:.3f}') for w, s in top3]}")

    # --- Phase 2: Exploitation ---
    if verbose:
        print(f"\n[Phase 2] Exploitation ({exploitation_budget} queries)")

    sorted_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
    top_words = [w for w, _ in sorted_words[:min(30, len(sorted_words))]]
    initial_queries = queries_used

    while queries_used < initial_queries + exploitation_budget and top_words:
        test_message = random.choice(spam_messages[:20])
        word = _epsilon_greedy_select(word_scores, top_words, 0.1)

        _, prob_orig = predict_fn(test_message)
        queries_used += 1

        augmented = test_message + " " + word
        _, prob_aug = predict_fn(augmented)
        queries_used += 1

        impact = prob_orig - prob_aug
        _update_score(word_scores, word_counts, word, impact, alpha)

    # --- Phase 3: Combinations ---
    if verbose:
        print(f"\n[Phase 3] Combinations ({combination_budget} queries)")

    best_combinations = {}
    combo_queries = 0
    sorted_final = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)
    top_combo_words = [w for w, _ in sorted_final[:min(20, len(sorted_final))]]

    for msg in spam_messages[:3]:
        if combo_queries >= combination_budget:
            break

        for i in range(len(top_combo_words)):
            for j in range(i + 1, min(i + 5, len(top_combo_words))):
                if combo_queries >= combination_budget:
                    break
                w1, w2 = top_combo_words[i], top_combo_words[j]
                augmented = msg + " " + w1 + " " + w2
                _, prob = predict_fn(augmented)
                combo_queries += 1
                queries_used += 1

                combo_key = (w1, w2)
                _, baseline = predict_fn(msg)
                combo_queries += 1
                queries_used += 1

                score = baseline - prob
                if score > best_combinations.get(combo_key, 0):
                    best_combinations[combo_key] = score

    # Final ranking
    final_words = sorted(word_scores.items(), key=lambda x: x[1], reverse=True)

    if verbose:
        print(f"\n[*] Discovery complete: {queries_used} queries used")
        print(f"    Top 10 words:")
        for word, score in final_words[:10]:
            print(f"      {word:15s} | impact: {score:.4f}")
        if best_combinations:
            top_combos = sorted(best_combinations.items(),
                                key=lambda x: x[1], reverse=True)[:5]
            print(f"    Top 5 combinations:")
            for combo, score in top_combos:
                print(f"      {'+'.join(combo):25s} | impact: {score:.4f}")

    return final_words, best_combinations, queries_used


def _epsilon_greedy_select(scores, candidates, epsilon):
    """ε-greedy selection: explore with probability ε, exploit otherwise."""
    if random.random() < epsilon:
        return random.choice(candidates)
    return max(candidates, key=lambda w: scores.get(w, 0))


def _update_score(scores, counts, word, impact, alpha):
    """Update word score with exponential moving average."""
    counts[word] = counts.get(word, 0) + 1
    if counts[word] == 1:
        scores[word] = impact
    else:
        scores[word] = alpha * impact + (1 - alpha) * scores.get(word, 0)


def blackbox_attack(target_url, spam_messages, ham_messages=None,
                    candidate_words=None, budget=1000,
                    body_template=None, label_key="label",
                    prob_key="spam_probability",
                    test_counts=None, verbose=True):
    """
    Full black-box GoodWord attack pipeline.

    Args:
        target_url: classifier API URL
        spam_messages: messages to evade
        ham_messages: ham messages for vocabulary building (optional)
        candidate_words: pre-built word list (optional)
        budget: query budget
        test_counts: word counts to evaluate (default: [0,5,10,15,20,25,30])

    Returns:
        (discovered_words, evasion_results)
    """
    if test_counts is None:
        test_counts = [0, 5, 10, 15, 20, 25, 30]

    def predict_fn(text):
        return query_classifier(target_url, text, body_template,
                                label_key, prob_key)

    # Build vocabulary if not provided
    if candidate_words is None:
        if ham_messages is None:
            candidate_words = [
                "thanks", "hello", "meeting", "tomorrow", "later",
                "going", "home", "work", "really", "good", "great",
                "sure", "yeah", "okay", "fine", "please", "today",
                "love", "happy", "nice", "call", "lunch", "dinner",
            ]
        else:
            candidate_words = build_candidate_vocabulary(ham_messages)

    print(f"[*] Black-box GoodWord attack")
    print(f"    Target: {target_url}")
    print(f"    Budget: {budget} queries")
    print(f"    Candidates: {len(candidate_words)} words")
    print(f"    Spam messages: {len(spam_messages)}")

    # Discovery
    discovered, combos, queries = three_phase_discovery(
        spam_messages=spam_messages[:50],
        candidate_words=candidate_words,
        predict_fn=predict_fn,
        budget=budget,
        verbose=verbose,
    )

    # Evaluate evasion
    print(f"\n[*] Evaluating evasion rate...")
    results = {}
    eval_messages = spam_messages[30:50] if len(spam_messages) > 50 else spam_messages

    for num_words in test_counts:
        selected = [w for w, _ in discovered[:num_words]]
        evaded = 0
        for msg in eval_messages:
            aug = msg + " " + " ".join(selected) if num_words > 0 else msg
            label, prob = predict_fn(aug)
            if prob < 0.5:  # classified as ham
                evaded += 1
        rate = 100 * evaded / max(len(eval_messages), 1)
        results[num_words] = rate
        print(f"    Words: {num_words:3d} | Evasion: {rate:.2f}%")

    return discovered, results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="GoodWord Evasion Attack for Text Classifiers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # White-box attack (requires model access)
  python goodword.py --mode whitebox \\
    --model spam_model.pkl --vectorizer vec.pkl \\
    --spam-file spam_messages.txt

  # Black-box attack (query-only)
  python goodword.py --mode blackbox \\
    --target http://target/api/classify --budget 1000 \\
    --spam-file spam_messages.txt

  # With custom vocabulary
  python goodword.py --mode blackbox \\
    --target http://target/api/classify \\
    --wordlist candidate_words.txt --spam-file spam.txt

Theory:
  Naive Bayes computes: log P(ham|msg) = log P(ham) + Σ log P(w|ham)
  Each GoodWord contributes additively to the ham score.
  ~20 well-chosen words achieve 100% evasion on Naive Bayes classifiers.
        """
    )
    parser.add_argument("--mode", choices=["whitebox", "blackbox"],
                        required=True, help="Attack mode")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to trained classifier (pickle/joblib)")
    parser.add_argument("--vectorizer", type=str, default=None,
                        help="Path to fitted vectorizer (pickle/joblib)")
    parser.add_argument("--target", type=str, default=None,
                        help="Target classifier API URL (blackbox mode)")
    parser.add_argument("--spam-file", type=str, default=None,
                        help="File with spam messages (one per line)")
    parser.add_argument("--ham-file", type=str, default=None,
                        help="File with ham messages for vocabulary building")
    parser.add_argument("--wordlist", type=str, default=None,
                        help="File with candidate words (one per line)")
    parser.add_argument("--budget", type=int, default=1000,
                        help="Query budget for black-box (default: 1000)")
    parser.add_argument("--top-n", type=int, default=100,
                        help="Number of GoodWords to extract (default: 100)")
    parser.add_argument("--body-template", type=str, default=None,
                        help='JSON body template with {{PAYLOAD}} placeholder')
    parser.add_argument("--output", type=str, default=None,
                        help="Export results to JSON")
    args = parser.parse_args()

    # Load spam messages
    spam_messages = []
    if args.spam_file:
        with open(args.spam_file) as f:
            spam_messages = [line.strip() for line in f if line.strip()]
    if not spam_messages:
        spam_messages = [
            "Congratulations! You won a free iPhone! Click here now!",
            "URGENT: Your account will be suspended. Verify immediately.",
            "Make $5000/week from home! Limited time offer!",
            "FREE entry to win $1000 cash prize! Text WIN to 12345",
            "Hot singles in your area want to meet you tonight!",
        ]
        print("[*] Using demo spam messages. Use --spam-file for real attacks.")

    if args.mode == "whitebox":
        if not _HAS_NP or not _HAS_JOBLIB:
            print("[!] Required: pip install numpy joblib scikit-learn")
            sys.exit(1)
        if not args.model or not args.vectorizer:
            print("[!] --model and --vectorizer required for whitebox mode")
            sys.exit(1)

        classifier = joblib.load(args.model)
        vectorizer = joblib.load(args.vectorizer)
        goodwords, results = whitebox_attack(
            classifier, vectorizer, spam_messages, top_n=args.top_n
        )

        if args.output:
            data = {
                "goodwords": [(w, float(s)) for w, s, _, _ in goodwords[:50]],
                "evasion_results": results,
            }
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)

    elif args.mode == "blackbox":
        if not args.target:
            print("[!] --target required for blackbox mode")
            sys.exit(1)

        ham_messages = None
        if args.ham_file:
            with open(args.ham_file) as f:
                ham_messages = [line.strip() for line in f if line.strip()]

        candidate_words = None
        if args.wordlist:
            with open(args.wordlist) as f:
                candidate_words = [line.strip() for line in f if line.strip()]

        discovered, results = blackbox_attack(
            target_url=args.target,
            spam_messages=spam_messages,
            ham_messages=ham_messages,
            candidate_words=candidate_words,
            budget=args.budget,
            body_template=args.body_template,
        )

        if args.output:
            data = {
                "discovered_words": [(w, float(s)) for w, s in discovered[:50]],
                "evasion_results": results,
            }
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
