"""RAG query engine — retrieves context from ChromaDB and synthesizes answers with Ollama.

This module provides the primary interface for answering patient questions about
the Sunrise Health Clinic.  It works in three stages:

    1. **Embed** the user's question with sentence-transformers (all-MiniLM-L6-v2).
    2. **Retrieve** the top-k most relevant document chunks from ChromaDB via
       cosine-similarity search.
    3. **Synthesize** a grounded answer by sending the retrieved context and the
       question to the Ollama LLM (gpt-oss:20b-cloud) with a strict system
       prompt that confines the model to the provided context.

Usage::

    from rag.query_engine import query_knowledge_base

    result = await query_knowledge_base("What insurance plans do you accept?")
    print(result["answer"])
    print(result["sources"])
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from loguru import logger

CHROMA_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME: str = "clinic_knowledge"
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")

# System prompt that instructs the LLM to answer *only* from provided context
_SYNTHESIS_SYSTEM_PROMPT: str = (
    "You are Maya, a helpful and professional virtual receptionist at Sunrise Health Clinic. "
    "Answer the patient's question using ONLY the information provided in the CONTEXT below. "
    "If the context does not contain enough information to answer the question, say: "
    '"I don\'t have information about that in our clinic records. '
    'Please call our office at (555) 234-5678 for further assistance." '
    "Keep your answers concise, clear, and friendly — use short sentences suitable for voice. "
    "Do NOT make up information, do NOT provide medical advice, and do NOT reference the context directly. "
    "Speak naturally as if you are talking to a patient on the phone."
)

# Module-level caches to avoid reloading on every request
_embedding_model: Any = None
_chroma_collection: Any = None


def _get_embedding_model() -> Any:
    """Lazily load and cache the sentence-transformer embedding model.

    Returns:
        The loaded SentenceTransformer model instance.

    Raises:
        RuntimeError: If the model fails to load.
    """
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            start = time.perf_counter()
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            elapsed = time.perf_counter() - start
            logger.info(
                "Loaded embedding model '{}' in {:.2f}s",
                EMBEDDING_MODEL,
                elapsed,
            )
        except Exception as exc:
            logger.error("Failed to load embedding model '{}': {}", EMBEDDING_MODEL, exc)
            raise RuntimeError(f"Embedding model load failed: {exc}") from exc
    return _embedding_model


def _get_chroma_collection() -> Any:
    """Lazily connect to ChromaDB and return the clinic knowledge collection.

    Returns:
        The ChromaDB collection object.

    Raises:
        RuntimeError: If the collection cannot be opened.
    """
    global _chroma_collection
    if _chroma_collection is None:
        try:
            import chromadb

            client = chromadb.PersistentClient(path=CHROMA_DIR)
            _chroma_collection = client.get_collection(name=COLLECTION_NAME)
            count = _chroma_collection.count()
            logger.info(
                "Connected to ChromaDB collection '{}' ({} documents)",
                COLLECTION_NAME,
                count,
            )
        except Exception as exc:
            logger.error(
                "Failed to open ChromaDB collection '{}': {}", COLLECTION_NAME, exc
            )
            raise RuntimeError(f"ChromaDB connection failed: {exc}") from exc
    return _chroma_collection


def reset_caches() -> None:
    """Reset module-level caches.  Useful in tests and after re-ingestion."""
    global _embedding_model, _chroma_collection
    _embedding_model = None
    _chroma_collection = None
    logger.debug("RAG query engine caches reset")


def retrieve_chunks(
    question: str,
    top_k: int = 5,
) -> tuple[list[str], list[str], list[float]]:
    """Embed a question and retrieve the most similar document chunks.

    Args:
        question: The natural-language question to search for.
        top_k: Number of top results to return.

    Returns:
        A 3-tuple of ``(documents, sources, distances)`` where:
        - *documents* is a list of chunk texts.
        - *sources* is a list of source filenames.
        - *distances* is a list of cosine distance scores (lower is more similar).

    Raises:
        RuntimeError: If embedding or retrieval fails.
    """
    model = _get_embedding_model()
    collection = _get_chroma_collection()

    try:
        start = time.perf_counter()
        query_embedding = model.encode([question], show_progress_bar=False).tolist()[0]
        embed_ms = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        query_ms = (time.perf_counter() - start) * 1000

        documents: list[str] = results["documents"][0] if results["documents"] else []
        metadatas: list[dict[str, Any]] = (
            results["metadatas"][0] if results["metadatas"] else []
        )
        distances: list[float] = (
            results["distances"][0] if results["distances"] else []
        )
        sources: list[str] = [m.get("source", "unknown") for m in metadatas]

        logger.debug(
            "Retrieved {} chunks for question (embed={:.0f}ms, query={:.0f}ms): '{}'",
            len(documents),
            embed_ms,
            query_ms,
            question[:80],
        )

        return documents, sources, distances

    except Exception as exc:
        logger.error("Retrieval failed for question '{}': {}", question[:80], exc)
        raise RuntimeError(f"Retrieval failed: {exc}") from exc


def _build_context_prompt(documents: list[str], sources: list[str]) -> str:
    """Format retrieved chunks into a numbered context block for the LLM.

    Args:
        documents: List of retrieved chunk texts.
        sources: List of corresponding source filenames.

    Returns:
        A formatted context string ready for injection into the LLM prompt.
    """
    if not documents:
        return "CONTEXT:\nNo relevant information found in the clinic knowledge base."

    parts: list[str] = ["CONTEXT:"]
    for i, (doc, source) in enumerate(zip(documents, sources), start=1):
        parts.append(f"\n[{i}] (Source: {source})\n{doc}")

    return "\n".join(parts)


async def _call_ollama(
    system_prompt: str,
    user_message: str,
    timeout: float = 30.0,
) -> str:
    """Send a chat completion request to the Ollama API and return the response.

    Uses the ``/api/chat`` endpoint with streaming disabled for simplicity in
    the RAG synthesis path (voice pipeline uses streaming separately).

    Args:
        system_prompt: The system prompt for the LLM.
        user_message: The user-facing message containing context and question.
        timeout: HTTP request timeout in seconds.

    Returns:
        The assistant's response text.

    Raises:
        RuntimeError: If the Ollama API request fails.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 512,
        },
    }

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        elapsed_ms = (time.perf_counter() - start) * 1000
        data = response.json()
        answer = data.get("message", {}).get("content", "").strip()

        logger.debug(
            "Ollama response ({:.0f}ms, model={}): '{}'",
            elapsed_ms,
            OLLAMA_MODEL,
            answer[:120],
        )

        return answer

    except httpx.TimeoutException:
        logger.error("Ollama request timed out after {:.0f}s", timeout)
        raise RuntimeError(f"Ollama request timed out after {timeout}s")
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama returned HTTP {}: {}",
            exc.response.status_code,
            exc.response.text[:200],
        )
        raise RuntimeError(
            f"Ollama HTTP error {exc.response.status_code}"
        ) from exc
    except Exception as exc:
        logger.error("Ollama request failed: {}", exc)
        raise RuntimeError(f"Ollama request failed: {exc}") from exc


async def query_knowledge_base(
    question: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Query the clinic knowledge base and return a synthesized answer.

    This is the primary public interface for the RAG module.  It retrieves
    relevant document chunks from ChromaDB, builds a context prompt, sends
    it to the Ollama LLM for synthesis, and returns the answer together with
    source attribution.

    Args:
        question: The patient's natural-language question.
        top_k: Number of context chunks to retrieve (default 5).

    Returns:
        A dictionary with keys:
        - ``"answer"`` (str): The synthesized response from the LLM.
        - ``"sources"`` (list[str]): Unique source filenames that contributed
          to the answer.
        - ``"chunks_retrieved"`` (int): Number of chunks retrieved.
        - ``"question"`` (str): Echo of the original question.

    Raises:
        RuntimeError: If any stage (retrieval or synthesis) fails.  The
            function catches and logs errors, returning a safe fallback
            answer so the voice agent never crashes.
    """
    logger.info("RAG query: '{}'", question[:100])
    overall_start = time.perf_counter()

    # ---- Retrieval ----
    try:
        documents, sources, distances = retrieve_chunks(question, top_k=top_k)
    except RuntimeError:
        # Return a graceful fallback if retrieval fails entirely
        logger.warning("Retrieval failed — returning fallback answer")
        return {
            "answer": (
                "I'm sorry, I'm having trouble looking that up right now. "
                "Please call our office at (555) 234-5678 and a staff member "
                "can help you with that."
            ),
            "sources": [],
            "chunks_retrieved": 0,
            "question": question,
        }

    # ---- Build context ----
    context = _build_context_prompt(documents, sources)
    user_message = f"{context}\n\nQUESTION:\n{question}"

    # ---- Synthesis ----
    try:
        answer = await _call_ollama(_SYNTHESIS_SYSTEM_PROMPT, user_message)
    except RuntimeError:
        # If the LLM is down, return the raw retrieved context as a fallback
        logger.warning("LLM synthesis failed — returning retrieval-only answer")
        if documents:
            answer = (
                "I found some information that might help, but I am unable to "
                "summarize it right now. Here is what I found: "
                + documents[0][:300]
            )
        else:
            answer = (
                "I'm sorry, I'm having trouble looking that up right now. "
                "Please call our office at (555) 234-5678 for assistance."
            )

    unique_sources = list(dict.fromkeys(sources))  # preserve order, deduplicate
    total_ms = (time.perf_counter() - overall_start) * 1000

    logger.info(
        "RAG complete in {:.0f}ms — {} chunks, {} sources",
        total_ms,
        len(documents),
        len(unique_sources),
    )

    return {
        "answer": answer,
        "sources": unique_sources,
        "chunks_retrieved": len(documents),
        "question": question,
    }
