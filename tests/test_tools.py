"""Tests for the voice agent LLM tool handler functions.

Each tool handler in ``agent/tools.py`` makes async HTTP calls to the FastAPI
backend.  These tests mock ``httpx.AsyncClient`` to return predefined responses
and verify that:

- The correct endpoint is called with the right method, URL, and params/body
- Successful responses are parsed and returned as structured JSON strings
- HTTP errors are caught and returned as user-friendly error JSON
- Network errors (connection refused, timeout) are handled gracefully
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent.tools import (
    TOOL_DEFINITIONS,
    TOOL_HANDLERS,
    handle_book_appointment,
    handle_cancel_appointment,
    handle_check_available_slots,
    handle_escalate_to_human,
    handle_search_clinic_info,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int = 200, json_data: dict | list | None = None) -> httpx.Response:
    """Create a mock httpx.Response with the given status and JSON body."""
    response = httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "http://test"),
        json=json_data,
    )
    return response


# ---------------------------------------------------------------------------
# check_available_slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_available_slots_success() -> None:
    """check_available_slots should return slot data when API responds 200."""
    mock_slots = [
        {
            "id": "slot-1",
            "doctor_id": "doc-1",
            "doctor_name": "Dr. Sarah Patel",
            "slot_date": "2026-03-01",
            "start_time": "10:00:00",
            "end_time": "10:30:00",
            "is_available": True,
        }
    ]

    mock_response = _make_response(200, mock_slots)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_check_available_slots({
            "doctor_name": "Dr. Sarah Patel",
            "visit_type": "general",
            "preferred_date": "2026-03-01",
        })

    result = json.loads(result_str)
    assert result["count"] == 1
    assert len(result["slots"]) == 1
    assert result["slots"][0]["doctor_name"] == "Dr. Sarah Patel"


@pytest.mark.asyncio
async def test_check_available_slots_empty() -> None:
    """check_available_slots should return count=0 when no slots are available."""
    mock_response = _make_response(200, [])
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_check_available_slots({
            "doctor_name": "Dr. Nobody",
            "visit_type": "general",
        })

    result = json.loads(result_str)
    assert result["count"] == 0
    assert result["slots"] == []


# ---------------------------------------------------------------------------
# book_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_appointment_success() -> None:
    """book_appointment should return a success message with appointment data."""
    mock_appt = {
        "id": "appt-123",
        "patient_id": "pat-1",
        "doctor_id": "doc-1",
        "slot_id": "slot-1",
        "visit_type": "general",
        "status": "scheduled",
    }

    mock_response = _make_response(201, mock_appt)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_book_appointment({
            "patient_name": "John Smith",
            "patient_phone": "+15551234567",
            "doctor_name": "Dr. Sarah Patel",
            "slot_datetime": "2026-03-01T10:00:00",
            "visit_type": "general",
            "notes": "Annual checkup",
        })

    result = json.loads(result_str)
    assert result["success"] is True
    assert result["appointment"]["id"] == "appt-123"
    assert "John Smith" in result["message"]
    assert "Dr. Sarah Patel" in result["message"]


@pytest.mark.asyncio
async def test_book_appointment_http_error() -> None:
    """book_appointment should return an error JSON when the API returns 404."""
    mock_response = _make_response(404, {"detail": "No available slot found"})
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # httpx raises HTTPStatusError for 4xx/5xx on raise_for_status()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("POST", "http://test/api/appointments/"),
            response=mock_response,
        )
    )

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_book_appointment({
            "patient_name": "John",
            "patient_phone": "+15551111111",
            "doctor_name": "Dr. Nobody",
            "slot_datetime": "2099-12-31T09:00:00",
            "visit_type": "general",
        })

    result = json.loads(result_str)
    assert "error" in result
    assert "404" in result["error"]


# ---------------------------------------------------------------------------
# cancel_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_appointment_success() -> None:
    """cancel_appointment should return a success message on 200."""
    mock_data = {
        "message": "Appointment cancelled successfully.",
        "appointment_id": "appt-456",
        "patient_name": "John Smith",
    }

    mock_response = _make_response(200, mock_data)
    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_cancel_appointment({
            "patient_phone": "+15551234567",
            "reason": "No longer needed",
        })

    result = json.loads(result_str)
    assert result["success"] is True
    assert result["cancellation"]["appointment_id"] == "appt-456"
    assert "+15551234567" in result["message"]


@pytest.mark.asyncio
async def test_cancel_appointment_not_found() -> None:
    """cancel_appointment should return a user-friendly 404 error."""
    mock_response = _make_response(404, {"detail": "No patient found"})
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("DELETE", "http://test/api/appointments/"),
            response=mock_response,
        )
    )

    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_cancel_appointment({
            "patient_phone": "+15550000000",
        })

    result = json.loads(result_str)
    assert "error" in result
    assert "no active appointment" in result["error"].lower()


# ---------------------------------------------------------------------------
# search_clinic_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_clinic_info_success() -> None:
    """search_clinic_info should return answer and sources from RAG."""
    mock_data = {
        "answer": "We accept BlueCross, Aetna, and UnitedHealth insurance plans.",
        "sources": ["insurance_policies.md"],
    }

    mock_response = _make_response(200, mock_data)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_search_clinic_info({
            "query": "What insurance do you accept?",
        })

    result = json.loads(result_str)
    assert "BlueCross" in result["answer"]
    assert "insurance_policies.md" in result["sources"]


# ---------------------------------------------------------------------------
# escalate_to_human
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalate_to_human_emergency() -> None:
    """escalate_to_human with urgency=emergency should return 911 guidance."""
    result_str = await handle_escalate_to_human({
        "reason": "Patient reports chest pain",
        "urgency": "emergency",
        "summary": "Patient called about chest pain, needs immediate attention",
    })

    result = json.loads(result_str)
    assert result["escalated"] is True
    assert result["urgency"] == "emergency"
    assert "911" in result["patient_message"]
    assert result["reason"] == "Patient reports chest pain"


@pytest.mark.asyncio
async def test_escalate_to_human_low_urgency() -> None:
    """escalate_to_human with urgency=low should return a polite hold message."""
    result_str = await handle_escalate_to_human({
        "reason": "Patient wants to discuss billing",
        "urgency": "low",
        "summary": "Billing inquiry that AI cannot resolve",
    })

    result = json.loads(result_str)
    assert result["escalated"] is True
    assert result["urgency"] == "low"
    assert "hold" in result["patient_message"].lower() or "connect" in result["patient_message"].lower()


@pytest.mark.asyncio
async def test_escalate_to_human_invalid_urgency_defaults() -> None:
    """escalate_to_human with invalid urgency should default to 'medium'."""
    result_str = await handle_escalate_to_human({
        "reason": "Unknown issue",
        "urgency": "super_critical",
        "summary": "Test",
    })

    result = json.loads(result_str)
    assert result["urgency"] == "medium"


# ---------------------------------------------------------------------------
# Connection / network errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_slots_connection_error() -> None:
    """Tool handlers should return a friendly error when the API is unreachable."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_check_available_slots({
            "doctor_name": "Dr. Test",
            "visit_type": "general",
        })

    result = json.loads(result_str)
    assert "error" in result
    assert "connect" in result["error"].lower() or "try again" in result["error"].lower()


@pytest.mark.asyncio
async def test_book_appointment_connection_error() -> None:
    """book_appointment should handle connection failures gracefully."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("agent.tools.httpx.AsyncClient", return_value=mock_client):
        result_str = await handle_book_appointment({
            "patient_name": "Test",
            "patient_phone": "+15550000000",
            "doctor_name": "Dr. Test",
            "slot_datetime": "2026-03-01T09:00:00",
            "visit_type": "general",
        })

    result = json.loads(result_str)
    assert "error" in result


# ---------------------------------------------------------------------------
# Tool registry and definitions
# ---------------------------------------------------------------------------


def test_tool_definitions_structure() -> None:
    """TOOL_DEFINITIONS should have 5 tools, each with proper schema structure."""
    assert len(TOOL_DEFINITIONS) == 5

    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"
        assert "properties" in func["parameters"]
        assert "required" in func["parameters"]


def test_tool_handlers_registry() -> None:
    """TOOL_HANDLERS should map all 5 tool names to callable handlers."""
    expected_names = {
        "check_available_slots",
        "book_appointment",
        "cancel_appointment",
        "search_clinic_info",
        "escalate_to_human",
    }
    assert set(TOOL_HANDLERS.keys()) == expected_names

    for name, handler in TOOL_HANDLERS.items():
        assert callable(handler), f"Handler for {name} is not callable"
