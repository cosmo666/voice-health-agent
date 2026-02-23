"""Tests for all FastAPI REST API endpoints.

Uses httpx AsyncClient with the ``client`` fixture that overrides the DB
dependency to use an in-memory SQLite database. Every test gets a clean
database via the ``db_engine`` fixture chain.

Tests cover:
- Health check
- Doctor listing and specialty filtering
- Patient creation, lookup, duplicate rejection
- Appointment slot queries, booking, cancellation, listing, rescheduling
- Call log creation, paginated listing, detail retrieval
"""

import uuid
from datetime import date, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """GET /health should return 200 with status field."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert data["services"]["api"] == "ok"


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_doctors_empty(client: AsyncClient) -> None:
    """GET /api/doctors/ should return an empty list when no doctors exist."""
    response = await client.get("/api/doctors/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_doctors(client: AsyncClient, sample_doctor: Doctor) -> None:
    """GET /api/doctors/ should return seeded doctors."""
    response = await client.get("/api/doctors/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    names = [d["name"] for d in data]
    assert "Dr. Sarah Patel" in names


@pytest.mark.asyncio
async def test_filter_doctors_by_specialty(
    client: AsyncClient, sample_doctor: Doctor, sample_doctor_b: Doctor
) -> None:
    """GET /api/doctors/?specialty=Cardiology should filter results."""
    response = await client.get("/api/doctors/", params={"specialty": "Cardiology"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["specialty"] == "Cardiology"
    assert data[0]["name"] == "Dr. Sarah Patel"


@pytest.mark.asyncio
async def test_filter_doctors_no_match(client: AsyncClient, sample_doctor: Doctor) -> None:
    """GET /api/doctors/?specialty=Neurology with no matching doctor returns empty list."""
    response = await client.get("/api/doctors/", params={"specialty": "Neurology"})
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_patient(client: AsyncClient) -> None:
    """POST /api/patients/ should create a new patient and return 201."""
    payload = {
        "name": "Alice Johnson",
        "phone": "+15551112222",
        "email": "alice@example.com",
        "insurance_provider": "UnitedHealth",
    }
    response = await client.post("/api/patients/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice Johnson"
    assert data["phone"] == "+15551112222"
    assert data["email"] == "alice@example.com"
    assert data["insurance_provider"] == "UnitedHealth"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_duplicate_patient(client: AsyncClient) -> None:
    """POST /api/patients/ with an already-used phone should return 409."""
    payload = {"name": "First Patient", "phone": "+15553334444"}
    response1 = await client.post("/api/patients/", json=payload)
    assert response1.status_code == 201

    payload2 = {"name": "Second Patient", "phone": "+15553334444"}
    response2 = await client.post("/api/patients/", json=payload2)
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_lookup_patient(client: AsyncClient, sample_patient: Patient) -> None:
    """GET /api/patients/?phone=... should return matching patient in a list."""
    response = await client.get(
        "/api/patients/", params={"phone": sample_patient.phone}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["phone"] == sample_patient.phone
    assert data[0]["name"] == "John Smith"


@pytest.mark.asyncio
async def test_lookup_patient_not_found(client: AsyncClient) -> None:
    """GET /api/patients/?phone=nonexistent should return an empty list."""
    response = await client.get(
        "/api/patients/", params={"phone": "+15550000000"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data == []


# ---------------------------------------------------------------------------
# Appointment Slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_available_slots(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """GET /api/appointments/slots should return available slots."""
    response = await client.get("/api/appointments/slots")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    slot_ids = [s["id"] for s in data]
    assert sample_slot.id in slot_ids


@pytest.mark.asyncio
async def test_get_available_slots_filter_by_doctor(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """GET /api/appointments/slots?doctor_name=Patel should filter by doctor."""
    response = await client.get(
        "/api/appointments/slots", params={"doctor_name": "Patel"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    for slot in data:
        assert "Patel" in slot["doctor_name"]


@pytest.mark.asyncio
async def test_get_available_slots_filter_by_date(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """GET /api/appointments/slots?date=... should filter to that date."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = await client.get(
        "/api/appointments/slots", params={"date": tomorrow}
    )
    assert response.status_code == 200
    data = response.json()
    for slot in data:
        assert slot["slot_date"] == tomorrow


@pytest.mark.asyncio
async def test_get_slots_invalid_date_format(client: AsyncClient) -> None:
    """GET /api/appointments/slots?date=bad-format should return 400."""
    response = await client.get(
        "/api/appointments/slots", params={"date": "not-a-date"}
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_appointment(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """POST /api/appointments/ should book a slot and return 201."""
    tomorrow = date.today() + timedelta(days=1)
    slot_dt = f"{tomorrow.isoformat()}T10:00:00"

    payload = {
        "patient_name": "New Patient",
        "patient_phone": "+15557778888",
        "doctor_name": "Dr. Sarah Patel",
        "slot_datetime": slot_dt,
        "visit_type": "general",
        "notes": "First visit",
    }
    response = await client.post("/api/appointments/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "scheduled"
    assert data["visit_type"] == "general"
    assert data["slot_id"] == sample_slot.id
    assert "id" in data


@pytest.mark.asyncio
async def test_book_appointment_creates_patient(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """Booking should auto-create a patient if the phone is new."""
    tomorrow = date.today() + timedelta(days=1)
    slot_dt = f"{tomorrow.isoformat()}T10:00:00"

    payload = {
        "patient_name": "Brand New Person",
        "patient_phone": "+15550001234",
        "doctor_name": "Dr. Sarah Patel",
        "slot_datetime": slot_dt,
        "visit_type": "general",
    }
    response = await client.post("/api/appointments/", json=payload)
    assert response.status_code == 201

    # Verify the patient was created
    patient_resp = await client.get(
        "/api/patients/", params={"phone": "+15550001234"}
    )
    assert patient_resp.status_code == 200
    patients = patient_resp.json()
    assert len(patients) == 1
    assert patients[0]["name"] == "Brand New Person"


@pytest.mark.asyncio
async def test_book_appointment_no_matching_slot(
    client: AsyncClient, sample_doctor: Doctor
) -> None:
    """Booking when no matching slot exists should return 404."""
    payload = {
        "patient_name": "Nobody",
        "patient_phone": "+15550005555",
        "doctor_name": "Dr. Sarah Patel",
        "slot_datetime": "2099-12-31T09:00:00",
        "visit_type": "general",
    }
    response = await client.post("/api/appointments/", json=payload)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_book_appointment_doctor_not_found(client: AsyncClient) -> None:
    """Booking with a nonexistent doctor name should return 404."""
    payload = {
        "patient_name": "Nobody",
        "patient_phone": "+15550006666",
        "doctor_name": "Dr. Nonexistent",
        "slot_datetime": "2026-03-01T09:00:00",
        "visit_type": "general",
    }
    response = await client.post("/api/appointments/", json=payload)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_book_appointment_invalid_visit_type(
    client: AsyncClient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """Booking with an invalid visit_type should return 400."""
    tomorrow = date.today() + timedelta(days=1)
    slot_dt = f"{tomorrow.isoformat()}T10:00:00"

    payload = {
        "patient_name": "Test",
        "patient_phone": "+15550007777",
        "doctor_name": "Dr. Sarah Patel",
        "slot_datetime": slot_dt,
        "visit_type": "invalid_type",
    }
    response = await client.post("/api/appointments/", json=payload)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_appointment(
    client: AsyncClient, sample_appointment: Appointment, sample_patient: Patient
) -> None:
    """DELETE /api/appointments/?patient_phone=... should cancel and return 200."""
    response = await client.delete(
        "/api/appointments/",
        params={
            "patient_phone": sample_patient.phone,
            "reason": "Schedule conflict",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Appointment cancelled successfully."
    assert data["appointment_id"] == sample_appointment.id


@pytest.mark.asyncio
async def test_cancel_no_appointment(client: AsyncClient) -> None:
    """DELETE /api/appointments/ for nonexistent patient should return 404."""
    response = await client.delete(
        "/api/appointments/",
        params={"patient_phone": "+15550000000"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_frees_slot(
    client: AsyncClient,
    sample_appointment: Appointment,
    sample_patient: Patient,
    sample_slot: TimeSlot,
) -> None:
    """Cancelling should make the slot available again."""
    # The slot should be unavailable before cancellation
    slots_before = await client.get("/api/appointments/slots")
    slot_ids_before = [s["id"] for s in slots_before.json()]
    assert sample_slot.id not in slot_ids_before

    # Cancel
    await client.delete(
        "/api/appointments/",
        params={"patient_phone": sample_patient.phone},
    )

    # The slot should now be available
    slots_after = await client.get("/api/appointments/slots")
    slot_ids_after = [s["id"] for s in slots_after.json()]
    assert sample_slot.id in slot_ids_after


# ---------------------------------------------------------------------------
# Rescheduling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_appointment(
    client: AsyncClient,
    sample_appointment: Appointment,
    sample_slot_b: TimeSlot,
) -> None:
    """PUT /api/appointments/{id}/reschedule should move to the new slot."""
    response = await client.put(
        f"/api/appointments/{sample_appointment.id}/reschedule",
        json={"new_slot_id": sample_slot_b.id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["slot_id"] == sample_slot_b.id
    assert data["status"] == "scheduled"


@pytest.mark.asyncio
async def test_reschedule_nonexistent_appointment(client: AsyncClient) -> None:
    """PUT /api/appointments/{bad_id}/reschedule should return 404."""
    fake_id = str(uuid.uuid4())
    response = await client.put(
        f"/api/appointments/{fake_id}/reschedule",
        json={"new_slot_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# List Appointments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_patient_appointments(
    client: AsyncClient,
    sample_appointment: Appointment,
    sample_patient: Patient,
) -> None:
    """GET /api/appointments/?patient_phone=... should list that patient's appointments."""
    response = await client.get(
        "/api/appointments/", params={"patient_phone": sample_patient.phone}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["patient_id"] == sample_patient.id


@pytest.mark.asyncio
async def test_get_appointments_empty(client: AsyncClient) -> None:
    """GET /api/appointments/?patient_phone=... for unknown phone returns empty list."""
    response = await client.get(
        "/api/appointments/", params={"patient_phone": "+15550000000"}
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Call Logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_call_log(client: AsyncClient) -> None:
    """POST /api/calls/ should save a call log and return 201."""
    payload = {
        "patient_phone": "+15559991111",
        "duration_seconds": 90,
        "transcript": "Patient asked about insurance. Maya provided details.",
        "summary": "Insurance inquiry",
        "tools_used": ["search_clinic_info"],
        "escalated": False,
        "sentiment_score": 0.6,
    }
    response = await client.post("/api/calls/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["patient_phone"] == "+15559991111"
    assert data["duration_seconds"] == 90
    assert data["tools_used"] == ["search_clinic_info"]
    assert data["escalated"] is False
    assert data["sentiment_score"] == 0.6
    assert "id" in data


@pytest.mark.asyncio
async def test_list_call_logs_paginated(client: AsyncClient) -> None:
    """GET /api/calls/ should return paginated results."""
    # Seed multiple call logs
    for i in range(7):
        await client.post("/api/calls/", json={
            "patient_phone": f"+1555000{i:04d}",
            "duration_seconds": 30 + i * 10,
            "transcript": f"Call transcript {i}",
            "tools_used": [],
        })

    response = await client.get("/api/calls/", params={"page": 1, "per_page": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 7
    assert data["page"] == 1
    assert data["per_page"] == 5
    assert len(data["items"]) == 5
    assert data["pages"] == 2

    # Page 2
    response2 = await client.get("/api/calls/", params={"page": 2, "per_page": 5})
    data2 = response2.json()
    assert len(data2["items"]) == 2
    assert data2["page"] == 2


@pytest.mark.asyncio
async def test_list_call_logs_filter_by_phone(client: AsyncClient) -> None:
    """GET /api/calls/?phone=... should filter by patient phone."""
    # Create two calls from different phones
    await client.post("/api/calls/", json={
        "patient_phone": "+15551110001",
        "duration_seconds": 45,
        "transcript": "Call from phone A",
        "tools_used": [],
    })
    await client.post("/api/calls/", json={
        "patient_phone": "+15551110002",
        "duration_seconds": 60,
        "transcript": "Call from phone B",
        "tools_used": [],
    })

    response = await client.get(
        "/api/calls/", params={"phone": "+15551110001"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["patient_phone"] == "+15551110001"


@pytest.mark.asyncio
async def test_get_call_detail(client: AsyncClient, sample_call_log: CallLog) -> None:
    """GET /api/calls/{id} should return the full call log record."""
    response = await client.get(f"/api/calls/{sample_call_log.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_call_log.id
    assert data["patient_phone"] == "+15551234567"
    assert data["duration_seconds"] == 120
    assert data["summary"] == "Patient requested appointment booking"
    assert data["sentiment_score"] == 0.8


@pytest.mark.asyncio
async def test_get_call_not_found(client: AsyncClient) -> None:
    """GET /api/calls/{nonexistent_id} should return 404."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/calls/{fake_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# RAG (fallback -- no RAG module fully initialised in test env)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_query_fallback(client: AsyncClient) -> None:
    """GET /api/rag/query?q=... should return a fallback answer if RAG is not set up."""
    response = await client.get("/api/rag/query", params={"q": "What insurance do you accept?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data
    # Should be a non-empty answer (either real RAG or fallback)
    assert len(data["answer"]) > 0
