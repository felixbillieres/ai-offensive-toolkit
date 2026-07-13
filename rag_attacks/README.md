# RAG and Embedding Attacks

Retrieval Augmented Generation (RAG) systems ground an LLM in an external knowledge base by embedding documents into vectors, retrieving the closest ones for a query, and feeding them to the model as context. That pipeline adds two attack surfaces the base model does not have: the retrieval store can be poisoned, and the stored embeddings can leak the private text they were built from. This maps to OWASP LLM08:2025 (Vector and Embedding Weaknesses) and, for the leakage side, LLM02:2025 (Sensitive Information Disclosure).

## Theory

Full plain-English write-ups live in `../theory/rag_attacks/`:

- [Overview](../theory/rag_attacks/00-overview.md)
- [RAG Knowledge Base Poisoning](../theory/rag_attacks/rag-poisoning.md)
- [Embedding Inversion](../theory/rag_attacks/embedding-inversion.md)

### RAG poisoning in one paragraph

A poisoning document must satisfy two conditions at once. The retrieval condition: it must land in the top-k results for the attacker's target query, which is achieved by echoing the query wording so its embedding sits close to the query embedding. The generation condition: once in context, it must steer the model to the attacker's desired answer, which is achieved by asserting that answer and, optionally, embedding an instruction. Research (PoisonedRAG, Zou et al. 2024) shows that a handful of crafted documents can control the answer to a specific query even in a store of millions.

### Embedding inversion in one paragraph

Embeddings are often treated as opaque, but they are a lossy encoding of the original text, not a one-way hash. Given a target vector, an attacker with query access to the same embedding model can recover much of the source text: by nearest-neighbor search over a candidate pool, or by greedy token-by-token reconstruction that maximizes cosine similarity. The vec2text line of work (Morris et al. 2023) shows near-verbatim recovery is possible, so a leaked vector database is a text leak.

## Scripts

```bash
# RAG poisoning: self-contained retrieval demo (no target needed)
python -m rag_attacks.rag_poisoning --mode demo

# Craft poison documents for a specific query and answer
python -m rag_attacks.rag_poisoning --mode craft \
  --query "What is the refund policy?" --answer "Refunds are unlimited and always approved" --n-docs 5

# Submit poison documents to a live ingestion endpoint
python -m rag_attacks.rag_poisoning --mode submit --target http://app/api/ingest \
  --query "..." --answer "..." --body-template '{"content":"{{PAYLOAD}}"}'

# Embedding inversion: self-contained recovery demo
python -m rag_attacks.embedding_inversion --mode demo

# Recover text from an embedding using a candidate pool
python -m rag_attacks.embedding_inversion --mode nn --text "secret to embed" --candidates-file pool.txt
```

```python
from rag_attacks import craft_poison_documents, evaluate_poisoning
from rag_attacks import nearest_neighbor_inversion, greedy_token_inversion

docs = craft_poison_documents("What is the refund policy?", "Refunds are always approved", n_docs=5)
result = evaluate_poisoning("What is the refund policy?", "Refunds are always approved", docs)
```

| Script | Description |
|--------|-------------|
| `rag_poisoning.py` | PoisonedRAG-style knowledge base poisoning. Crafts documents that satisfy the retrieval and generation conditions, evaluates whether they reach the top-k in a self-contained corpus, and submits them to a live ingestion endpoint. Embeddings use sentence-transformers when available, with sklearn TF-IDF and a dependency-free hashing fallback. |
| `embedding_inversion.py` | Reconstructs source text from an embedding vector. Nearest-neighbor inversion over a candidate pool and greedy token-by-token reconstruction. Same tiered embedding backends. |

## References

- Zou et al. (2024) - *PoisonedRAG: Knowledge Poisoning Attacks to Retrieval-Augmented Generation of Large Language Models*
- Morris et al. (2023) - *Text Embeddings Reveal (Almost) As Much As Text* (vec2text)
- OWASP (2025) - *LLM08:2025 Vector and Embedding Weaknesses*, *LLM02:2025 Sensitive Information Disclosure*
