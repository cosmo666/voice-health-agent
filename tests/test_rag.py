"""Tests for the RAG (Retrieval-Augmented Generation) knowledge base module.

Tests cover:
- Text chunking with overlap (chunk_text function)
- Sentence splitting heuristics
- ChromaDB ingestion (temporary in-memory collection)
- Chunk retrieval relevance
- End-to-end query_knowledge_base with mocked Ollama LLM
- Fallback behavior when retrieval or LLM fails

Uses temporary directories and in-memory ChromaDB to avoid touching production data.
The Ollama LLM is mocked for synthesis tests since the cloud model is not available
in CI/test environments.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from rag.ingest import chunk_text, _split_into_sentences


# ---------------------------------------------------------------------------
# Text Chunking Tests
# ---------------------------------------------------------------------------


def test_chunk_text_basic() -> None:
    """chunk_text should split a long text into multiple chunks."""
    # Create text with two distinct paragraphs
    paragraph1 = "This is the first paragraph. " * 20  # ~580 chars
    paragraph2 = "This is the second paragraph. " * 20  # ~600 chars
    text = f"{paragraph1}\n\n{paragraph2}"

    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"
    # All chunks should be non-empty
    for chunk in chunks:
        assert len(chunk.strip()) > 0


def test_chunk_text_empty_input() -> None:
    """chunk_text should return an empty list for empty/whitespace input."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("\n\n") == []


def test_chunk_text_small_text_single_chunk() -> None:
    """A short text that fits within chunk_size should produce a single chunk."""
    text = "This is a short paragraph."
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert "short paragraph" in chunks[0]


def test_chunk_text_overlap_applied() -> None:
    """Consecutive chunks should have overlapping content when overlap > 0."""
    # Create enough content to force multiple chunks
    text = "Sentence one about cardiology. " * 30
    text += "\n\nSentence two about insurance plans. " * 30

    chunks = chunk_text(text, chunk_size=300, overlap=50)

    assert len(chunks) >= 2

    # Check that some content from end of chunk[0] appears at start of chunk[1]
    # The overlap mechanism takes the last N chars from the previous chunk
    if len(chunks) >= 2:
        tail_of_first = chunks[0][-50:]
        # The second chunk should start with some portion of the first chunk's tail
        # (with possible whitespace trimming)
        overlap_found = any(
            word in chunks[1][:100]
            for word in tail_of_first.split()
            if len(word) > 3
        )
        assert overlap_found, (
            f"Expected overlap content from first chunk tail in second chunk start. "
            f"Tail: {tail_of_first!r}, Start of second: {chunks[1][:100]!r}"
        )


def test_chunk_text_preserves_paragraphs() -> None:
    """Short paragraphs should each become their own chunk."""
    text = "First topic.\n\nSecond topic.\n\nThird topic."
    chunks = chunk_text(text, chunk_size=500, overlap=0)
    assert len(chunks) == 3
    assert chunks[0] == "First topic."
    assert chunks[1] == "Second topic."
    assert chunks[2] == "Third topic."


# ---------------------------------------------------------------------------
# Sentence Splitting Tests
# ---------------------------------------------------------------------------


def test_split_into_sentences_basic() -> None:
    """_split_into_sentences should split on period-space boundaries."""
    text = "First sentence. Second sentence. Third one."
    sentences = _split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "First sentence."
    assert sentences[1] == "Second sentence."
    assert sentences[2] == "Third one."


def test_split_into_sentences_preserves_abbreviations() -> None:
    """_split_into_sentences should not split on Dr., Mr., etc."""
    text = "Dr. Patel is a cardiologist. She sees patients daily."
    sentences = _split_into_sentences(text)
    assert len(sentences) == 2
    assert "Dr. Patel" in sentences[0]


# ---------------------------------------------------------------------------
# ChromaDB Ingestion Tests (in-memory)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chromadb_ingestion_and_count() -> None:
    """Ingesting documents should create the expected number of chunks in ChromaDB."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        pytest.skip("chromadb or sentence-transformers not installed")

    # Create temp directory with a test Markdown file
    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        doc_content = (
            "# Insurance Policies\n\n"
            "We accept BlueCross BlueShield, Aetna, and UnitedHealth insurance plans.\n\n"
            "## Copays\n\n"
            "General visits have a $30 copay. Specialist visits have a $50 copay.\n\n"
            "## Deductibles\n\n"
            "Annual deductibles range from $500 to $3000 depending on your plan tier."
        )
        (docs_dir / "insurance_policies.md").write_text(doc_content, encoding="utf-8")

        chroma_dir = Path(tmpdir) / "chroma"

        from rag.ingest import ingest_documents

        count = ingest_documents(
            docs_dir=docs_dir,
            chroma_dir=str(chroma_dir),
            collection_name="test_collection",
        )

        assert count > 0, "Expected at least one chunk to be ingested"

        # Verify the collection has the right count
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection("test_collection")
        assert collection.count() == count


@pytest.mark.asyncio
async def test_retrieval_returns_relevant_chunks() -> None:
    """Querying ChromaDB should return chunks relevant to the question."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        pytest.skip("chromadb or sentence-transformers not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        # Create two distinct documents
        insurance_doc = (
            "# Insurance Information\n\n"
            "Sunrise Health Clinic accepts BlueCross BlueShield, Aetna, "
            "UnitedHealth, and Cigna insurance plans. "
            "The copay for a general visit is $30. Specialist visits have a $50 copay."
        )
        hours_doc = (
            "# Clinic Hours\n\n"
            "Sunrise Health Clinic is open Monday through Friday from 8:00 AM to 6:00 PM. "
            "Saturday hours are 9:00 AM to 1:00 PM. The clinic is closed on Sundays."
        )

        (docs_dir / "insurance_policies.md").write_text(insurance_doc, encoding="utf-8")
        (docs_dir / "clinic_hours.md").write_text(hours_doc, encoding="utf-8")

        chroma_dir = Path(tmpdir) / "chroma"

        from rag.ingest import ingest_documents

        ingest_documents(
            docs_dir=docs_dir,
            chroma_dir=str(chroma_dir),
            collection_name="test_retrieval",
        )

        # Now query for insurance-related information
        model = SentenceTransformer("all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection("test_retrieval")

        query_embedding = model.encode(
            ["What insurance plans do you accept?"], show_progress_bar=False
        ).tolist()

        results = collection.query(
            query_embeddings=query_embedding,
            n_results=2,
            include=["documents", "metadatas"],
        )

        assert len(results["documents"][0]) >= 1
        # The top result should be from the insurance document
        top_doc = results["documents"][0][0]
        assert "insurance" in top_doc.lower() or "BlueCross" in top_doc


# ---------------------------------------------------------------------------
# query_knowledge_base with mocked Ollama
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_knowledge_base_with_mocked_ollama() -> None:
    """query_knowledge_base should return answer and sources when Ollama is mocked."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        pytest.skip("chromadb or sentence-transformers not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()

        faq_doc = (
            "# Patient FAQ\n\n"
            "## What are your clinic hours?\n\n"
            "We are open Monday through Friday from 8 AM to 6 PM.\n\n"
            "## Do you accept walk-ins?\n\n"
            "Yes, we accept walk-in patients. However, appointments are recommended "
            "to minimize wait times."
        )
        (docs_dir / "patient_faq.md").write_text(faq_doc, encoding="utf-8")

        chroma_dir = Path(tmpdir) / "chroma"

        from rag.ingest import ingest_documents
        from rag.query_engine import query_knowledge_base, reset_caches

        # Reset caches so the module picks up our test ChromaDB
        reset_caches()

        ingest_documents(
            docs_dir=docs_dir,
            chroma_dir=str(chroma_dir),
            collection_name="clinic_knowledge",
        )

        # Patch the module-level constants and Ollama call
        mock_ollama_answer = "We are open Monday through Friday from 8 AM to 6 PM."

        with (
            patch("rag.query_engine.CHROMA_DIR", str(chroma_dir)),
            patch(
                "rag.query_engine._call_ollama",
                new_callable=AsyncMock,
                return_value=mock_ollama_answer,
            ),
        ):
            # Reset caches again after patching CHROMA_DIR
            reset_caches()

            result = await query_knowledge_base("What are your clinic hours?")

        assert "answer" in result
        assert "sources" in result
        assert len(result["answer"]) > 0
        assert result["chunks_retrieved"] > 0
        # The mocked answer should come through
        assert "Monday" in result["answer"]

        # Clean up module state
        reset_caches()


@pytest.mark.asyncio
async def test_query_knowledge_base_retrieval_failure_fallback() -> None:
    """query_knowledge_base should return a fallback answer when retrieval fails."""
    from rag.query_engine import query_knowledge_base, reset_caches

    reset_caches()

    # Patch retrieve_chunks to raise RuntimeError (simulates missing ChromaDB)
    with patch(
        "rag.query_engine.retrieve_chunks",
        side_effect=RuntimeError("ChromaDB not available"),
    ):
        result = await query_knowledge_base("What insurance do you accept?")

    assert "answer" in result
    assert len(result["answer"]) > 0
    # Should be a graceful fallback message
    assert "sorry" in result["answer"].lower() or "call" in result["answer"].lower()
    assert result["chunks_retrieved"] == 0
    assert result["sources"] == []

    reset_caches()
