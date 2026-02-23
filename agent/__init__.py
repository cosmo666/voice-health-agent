"""Pipecat Voice Agent -- Maya, the AI receptionist for Sunrise Health Clinic.

This package contains the real-time voice pipeline that powers Maya:

- ``config`` -- Pydantic settings for all tuneable parameters.
- ``prompts`` -- System prompt, escalation keywords, filler phrases.
- ``tools`` -- Five LLM tool definitions and their async HTTP handlers.
- ``pipeline`` -- Factory that builds the VAD -> STT -> LLM -> TTS chain.
- ``flows`` -- Lightweight conversation state machine for tracking/logging.
- ``main`` -- FastAPI app that serves the WebRTC UI and signaling endpoint.
"""
