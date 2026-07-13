# RAG and Embedding Attacks: Overview

> **In one sentence:** When an LLM is wired to a vector database so it can look things up, that database becomes something you can poison to control answers and something you can invert to steal the private text inside it.

## Why this folder exists

A plain LLM only knows what was baked into its weights at training time. Retrieval Augmented Generation (RAG) fixes that by giving the model a searchable memory. The pipeline looks like this:

```
Documents  ->  Embedding model  ->  Vectors stored in a vector DB
                                              |
User query ->  Embedding model  ->  Query vector
                                              |
                                   Nearest-neighbor search (top-k)
                                              |
                         Retrieved documents + query  ->  LLM  ->  Answer
```

Two brand new attack surfaces appear here, neither of which exists in a standalone model:

1. **The store can be poisoned.** If you can get even a few crafted documents into the knowledge base, you can control what the model retrieves and therefore what it answers. See [rag-poisoning.md](rag-poisoning.md).
2. **The stored vectors can leak their source text.** Embeddings are a lossy encoding, not a hash, so a leaked vector database is a text leak. See [embedding-inversion.md](embedding-inversion.md).

This maps to OWASP LLM08:2025 (Vector and Embedding Weaknesses), with the leakage side also touching LLM02:2025 (Sensitive Information Disclosure).

## The two attacks at a glance

| | RAG poisoning | Embedding inversion |
|---|---|---|
| **Goal** | Control the model's answer | Recover private source text |
| **Direction** | Write into the store | Read out of the store |
| **What you need** | A way to add documents (upload, comment, indexed web page, shared drive) | Access to embedding vectors plus query access to the same embedding model |
| **Property abused** | Retrieval picks the nearest vectors, and the model trusts retrieved context | Embeddings preserve enough information to reconstruct the input |
| **OWASP** | LLM08 | LLM08 and LLM02 |

## How they connect to the rest of the toolkit

- RAG poisoning is a form of [indirect prompt injection](../prompt_injection/indirect-prompt-injection.md): the payload rides inside data the model reads later, not inside the user's prompt. The difference is that here you also have to win the retrieval step, not just the reading step.
- RAG poisoning is also a [data poisoning](../data_poisoning/00-overview.md) attack, but at inference-store level rather than training-set level. You do not retrain anything, you just contaminate the source of truth.
- Embedding inversion is a privacy attack, a cousin of [model inversion](../privacy/model-inversion.md). Model inversion reconstructs training inputs from a classifier; embedding inversion reconstructs text from its vector.

## Where to go next

- Start with [rag-poisoning.md](rag-poisoning.md) if the target answers questions from a document store and you can influence that store.
- Read [embedding-inversion.md](embedding-inversion.md) if you have obtained embedding vectors (a dumped or exposed vector index) and want to recover the underlying text.

## References

- Zou et al. (2024) - *PoisonedRAG: Knowledge Poisoning Attacks to Retrieval-Augmented Generation of Large Language Models*
- Morris et al. (2023) - *Text Embeddings Reveal (Almost) As Much As Text* (vec2text)
- OWASP (2025) - *LLM08:2025 Vector and Embedding Weaknesses*
