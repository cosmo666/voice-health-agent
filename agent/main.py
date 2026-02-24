"""Voice agent server -- serves the WebRTC UI and handles P2P signaling.

This is the entry point for the Pipecat voice agent.  It exposes a FastAPI
application with two responsibilities:

1. **Static UI** -- Serves a custom audio-only WebRTC client at ``/client``
   so patients can open ``http://localhost:7860`` in Chrome, click "Connect",
   and start talking to Maya.  No video or screen sharing.

2. **WebRTC signaling** -- ``POST /sessions/{id}/api/offer`` accepts an SDP
   offer from the browser, creates a full voice pipeline (VAD -> STT -> LLM
   -> TTS), and returns an SDP answer.  The pipeline then runs in the
   background, streaming audio bidirectionally over the P2P connection.

Start with::

    uvicorn agent.main:app --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import asyncio
import pathlib
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
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
# Mount the custom audio-only WebRTC client UI
# ---------------------------------------------------------------------------

_STATIC_DIR = pathlib.Path(__file__).parent / "static"
app.mount("/client", StaticFiles(directory=str(_STATIC_DIR), html=True), name="client")
logger.info("Mounted custom audio-only WebRTC UI at /client")

# ---------------------------------------------------------------------------
# Active sessions registry (for graceful shutdown and monitoring)
# ---------------------------------------------------------------------------

_active_sessions: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# WebRTC request handler (manages connections)
# ---------------------------------------------------------------------------

_webrtc_handler = SmallWebRTCRequestHandler()


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
                "stt_language": settings.whisper_language or "auto-detect",
                "tts_engine": f"Sarvam {settings.sarvam_model}",
                "tts_voice": settings.sarvam_voice,
                "vad_stop_secs": settings.vad_stop_secs,
            },
        }
    )


@app.post("/start")
async def start_session(request: Request) -> JSONResponse:
    """Create a new voice agent session.

    The prebuilt SmallWebRTC UI calls this endpoint first. It returns a
    ``session_id`` which the UI uses to build the SDP offer URL:
    ``/sessions/{session_id}/api/offer``.

    Returns:
        JSON with ``session_id`` (string).
    """
    session_id = str(uuid.uuid4())
    logger.info("New session created: {}", session_id)
    return JSONResponse(content={"session_id": session_id})


@app.post("/sessions/{session_id}/api/offer")
async def offer(session_id: str, request: Request) -> JSONResponse:
    """Handle a WebRTC SDP offer from the browser client.

    This endpoint performs the following sequence:

    1. Parses the SDP offer from the request body.
    2. Uses ``SmallWebRTCRequestHandler`` to manage the WebRTC connection.
    3. In the connection callback, creates a ``SmallWebRTCTransport`` with
       Silero VAD, builds the full voice pipeline (audio only), and runs it.
    4. Returns the SDP answer so the browser can complete the P2P connection.

    Args:
        session_id: The session ID returned by ``POST /start``.

    Request Body:
        JSON with ``sdp`` (string), ``type`` (string), and optionally ``pc_id``.

    Returns:
        JSON with ``sdp`` (string), ``type`` (string), and ``pc_id`` (string).
    """
    try:
        body = await request.json()
    except Exception:
        logger.error("Malformed JSON in offer request body")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON in request body"},
        )

    sdp: str | None = body.get("sdp")
    offer_type: str = body.get("type", "offer")
    pc_id: str | None = body.get("pc_id")

    if not sdp:
        logger.error("Missing 'sdp' field in offer request")
        return JSONResponse(
            status_code=400,
            content={"error": "Missing required 'sdp' field"},
        )

    logger.info(
        "Received WebRTC offer | session={} type={} sdp_length={} pc_id={}",
        session_id,
        offer_type,
        len(sdp),
        pc_id,
    )

    try:
        webrtc_request = SmallWebRTCRequest(
            sdp=sdp,
            type=offer_type,
            pc_id=pc_id,
        )

        async def _on_connection(webrtc_connection: SmallWebRTCConnection) -> None:
            """Callback invoked when a new WebRTC connection is created.

            Builds the full voice pipeline (audio only) and runs it in a
            background task.
            """
            logger.info("New WebRTC connection: {}", webrtc_connection.pc_id)

            # -- Build transport parameters (audio only, no video) --------------
            # VAD is passed to the LLMContextAggregatorPair via pipeline.py
            # (not TransportParams) per pipecat 0.0.103 API.
            vad_analyzer = SileroVADAnalyzer(
                params=VADParams(
                    stop_secs=settings.vad_stop_secs,
                    start_secs=settings.vad_start_secs,
                    confidence=settings.vad_confidence,
                    min_volume=settings.vad_min_volume,
                )
            )
            transport_params = TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                video_in_enabled=False,
                video_out_enabled=False,
            )

            # -- Create transport -----------------------------------------------
            transport = SmallWebRTCTransport(
                webrtc_connection=webrtc_connection,
                params=transport_params,
            )

            # -- Create conversation context for this session -------------------
            conversation_ctx = ConversationContext()

            # -- Create the full voice pipeline ---------------------------------
            task, runner, llm_context = await create_pipeline(
                transport, conversation_ctx, vad_analyzer=vad_analyzer
            )
            sid = webrtc_connection.pc_id or session_id
            _active_sessions[sid] = {
                "task": task,
                "runner": runner,
                "context": conversation_ctx,
            }

            # -- Run the pipeline in the background -----------------------------
            async def _run_and_cleanup() -> None:
                """Execute the pipeline and clean up when it finishes."""
                try:
                    logger.info("Pipeline started for session {}", sid)
                    await runner.run(task)
                except asyncio.CancelledError:
                    logger.info(
                        "Pipeline cancelled for session {}", sid
                    )
                except Exception as run_exc:
                    logger.error(
                        "Pipeline error in session {}: {}",
                        sid,
                        run_exc,
                    )
                finally:
                    _active_sessions.pop(sid, None)

                    # Extract transcript from LLM context messages
                    try:
                        messages = getattr(
                            llm_context, "messages", None
                        )
                        if messages is None:
                            messages = (
                                llm_context.get_messages()
                                if hasattr(llm_context, "get_messages")
                                else []
                            )
                        logger.info(
                            "Extracting transcript | {} message(s) in "
                            "LLM context for session {}",
                            len(messages),
                            sid,
                        )
                        for msg in messages:
                            # Handle both dict and object messages
                            role = (
                                msg.get("role", "")
                                if isinstance(msg, dict)
                                else getattr(msg, "role", "")
                            )
                            content = (
                                msg.get("content")
                                if isinstance(msg, dict)
                                else getattr(msg, "content", None)
                            )
                            if not content or not isinstance(content, str):
                                continue
                            if role == "system":
                                continue
                            if role == "user":
                                conversation_ctx.add_transcript_line(
                                    "user", content
                                )
                                conversation_ctx.increment_turn()
                            elif role == "assistant":
                                conversation_ctx.add_transcript_line(
                                    "maya", content
                                )
                                conversation_ctx.increment_turn()
                    except Exception as extract_exc:
                        logger.error(
                            "Failed to extract transcript for session "
                            "{}: {}",
                            sid,
                            extract_exc,
                        )

                    logger.info(
                        "Pipeline ended for session {} | "
                        "duration={}s turns={} escalated={} "
                        "transcript_lines={}",
                        sid,
                        conversation_ctx.duration_seconds(),
                        conversation_ctx.turn_count,
                        conversation_ctx.escalated,
                        len(conversation_ctx.transcript_lines),
                    )
                    # Attempt to save the call log to the backend
                    await _save_call_log(conversation_ctx)

            # -- Watch for client disconnection --------------------------------
            async def _watch_disconnect() -> None:
                """Poll WebRTC connection and cancel pipeline on disconnect."""
                try:
                    while sid in _active_sessions:
                        await asyncio.sleep(2)
                        try:
                            connected = webrtc_connection.is_connected()
                        except Exception:
                            connected = False
                        if not connected:
                            logger.info(
                                "WebRTC client disconnected | session={}",
                                sid,
                            )
                            try:
                                await task.cancel()
                            except Exception as cancel_exc:
                                logger.warning(
                                    "Error cancelling task for {}: {}",
                                    sid,
                                    cancel_exc,
                                )
                            break
                except asyncio.CancelledError:
                    pass

            asyncio.create_task(_run_and_cleanup())
            asyncio.create_task(_watch_disconnect())

        # -- Use the request handler to manage the connection -------------------
        answer = await _webrtc_handler.handle_web_request(
            webrtc_request, _on_connection
        )

        if answer is None:
            return JSONResponse(
                status_code=500,
                content={"error": "No SDP answer generated"},
            )

        logger.info("Returning SDP answer | pc_id={}", answer.get("pc_id"))
        return JSONResponse(content=answer)

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

    # Skip only truly empty connections (accidental connect/disconnect)
    duration = ctx.duration_seconds()
    if duration < 3 and ctx.turn_count < 1 and not ctx.transcript_lines:
        logger.debug(
            "Skipping call log save -- trivial connection ({}s, {} turns)",
            duration,
            ctx.turn_count,
        )
        return

    logger.info(
        "Saving call log | phone={} duration={}s turns={} "
        "transcript_lines={} tools={}",
        call_data["patient_phone"],
        call_data["duration_seconds"],
        ctx.turn_count,
        len(ctx.transcript_lines),
        call_data.get("tools_used", []),
    )

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
                    "Call log saved successfully | id={}",
                    response.json().get("id", "?"),
                )
            else:
                logger.warning(
                    "Call log save returned HTTP {} | {}",
                    response.status_code,
                    response.text[:200],
                )
    except httpx.RequestError as exc:
        logger.warning(
            "Could not save call log (backend unreachable at {}): {}",
            settings.api_base_url,
            exc,
        )
    except Exception as exc:
        logger.warning("Unexpected error saving call log: {}", exc)


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _on_startup() -> None:
    """Log configuration on server start."""
    logger.info(
        "Maya Voice Agent ready | http://localhost:{} | model={} stt={} tts=Sarvam {} voice={}",
        settings.agent_port,
        settings.ollama_model,
        settings.whisper_model,
        settings.sarvam_model,
        settings.sarvam_voice,
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

    # Clean up the WebRTC request handler
    try:
        await _webrtc_handler.close()
    except Exception as exc:
        logger.warning("Error closing WebRTC handler: {}", exc)

    logger.info("Maya Voice Agent shut down cleanly")
