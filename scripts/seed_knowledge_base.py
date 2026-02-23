"""Ingest RAG documents into ChromaDB.

Reads all Markdown files from ``rag/documents/``, chunks them, embeds them
using the ``all-MiniLM-L6-v2`` sentence-transformer model, and stores the
resulting vectors in a persistent ChromaDB collection.

The ingestion function is imported from ``rag.ingest`` -- this script simply
provides a CLI entry point with logging and error handling.

Usage::

    python scripts/seed_knowledge_base.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


def main() -> None:
    """Run the document ingestion pipeline.

    Imports ``ingest_documents`` from the RAG module and runs it.  Logs the
    number of chunks successfully ingested, or raises on failure so that
    CI / setup scripts surface the error.
    """
    logger.info("Starting knowledge base ingestion...")
    try:
        from rag.ingest import ingest_documents

        num_chunks = ingest_documents()
        logger.info("Successfully ingested {} chunks into ChromaDB", num_chunks)
    except ImportError as exc:
        logger.error(
            "RAG ingest module not available. Ensure rag/ingest.py exists "
            "and all dependencies are installed: {}",
            exc,
        )
        raise
    except FileNotFoundError as exc:
        logger.error(
            "RAG documents not found. Ensure rag/documents/ contains "
            "Markdown files: {}",
            exc,
        )
        raise
    except Exception as exc:
        logger.error("Failed to ingest documents: {}", exc)
        raise


if __name__ == "__main__":
    main()
