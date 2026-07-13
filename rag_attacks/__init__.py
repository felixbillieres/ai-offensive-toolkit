"""RAG and embedding attacks - knowledge base poisoning and embedding inversion (OWASP LLM08)."""

from .rag_poisoning import (
    craft_poison_documents, build_demo_corpus, embed_texts,
    retrieve, evaluate_poisoning, submit_documents_http,
)
from .embedding_inversion import (
    nearest_neighbor_inversion, greedy_token_inversion,
)
