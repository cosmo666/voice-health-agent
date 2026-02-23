"""Tests for SQLAlchemy ORM models and database relationships.

Validates:
- Model creation with all fields
- Default values (is_available, status, escalated, created_at)
- Unique constraints (Patient.phone, Appointment.slot_id)
- Foreign key relationships (TimeSlot->Doctor, Appointment->Patient/Doctor/TimeSlot)
- Cascade deletes (deleting Doctor cascades to TimeSlots and Appointments)
- Relationship navigation (doctor.time_slots, patient.appointments, etc.)
"""

import uuid
from datetime import date, time, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog


@pytest.mark.asyncio
async def test_doctor_creation_all_fields(db_session: AsyncSession) -> None:
    """A Doctor record should persist with all fields populated correctly."""
    doctor_id = str(uuid.uuid4())
    doctor = Doctor(
        id=doctor_id,
        name="Dr. Sarah Patel",
        specialty="Cardiology",
        bio="Board certified cardiologist",
        available_days=["Monday", "Wednesday", "Friday"],
        consultation_fee=150.0,
    )
    db_session.add(doctor)
    await db_session.commit()

    result = await db_session.execute(select(Doctor).where(Doctor.id == doctor_id))
    loaded = result.scalar_one()

    assert loaded.name == "Dr. Sarah Patel"
    assert loaded.specialty == "Cardiology"
    assert loaded.bio == "Board certified cardiologist"
    assert loaded.available_days == ["Monday", "Wednesday", "Friday"]
    assert loaded.consultation_fee == 150.0
    assert loaded.created_at is not None
    assert isinstance(loaded.created_at, datetime)


@pytest.mark.asyncio
async def test_patient_creation_and_defaults(db_session: AsyncSession) -> None:
    """A Patient record should persist and auto-generate id and created_at."""
    patient = Patient(
        name="Jane Doe",
        phone="+15559876543",
        email="jane@example.com",
        insurance_provider="Aetna",
        date_of_birth=date(1990, 5, 15),
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)

    assert patient.id is not None
    assert len(patient.id) == 36  # UUID length
    assert patient.name == "Jane Doe"
    assert patient.phone == "+15559876543"
    assert patient.email == "jane@example.com"
    assert patient.insurance_provider == "Aetna"
    assert patient.date_of_birth == date(1990, 5, 15)
    assert patient.created_at is not None


@pytest.mark.asyncio
async def test_patient_phone_uniqueness(db_session: AsyncSession) -> None:
    """Inserting two patients with the same phone should raise IntegrityError."""
    patient1 = Patient(name="Alice", phone="+15551111111")
    patient2 = Patient(name="Bob", phone="+15551111111")

    db_session.add(patient1)
    await db_session.commit()

    db_session.add(patient2)
    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_timeslot_default_is_available(db_session: AsyncSession, sample_doctor: Doctor) -> None:
    """TimeSlot.is_available should default to True when not specified."""
    slot = TimeSlot(
        doctor_id=sample_doctor.id,
        slot_date=date.today() + timedelta(days=2),
        start_time=time(9, 0),
        end_time=time(9, 30),
    )
    db_session.add(slot)
    await db_session.commit()
    await db_session.refresh(slot)

    assert slot.is_available is True


@pytest.mark.asyncio
async def test_timeslot_fk_relationship_to_doctor(
    db_session: AsyncSession, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """TimeSlot should have a navigable relationship back to its Doctor."""
    result = await db_session.execute(
        select(TimeSlot).where(TimeSlot.id == sample_slot.id)
    )
    loaded_slot = result.scalar_one()

    # Explicitly load the doctor via the foreign key
    doctor_result = await db_session.execute(
        select(Doctor).where(Doctor.id == loaded_slot.doctor_id)
    )
    loaded_doctor = doctor_result.scalar_one()

    assert loaded_doctor.id == sample_doctor.id
    assert loaded_doctor.name == sample_doctor.name


@pytest.mark.asyncio
async def test_appointment_default_status(
    db_session: AsyncSession, sample_patient: Patient, sample_doctor: Doctor, sample_slot: TimeSlot
) -> None:
    """Appointment.status should default to 'scheduled'."""
    appointment = Appointment(
        patient_id=sample_patient.id,
        doctor_id=sample_doctor.id,
        slot_id=sample_slot.id,
        visit_type="general",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)

    assert appointment.status == "scheduled"
    assert appointment.created_at is not None
    assert appointment.updated_at is not None


@pytest.mark.asyncio
async def test_appointment_slot_uniqueness(db_session: AsyncSession) -> None:
    """Two appointments cannot reference the same time slot (slot_id is unique)."""
    doctor = Doctor(
        id=str(uuid.uuid4()),
        name="Dr. Unique Test",
        specialty="Testing",
        available_days=["Monday"],
        consultation_fee=50.0,
    )
    db_session.add(doctor)
    await db_session.flush()

    patient1 = Patient(name="Pat1", phone="+15550000001")
    patient2 = Patient(name="Pat2", phone="+15550000002")
    db_session.add_all([patient1, patient2])
    await db_session.flush()

    slot = TimeSlot(
        id=str(uuid.uuid4()),
        doctor_id=doctor.id,
        slot_date=date.today() + timedelta(days=3),
        start_time=time(11, 0),
        end_time=time(11, 30),
        is_available=True,
    )
    db_session.add(slot)
    await db_session.flush()

    appt1 = Appointment(
        patient_id=patient1.id,
        doctor_id=doctor.id,
        slot_id=slot.id,
        visit_type="general",
    )
    db_session.add(appt1)
    await db_session.commit()

    appt2 = Appointment(
        patient_id=patient2.id,
        doctor_id=doctor.id,
        slot_id=slot.id,
        visit_type="followup",
    )
    db_session.add(appt2)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_appointment_fk_relationships(
    db_session: AsyncSession,
    sample_appointment: Appointment,
    sample_patient: Patient,
    sample_doctor: Doctor,
    sample_slot: TimeSlot,
) -> None:
    """Appointment FK columns should point to the correct parent records."""
    assert sample_appointment.patient_id == sample_patient.id
    assert sample_appointment.doctor_id == sample_doctor.id
    assert sample_appointment.slot_id == sample_slot.id


@pytest.mark.asyncio
async def test_calllog_creation_with_json_fields(db_session: AsyncSession) -> None:
    """CallLog should persist JSON fields (tools_used) and default values correctly."""
    call_log = CallLog(
        patient_phone="+15559999999",
        duration_seconds=60,
        transcript="Hello, I need help.",
        tools_used=["check_available_slots"],
    )
    db_session.add(call_log)
    await db_session.commit()
    await db_session.refresh(call_log)

    assert call_log.id is not None
    assert call_log.patient_phone == "+15559999999"
    assert call_log.duration_seconds == 60
    assert call_log.transcript == "Hello, I need help."
    assert call_log.tools_used == ["check_available_slots"]
    assert call_log.escalated is False  # default
    assert call_log.sentiment_score is None  # nullable default
    assert call_log.summary is None  # nullable default
    assert call_log.created_at is not None


@pytest.mark.asyncio
async def test_calllog_escalated_default_false(db_session: AsyncSession) -> None:
    """CallLog.escalated should default to False."""
    call_log = CallLog(
        patient_phone="+15550000010",
        duration_seconds=30,
        transcript="Test transcript",
        tools_used=[],
    )
    db_session.add(call_log)
    await db_session.commit()
    await db_session.refresh(call_log)

    assert call_log.escalated is False


@pytest.mark.asyncio
async def test_cascade_delete_doctor_removes_slots(db_session: AsyncSession) -> None:
    """Deleting a Doctor should cascade-delete associated TimeSlots."""
    doctor = Doctor(
        id=str(uuid.uuid4()),
        name="Dr. Cascade Test",
        specialty="Testing",
        available_days=["Tuesday"],
        consultation_fee=75.0,
    )
    db_session.add(doctor)
    await db_session.flush()

    slot1 = TimeSlot(
        doctor_id=doctor.id,
        slot_date=date.today() + timedelta(days=5),
        start_time=time(9, 0),
        end_time=time(9, 30),
    )
    slot2 = TimeSlot(
        doctor_id=doctor.id,
        slot_date=date.today() + timedelta(days=5),
        start_time=time(10, 0),
        end_time=time(10, 30),
    )
    db_session.add_all([slot1, slot2])
    await db_session.commit()

    # Verify slots exist
    result = await db_session.execute(
        select(TimeSlot).where(TimeSlot.doctor_id == doctor.id)
    )
    assert len(result.scalars().all()) == 2

    # Delete the doctor
    await db_session.delete(doctor)
    await db_session.commit()

    # Verify slots are gone
    result = await db_session.execute(
        select(TimeSlot).where(TimeSlot.doctor_id == doctor.id)
    )
    remaining = result.scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_cascade_delete_patient_removes_appointments(db_session: AsyncSession) -> None:
    """Deleting a Patient should cascade-delete their Appointments."""
    doctor = Doctor(
        id=str(uuid.uuid4()),
        name="Dr. Pat Cascade",
        specialty="Testing",
        available_days=["Wednesday"],
        consultation_fee=80.0,
    )
    db_session.add(doctor)
    await db_session.flush()

    patient = Patient(name="CascadePatient", phone="+15550009999")
    db_session.add(patient)
    await db_session.flush()

    slot = TimeSlot(
        id=str(uuid.uuid4()),
        doctor_id=doctor.id,
        slot_date=date.today() + timedelta(days=6),
        start_time=time(13, 0),
        end_time=time(13, 30),
    )
    db_session.add(slot)
    await db_session.flush()

    appt = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_id=slot.id,
        visit_type="general",
    )
    db_session.add(appt)
    await db_session.commit()

    # Verify appointment exists
    result = await db_session.execute(
        select(Appointment).where(Appointment.patient_id == patient.id)
    )
    assert len(result.scalars().all()) == 1

    # Delete the patient
    await db_session.delete(patient)
    await db_session.commit()

    # Verify appointment is gone
    result = await db_session.execute(
        select(Appointment).where(Appointment.patient_id == patient.id)
    )
    remaining = result.scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_doctor_repr(sample_doctor: Doctor) -> None:
    """Doctor.__repr__ should include id, name, and specialty."""
    repr_str = repr(sample_doctor)
    assert "Dr. Sarah Patel" in repr_str
    assert "Cardiology" in repr_str


@pytest.mark.asyncio
async def test_patient_nullable_fields(db_session: AsyncSession) -> None:
    """Patient optional fields (email, insurance, DOB) can be None."""
    patient = Patient(name="Minimal Patient", phone="+15550008888")
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)

    assert patient.email is None
    assert patient.insurance_provider is None
    assert patient.date_of_birth is None
