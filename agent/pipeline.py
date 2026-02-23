"""Pipecat voice pipeline -- VAD -> STT -> LLM -> TTS with real-time conversation.

Constructs the full audio processing pipeline used by the voice agent server.
The pipeline chains together:

1. **SmallWebRTCTransport** -- P2P WebRTC audio I/O (no external service).
2. **Silero VAD** -- Voice Activity Detection on CPU (~50 MB).
3. **Faster-Whisper** -- Speech-to-Text on CPU with int8 quantisation (~150 MB).
4. **OpenAILLMContext** -- Manages conversation history and tool definitions.
5. **OLLamaLLMService** -- gpt-oss:20b-cloud via local Ollama API.
6. **KokoroTTSService** -- Text-to-Speech on CPU via ONNX (~200 MB).

Interruption handling is enabled: if the user speaks while Maya is talking,
the pipeline cancels TTS output and switches to listening mode.

Usage::

    task, runner = await create_pipeline(transport)
    await runner.run(task)
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from agent.config import settings
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
) -> tuple[PipelineTask, PipelineRunner]:
    """Create and configure the full voice pipeline.

    Builds the chain: transport.input -> STT -> context_aggregator.user ->
    LLM -> TTS -> transport.output -> context_aggregator.assistant.

    Tool calls from the LLM are intercepted, dispatched to the appropriate
    async handler in ``agent.tools``, and the result is fed back into the
    LLM context for the next generation turn.

    Args:
        transport: A ``SmallWebRTCTransport`` instance that has been
            pre-configured with VAD parameters and is ready to receive
            an SDP offer.

    Returns:
        A ``(PipelineTask, PipelineRunner)`` tuple.  The caller should
        await ``runner.run(task)`` to start processing audio.

    Raises:
        RuntimeError: If a required Pipecat service fails to initialise.
    """
    logger.info("Creating voice pipeline...")

    # -- STT: Faster-Whisper on CPU, int8 quantisation ----------------------
    try:
        stt = WhisperSTTService(
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            language=settings.whisper_language,
            no_speech_prob=0.4,
        )
        logger.info(
            "STT ready | model={} device={} compute={}",
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
    except Exception as exc:
        logger.error("Failed to initialise Faster-Whisper STT: {}", exc)
        raise RuntimeError(f"STT init failed: {exc}") from exc

    # -- TTS: Kokoro 82M ONNX on CPU ---------------------------------------
    try:
        tts = KokoroTTSService(
            voice_id=settings.kokoro_voice,
        )
        logger.info(
            "TTS ready | voice={}",
            settings.kokoro_voice,
        )
    except Exception as exc:
        logger.error("Failed to initialise Kokoro TTS: {}", exc)
        raise RuntimeError(f"TTS init failed: {exc}") from exc

    # -- LLM: gpt-oss:20b-cloud via Ollama ---------------------------------
    try:
        llm = OLLamaLLMService(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url + "/v1",
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
    context = OpenAILLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=TOOL_DEFINITIONS,
    )
    context_aggregator = llm.create_context_aggregator(context)

    logger.info(
        "LLM context initialised | {} tool(s) registered",
        len(TOOL_DEFINITIONS),
    )

    # -- Register function-call handlers ------------------------------------
    # Pipecat dispatches tool calls emitted by the LLM to registered
    # handlers.  The handler receives the function name, parsed arguments,
    # and a tool-call ID; it must return a string (the tool result).

    async def _handle_function_call(
        function_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        llm_service: Any,
        context: OpenAILLMContext,
        result_callback: Any,
    ) -> None:
        """Dispatch an LLM tool call to the matching handler.

        Args:
            function_name: Name of the function the LLM wants to call.
            tool_call_id: Unique ID for this tool invocation.
            arguments: Parsed JSON arguments from the LLM.
            llm_service: Reference to the LLM service (unused here).
            context: The conversation context to append the result to.
            result_callback: Async callback to send the tool result back
                into the pipeline.
        """
        logger.info(
            "Dispatching tool call | name={} id={} args={}",
            function_name,
            tool_call_id,
            json.dumps(arguments)[:200],
        )

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

        await result_callback(result_str)

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

    # -- Send initial greeting after pipeline starts -------------------------
    @task.event_handler("on_first_participant_joined")
    async def _on_first_participant_joined(transport: Any, participant: Any) -> None:
        """Greet the caller as soon as they connect via WebRTC.

        Injects a ``TTSSpeakFrame`` with Maya's greeting so the patient
        hears a welcome message without needing to speak first.
        """
        logger.info("First participant joined, sending greeting")
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    runner = PipelineRunner()

    logger.info("Pipeline factory complete -- ready to run")
    return task, runner
