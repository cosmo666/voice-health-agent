"""Async background task manager for post-call processing.

After a voice call ends, three background tasks run asynchronously:
1. **generate_call_summary** -- uses Ollama LLM to create a concise summary
   of the full transcript.
2. **analyze_sentiment** -- uses Ollama LLM to produce a sentiment score
   (-1.0 to 1.0) for the call.
3. **generate_ai_insights** -- uses qwen3-next:80b-cloud (a more powerful
   model) to produce structured JSON analytics: topics, patient intent,
   action items, language detected, key moments, and recommendations.

All tasks update the corresponding CallLog record in the database. Errors
are logged but never propagated to the caller -- the call log is still
saved even if post-processing fails.
"""

import json
import os
import re

import httpx
from loguru import logger
from sqlalchemy import select

from api.database import async_session_maker
from api.models import CallLog

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")
ANALYTICS_MODEL: str = os.getenv("ANALYTICS_MODEL", "qwen3-next:80b-cloud")

# Timeout for Ollama requests -- generous because cloud inference can be slow
_OLLAMA_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
# Insights generation can take longer with the larger model
_INSIGHTS_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)


async def _ollama_generate(
    prompt: str,
    model: str | None = None,
    timeout: httpx.Timeout | None = None,
) -> str:
    """Send a prompt to the Ollama /api/generate endpoint and return the response text.

    Args:
        prompt: The full prompt string including any system instructions.
        model: Optional model override. Defaults to OLLAMA_MODEL.
        timeout: Optional timeout override. Defaults to _OLLAMA_TIMEOUT.

    Returns:
        The generated text response from the model.

    Raises:
        httpx.HTTPStatusError: If Ollama returns a non-2xx status.
        httpx.ConnectError: If Ollama is unreachable.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model or OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    # Use higher token limit for insights generation
    if model == ANALYTICS_MODEL:
        payload["options"]["num_predict"] = 1024

    async with httpx.AsyncClient(timeout=timeout or _OLLAMA_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "").strip()

        # Strip <think>...</think> blocks from chain-of-thought models
        # (qwen3, gpt-oss, etc.) that include reasoning in their output.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        return text


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
                "/no_think\n"
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
                "/no_think\n"
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


async def generate_ai_insights(call_id: str) -> None:
    """Generate rich AI-powered insights for a call using qwen3-next:80b-cloud.

    Produces a structured JSON analysis including: topics discussed, patient
    intent, action items, language detected, key moments, resolution status,
    and recommendations for clinic operations.

    Args:
        call_id: UUID of the CallLog record to analyze.
    """
    logger.info(
        "Generating AI insights for call_id={} using model={}",
        call_id,
        ANALYTICS_MODEL,
    )

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(CallLog).where(CallLog.id == call_id)
            )
            call_log: CallLog | None = result.scalar_one_or_none()

            if call_log is None:
                logger.warning(
                    "CallLog not found for AI insights: call_id={}", call_id
                )
                return

            if not call_log.transcript.strip():
                logger.info(
                    "Empty transcript, skipping AI insights: call_id={}", call_id
                )
                return

            prompt = (
                "/no_think\n"
                "You are an expert healthcare call analyst. Analyze the following phone call "
                "transcript between a patient and Maya, an AI receptionist at Sunrise Health Clinic.\n\n"
                "Return ONLY valid JSON (no markdown, no explanation) with this exact structure:\n"
                "{\n"
                '  "topics": ["topic1", "topic2"],\n'
                '  "patient_intent": "Brief description of what the patient wanted",\n'
                '  "resolution_status": "resolved" | "partially_resolved" | "unresolved" | "escalated",\n'
                '  "language_detected": "english" | "hindi" | "hinglish",\n'
                '  "key_moments": [\n'
                '    {"timestamp": "HH:MM:SS or N/A", "event": "description of key moment"}\n'
                "  ],\n"
                '  "action_items": ["action1", "action2"],\n'
                '  "patient_satisfaction": "high" | "medium" | "low",\n'
                '  "agent_performance": {\n'
                '    "response_quality": "excellent" | "good" | "fair" | "poor",\n'
                '    "empathy_score": "high" | "medium" | "low",\n'
                '    "accuracy": "high" | "medium" | "low",\n'
                '    "areas_for_improvement": ["area1"]\n'
                "  },\n"
                '  "recommendations": ["recommendation for clinic operations"]\n'
                "}\n\n"
                "Rules:\n"
                "- topics: Main subjects discussed (e.g., 'appointment booking', 'insurance inquiry', 'doctor availability')\n"
                "- patient_intent: The primary reason for the call in one sentence\n"
                "- resolution_status: Was the patient's issue fully resolved?\n"
                "- language_detected: Primary language used by the patient\n"
                "- key_moments: Important events (booking confirmed, escalation triggered, etc.)\n"
                "- action_items: Follow-up tasks (e.g., 'Patient needs to bring insurance card')\n"
                "- patient_satisfaction: Inferred from tone and outcome\n"
                "- agent_performance: How well did Maya handle the call?\n"
                "- recommendations: Actionable suggestions for improving clinic operations\n\n"
                f"TRANSCRIPT:\n{call_log.transcript}\n\nJSON ANALYSIS:"
            )

            raw_response = await _ollama_generate(
                prompt, model=ANALYTICS_MODEL, timeout=_INSIGHTS_TIMEOUT
            )

            # Parse the JSON response
            insights = _parse_insights_json(raw_response, call_id)

            if insights:
                call_log.ai_insights = insights
                await session.commit()
                logger.info(
                    "AI insights saved: call_id={}, topics={}, resolution={}",
                    call_id,
                    insights.get("topics", []),
                    insights.get("resolution_status", "unknown"),
                )
            else:
                logger.warning(
                    "Failed to parse AI insights for call_id={}", call_id
                )

    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at {} for AI insights "
            "(call_id={}). Is Ollama running?",
            OLLAMA_BASE_URL,
            call_id,
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama returned HTTP {} during AI insights for call_id={}: {}",
            exc.response.status_code,
            call_id,
            exc.response.text[:500],
        )
    except Exception as exc:
        logger.error(
            "Unexpected error generating AI insights for call_id={}: {}",
            call_id,
            exc,
        )


def _parse_insights_json(raw: str, call_id: str) -> dict | None:
    """Extract and parse JSON from the LLM response.

    Handles cases where the model wraps JSON in markdown code fences or
    includes extra text before/after the JSON object.

    Args:
        raw: Raw text response from the LLM.
        call_id: Call ID for logging purposes.

    Returns:
        Parsed dict if successful, None otherwise.
    """
    if not raw:
        return None

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try to find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning(
            "No JSON object found in AI insights response for call_id={}: {}",
            call_id,
            text[:200],
        )
        return None

    json_str = text[start : end + 1]

    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict):
            logger.warning(
                "AI insights JSON is not an object for call_id={}", call_id
            )
            return None
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning(
            "Failed to parse AI insights JSON for call_id={}: {} | raw: {}",
            call_id,
            exc,
            json_str[:300],
        )
        return None


async def process_call_post(call_id: str) -> None:
    """Orchestrate all post-call processing tasks.

    Runs summary generation, sentiment analysis, and AI insights sequentially
    for a given call log. Each task handles its own errors independently --
    a failure in one does not prevent the others from running.

    This function is designed to be fired via ``asyncio.create_task()``
    from a route handler so it runs in the background without blocking
    the HTTP response.

    Args:
        call_id: UUID of the CallLog record to process.
    """
    logger.info("Starting post-call processing for call_id={}", call_id)

    await generate_call_summary(call_id)
    await analyze_sentiment(call_id)
    await generate_ai_insights(call_id)

    logger.info("Post-call processing completed for call_id={}", call_id)
