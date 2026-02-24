"""Pipecat voice pipeline -- VAD -> STT -> LLM -> TTS with real-time conversation.

Constructs the full audio processing pipeline used by the voice agent server.
The pipeline chains together:

1. **SmallWebRTCTransport** -- P2P WebRTC audio I/O (no external service).
2. **Silero VAD** -- Voice Activity Detection on CPU (~50 MB).
3. **Faster-Whisper** -- Multilingual STT on CPU with int8 quantisation (~300 MB).
4. **LLMContext** -- Manages conversation history and tool definitions.
5. **OLLamaLLMService** -- gpt-oss:20b-cloud via local Ollama API.
6. **SarvamTTSService** -- Streaming TTS via Sarvam AI (Hindi + English).

Interruption handling is enabled: if the user speaks while Maya is talking,
the pipeline cancels TTS output and switches to listening mode.

Usage::

    task, runner = await create_pipeline(transport)
    await runner.run(task)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from loguru import logger

from pipecat.adapters.schemas.tools_schema import AdapterType, ToolsSchema
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from agent.config import settings
from agent.flows import ConversationContext
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, TOOL_HANDLERS

# ---------------------------------------------------------------------------
# Greeting message (sent as TTS once the pipeline is running)
# ---------------------------------------------------------------------------

GREETING_MESSAGE: str = (
    "Hi, this is Maya at Sunrise Health Clinic. How can I help you today?"
)


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


async def create_pipeline(
    transport: SmallWebRTCTransport,
    conversation_ctx: ConversationContext | None = None,
    vad_analyzer: Optional[VADAnalyzer] = None,
) -> tuple[PipelineTask, PipelineRunner, LLMContext]:
    """Create and configure the full voice pipeline.

    Builds the chain: transport.input -> STT -> context_aggregator.user ->
    LLM -> TTS -> transport.output -> context_aggregator.assistant.

    Tool calls from the LLM are intercepted, dispatched to the appropriate
    async handler in ``agent.tools``, and the result is fed back into the
    LLM context for the next generation turn.

    Args:
        transport: A ``SmallWebRTCTransport`` instance that has been
            pre-configured and is ready to receive an SDP offer.
        conversation_ctx: Optional conversation context for tracking tool
            usage, escalation, and other metadata during the call.
        vad_analyzer: Optional VAD analyzer for voice activity detection.

    Returns:
        A ``(PipelineTask, PipelineRunner, LLMContext)`` tuple.
        The caller should await ``runner.run(task)`` to start processing
        audio.  After the pipeline ends, the ``LLMContext`` contains
        all conversation messages for transcript extraction.

    Raises:
        RuntimeError: If a required Pipecat service fails to initialise.
    """
    logger.info("Creating voice pipeline...")

    # -- STT: Faster-Whisper multilingual on CPU, int8 quantisation ----------
    try:
        stt_kwargs: dict[str, Any] = {
            "model": settings.whisper_model,
            "device": settings.whisper_device,
            "compute_type": settings.whisper_compute_type,
            "no_speech_prob": 0.4,
        }
        if settings.whisper_language:
            # Specific language forced (e.g. "en" or "hi")
            stt_kwargs["language"] = Language(settings.whisper_language)
        # When whisper_language is empty, omit the kwarg entirely so
        # WhisperSTTService uses its default (Language.EN).  Passing None
        # crashes pipecat 0.0.103 with "'NoneType' has no attribute 'value'".
        stt = WhisperSTTService(**stt_kwargs)
        lang_mode = settings.whisper_language or "auto-detect"
        logger.info(
            "STT ready | model={} device={} compute={} language={}",
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
            lang_mode,
        )
    except Exception as exc:
        logger.error("Failed to initialise Faster-Whisper STT: {}", exc)
        raise RuntimeError(f"STT init failed: {exc}") from exc

    # -- TTS: Sarvam AI streaming (Hindi + English) -------------------------
    try:
        tts = SarvamTTSService(
            api_key=settings.sarvam_api_key,
            model=settings.sarvam_model,
            voice_id=settings.sarvam_voice,
            sample_rate=24000,
            params=SarvamTTSService.InputParams(
                language=Language.HI,
                pace=settings.sarvam_pace,
                temperature=settings.sarvam_temperature,
            ),
        )
        logger.info(
            "TTS ready | engine=Sarvam model={} voice={} temp={}",
            settings.sarvam_model,
            settings.sarvam_voice,
            settings.sarvam_temperature,
        )
    except Exception as exc:
        logger.error("Failed to initialise Sarvam TTS: {}", exc)
        raise RuntimeError(f"TTS init failed: {exc}") from exc

    # -- LLM: gpt-oss:20b-cloud via Ollama ---------------------------------
    try:
        llm = OLLamaLLMService(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url + "/v1",
            function_call_timeout_secs=30.0,
        )  # OLLamaLLMService expects base_url with /v1 suffix
        logger.info(
            "LLM ready | model={} base_url={}",
            settings.ollama_model,
            settings.ollama_base_url,
        )
    except Exception as exc:
        logger.error("Failed to initialise Ollama LLM service: {}", exc)
        raise RuntimeError(f"LLM init failed: {exc}") from exc

    # -- Conversation context with system prompt and tools ------------------
    tools_schema = ToolsSchema(
        standard_tools=[],
        custom_tools={AdapterType.SHIM: TOOL_DEFINITIONS},
    )
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=tools_schema,
    )

    # Build context aggregator pair with VAD (moved from TransportParams)
    user_params = LLMUserAggregatorParams(vad_analyzer=vad_analyzer)
    context_aggregator = LLMContextAggregatorPair(
        context, user_params=user_params
    )

    logger.info(
        "LLM context initialised | {} tool(s) registered",
        len(TOOL_DEFINITIONS),
    )

    # -- Register function-call handlers ------------------------------------
    # Pipecat dispatches tool calls emitted by the LLM to registered
    # handlers.  Each handler receives a FunctionCallParams dataclass.

    async def _handle_function_call(params: FunctionCallParams) -> None:
        """Dispatch an LLM tool call to the matching handler.

        Args:
            params: FunctionCallParams with function_name, tool_call_id,
                arguments, llm, context, and result_callback.
        """
        function_name = params.function_name
        tool_call_id = params.tool_call_id
        arguments = dict(params.arguments)

        logger.info(
            "Dispatching tool call | name={} id={} args={}",
            function_name,
            tool_call_id,
            json.dumps(arguments)[:200],
        )

        # Track tool usage in conversation context
        if conversation_ctx is not None:
            conversation_ctx.record_tool_use(function_name)
            if function_name == "escalate_to_human":
                conversation_ctx.mark_escalated()

        handler = TOOL_HANDLERS.get(function_name)
        if handler is None:
            logger.warning("No handler for tool {!r}", function_name)
            result_str = json.dumps({"error": f"Unknown tool: {function_name}"})
        else:
            try:
                result_str = await handler(arguments)
            except Exception as exc:
                logger.error(
                    "Tool handler {!r} raised an exception: {}",
                    function_name,
                    exc,
                )
                result_str = json.dumps({
                    "error": f"Tool execution failed: {exc!s}",
                })

        logger.debug(
            "Tool result for {} ({}): {}",
            function_name,
            tool_call_id,
            result_str[:300],
        )

        await params.result_callback(result_str)

        # If end_call was invoked, schedule a graceful pipeline shutdown
        # after a short delay so Maya's farewell speech can finish playing.
        if function_name == "end_call":
            async def _end_pipeline_after_farewell() -> None:
                await asyncio.sleep(4)
                logger.info("end_call: sending EndFrame to stop pipeline")
                await task.queue_frames([EndFrame()])

            asyncio.create_task(_end_pipeline_after_farewell())

    # Register each tool handler with the LLM service
    for tool_def in TOOL_DEFINITIONS:
        func_name = tool_def["function"]["name"]
        llm.register_function(func_name, _handle_function_call)
        logger.debug("Registered tool handler: {}", func_name)

    # -- Assemble the pipeline ----------------------------------------------
    pipeline = Pipeline(
        [
            transport.input(),           # WebRTC audio in -> frames
            stt,                         # Audio frames -> text transcription
            context_aggregator.user(),   # Accumulate user text into context
            llm,                         # Generate response (may include tool calls)
            tts,                         # Convert response text -> audio frames
            transport.output(),          # Audio frames -> WebRTC audio out
            context_aggregator.assistant(),  # Accumulate assistant output
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    logger.info("Pipeline assembled | interruptions=True")

    # -- Send initial greeting when client connects -------------------------
    # In pipecat 0.0.103, PipelineTask does not have an
    # "on_first_participant_joined" event.  Use the transport-level
    # "on_client_connected" event instead.
    @transport.event_handler("on_client_connected")
    async def _on_client_connected(transport_ref: Any, *args: Any) -> None:
        """Greet the caller as soon as they connect via WebRTC.

        Queues an LLMRunFrame to trigger the LLM to generate Maya's
        opening greeting from the system prompt.
        """
        logger.info("Client connected, sending greeting")
        await task.queue_frames([LLMRunFrame()])

    runner = PipelineRunner()

    logger.info("Pipeline factory complete -- ready to run")
    return task, runner, context
