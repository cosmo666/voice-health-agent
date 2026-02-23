"""Ingest markdown documents into ChromaDB vector store.

Reads all Markdown files from the rag/documents/ directory, splits them into
overlapping text chunks (paragraph-aware, then sentence-aware for oversized
paragraphs), embeds each chunk with the all-MiniLM-L6-v2 sentence-transformer
model, and stores them in a persistent ChromaDB collection with source metadata.

Usage:
    python -m rag.ingest          # run from project root
    python rag/ingest.py          # or directly
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger

DOCS_DIR: Path = Path(__file__).parent / "documents"
CHROMA_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME: str = "clinic_knowledge"
CHUNK_SIZE: int = 500  # target max characters per chunk
CHUNK_OVERLAP: int = 50  # overlap characters between consecutive chunks


def _split_into_sentences(text: str) -> list[str]:
    """Split a block of text into individual sentences using regex heuristics.

    Handles common abbreviations (Dr., Mr., Mrs., Ms., e.g., i.e.) and avoids
    splitting on decimal numbers.  Returns a list of stripped, non-empty sentences.

    Args:
        text: The input text to split into sentences.

    Returns:
        A list of sentence strings.
    """
    # Protect common abbreviations from the sentence splitter
    protected = text
    abbreviations = [
        "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Sr.", "Jr.",
        "e.g.", "i.e.", "vs.", "etc.", "Inc.", "Ltd.", "St.",
        "Ave.", "Blvd.", "Dept.", "approx.", "appt.",
    ]
    placeholders: dict[str, str] = {}
    for i, abbr in enumerate(abbreviations):
        placeholder = f"__ABBR{i}__"
        placeholders[placeholder] = abbr
        protected = protected.replace(abbr, placeholder)

    # Split on sentence-ending punctuation followed by whitespace
    raw_sentences = re.split(r"(?<=[.!?])\s+", protected)

    # Restore abbreviations
    sentences: list[str] = []
    for sent in raw_sentences:
        for placeholder, abbr in placeholders.items():
            sent = sent.replace(placeholder, abbr)
        stripped = sent.strip()
        if stripped:
            sentences.append(stripped)

    return sentences


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks using a paragraph-then-sentence strategy.

    Algorithm:
        1. Split the document by double-newline boundaries (paragraphs / sections).
        2. If a paragraph fits within *chunk_size*, keep it as a single chunk.
        3. If a paragraph exceeds *chunk_size*, break it down by sentences and
           greedily accumulate sentences until the chunk would exceed the limit.
        4. Between consecutive chunks, include *overlap* characters from the end
           of the previous chunk at the start of the next one.

    Args:
        text: The full document text to chunk.
        chunk_size: Maximum number of characters per chunk (soft limit — a single
            sentence longer than this will become its own chunk).
        overlap: Number of trailing characters from the previous chunk to prepend
            to the next chunk for context continuity.

    Returns:
        A list of non-empty text chunks.
    """
    if not text or not text.strip():
        return []

    # Step 1 — split into paragraphs (double newline)
    paragraphs: list[str] = [
        p.strip() for p in re.split(r"\n{2,}", text) if p.strip()
    ]

    raw_chunks: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            raw_chunks.append(paragraph)
        else:
            # Paragraph too large — break by sentences
            sentences = _split_into_sentences(paragraph)
            current_chunk_parts: list[str] = []
            current_len = 0

            for sentence in sentences:
                sentence_len = len(sentence)

                # If adding this sentence would exceed the limit, flush current chunk
                if current_len + sentence_len + 1 > chunk_size and current_chunk_parts:
                    raw_chunks.append(" ".join(current_chunk_parts))
                    current_chunk_parts = []
                    current_len = 0

                current_chunk_parts.append(sentence)
                current_len += sentence_len + 1  # +1 for space

            # Flush remaining sentences
            if current_chunk_parts:
                raw_chunks.append(" ".join(current_chunk_parts))

    # Step 2 — apply overlap between consecutive chunks
    if overlap <= 0 or len(raw_chunks) <= 1:
        return raw_chunks

    overlapped_chunks: list[str] = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        prev_chunk = raw_chunks[i - 1]
        # Take the last *overlap* characters of the previous chunk as prefix
        overlap_text = prev_chunk[-overlap:].lstrip()
        combined = f"{overlap_text} {raw_chunks[i]}" if overlap_text else raw_chunks[i]
        overlapped_chunks.append(combined)

    return overlapped_chunks


def ingest_documents(
    docs_dir: Optional[Path] = None,
    chroma_dir: Optional[str] = None,
    collection_name: Optional[str] = None,
    embedding_model_name: Optional[str] = None,
) -> int:
    """Ingest all Markdown documents from *docs_dir* into a ChromaDB collection.

    This function:
        1. Loads the sentence-transformer embedding model.
        2. Creates (or recreates) a persistent ChromaDB collection.
        3. Reads every ``*.md`` file in *docs_dir*.
        4. Chunks each file using :func:`chunk_text`.
        5. Embeds the chunks and upserts them into ChromaDB with metadata
           (source filename, chunk index).

    Args:
        docs_dir: Directory containing Markdown documents.  Defaults to
            ``rag/documents/``.
        chroma_dir: Path where ChromaDB persists data on disk.  Defaults to
            the ``CHROMA_PERSIST_DIR`` environment variable or ``./chroma_db``.
        collection_name: Name of the ChromaDB collection.  Defaults to
            ``"clinic_knowledge"``.
        embedding_model_name: HuggingFace model ID for sentence embeddings.
            Defaults to the ``EMBEDDING_MODEL`` environment variable or
            ``"all-MiniLM-L6-v2"``.

    Returns:
        The total number of chunks ingested.

    Raises:
        FileNotFoundError: If *docs_dir* does not exist.
        RuntimeError: If embedding or ChromaDB operations fail.
    """
    docs_dir = docs_dir or DOCS_DIR
    chroma_dir = chroma_dir or CHROMA_DIR
    collection_name = collection_name or COLLECTION_NAME
    embedding_model_name = embedding_model_name or EMBEDDING_MODEL

    if not docs_dir.exists():
        msg = f"Documents directory does not exist: {docs_dir}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    logger.info(
        "Starting document ingestion — docs_dir={}, chroma_dir={}, model={}",
        docs_dir,
        chroma_dir,
        embedding_model_name,
    )

    # ------------------------------------------------------------------
    # 1. Load the embedding model
    # ------------------------------------------------------------------
    try:
        from sentence_transformers import SentenceTransformer

        start = time.perf_counter()
        model = SentenceTransformer(embedding_model_name)
        elapsed = time.perf_counter() - start
        logger.info(
            "Loaded embedding model '{}' in {:.2f}s",
            embedding_model_name,
            elapsed,
        )
    except Exception as exc:
        logger.error("Failed to load embedding model '{}': {}", embedding_model_name, exc)
        raise RuntimeError(f"Embedding model load failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 2. Set up ChromaDB persistent client and collection
    # ------------------------------------------------------------------
    try:
        import chromadb

        client = chromadb.PersistentClient(path=chroma_dir)
        # Delete existing collection to re-ingest cleanly
        existing_collections = [c.name for c in client.list_collections()]
        if collection_name in existing_collections:
            client.delete_collection(name=collection_name)
            logger.info("Deleted existing ChromaDB collection '{}'", collection_name)

        collection = client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Created ChromaDB collection '{}' at '{}'", collection_name, chroma_dir
        )
    except Exception as exc:
        logger.error("ChromaDB setup failed: {}", exc)
        raise RuntimeError(f"ChromaDB setup failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 3. Read, chunk, embed, and store each Markdown file
    # ------------------------------------------------------------------
    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        logger.warning("No Markdown files found in {}", docs_dir)
        return 0

    logger.info("Found {} Markdown files to ingest", len(md_files))

    total_chunks = 0
    all_ids: list[str] = []
    all_documents: list[str] = []
    all_embeddings: list[list[float]] = []
    all_metadatas: list[dict[str, str | int]] = []

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to read {}: {}", md_file.name, exc)
            continue

        if not content.strip():
            logger.warning("Skipping empty file: {}", md_file.name)
            continue

        chunks = chunk_text(content)
        if not chunks:
            logger.warning("No chunks produced from {}", md_file.name)
            continue

        logger.info(
            "Chunked '{}': {} chunks (avg {:.0f} chars)",
            md_file.name,
            len(chunks),
            sum(len(c) for c in chunks) / len(chunks),
        )

        # Embed all chunks for this file in one batch
        try:
            embeddings = model.encode(chunks, show_progress_bar=False).tolist()
        except Exception as exc:
            logger.error("Embedding failed for {}: {}", md_file.name, exc)
            continue

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc_id = f"{md_file.stem}__chunk_{idx:04d}"
            all_ids.append(doc_id)
            all_documents.append(chunk)
            all_embeddings.append(embedding)
            all_metadatas.append(
                {
                    "source": md_file.name,
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                }
            )

        total_chunks += len(chunks)

    # ------------------------------------------------------------------
    # 4. Batch upsert into ChromaDB
    # ------------------------------------------------------------------
    if all_ids:
        try:
            # ChromaDB supports batches up to ~41666 items; we batch at 5000
            batch_size = 5000
            for i in range(0, len(all_ids), batch_size):
                end = min(i + batch_size, len(all_ids))
                collection.add(
                    ids=all_ids[i:end],
                    documents=all_documents[i:end],
                    embeddings=all_embeddings[i:end],
                    metadatas=all_metadatas[i:end],
                )
            logger.info(
                "Successfully ingested {} chunks into ChromaDB collection '{}'",
                total_chunks,
                collection_name,
            )
        except Exception as exc:
            logger.error("ChromaDB upsert failed: {}", exc)
            raise RuntimeError(f"ChromaDB upsert failed: {exc}") from exc
    else:
        logger.warning("No chunks to ingest — check document content")

    return total_chunks


def main() -> None:
    """Entry point for CLI invocation."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    start = time.perf_counter()
    try:
        count = ingest_documents()
        elapsed = time.perf_counter() - start
        logger.info(
            "Ingestion complete — {} total chunks in {:.2f}s", count, elapsed
        )
    except Exception as exc:
        logger.error("Ingestion failed: {}", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
