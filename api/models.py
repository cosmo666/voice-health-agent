"""SQLAlchemy 2.0 ORM models for the Sunrise Health Clinic database.

Defines five tables:
- Doctor: clinic physicians with specialties and availability
- Patient: registered patients with contact and insurance info
- TimeSlot: bookable 30-minute appointment windows per doctor
- Appointment: booked visits linking patients, doctors, and time slots
- CallLog: voice call transcripts with analytics metadata
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


def _generate_uuid() -> str:
    """Generate a new UUID4 string for use as a primary key."""
    return str(uuid.uuid4())


class Doctor(Base):
    """A physician at Sunrise Health Clinic.

    Attributes:
        id: UUID primary key.
        name: Full name (e.g., "Dr. Sarah Patel").
        specialty: Medical specialty (e.g., "Cardiology").
        bio: Free-text biography.
        available_days: JSON list of weekday strings (e.g., ["Monday", "Wednesday"]).
        consultation_fee: Fee in USD.
        created_at: Record creation timestamp.
    """

    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    specialty: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_days: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    consultation_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    time_slots: Mapped[list["TimeSlot"]] = relationship(
        "TimeSlot", back_populates="doctor", cascade="all, delete-orphan"
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="doctor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Doctor(id={self.id!r}, name={self.name!r}, specialty={self.specialty!r})>"


class Patient(Base):
    """A patient registered with the clinic.

    Attributes:
        id: UUID primary key.
        name: Full name.
        phone: Unique phone number (primary lookup key for voice agent).
        email: Optional email address.
        insurance_provider: Optional insurance company name.
        date_of_birth: Optional DOB.
        created_at: Record creation timestamp.
    """

    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    insurance_provider: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="patient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Patient(id={self.id!r}, name={self.name!r}, phone={self.phone!r})>"


class TimeSlot(Base):
    """A bookable 30-minute appointment window for a specific doctor.

    Attributes:
        id: UUID primary key.
        doctor_id: FK to the Doctor table.
        slot_date: Calendar date of the slot.
        start_time: Start time (e.g., 09:00).
        end_time: End time (e.g., 09:30).
        is_available: Whether the slot is open for booking.
    """

    __tablename__ = "time_slots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    slot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="time_slots")
    appointment: Mapped["Appointment | None"] = relationship(
        "Appointment", back_populates="time_slot", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<TimeSlot(id={self.id!r}, doctor_id={self.doctor_id!r}, "
            f"date={self.slot_date}, time={self.start_time}-{self.end_time}, "
            f"available={self.is_available})>"
        )


class Appointment(Base):
    """A booked patient visit linking a patient, doctor, and time slot.

    Attributes:
        id: UUID primary key.
        patient_id: FK to Patient.
        doctor_id: FK to Doctor.
        slot_id: FK to TimeSlot (unique -- one appointment per slot).
        visit_type: One of general, followup, specialist, urgent.
        status: One of scheduled, cancelled, completed, no_show.
        notes: Optional free-text notes.
        created_at: Booking timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    patient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("time_slots.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    visit_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="general"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="appointments")
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="appointments")
    time_slot: Mapped["TimeSlot"] = relationship(
        "TimeSlot", back_populates="appointment"
    )

    def __repr__(self) -> str:
        return (
            f"<Appointment(id={self.id!r}, patient_id={self.patient_id!r}, "
            f"doctor_id={self.doctor_id!r}, status={self.status!r})>"
        )


class CallLog(Base):
    """A recorded voice call between a patient and the AI receptionist.

    Attributes:
        id: UUID primary key.
        patient_phone: Caller's phone number.
        duration_seconds: Call length in seconds.
        transcript: Full conversation transcript.
        summary: AI-generated summary (populated post-call).
        tools_used: JSON list of tool names invoked during the call.
        escalated: Whether the call was escalated to a human.
        sentiment_score: AI-computed sentiment (-1.0 to 1.0, populated post-call).
        created_at: Call start timestamp.
    """

    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    patient_phone: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<CallLog(id={self.id!r}, phone={self.patient_phone!r}, "
            f"duration={self.duration_seconds}s, escalated={self.escalated})>"
        )
