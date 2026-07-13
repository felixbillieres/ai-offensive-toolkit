#!/usr/bin/env python3
"""
Embedding Inversion Attack
==========================
Reconstruct the source text from its embedding vector, the privacy leak that
turns a RAG vector database into a copy of the private corpus it indexes.

Vector databases store embeddings of private documents (support tickets, code,
medical notes, chat logs). Those embeddings are widely treated as opaque, non
reversible hashes. They are not. The vec2text line of work (Morris et al.,
2023, "Text Embeddings Reveal (Almost) As Much As Text") shows that a dedicated
decoder can recover the original text almost verbatim from an embedding alone.

This module implements dependency light approximations of that idea:
  - Retrieval based inversion: rank a candidate pool by cosine similarity to
    the target embedding and return the best match (the practical attack when
    the attacker holds a plausible candidate set).
  - Greedy token inversion: rebuild text token by token, keeping each vocab
    word that increases cosine similarity to the target embedding.

All embedding backends are optional. Import never fails: sentence-transformers
is used if present, otherwise a scikit-learn TF-IDF space, otherwise a pure
Python hashing bag of words.

Usage:
    python -m rag_attacks.embedding_inversion --mode demo
    python -m rag_attacks.embedding_inversion --mode nn --text "secret" --candidates-file pool.txt
    python -m rag_attacks.embedding_inversion --mode greedy --text "secret" --vocab-file vocab.txt
"""

import argparse
import json
import re
import sys

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False

try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


DEFAULT_ST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_HASH_DIM = 512

# Cache the loaded sentence-transformer so repeated calls do not reload weights.
_ST_CACHE = {}


# ============================================================
# EMBEDDING BACKENDS (all optional, gated)
# ============================================================

def _require_numpy():
    if not _HAS_NP:
        print("[!] numpy is required: pip install numpy")
        sys.exit(1)


def _tokenize(text):
    """Lowercase word tokens, used by the fallback backends."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _hash_embed(texts, dim=_HASH_DIM):
    """Pure Python hashing bag of words. Zero dependencies beyond numpy."""
    vectors = np.zeros((len(texts), dim), dtype=np.float64)
    for i, text in enumerate(texts):
        for token in _tokenize(text):
            idx = hash(token) % dim
            vectors[i, idx] += 1.0
    return vectors


def _st_model(model_name=None):
    """Load (and cache) a sentence-transformers model."""
    name = model_name or DEFAULT_ST_MODEL
    if name not in _ST_CACHE:
        _ST_CACHE[name] = SentenceTransformer(name)
    return _ST_CACHE[name]


def embed_texts(texts, model_name=None):
    """
    Embed a list of texts into a numpy array (one row per text).

    Backend selection, best available first:
      1. sentence-transformers (_HAS_ST): real semantic embeddings, the space
         a production RAG store actually uses.
      2. scikit-learn TfidfVectorizer (_HAS_SKLEARN): TF-IDF fallback, fit on
         the provided texts.
      3. Hashing bag of words: pure numpy, always available.

    Args:
        texts: list of strings.
        model_name: sentence-transformers model id (ignored by fallbacks).

    Returns:
        numpy.ndarray of shape (len(texts), dim).
    """
    _require_numpy()
    if isinstance(texts, str):
        texts = [texts]

    if _HAS_ST:
        model = _st_model(model_name)
        vecs = model.encode(list(texts), convert_to_numpy=True,
                            show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float64)

    if _HAS_SKLEARN:
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(list(texts))
        return np.asarray(matrix.todense(), dtype=np.float64)

    return _hash_embed(list(texts))


# ============================================================
# SIMILARITY HELPERS
# ============================================================

def _cosine(a, b):
    """Cosine similarity between two 1D numpy vectors."""
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12
    return float(np.dot(a, b) / denom)


def _cosine_matrix(target, matrix):
    """Cosine similarity of a target vector against every row of a matrix."""
    target = np.asarray(target, dtype=np.float64).ravel()
    norms = np.linalg.norm(matrix, axis=1) + 1e-12
    t_norm = np.linalg.norm(target) + 1e-12
    return (matrix @ target) / (norms * t_norm)


# ============================================================
# ATTACK 1: RETRIEVAL BASED (NEAREST NEIGHBOR) INVERSION
# ============================================================

def nearest_neighbor_inversion(target_embedding, candidate_texts, model_name=None):
    """
    Recover the source text by matching the target embedding against a pool.

    This is the practical attack when the attacker has a candidate pool of
    plausible source texts (leaked corpus, guessed sentences, a public dataset
    the index was built from). Embed every candidate, then return whichever one
    lands closest to the stolen embedding in cosine space.

    Args:
        target_embedding: the embedding to invert (1D array-like).
        candidate_texts: list of candidate source strings.
        model_name: embedding model id (must match the victim store's model
            for the fallback-agnostic result to be meaningful).

    Returns:
        (best_text, best_score) where best_score is cosine similarity in [-1, 1].
    """
    _require_numpy()
    if not candidate_texts:
        return None, 0.0

    target = np.asarray(target_embedding, dtype=np.float64).ravel()
    cand_matrix = embed_texts(candidate_texts, model_name=model_name)

    sims = _cosine_matrix(target, cand_matrix)
    best_idx = int(np.argmax(sims))
    return candidate_texts[best_idx], float(sims[best_idx])


# ============================================================
# ATTACK 2: GREEDY TOKEN INVERSION
# ============================================================

def greedy_token_inversion(target_embedding, vocab, model_name=None,
                           max_len=20, beam=1):
    """
    Reconstruct text token by token by hill climbing cosine similarity.

    Starting from an empty string, at each step append the vocab word whose
    addition most increases the cosine similarity between the embedding of the
    reconstructed text so far and the target embedding. Stop when no word
    improves the score or max_len tokens have been added. This is a crude,
    dependency-light stand in for a trained vec2text decoder.

    Args:
        target_embedding: the embedding to invert (1D array-like).
        vocab: list of candidate words to draw from.
        model_name: embedding model id.
        max_len: maximum number of tokens to append.
        beam: beam width. beam=1 is pure greedy. Larger keeps the best `beam`
            partial reconstructions at each step.

    Returns:
        (reconstructed_text, final_similarity).
    """
    _require_numpy()
    target = np.asarray(target_embedding, dtype=np.float64).ravel()
    vocab = list(dict.fromkeys(w for w in vocab if w))
    if not vocab:
        return "", 0.0

    beam = max(1, int(beam))

    def score_of(text):
        if not text:
            return -1.0
        emb = embed_texts([text], model_name=model_name)[0]
        return _cosine(target, emb)

    # Each beam entry is (tokens, score).
    beams = [([], -1.0)]

    for _ in range(max_len):
        candidates = []
        for tokens, base_score in beams:
            improved = False
            for word in vocab:
                new_tokens = tokens + [word]
                new_score = score_of(" ".join(new_tokens))
                if new_score > base_score:
                    candidates.append((new_tokens, new_score))
                    improved = True
            # Allow keeping the current beam if nothing improved it.
            if not improved and tokens:
                candidates.append((tokens, base_score))

        if not candidates:
            break

        candidates.sort(key=lambda x: x[1], reverse=True)
        new_beams = candidates[:beam]

        # Stop if the best beam did not improve over the previous best.
        best_prev = max(s for _, s in beams)
        best_now = new_beams[0][1]
        if best_now <= best_prev and new_beams[0][0] == beams[0][0]:
            break
        beams = new_beams

    best_tokens, best_score = max(beams, key=lambda x: x[1])
    return " ".join(best_tokens), float(best_score)


# ============================================================
# DEMO
# ============================================================

def demo(model_name=None):
    """
    Self-contained example: embed a secret sentence, then recover it two ways.

    Shows both attacks against a single held-out secret:
      1. nearest_neighbor_inversion over a small candidate pool.
      2. greedy_token_inversion over a small vocabulary.
    """
    _require_numpy()

    secret = "the admin password is stored in the config vault"
    print("[*] Embedding inversion demo")
    print(f"    Backend: {_active_backend()}")
    print(f"    Secret : {secret!r}\n")

    target = embed_texts([secret], model_name=model_name)[0]

    # --- Attack 1: nearest neighbor over a candidate pool ---
    candidate_pool = [
        "the weather is nice today in the city",
        "the admin password is stored in the config vault",
        "please reset my account password by email",
        "the database backup runs every night at midnight",
        "the admin token is kept in the secrets manager",
        "users can update their profile picture anytime",
    ]
    nn_text, nn_score = nearest_neighbor_inversion(
        target, candidate_pool, model_name=model_name)
    print("[Attack 1] Nearest-neighbor (retrieval based) inversion")
    print(f"    Recovered : {nn_text!r}")
    print(f"    Similarity: {nn_score:.4f}")
    print(f"    Exact match: {nn_text == secret}\n")

    # --- Attack 2: greedy token inversion over a small vocab ---
    vocab = [
        "the", "admin", "password", "is", "stored", "in", "config", "vault",
        "user", "token", "secret", "weather", "nice", "today", "database",
        "backup", "runs", "every", "night", "the", "kept", "manager",
    ]
    greedy_text, greedy_score = greedy_token_inversion(
        target, vocab, model_name=model_name, max_len=12, beam=1)
    print("[Attack 2] Greedy token inversion")
    print(f"    Recovered : {greedy_text!r}")
    print(f"    Similarity: {greedy_score:.4f}\n")

    return {
        "secret": secret,
        "backend": _active_backend(),
        "nearest_neighbor": {"text": nn_text, "similarity": nn_score},
        "greedy": {"text": greedy_text, "similarity": greedy_score},
    }


def _active_backend():
    if _HAS_ST:
        return "sentence-transformers"
    if _HAS_SKLEARN:
        return "sklearn-tfidf"
    return "hashing-bag-of-words"


# ============================================================
# CLI
# ============================================================

def _load_lines(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Embedding Inversion Attack (RAG / vector DB privacy leak)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Built-in self-contained example
  python -m rag_attacks.embedding_inversion --mode demo

  # Retrieval based inversion: embed a secret, recover it from a candidate pool
  python -m rag_attacks.embedding_inversion --mode nn \\
    --text "the admin password is stored in the config vault" \\
    --candidates-file pool.txt

  # Greedy token inversion: rebuild the secret from a vocabulary
  python -m rag_attacks.embedding_inversion --mode greedy \\
    --text "the admin password is stored in the config vault" \\
    --vocab-file vocab.txt

Note:
  The SOTA is vec2text (Morris et al., 2023): a trained decoder that recovers
  text almost verbatim from an embedding. This tool ships dependency light
  approximations of that leak. Use --model to match the victim store's
  embedding model for meaningful cosine scores.
        """
    )
    parser.add_argument("--mode", choices=["nn", "greedy", "demo"],
                        required=True, help="Attack mode")
    parser.add_argument("--text", type=str, default=None,
                        help="Secret text to embed as the target (nn/greedy)")
    parser.add_argument("--candidates-file", type=str, default=None,
                        help="Candidate pool, one per line (nn mode)")
    parser.add_argument("--vocab-file", type=str, default=None,
                        help="Vocabulary words, one per line (greedy mode)")
    parser.add_argument("--model", type=str, default=None,
                        help="Embedding model name (sentence-transformers id)")
    parser.add_argument("--max-len", type=int, default=20,
                        help="Max tokens for greedy inversion (default: 20)")
    parser.add_argument("--beam", type=int, default=1,
                        help="Beam width for greedy inversion (default: 1)")
    parser.add_argument("--output", type=str, default=None,
                        help="Export result to JSON")
    args = parser.parse_args()

    if not _HAS_NP:
        print("[!] numpy is required: pip install numpy")
        sys.exit(1)

    print(f"[*] Active embedding backend: {_active_backend()}")
    result = None

    if args.mode == "demo":
        result = demo(model_name=args.model)

    elif args.mode == "nn":
        if not args.text or not args.candidates_file:
            print("[!] --text and --candidates-file are required for nn mode")
            sys.exit(1)
        candidates = _load_lines(args.candidates_file)
        target = embed_texts([args.text], model_name=args.model)[0]
        text, score = nearest_neighbor_inversion(
            target, candidates, model_name=args.model)
        print(f"\n[*] Nearest-neighbor inversion")
        print(f"    Secret    : {args.text!r}")
        print(f"    Recovered : {text!r}")
        print(f"    Similarity: {score:.4f}")
        result = {"mode": "nn", "secret": args.text,
                  "recovered": text, "similarity": score}

    elif args.mode == "greedy":
        if not args.text or not args.vocab_file:
            print("[!] --text and --vocab-file are required for greedy mode")
            sys.exit(1)
        vocab = _load_lines(args.vocab_file)
        target = embed_texts([args.text], model_name=args.model)[0]
        text, score = greedy_token_inversion(
            target, vocab, model_name=args.model,
            max_len=args.max_len, beam=args.beam)
        print(f"\n[*] Greedy token inversion")
        print(f"    Secret    : {args.text!r}")
        print(f"    Recovered : {text!r}")
        print(f"    Similarity: {score:.4f}")
        result = {"mode": "greedy", "secret": args.text,
                  "recovered": text, "similarity": score}

    if args.output and result is not None:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n[*] Result written to {args.output}")


if __name__ == "__main__":
    main()
