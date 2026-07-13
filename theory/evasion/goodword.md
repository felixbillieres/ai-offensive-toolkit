# GoodWord Attack (Text Classifier Evasion)

> **In one sentence:** Sneak a spam or malicious message past a text classifier by adding a few innocent, "hammy" words that additively drag the classifier's score across its decision threshold.

## What it is

The GoodWord attack (Lowd and Meek, 2005) is an evasion attack against **text classifiers**: spam filters, content moderation, phishing detectors. It does not change the malicious payload; it *appends benign words* ("good words") whose presence the classifier associates with the safe class. Because many classic text classifiers score words additively, enough good words tip the total from "spam" to "ham". The toolkit ships both a white-box and a black-box version in `goodword.py`.

## The problem it exploits

Naive Bayes, logistic regression, and linear SVMs all score a document as a **sum of per-word contributions**. A Naive Bayes spam filter computes:

```
log P(ham | msg) = log P(ham) + sum over words w in msg of log P(w | ham)
```

Each word pushes the score toward ham or spam independently. This additivity is the flaw: a word strongly associated with legitimate mail ("meeting", "thanks", "invoice") contributes a big positive push toward ham *regardless of the surrounding spam*. Add enough such words and their combined push overwhelms the spammy words. GoodWord exploits exactly this linear, per-word additive structure. Against Naive Bayes, roughly 20 well-chosen words reach ~100% evasion.

## Intuition

Picture a bouncer who decides "spam or not" by adding points: bad words score negative, wholesome words score positive, and if the total is above zero you get in. A spammer cannot easily remove the bad words (that is the payload), but they *can* pile on wholesome words. Staple enough phrases like "team meeting agenda thanks regards" onto the message and the positive points bury the negative ones, so the bouncer waves the spam through. The message still reads as spam to a human, but the arithmetic says "legitimate".

## How it works

### White-box (you can read the model)

```
For a Naive Bayes model with feature_log_prob_:
    goodness(w) = P(w | ham) / P(w | spam)          # high = strong ham signal
    rank all vocabulary words by goodness, take the top N
    augmented_message = spam_message + " " + top-N good words
```

The toolkit's `extract_goodwords` reads `classifier.feature_log_prob_[0]` (ham) and `[1]` (spam) directly, computes the goodness ratio for every vocabulary word, and returns them ranked. `whitebox_attack` then measures evasion at increasing word counts (0, 5, 10, 15, 20).

### Black-box (query only, 3-phase adaptive discovery)

When you cannot read the model, discover good words by querying and watching the spam probability drop:

```
Phase 1 Exploration (40% of budget): test many candidate words with
        epsilon-greedy selection; score each word by how much it lowers
        the spam probability (impact = prob_before - prob_after),
        tracked with an exponential moving average.
Phase 2 Exploitation (40%): re-test the top ~30 words to refine scores.
Phase 3 Combinations (20%): search for synergistic word pairs.
Then evaluate evasion at increasing word counts.
```

The toolkit's `three_phase_discovery` implements this with `_epsilon_greedy_select` and EMA scoring; `blackbox_attack` wraps it end to end and can build the candidate vocabulary from known ham messages.

## Threat model and prerequisites

- **White-box:** you have the trained classifier and its vectorizer (e.g. a pickled `MultinomialNB` + `CountVectorizer`). Zero queries needed.
- **Black-box:** you can send text to the classifier API and read back a label and/or a spam probability. Query budget is the constraint (default 1000).
- **Applies to:** any classifier that combines word features additively (Naive Bayes, logistic regression, linear SVM). Modern transformer-based moderation is far less linear, so this specific technique is weaker there.

## When to use it

Use GoodWord when:

- The target is a **classic linear/Naive-Bayes text classifier** (spam filters, simple moderation).
- You can either **read the model** (white-box, instant) or **query it** (black-box, with a query budget).

For non-linear NLP models (transformers), prefer token-level adversarial text attacks (synonym substitution, character perturbations) rather than pure additive good-word insertion; GoodWord remains a strong baseline and a great teaching example of the additive-scoring flaw.

## Step by step with the toolkit

`goodword.py` has a full CLI.

```bash
# White-box: extract good words from a pickled model and measure evasion
python -m evasion.goodword --mode whitebox \
    --model spam_model.pkl --vectorizer vec.pkl \
    --spam-file spam_messages.txt --output wb.json

# Black-box: discover good words by querying a remote API
python -m evasion.goodword --mode blackbox \
    --target http://target/api/classify --budget 1000 \
    --spam-file spam_messages.txt

# Black-box with a custom candidate wordlist and JSON body template
python -m evasion.goodword --mode blackbox \
    --target http://target/api/classify \
    --wordlist candidate_words.txt --spam-file spam.txt \
    --body-template '{"message":"{{PAYLOAD}}"}'
```

In Python:

```python
from evasion.goodword import extract_goodwords, whitebox_attack, blackbox_attack

goodwords, results = whitebox_attack(classifier, vectorizer, spam_messages, top_n=100)
# results maps word_count -> evasion_rate_percent
```

Key flags: `--mode {whitebox,blackbox}`, `--model`/`--vectorizer` (white-box), `--target`/`--budget` (black-box), `--spam-file`, `--ham-file` (builds candidate vocabulary), `--wordlist`, `--body-template` (with `{{PAYLOAD}}`), `--top-n`, `--output`.

## Detection and defense

- **Non-linear models** (transformers, gradient-boosted feature interactions) break the additive assumption and blunt the attack.
- **Feature-count / length anomaly detection**: messages padded with many unrelated ham words look statistically odd.
- **Ignoring or down-weighting good words** (feature selection, dropping tokens with suspiciously high ham weight) reduces their leverage.
- **Query rate limiting** raises the cost of black-box discovery.
- **Retraining on adversarial (good-word-padded) examples** teaches the filter to distrust the padding pattern.

## Explain it to a non-expert

Simple spam filters score each word for and against and add it all up. GoodWord keeps the spam but staples on a bunch of ordinary, wholesome words until the "looks legitimate" points outweigh the "looks like spam" points, so the filter lets it through. You can find those magic words either by reading the filter's internals or by probing it and watching which words lower its suspicion. It is the classic demonstration of why additive text scoring is easy to game.

## References

- Lowd and Meek (2005), *Good Word Attacks on Statistical Spam Filters*
- HTB AI Red Teamer, module 08 (evasion foundations), GoodWord and black-box GoodWord sections
- Related: [overview](00-overview.md), and for image evasion, [FGSM](fgsm.md) / [PGD](pgd.md)
