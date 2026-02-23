"""RAG knowledge base for clinic FAQ, insurance, and service information.

This package provides:
- ``ingest``: Markdown document chunking and ChromaDB vector store ingestion.
- ``query_engine``: Semantic retrieval + Ollama LLM synthesis for answering
  patient questions.
- ``evaluate``: Automated quality evaluation of retrieval and answer accuracy.
"""

from rag.ingest import chunk_text, ingest_documents
from rag.query_engine import query_knowledge_base, reset_caches, retrieve_chunks

__all__ = [
    "chunk_text",
    "ingest_documents",
    "query_knowledge_base",
    "reset_caches",
    "retrieve_chunks",
]
