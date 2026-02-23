"""Voice agent server -- serves the WebRTC UI and handles P2P signaling.

This is the entry point for the Pipecat voice agent.  It exposes a FastAPI
application with two responsibilities:

1. **Static UI** -- Mounts the ``pipecat-ai-small-webrtc-prebuilt`` frontend
   at ``/client`` so patients can open ``http://localhost:7860`` in Chrome,
   click "Connect", and start talking to Maya.

2. **WebRTC signaling** -- ``POST /api/offer`` accepts an SDP offer from the
   browser, creates a full voice pipeline (VAD -> STT -> LLM -> TTS), and
   returns an SDP answer.  The pipeline then runs in the background,
   streaming audio bidirectionally over the P2P connection.

Start with::

    uvicorn agent.main:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger

from pipecat.transports.services.small_webrtc import SmallWebRTCTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer, VADParams
from pipecat.transports.base_transport import TransportParams

from agent.config import settings
from agent.pipeline import create_pipeline
from agent.flows import ConversationContext

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Maya Voice Agent",
    description="Real-time voice AI receptionist for Sunrise Health Clinic",
    version="1.0.0",
)

# CORS -- allow the React dashboard and any local dev origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount the prebuilt WebRTC client UI
# ---------------------------------------------------------------------------

try:
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

    # SmallWebRTCPrebuiltUI is a Starlette application / static-files mount
    app.mount("/client", SmallWebRTCPrebuiltUI())
    logger.info("Mounted SmallWebRTCPrebuiltUI at /client")
except ImportError:
    logger.warning(
        "pipecat-ai-small-webrtc-prebuilt not installed -- "
        "/client UI will not be available.  Install with: "
        "pip install pipecat-ai-small-webrtc-prebuilt"
    )
except Exception as exc:
    logger.warning(
        "Failed to mount SmallWebRTCPrebuiltUI: {} -- "
        "The /client path will return 404.",
        exc,
    )

# ---------------------------------------------------------------------------
# Active sessions registry (for graceful shutdown and monitoring)
# ---------------------------------------------------------------------------

_active_sessions: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect the bare root URL to the WebRTC client UI."""
    logger.debug("Redirecting / -> /client/index.html")
    return RedirectResponse(url="/client/index.html")


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint for the voice agent server.

    Returns:
        JSON with ``status``, ``active_sessions``, and component info.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "service": "voice-agent",
            "active_sessions": len(_active_sessions),
            "config": {
                "llm_model": settings.ollama_model,
                "stt_model": settings.whisper_model,
                "tts_voice": settings.kokoro_voice,
                "vad_stop_secs": settings.vad_stop_secs,
            },
        }
    )


@app.post("/api/offer")
async def offer(request: Request) -> JSONResponse:
    """Handle a WebRTC SDP offer from the browser client.

    This endpoint performs the following sequence:

    1. Parses the SDP offer from the request body.
    2. Creates a ``SmallWebRTCTransport`` with Silero VAD and optional
       SmartTurn v3 for AI-powered turn detection.
    3. Builds the full voice pipeline (STT -> LLM -> TTS).
    4. Passes the SDP offer to the transport to generate an SDP answer.
    5. Launches the pipeline in a background ``asyncio.Task``.
    6. Returns the SDP answer so the browser can complete the P2P connection.

    Request Body:
        JSON with ``sdp`` (string) and ``type`` (string, usually ``"offer"``).

    Returns:
        JSON with ``sdp`` (string) and ``type`` (string, usually ``"answer"``).
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        logger.error("Malformed JSON in /api/offer request body")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON in request body"},
        )

    sdp: str | None = body.get("sdp")
    offer_type: str = body.get("type", "offer")

    if not sdp:
        logger.error("Missing 'sdp' field in /api/offer request")
        return JSONResponse(
            status_code=400,
            content={"error": "Missing required 'sdp' field"},
        )

    logger.info(
        "Received WebRTC offer | type={} sdp_length={}",
        offer_type,
        len(sdp),
    )

    try:
        # -- Build VAD parameters -------------------------------------------
        vad_analyzer = SileroVADAnalyzer(
            params=VADParams(
                stop_secs=settings.vad_stop_secs,
                start_secs=settings.vad_start_secs,
                confidence=settings.vad_confidence,
                min_volume=settings.vad_min_volume,
            )
        )

        # -- Build transport parameters -------------------------------------
        transport_params = TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=vad_analyzer,
        )

        # Attempt to add SmartTurn v3 for AI-powered turn detection.
        # This is optional -- if the import fails we fall back to plain
        # silence-based VAD which still works fine.
        try:
            from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
                LocalSmartTurnAnalyzerV3,
            )
            from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

            transport_params.turn_stop_strategy = TurnAnalyzerUserTurnStopStrategy(
                turn_analyzer=LocalSmartTurnAnalyzerV3()
            )
            logger.info("SmartTurn v3 enabled for AI-powered turn detection")
        except ImportError:
            logger.info(
                "SmartTurn v3 not available -- using silence-based VAD only"
            )
        except Exception as turn_exc:
            logger.warning(
                "SmartTurn v3 init failed ({}), falling back to silence VAD",
                turn_exc,
            )

        # -- Create transport -----------------------------------------------
        transport = SmallWebRTCTransport(
            webrtc_connection=None,
            params=transport_params,
        )

        # -- Create the full voice pipeline ---------------------------------
        task, runner = await create_pipeline(transport)

        # -- Handle the SDP offer/answer exchange ---------------------------
        answer = await transport.handle_offer(sdp, offer_type)

        # -- Create conversation context for this session -------------------
        conversation_ctx = ConversationContext()
        session_id = str(id(task))
        _active_sessions[session_id] = {
            "task": task,
            "runner": runner,
            "context": conversation_ctx,
        }

        # -- Run the pipeline in the background -----------------------------
        async def _run_and_cleanup() -> None:
            """Execute the pipeline and clean up when it finishes."""
            try:
                logger.info(
                    "Pipeline started for session {}",
                    session_id,
                )
                await runner.run(task)
            except Exception as run_exc:
                logger.error(
                    "Pipeline error in session {}: {}",
                    session_id,
                    run_exc,
                )
            finally:
                _active_sessions.pop(session_id, None)
                logger.info(
                    "Pipeline ended for session {} | "
                    "duration={}s turns={} escalated={}",
                    session_id,
                    conversation_ctx.duration_seconds(),
                    conversation_ctx.turn_count,
                    conversation_ctx.escalated,
                )

                # Attempt to save the call log to the backend
                await _save_call_log(conversation_ctx)

        asyncio.create_task(_run_and_cleanup())

        # -- Return the SDP answer ------------------------------------------
        logger.info("Returning SDP answer for session {}", session_id)
        return JSONResponse(
            content={
                "sdp": answer.sdp,
                "type": answer.type,
            }
        )

    except AttributeError:
        # Some Pipecat versions return the answer as a dict instead of
        # an object with .sdp / .type attributes.  Handle both.
        logger.info("Attempting dict-based SDP answer format")
        try:
            answer_dict = answer if isinstance(answer, dict) else vars(answer)
            return JSONResponse(content=answer_dict)
        except Exception as fallback_exc:
            logger.error("Could not format SDP answer: {}", fallback_exc)
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to generate SDP answer"},
            )

    except Exception as exc:
        logger.error("Failed to handle WebRTC offer: {}", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Pipeline creation failed: {exc!s}"},
        )


# ---------------------------------------------------------------------------
# Call-log persistence helper
# ---------------------------------------------------------------------------


async def _save_call_log(ctx: ConversationContext) -> None:
    """Persist the conversation as a call log via the FastAPI backend.

    Silently catches errors so pipeline teardown is never blocked by a
    logging failure.

    Args:
        ctx: The ``ConversationContext`` for the ended session.
    """
    import httpx

    call_data = ctx.to_call_log()

    # Skip if there is essentially no conversation
    if ctx.turn_count < 1 and not ctx.transcript_lines:
        logger.debug("Skipping call log save -- no turns recorded")
        return

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        ) as client:
            response = await client.post(
                f"{settings.api_base_url}/api/calls/",
                json=call_data,
            )
            if response.is_success:
                logger.info(
                    "Call log saved | phone={} duration={}s",
                    call_data["patient_phone"],
                    call_data["duration_seconds"],
                )
            else:
                logger.warning(
                    "Call log save returned HTTP {} | {}",
                    response.status_code,
                    response.text[:200],
                )
    except httpx.RequestError as exc:
        logger.warning("Could not save call log (backend unreachable): {}", exc)
    except Exception as exc:
        logger.warning("Unexpected error saving call log: {}", exc)


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _on_startup() -> None:
    """Log configuration on server start."""
    logger.info(
        "Maya Voice Agent starting | host={} port={} model={} stt={} tts={}",
        settings.agent_host,
        settings.agent_port,
        settings.ollama_model,
        settings.whisper_model,
        settings.kokoro_voice,
    )


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Gracefully terminate any active pipeline sessions."""
    session_count = len(_active_sessions)
    if session_count:
        logger.info(
            "Shutting down with {} active session(s) -- cleaning up",
            session_count,
        )
        for session_id, session in list(_active_sessions.items()):
            try:
                task = session.get("task")
                if task is not None:
                    await task.cancel()
                    logger.debug("Cancelled pipeline task {}", session_id)
            except Exception as exc:
                logger.warning(
                    "Error cancelling session {}: {}",
                    session_id,
                    exc,
                )
        _active_sessions.clear()
    logger.info("Maya Voice Agent shut down cleanly")
