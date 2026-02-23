"""Async background task manager for post-call processing.

After a voice call ends, two background tasks run asynchronously:
1. **generate_call_summary** -- uses Ollama LLM to create a concise summary
   of the full transcript.
2. **analyze_sentiment** -- uses Ollama LLM to produce a sentiment score
   (-1.0 to 1.0) for the call.

Both tasks update the corresponding CallLog record in the database. Errors
are logged but never propagated to the caller -- the call log is still
saved even if post-processing fails.
"""

import os

import httpx
from loguru import logger
from sqlalchemy import select

from api.database import async_session_maker
from api.models import CallLog

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")

# Timeout for Ollama requests -- generous because cloud inference can be slow
_OLLAMA_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)


async def _ollama_generate(prompt: str) -> str:
    """Send a prompt to the Ollama /api/generate endpoint and return the response text.

    Args:
        prompt: The full prompt string including any system instructions.

    Returns:
        The generated text response from the model.

    Raises:
        httpx.HTTPStatusError: If Ollama returns a non-2xx status.
        httpx.ConnectError: If Ollama is unreachable.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()


async def generate_call_summary(call_id: str) -> None:
    """Generate an AI summary of a call transcript and persist it.

    Reads the CallLog transcript from the database, sends it to Ollama
    for summarization, and writes the result back to the summary column.

    Args:
        call_id: UUID of the CallLog record to summarize.
    """
    logger.info("Generating call summary for call_id={}", call_id)

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CallLog).where(CallLog.id == call_id)
            )
            call_log: CallLog | None = result.scalar_one_or_none()

            if call_log is None:
                logger.warning(
                    "CallLog not found for summary generation: call_id={}", call_id
                )
                return

            if not call_log.transcript.strip():
                logger.info("Empty transcript, skipping summary: call_id={}", call_id)
                return

            prompt = (
                "You are a medical office assistant. Summarize the following phone call "
                "transcript between a patient and an AI receptionist named Maya at "
                "Sunrise Health Clinic. Focus on: what the patient wanted, what actions "
                "were taken, and the outcome. Keep the summary to 2-3 sentences.\n\n"
                f"TRANSCRIPT:\n{call_log.transcript}\n\nSUMMARY:"
            )

            summary_text = await _ollama_generate(prompt)

            if summary_text:
                call_log.summary = summary_text
                await session.commit()
                logger.info(
                    "Call summary saved successfully: call_id={}, length={}",
                    call_id,
                    len(summary_text),
                )
            else:
                logger.warning(
                    "Ollama returned empty summary for call_id={}", call_id
                )

    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at {} for summary generation "
            "(call_id={}). Is Ollama running?",
            OLLAMA_BASE_URL,
            call_id,
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama returned HTTP {} during summary generation for call_id={}: {}",
            exc.response.status_code,
            call_id,
            exc.response.text[:500],
        )
    except Exception as exc:
        logger.error(
            "Unexpected error generating call summary for call_id={}: {}",
            call_id,
            exc,
        )


async def analyze_sentiment(call_id: str) -> None:
    """Compute a sentiment score for a call transcript and persist it.

    The score ranges from -1.0 (very negative) to 1.0 (very positive).
    Neutral calls score around 0.0.

    Args:
        call_id: UUID of the CallLog record to analyze.
    """
    logger.info("Analyzing sentiment for call_id={}", call_id)

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CallLog).where(CallLog.id == call_id)
            )
            call_log: CallLog | None = result.scalar_one_or_none()

            if call_log is None:
                logger.warning(
                    "CallLog not found for sentiment analysis: call_id={}", call_id
                )
                return

            if not call_log.transcript.strip():
                logger.info(
                    "Empty transcript, skipping sentiment: call_id={}", call_id
                )
                return

            prompt = (
                "Analyze the sentiment of this phone call transcript between a patient "
                "and an AI clinic receptionist. Return ONLY a single decimal number "
                "between -1.0 (very negative/frustrated) and 1.0 (very positive/satisfied). "
                "0.0 is neutral. Do not include any other text, just the number.\n\n"
                f"TRANSCRIPT:\n{call_log.transcript}\n\nSENTIMENT SCORE:"
            )

            score_text = await _ollama_generate(prompt)

            try:
                score = float(score_text.strip().split()[0])
                score = max(-1.0, min(1.0, score))  # clamp to valid range
            except (ValueError, IndexError):
                logger.warning(
                    "Could not parse sentiment score '{}' for call_id={}, "
                    "defaulting to 0.0",
                    score_text,
                    call_id,
                )
                score = 0.0

            call_log.sentiment_score = score
            await session.commit()
            logger.info(
                "Sentiment score saved: call_id={}, score={:.2f}",
                call_id,
                score,
            )

    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at {} for sentiment analysis "
            "(call_id={}). Is Ollama running?",
            OLLAMA_BASE_URL,
            call_id,
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama returned HTTP {} during sentiment analysis for call_id={}: {}",
            exc.response.status_code,
            call_id,
            exc.response.text[:500],
        )
    except Exception as exc:
        logger.error(
            "Unexpected error analyzing sentiment for call_id={}: {}",
            call_id,
            exc,
        )


async def process_call_post(call_id: str) -> None:
    """Orchestrate all post-call processing tasks.

    Runs summary generation and sentiment analysis sequentially for a
    given call log. Each task handles its own errors independently --
    a failure in one does not prevent the other from running.

    This function is designed to be fired via ``asyncio.create_task()``
    from a route handler so it runs in the background without blocking
    the HTTP response.

    Args:
        call_id: UUID of the CallLog record to process.
    """
    logger.info("Starting post-call processing for call_id={}", call_id)

    await generate_call_summary(call_id)
    await analyze_sentiment(call_id)

    logger.info("Post-call processing completed for call_id={}", call_id)
