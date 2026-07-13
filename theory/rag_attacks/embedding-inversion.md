# Embedding Inversion

> **In one sentence:** Embedding inversion turns the "opaque" vectors stored in a RAG vector database back into the private text they were computed from, so the embedding index is really a lightly obfuscated copy of the source corpus.

## What it is

A RAG pipeline embeds every private document into a vector and stores those vectors in a vector database (FAISS, Pinecone, Milvus, pgvector) for similarity search. Teams routinely treat those embeddings as safe to log, export, or expose, believing a float array cannot be turned back into text. Embedding inversion is the attack that proves otherwise: given an embedding, recover the sentence that produced it.

The state of the art is **vec2text** (Morris et al., 2023, "Text Embeddings Reveal (Almost) As Much As Text"): a decoder trained to map embeddings back to text, which iteratively refines a guess until its re-embedding matches the target. It reconstructs many inputs almost verbatim.

This toolkit ships two dependency light approximations of the same leak:

1. **Retrieval based inversion**: if the attacker holds a pool of plausible source texts, embed them all and return whichever is closest in cosine space to the stolen embedding. This is the practical attack against a known or guessable corpus.
2. **Greedy token inversion**: rebuild text one word at a time, keeping each vocabulary word that pushes the reconstruction's embedding closer to the target.

Unlike [model inversion](../privacy/model-inversion.md), which reconstructs a *training* example from a model's parameters, embedding inversion reconstructs a specific *stored* text from its vector at inference time.

## The problem it exploits

Embeddings are designed to preserve meaning. Two texts with similar meaning map to nearby vectors, and the mapping is smooth and information rich. That is exactly the property that makes them invertible: the vector is not a one-way hash, it is a dense, near lossless encoding of the input. A model trained to undo the encoding (vec2text), or a search over candidate texts, can recover the original because the embedding still carries almost all of the input's semantic content.

The consequence for RAG: the vector store is not a safe derivative of your private data. It is your private data in another coordinate system. Anyone who reads the vectors (a leaked database dump, an over-permissioned index, an API that returns embeddings, or an injection that dumps retrieved chunks) can read the corpus.

## Intuition

Think of an embedding as a very detailed fingerprint of a sentence. A naive assumption is that a fingerprint cannot reproduce the finger. But these fingerprints are so complete that if you have a lineup of suspects (a candidate pool) you can find the exact match instantly (nearest neighbor), and even without a lineup you can grow the sentence word by word, checking after each word whether the fingerprint got closer, until you have reconstructed it (greedy inversion, and, done properly with a trained decoder, vec2text).

The greedy version is like a game of hot and cold: you propose a word, the cosine similarity tells you warmer or colder, and you keep the warm words.

## How it works

### Retrieval based (nearest neighbor) inversion

You have a target embedding `e` (stolen from the vector store) and a pool of candidate texts you think might be the source.

```
1. Embed every candidate c_i with the same model the victim used -> v_i.
2. Compute cosine similarity  sim(e, v_i)  for all i.
3. Return the candidate with the highest similarity, plus that score.
```

If the true source text is in the pool and you use the victim's embedding model, the match is exact (similarity ~= 1.0). This is the strongest, cheapest attack whenever the corpus is public, leaked, or guessable (for example a known dataset the index was built from).

### Greedy token inversion

When you have no candidate pool, only a vocabulary, rebuild the text incrementally:

```
reconstruction = ""
repeat up to max_len times:
    for each word w in vocab:
        score w by  cosine( embed(reconstruction + " " + w), e )
    append the w with the highest score, if it improves the current score
    stop when no word improves it
return reconstruction and its final similarity
```

`beam > 1` keeps the best few partial reconstructions at each step instead of committing to one, which recovers from early mistakes. This is a crude stand in for vec2text: it recovers the bag of words and often much of the phrasing, but word order is approximate. It illustrates the mechanism (embeddings are climbable) without training a decoder.

### The SOTA (vec2text)

Morris et al. train a conditional decoder plus a correction loop: generate a hypothesis text, embed it, compare to the target, and correct. After a few rounds it converges to near verbatim reconstructions. The toolkit's greedy method is the same "re-embed and get closer" idea without the learned decoder.

## Threat model and prerequisites

| Attack | Access needed | What you recover |
|---|---|---|
| Nearest neighbor inversion | The target embedding, a candidate pool containing (or close to) the source, and the victim's embedding model | The exact source text if it is in the pool |
| Greedy token inversion | The target embedding, the victim's embedding model, and a vocabulary | An approximate reconstruction (bag of words, rough phrasing) |
| vec2text (SOTA) | The target embedding, the embedding model (or a black box query API for it), and compute to train a decoder | Near verbatim text |

In all cases the attacker must be able to embed with the same model as the victim, because cosine scores are only meaningful within one embedding space. The core prerequisite is simply read access to stored embeddings, which is far weaker than access to the model's weights. This maps to **OWASP LLM02 (Sensitive Information Disclosure)**, the leak itself, and **OWASP LLM08 (Vector and Embedding Weaknesses)**, the class of risks specific to RAG vector stores.

## When to use it

- **Prove a vector store is a data leak surface**: reconstruct a real chunk from an exported or leaked embedding to show that "we only stored vectors" is not a privacy control.
- **Escalate an index or database exposure**: a misconfigured Pinecone/FAISS/pgvector instance, an S3 bucket of embeddings, or an API that returns raw vectors becomes full corpus disclosure.
- **Chain with retrieval leaks**: if an indirect [prompt injection](../prompt_injection/00-overview.md) or an over-eager RAG app leaks retrieved embeddings rather than text, invert them to read the private chunks.
- **Compare against poisoning**: pair with [RAG poisoning](./rag-poisoning.md) in a report to cover both confidentiality (inversion reads the store) and integrity (poisoning writes to it).

## Step by step with the toolkit

The script is `rag_attacks/embedding_inversion.py`. All embedding backends are optional: it uses `sentence-transformers` if installed, otherwise a scikit-learn TF-IDF space, otherwise a pure Python hashing bag of words. Import never fails.

Run the built-in self-contained example (embeds a secret sentence and recovers it two ways):

```bash
python -m rag_attacks.embedding_inversion --mode demo
```

Retrieval based inversion against a candidate pool (`pool.txt` has one candidate per line):

```bash
python -m rag_attacks.embedding_inversion --mode nn \
  --text "the admin password is stored in the config vault" \
  --candidates-file pool.txt
```

Here `--text` is the secret whose embedding you are trying to invert (in a real attack this embedding comes from the victim store, not from re-embedding the plaintext). If the secret is in `pool.txt` the recovered similarity is ~1.0 and the match is exact.

Greedy token inversion from a vocabulary (`vocab.txt`, one word per line):

```bash
python -m rag_attacks.embedding_inversion --mode greedy \
  --text "the admin password is stored in the config vault" \
  --vocab-file vocab.txt --max-len 15 --beam 3
```

Match the victim's embedding model so cosine scores are meaningful, and save the result:

```bash
python -m rag_attacks.embedding_inversion --mode nn \
  --text "..." --candidates-file pool.txt \
  --model sentence-transformers/all-MiniLM-L6-v2 --output result.json
```

Public API, importable for pipelines:

```python
from rag_attacks.embedding_inversion import (
    embed_texts, nearest_neighbor_inversion, greedy_token_inversion, demo,
)
```

Interpreting output: a nearest neighbor similarity near 1.0 means the source was in your pool and you have recovered it exactly. A greedy similarity of 0.8 to 0.9 typically means you recovered the right words with approximate ordering, enough to read the secret.

## Detection and defense

- **Treat embeddings as sensitive data**: apply the same access controls, encryption at rest, and audit logging to the vector store as to the source documents. Never return raw embeddings from an API, and never log them.
- **Do not embed secrets you would not store in plaintext**: credentials, PII, and keys should be redacted or tokenized before embedding, because the embedding preserves them.
- **Tenant isolation**: partition the vector store per tenant so one user's query or breach cannot reach another tenant's vectors.
- **Add noise or dimensionality reduction (partial)**: perturbing or truncating embeddings raises the reconstruction error, but degrades retrieval quality and does not stop retrieval based inversion when the corpus is known. Treat as defense in depth, not a guarantee.
- **Monitor for bulk vector access**: large or scripted reads of the index, or an application path that surfaces embeddings, are the detectable signals.
- **Guard the RAG output path**: since injection can exfiltrate retrieved content, apply output handling and guardrails so retrieved chunks (and any vectors) are not echoed back to untrusted callers. See [RAG poisoning](./rag-poisoning.md) for the integrity side of the same store.

The defenses mirror those for [model inversion](../privacy/model-inversion.md): the durable fix is to not put recoverable secrets into the artifact in the first place, and to lock down who can read it.

## Explain it to a non-expert

A RAG system reads your private documents and turns each one into a long list of numbers, then stores those lists so it can find relevant text quickly. People assume that once a sentence becomes a list of numbers, it is scrambled beyond recovery, like a smoothie you cannot turn back into fruit. It is not. The numbers keep almost all the meaning, so with the right tool you can run the blender in reverse and get the sentence back, sometimes word for word. That means the box of numbers is really a copy of your private files. If someone gets the numbers, they get your documents.

## References

- Morris, Kuleshov, Shmatikov, Rush (2023), *Text Embeddings Reveal (Almost) As Much As Text* (vec2text).
- Morris et al. (2024), *Language Model Inversion*.
- Song, Raghunathan (2020), *Information Leakage in Embedding Models*.
- Li et al. (2023), *Sentence Embedding Leaks More Information than You Expect: Generative Embedding Inversion Attack*.
- OWASP Top 10 for LLM Applications: LLM02 (Sensitive Information Disclosure) and LLM08 (Vector and Embedding Weaknesses).
- Related toolkit pages: [RAG poisoning](./rag-poisoning.md), [model inversion](../privacy/model-inversion.md).
