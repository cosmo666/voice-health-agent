"""Pydantic v2 request/response schemas for the Sunrise Health Clinic API.

All schemas use `model_config = ConfigDict(from_attributes=True)` so they can
be constructed directly from SQLAlchemy ORM model instances.
"""

from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


class DoctorResponse(BaseModel):
    """Response schema for a clinic doctor."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    specialty: str
    bio: Optional[str] = None
    available_days: list[str] = Field(default_factory=list)
    consultation_fee: float
    created_at: datetime


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------


class PatientCreate(BaseModel):
    """Request body to register a new patient."""

    name: str = Field(..., min_length=1, max_length=200, description="Patient full name")
    phone: str = Field(..., min_length=1, max_length=20, description="Unique phone number")
    email: Optional[str] = Field(None, max_length=254)
    insurance_provider: Optional[str] = Field(None, max_length=200)
    date_of_birth: Optional[date] = None


class PatientResponse(BaseModel):
    """Response schema for a patient record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    phone: str
    email: Optional[str] = None
    insurance_provider: Optional[str] = None
    date_of_birth: Optional[date] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# TimeSlot
# ---------------------------------------------------------------------------


class TimeSlotResponse(BaseModel):
    """Response schema for an available time slot."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    slot_date: date
    start_time: time
    end_time: time
    is_available: bool


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------


class AppointmentCreate(BaseModel):
    """Request body to book a new appointment.

    The API will find-or-create the patient by phone, look up the doctor
    by name, and match the requested datetime to an available slot.
    """

    patient_name: str = Field(..., min_length=1, max_length=200)
    patient_phone: str = Field(..., min_length=1, max_length=20)
    doctor_name: str = Field(..., min_length=1, max_length=200)
    slot_datetime: str = Field(
        ...,
        description="ISO datetime string for the desired slot (e.g. '2026-02-25T09:00:00')",
    )
    visit_type: str = Field(
        default="general",
        description="One of: general, followup, specialist, urgent",
    )
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    """Response schema for a booked appointment."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    doctor_id: str
    slot_id: str
    visit_type: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    patient: Optional[PatientResponse] = None
    doctor: Optional[DoctorResponse] = None
    time_slot: Optional[TimeSlotResponse] = None


class AppointmentReschedule(BaseModel):
    """Request body to reschedule an appointment to a different slot."""

    new_slot_id: str = Field(..., description="UUID of the new time slot to move to")


# ---------------------------------------------------------------------------
# CallLog
# ---------------------------------------------------------------------------


class CallLogCreate(BaseModel):
    """Request body to save a voice call record."""

    patient_phone: str = Field(..., min_length=1, max_length=20)
    duration_seconds: int = Field(..., ge=0)
    transcript: str = Field(..., min_length=1)
    summary: Optional[str] = None
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool = False
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)


class CallLogResponse(BaseModel):
    """Response schema for a call log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_phone: str
    duration_seconds: int
    transcript: str
    summary: Optional[str] = None
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool
    sentiment_score: Optional[float] = None
    created_at: datetime


class PaginatedCallLogs(BaseModel):
    """Paginated response for call log listings."""

    items: list[CallLogResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


class RAGQueryResponse(BaseModel):
    """Response from the RAG knowledge-base query endpoint."""

    answer: str
    sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response showing service status."""

    status: str
    services: dict[str, str] = Field(default_factory=dict)
