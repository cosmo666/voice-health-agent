"""FastAPI application for the Sunrise Health Clinic backend.

Entry point for the REST API that serves the voice agent, admin dashboard,
and external integrations. Provides:

- Health check endpoint with service status
- CRUD routes for appointments, doctors, patients, and call logs
- RAG knowledge-base query endpoint
- CORS middleware for development (allows all origins)
- Automatic database initialization on startup via lifespan

Start with::

    uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.database import init_db
from api.routes import appointments, calls, doctors, patients
from api.schemas import HealthResponse, RAGQueryResponse

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

# Remove default loguru handler and add a structured one
logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=True,
)

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    On startup: initializes the database (creates tables if they don't exist).
    On shutdown: logs a clean shutdown message.
    """
    logger.info("Sunrise Health Clinic API starting up...")
    await init_db()
    logger.info("Database initialized, API ready | http://localhost:8000")

    # Pre-warm RAG embedding model so the first query doesn't cold-start
    try:
        from rag.query_engine import _get_embedding_model, _get_chroma_collection

        _get_embedding_model()
        _get_chroma_collection()
        logger.info("RAG engine pre-warmed (embedding model + ChromaDB loaded)")
    except Exception as exc:
        logger.warning("RAG pre-warm skipped (not critical): {}", exc)
    yield
    logger.info("Sunrise Health Clinic API shutting down...")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Sunrise Health Clinic API",
    description=(
        "Backend API for the Voice AI Health Agent. Manages appointments, "
        "doctors, patients, call logs, and RAG-powered clinic information queries."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware (permissive for local development)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount route modules
# ---------------------------------------------------------------------------

app.include_router(appointments.router)
app.include_router(doctors.router)
app.include_router(patients.router)
app.include_router(calls.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Check the health of the API and its dependent services.

    Returns status information for:
    - api: always "ok" if this endpoint responds
    - database: "ok" if a simple query succeeds against SQLite
    - ollama: "ok" if the Ollama server is reachable

    Any service that fails its check returns "unavailable" rather than
    causing the entire health check to error.
    """
    services: dict[str, str] = {"api": "ok"}

    # Check database connectivity
    try:
        from api.database import async_session_maker
        from sqlalchemy import text

        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception as exc:
        logger.warning("Health check: database unavailable: {}", exc)
        services["database"] = "unavailable"

    # Check Ollama connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                services["ollama"] = "ok"
            else:
                services["ollama"] = f"http_{resp.status_code}"
    except httpx.ConnectError:
        logger.warning("Health check: Ollama not reachable at {}", OLLAMA_BASE_URL)
        services["ollama"] = "unavailable"
    except Exception as exc:
        logger.warning("Health check: Ollama check failed: {}", exc)
        services["ollama"] = "unavailable"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"

    return HealthResponse(status=overall, services=services)


# ---------------------------------------------------------------------------
# RAG query endpoint
# ---------------------------------------------------------------------------


@app.get("/api/rag/query", response_model=RAGQueryResponse, tags=["rag"])
async def rag_query(
    q: str = Query(..., min_length=1, description="Natural language question about the clinic"),
) -> RAGQueryResponse:
    """Answer a clinic-related question using RAG (Retrieval-Augmented Generation).

    Retrieves relevant chunks from the ChromaDB knowledge base and synthesizes
    an answer via the Ollama LLM. Falls back to a helpful default message if
    the RAG engine is not initialized or encounters an error.

    Args:
        q: The patient's question (e.g., "What insurance do you accept?").

    Returns:
        RAGQueryResponse with the answer text and list of source documents.
    """
    logger.info("RAG query received: q={!r}", q)

    try:
        from rag.query_engine import query_knowledge_base

        result = await query_knowledge_base(q)
        logger.info("RAG query answered successfully, sources={}", len(result.get("sources", [])))
        return RAGQueryResponse(
            answer=result.get("answer", "I'm sorry, I couldn't find an answer to that question."),
            sources=result.get("sources", []),
        )
    except ImportError:
        logger.warning("RAG module not available -- returning fallback response")
        return RAGQueryResponse(
            answer=(
                "I'm sorry, the knowledge base is not yet set up. "
                "Please run 'python scripts/seed_knowledge_base.py' first. "
                "In the meantime, I can help you book or manage appointments."
            ),
            sources=[],
        )
    except Exception as exc:
        logger.error("RAG query failed: {}", exc)
        return RAGQueryResponse(
            answer=(
                "I'm sorry, I encountered an issue searching our knowledge base. "
                "Let me connect you with someone who can help. Is there anything "
                "else I can assist with, like booking an appointment?"
            ),
            sources=[],
        )
