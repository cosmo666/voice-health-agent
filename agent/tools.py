"""LLM tool definitions and async handler functions for the Maya voice agent.

Defines five tools in OpenAI function-calling schema format and provides a
corresponding async handler for each.  Handlers call the FastAPI backend via
``httpx.AsyncClient``.

Exports:
    TOOL_DEFINITIONS: list[dict] -- OpenAI function-calling schema for all tools.
    TOOL_HANDLERS: dict[str, Callable] -- Mapping of tool name -> async handler.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Coroutine

import httpx
from loguru import logger

from agent.config import settings

# ---------------------------------------------------------------------------
# Shared HTTP client factory
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


def _api_url(path: str) -> str:
    """Build a full URL for the FastAPI backend.

    Args:
        path: API path starting with ``/`` (e.g. ``/api/appointments/slots``).

    Returns:
        Fully-qualified URL string.
    """
    return f"{settings.api_base_url.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Tool: check_available_slots
# ---------------------------------------------------------------------------


async def handle_check_available_slots(args: dict[str, Any]) -> str:
    """Query the backend for available appointment slots.

    Args:
        args: Dict with keys ``doctor_name`` (str), ``visit_type`` (str),
              and optionally ``preferred_date`` (str, ISO format).

    Returns:
        JSON string with the list of available slots or an error message.
    """
    doctor_name: str = args.get("doctor_name", "")
    visit_type: str = args.get("visit_type", "general")
    preferred_date: str | None = args.get("preferred_date")

    params: dict[str, str] = {
        "doctor_name": doctor_name,
        "visit_type": visit_type,
    }
    if preferred_date:
        params["date"] = preferred_date

    logger.info(
        "Tool check_available_slots | doctor={} type={} date={}",
        doctor_name,
        visit_type,
        preferred_date or "any",
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(
                _api_url("/api/appointments/slots"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        slot_count = len(data) if isinstance(data, list) else 0
        logger.info(
            "check_available_slots returned {} slot(s) for {}",
            slot_count,
            doctor_name,
        )
        return json.dumps({"slots": data, "count": slot_count})

    except httpx.HTTPStatusError as exc:
        error_detail = exc.response.text[:500] if exc.response else str(exc)
        logger.error(
            "check_available_slots HTTP {} | {}",
            exc.response.status_code,
            error_detail,
        )
        return json.dumps({
            "error": f"Failed to check slots (HTTP {exc.response.status_code})",
            "detail": error_detail,
        })
    except httpx.RequestError as exc:
        logger.error("check_available_slots request failed | {}", exc)
        return json.dumps({
            "error": "Could not connect to the appointment service. Please try again.",
        })


# ---------------------------------------------------------------------------
# Tool: book_appointment
# ---------------------------------------------------------------------------


async def handle_book_appointment(args: dict[str, Any]) -> str:
    """Book a new appointment via the backend.

    Args:
        args: Dict with keys ``patient_name``, ``patient_phone``,
              ``doctor_name``, ``slot_datetime``, ``visit_type``,
              and optionally ``notes``.

    Returns:
        JSON string with the created appointment data or an error message.
    """
    payload: dict[str, Any] = {
        "patient_name": args.get("patient_name", ""),
        "patient_phone": args.get("patient_phone", ""),
        "doctor_name": args.get("doctor_name", ""),
        "slot_datetime": args.get("slot_datetime", ""),
        "visit_type": args.get("visit_type", "general"),
    }
    if args.get("notes"):
        payload["notes"] = args["notes"]

    logger.info(
        "Tool book_appointment | patient={} phone={} doctor={} slot={} type={}",
        payload["patient_name"],
        payload["patient_phone"],
        payload["doctor_name"],
        payload["slot_datetime"],
        payload["visit_type"],
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                _api_url("/api/appointments/"),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        logger.info("book_appointment succeeded | appointment_id={}", data.get("id"))
        return json.dumps({
            "success": True,
            "appointment": data,
            "message": (
                f"Appointment booked for {payload['patient_name']} with "
                f"{payload['doctor_name']} on {payload['slot_datetime']}."
            ),
        })

    except httpx.HTTPStatusError as exc:
        error_detail = exc.response.text[:500] if exc.response else str(exc)
        logger.error(
            "book_appointment HTTP {} | {}",
            exc.response.status_code,
            error_detail,
        )
        return json.dumps({
            "error": f"Could not book the appointment (HTTP {exc.response.status_code})",
            "detail": error_detail,
        })
    except httpx.RequestError as exc:
        logger.error("book_appointment request failed | {}", exc)
        return json.dumps({
            "error": "Could not connect to the appointment service. Please try again.",
        })


# ---------------------------------------------------------------------------
# Tool: cancel_appointment
# ---------------------------------------------------------------------------


async def handle_cancel_appointment(args: dict[str, Any]) -> str:
    """Cancel the most recent scheduled appointment for a patient.

    Args:
        args: Dict with keys ``patient_phone`` (str) and optionally
              ``reason`` (str).

    Returns:
        JSON string confirming the cancellation or an error message.
    """
    patient_phone: str = args.get("patient_phone", "")
    reason: str | None = args.get("reason")

    params: dict[str, str] = {"patient_phone": patient_phone}
    if reason:
        params["reason"] = reason

    logger.info(
        "Tool cancel_appointment | phone={} reason={}",
        patient_phone,
        reason or "none",
    )

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.delete(
                _api_url("/api/appointments/"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        logger.info("cancel_appointment succeeded | phone={}", patient_phone)
        return json.dumps({
            "success": True,
            "cancellation": data,
            "message": f"Appointment for phone {patient_phone} has been cancelled.",
        })

    except httpx.HTTPStatusError as exc:
        error_detail = exc.response.text[:500] if exc.response else str(exc)
        logger.error(
            "cancel_appointment HTTP {} | {}",
            exc.response.status_code,
            error_detail,
        )
        # Provide a user-friendly message for common errors
        if exc.response.status_code == 404:
            return json.dumps({
                "error": "No active appointment found for that phone number.",
            })
        return json.dumps({
            "error": f"Could not cancel the appointment (HTTP {exc.response.status_code})",
            "detail": error_detail,
        })
    except httpx.RequestError as exc:
        logger.error("cancel_appointment request failed | {}", exc)
        return json.dumps({
            "error": "Could not connect to the appointment service. Please try again.",
        })


# ---------------------------------------------------------------------------
# Tool: search_clinic_info
# ---------------------------------------------------------------------------


async def handle_search_clinic_info(args: dict[str, Any]) -> str:
    """Query the RAG knowledge base for clinic information.

    Args:
        args: Dict with key ``query`` (str) -- the patient's question.

    Returns:
        JSON string with the RAG answer and source documents, or an error.
    """
    query: str = args.get("query", "")

    logger.info("Tool search_clinic_info | query={!r}", query[:120])

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(
                _api_url("/api/rag/query"),
                params={"q": query},
            )
            response.raise_for_status()
            data = response.json()

        answer = data.get("answer", "")
        sources = data.get("sources", [])
        logger.info(
            "search_clinic_info returned answer ({} chars) with {} source(s)",
            len(answer),
            len(sources),
        )
        return json.dumps({
            "answer": answer,
            "sources": sources,
        })

    except httpx.HTTPStatusError as exc:
        error_detail = exc.response.text[:500] if exc.response else str(exc)
        logger.error(
            "search_clinic_info HTTP {} | {}",
            exc.response.status_code,
            error_detail,
        )
        return json.dumps({
            "error": "I wasn't able to find that information right now.",
            "detail": error_detail,
        })
    except httpx.RequestError as exc:
        logger.error("search_clinic_info request failed | {}", exc)
        return json.dumps({
            "error": "The knowledge base is temporarily unavailable. Please try again.",
        })


# ---------------------------------------------------------------------------
# Tool: escalate_to_human
# ---------------------------------------------------------------------------


async def handle_escalate_to_human(args: dict[str, Any]) -> str:
    """Log an escalation event and return a patient-facing message.

    This does NOT call an external API -- it records the escalation locally
    and returns a message for Maya to read to the patient.

    Args:
        args: Dict with keys ``reason`` (str), ``urgency`` (str -- one of
              low/medium/high/emergency), and ``summary`` (str).

    Returns:
        JSON string with the escalation confirmation.
    """
    reason: str = args.get("reason", "Unknown reason")
    urgency: str = args.get("urgency", "medium")
    summary: str = args.get("summary", "")

    # Validate urgency level
    valid_urgencies = {"low", "medium", "high", "emergency"}
    if urgency not in valid_urgencies:
        logger.warning(
            "Invalid urgency {!r}, defaulting to 'medium'",
            urgency,
        )
        urgency = "medium"

    timestamp = datetime.utcnow().isoformat()

    logger.warning(
        "ESCALATION | urgency={} | reason={!r} | summary={!r} | ts={}",
        urgency,
        reason,
        summary[:200],
        timestamp,
    )

    # Compose message based on urgency
    if urgency == "emergency":
        patient_message = (
            "I'm connecting you with our medical staff immediately. "
            "If this is a life-threatening emergency, please hang up and call 911."
        )
    elif urgency == "high":
        patient_message = (
            "I'm transferring you to a staff member right away. "
            "Please stay on the line."
        )
    else:
        patient_message = (
            "Let me connect you with one of our staff members who can help "
            "you with this. Please hold for just a moment."
        )

    return json.dumps({
        "escalated": True,
        "urgency": urgency,
        "reason": reason,
        "summary": summary,
        "timestamp": timestamp,
        "patient_message": patient_message,
    })


# ---------------------------------------------------------------------------
# Tool: end_call
# ---------------------------------------------------------------------------


async def handle_end_call(args: dict[str, Any]) -> str:
    """End the voice call gracefully after the patient says goodbye.

    Args:
        args: Dict with key ``reason`` (str) describing why the call ended.

    Returns:
        JSON string confirming the call has ended.
    """
    reason: str = args.get("reason", "Patient ended the conversation")

    logger.info("Tool end_call | reason={!r}", reason)

    return json.dumps({
        "ended": True,
        "reason": reason,
        "message": "Thank you for calling Sunrise Health Clinic. Goodbye!",
    })


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_available_slots",
            "description": (
                "Check available appointment slots for a specific doctor. "
                "Returns a list of open time slots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_name": {
                        "type": "string",
                        "description": (
                            "Full name of the doctor (e.g. 'Dr. Sarah Patel')."
                        ),
                    },
                    "visit_type": {
                        "type": "string",
                        "enum": ["general", "followup", "specialist", "urgent"],
                        "description": "Type of visit.",
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": (
                            "Preferred date in ISO format (YYYY-MM-DD). "
                            "Omit to search all available dates."
                        ),
                    },
                },
                "required": ["doctor_name", "visit_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book a new appointment for a patient with a specific doctor "
                "at a given date/time. Creates the patient record if they are "
                "not already registered."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "Full name of the patient.",
                    },
                    "patient_phone": {
                        "type": "string",
                        "description": "Patient's phone number (used as unique ID).",
                    },
                    "doctor_name": {
                        "type": "string",
                        "description": "Full name of the doctor to book with.",
                    },
                    "slot_datetime": {
                        "type": "string",
                        "description": (
                            "Exact ISO datetime of the slot to book "
                            "(e.g. '2026-02-25T09:00:00')."
                        ),
                    },
                    "visit_type": {
                        "type": "string",
                        "enum": ["general", "followup", "specialist", "urgent"],
                        "description": "Type of visit.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the appointment.",
                    },
                },
                "required": [
                    "patient_name",
                    "patient_phone",
                    "doctor_name",
                    "slot_datetime",
                    "visit_type",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": (
                "Cancel the most recent scheduled appointment for a patient, "
                "identified by their phone number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_phone": {
                        "type": "string",
                        "description": "Patient's phone number.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional reason for cancellation.",
                    },
                },
                "required": ["patient_phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clinic_info",
            "description": (
                "Search the clinic's knowledge base for information about "
                "services, insurance policies, doctor profiles, clinic hours, "
                "parking, COVID policies, and other frequently asked questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or search query from the patient.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Transfer the call to a human staff member. Use this when the "
                "patient has a medical emergency, requests a human, is very "
                "frustrated, or the issue cannot be resolved by the AI agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the call is being escalated.",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "emergency"],
                        "description": "Urgency level of the escalation.",
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "Brief summary of the conversation so far for "
                            "the human agent."
                        ),
                    },
                },
                "required": ["reason", "urgency", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": (
                "End the phone call gracefully. Call this AFTER you have said "
                "your farewell message when the patient says goodbye, thanks you, "
                "says 'that will be all', or indicates they have no more questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": (
                            "Brief reason the call is ending "
                            "(e.g. 'Patient said goodbye')."
                        ),
                    },
                },
                "required": ["reason"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

TOOL_HANDLERS: dict[
    str,
    Callable[[dict[str, Any]], Coroutine[Any, Any, str]],
] = {
    "check_available_slots": handle_check_available_slots,
    "book_appointment": handle_book_appointment,
    "cancel_appointment": handle_cancel_appointment,
    "search_clinic_info": handle_search_clinic_info,
    "escalate_to_human": handle_escalate_to_human,
    "end_call": handle_end_call,
}
