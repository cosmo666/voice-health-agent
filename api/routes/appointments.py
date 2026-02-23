"""Appointment management endpoints for the Sunrise Health Clinic API.

Provides CRUD operations for healthcare appointments:
- Querying available time slots with doctor/date/type filters
- Booking new appointments (auto-creates patients if needed)
- Cancelling appointments (frees the associated time slot)
- Rescheduling to a different time slot
- Listing appointments by patient phone number
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_db
from api.models import Appointment, Doctor, Patient, TimeSlot
from api.schemas import (
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    TimeSlotResponse,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.get("/slots", response_model=list[TimeSlotResponse])
async def get_available_slots(
    doctor_name: Optional[str] = Query(None, description="Filter by doctor name (case-insensitive contains)"),
    visit_type: Optional[str] = Query(None, description="Visit type filter (unused in slot query, for context)"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> list[TimeSlotResponse]:
    """Return available time slots, optionally filtered by doctor name and/or date.

    Query parameters:
        doctor_name: Partial or full doctor name for case-insensitive search.
        visit_type: Included for voice agent context but does not filter slots.
        date: ISO date string to restrict results to a single day.

    Returns:
        List of available TimeSlotResponse objects with doctor names populated.
    """
    logger.info(
        "Querying available slots: doctor_name={}, date={}", doctor_name, date
    )

    stmt = (
        select(TimeSlot)
        .join(Doctor, TimeSlot.doctor_id == Doctor.id)
        .where(TimeSlot.is_available == True)  # noqa: E712
        .order_by(TimeSlot.slot_date, TimeSlot.start_time)
    )

    if doctor_name:
        stmt = stmt.where(Doctor.name.ilike(f"%{doctor_name}%"))

    if date:
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d").date()
            stmt = stmt.where(TimeSlot.slot_date == filter_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format '{date}'. Expected YYYY-MM-DD.",
            )

    stmt = stmt.options(selectinload(TimeSlot.doctor))

    result = await db.execute(stmt)
    slots = result.scalars().all()

    logger.info("Found {} available slots", len(slots))

    return [
        TimeSlotResponse(
            id=slot.id,
            doctor_id=slot.doctor_id,
            doctor_name=slot.doctor.name if slot.doctor else None,
            slot_date=slot.slot_date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_available=slot.is_available,
        )
        for slot in slots
    ]


@router.post("/", response_model=AppointmentResponse, status_code=201)
async def book_appointment(
    body: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
) -> AppointmentResponse:
    """Book a new appointment.

    Workflow:
    1. Find or create the patient by phone number.
    2. Look up the doctor by name (case-insensitive).
    3. Parse the requested slot_datetime and find a matching available slot.
    4. Create the appointment and mark the slot as unavailable.

    Args:
        body: Appointment booking details.

    Returns:
        The created AppointmentResponse with nested patient, doctor, slot.

    Raises:
        HTTPException 404: Doctor or available slot not found.
        HTTPException 400: Invalid datetime format.
    """
    logger.info(
        "Booking appointment: patient={}, doctor={}, datetime={}",
        body.patient_name,
        body.doctor_name,
        body.slot_datetime,
    )

    # Validate visit_type
    valid_visit_types = {"general", "followup", "specialist", "urgent"}
    if body.visit_type not in valid_visit_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid visit_type '{body.visit_type}'. Must be one of: {', '.join(sorted(valid_visit_types))}",
        )

    # 1. Find or create patient
    patient_result = await db.execute(
        select(Patient).where(Patient.phone == body.patient_phone)
    )
    patient: Patient | None = patient_result.scalar_one_or_none()

    if patient is None:
        patient = Patient(name=body.patient_name, phone=body.patient_phone)
        db.add(patient)
        await db.flush()
        logger.info("Created new patient: name={}, phone={}", patient.name, patient.phone)
    else:
        logger.info("Found existing patient: id={}, name={}", patient.id, patient.name)

    # 2. Find doctor by name
    doctor_result = await db.execute(
        select(Doctor).where(Doctor.name.ilike(f"%{body.doctor_name}%"))
    )
    doctor: Doctor | None = doctor_result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Doctor matching '{body.doctor_name}' not found.",
        )

    # 3. Parse slot datetime and find matching available slot
    try:
        requested_dt = datetime.fromisoformat(body.slot_datetime)
        requested_date = requested_dt.date()
        requested_time = requested_dt.time()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid slot_datetime format '{body.slot_datetime}'. Use ISO format (YYYY-MM-DDTHH:MM:SS).",
        )

    slot_result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.doctor_id == doctor.id,
            TimeSlot.slot_date == requested_date,
            TimeSlot.start_time == requested_time,
            TimeSlot.is_available == True,  # noqa: E712
        )
    )
    slot: TimeSlot | None = slot_result.scalar_one_or_none()

    if slot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No available slot found for {doctor.name} on "
                f"{requested_date} at {requested_time}."
            ),
        )

    # 4. Create appointment and mark slot unavailable
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        slot_id=slot.id,
        visit_type=body.visit_type,
        status="scheduled",
        notes=body.notes,
    )
    slot.is_available = False

    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    logger.info(
        "Appointment booked: id={}, patient={}, doctor={}, slot={}",
        appointment.id,
        patient.name,
        doctor.name,
        f"{slot.slot_date} {slot.start_time}",
    )

    # Build response with nested objects
    return AppointmentResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        slot_id=appointment.slot_id,
        visit_type=appointment.visit_type,
        status=appointment.status,
        notes=appointment.notes,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        patient=PatientResponseFromModel(patient),
        doctor=DoctorResponseFromModel(doctor),
        time_slot=TimeSlotResponseFromModel(slot, doctor.name),
    )


@router.delete("/", status_code=200)
async def cancel_appointment(
    patient_phone: str = Query(..., description="Phone number of the patient"),
    reason: Optional[str] = Query(None, description="Cancellation reason"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel the most recent scheduled appointment for a patient.

    Finds the patient by phone, then their most recently created scheduled
    appointment, marks it as cancelled, and frees up the associated time slot.

    Args:
        patient_phone: Patient's phone number.
        reason: Optional cancellation reason stored in notes.

    Returns:
        Confirmation dict with the cancelled appointment ID and message.

    Raises:
        HTTPException 404: Patient not found or no scheduled appointment exists.
    """
    logger.info(
        "Cancelling appointment: phone={}, reason={}", patient_phone, reason
    )

    # Find patient
    patient_result = await db.execute(
        select(Patient).where(Patient.phone == patient_phone)
    )
    patient: Patient | None = patient_result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail=f"No patient found with phone number '{patient_phone}'.",
        )

    # Find most recent scheduled appointment
    appt_result = await db.execute(
        select(Appointment)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status == "scheduled",
        )
        .order_by(Appointment.created_at.desc())
        .limit(1)
    )
    appointment: Appointment | None = appt_result.scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=404,
            detail=f"No scheduled appointment found for patient '{patient.name}'.",
        )

    # Free up the time slot
    slot_result = await db.execute(
        select(TimeSlot).where(TimeSlot.id == appointment.slot_id)
    )
    slot: TimeSlot | None = slot_result.scalar_one_or_none()

    if slot is not None:
        slot.is_available = True

    # Cancel the appointment
    appointment.status = "cancelled"
    if reason:
        appointment.notes = (
            f"{appointment.notes}\nCancellation reason: {reason}"
            if appointment.notes
            else f"Cancellation reason: {reason}"
        )

    await db.commit()

    logger.info("Appointment cancelled: id={}", appointment.id)

    return {
        "message": "Appointment cancelled successfully.",
        "appointment_id": appointment.id,
        "patient_name": patient.name,
    }


@router.put("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: str,
    body: AppointmentReschedule,
    db: AsyncSession = Depends(get_db),
) -> AppointmentResponse:
    """Reschedule an existing appointment to a different time slot.

    Frees the old time slot and books the new one in a single transaction.

    Args:
        appointment_id: UUID of the appointment to reschedule.
        body: Contains the new_slot_id to move to.

    Returns:
        Updated AppointmentResponse.

    Raises:
        HTTPException 404: Appointment or new slot not found.
        HTTPException 400: Appointment not in scheduled status or new slot unavailable.
    """
    logger.info(
        "Rescheduling appointment: id={}, new_slot_id={}",
        appointment_id,
        body.new_slot_id,
    )

    # Find the appointment
    appt_result = await db.execute(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(
            selectinload(Appointment.patient),
            selectinload(Appointment.doctor),
        )
    )
    appointment: Appointment | None = appt_result.scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Appointment '{appointment_id}' not found.",
        )

    if appointment.status != "scheduled":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reschedule appointment with status '{appointment.status}'. "
            "Only 'scheduled' appointments can be rescheduled.",
        )

    # Free old slot
    old_slot_result = await db.execute(
        select(TimeSlot).where(TimeSlot.id == appointment.slot_id)
    )
    old_slot: TimeSlot | None = old_slot_result.scalar_one_or_none()

    if old_slot is not None:
        old_slot.is_available = True

    # Reserve new slot
    new_slot_result = await db.execute(
        select(TimeSlot)
        .where(TimeSlot.id == body.new_slot_id)
        .options(selectinload(TimeSlot.doctor))
    )
    new_slot: TimeSlot | None = new_slot_result.scalar_one_or_none()

    if new_slot is None:
        raise HTTPException(
            status_code=404,
            detail=f"New time slot '{body.new_slot_id}' not found.",
        )

    if not new_slot.is_available:
        raise HTTPException(
            status_code=400,
            detail=f"Time slot '{body.new_slot_id}' is not available.",
        )

    # Update appointment
    new_slot.is_available = False
    appointment.slot_id = new_slot.id
    appointment.doctor_id = new_slot.doctor_id
    appointment.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(appointment)

    logger.info(
        "Appointment rescheduled: id={}, new_slot={}",
        appointment.id,
        f"{new_slot.slot_date} {new_slot.start_time}",
    )

    return AppointmentResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        slot_id=appointment.slot_id,
        visit_type=appointment.visit_type,
        status=appointment.status,
        notes=appointment.notes,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        patient=PatientResponseFromModel(appointment.patient) if appointment.patient else None,
        doctor=DoctorResponseFromModel(appointment.doctor) if appointment.doctor else None,
        time_slot=TimeSlotResponseFromModel(new_slot, new_slot.doctor.name if new_slot.doctor else None),
    )


@router.get("/", response_model=list[AppointmentResponse])
async def list_appointments(
    patient_phone: Optional[str] = Query(None, description="Filter by patient phone"),
    db: AsyncSession = Depends(get_db),
) -> list[AppointmentResponse]:
    """List appointments, optionally filtered by patient phone number.

    Args:
        patient_phone: If provided, only return appointments for this patient.

    Returns:
        List of AppointmentResponse objects with nested relationships.
    """
    logger.info("Listing appointments: patient_phone={}", patient_phone)

    stmt = (
        select(Appointment)
        .options(
            selectinload(Appointment.patient),
            selectinload(Appointment.doctor),
            selectinload(Appointment.time_slot),
        )
        .order_by(Appointment.created_at.desc())
    )

    if patient_phone:
        stmt = stmt.join(Patient, Appointment.patient_id == Patient.id).where(
            Patient.phone == patient_phone
        )

    result = await db.execute(stmt)
    appointments = result.scalars().all()

    logger.info("Found {} appointments", len(appointments))

    return [
        AppointmentResponse(
            id=appt.id,
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            slot_id=appt.slot_id,
            visit_type=appt.visit_type,
            status=appt.status,
            notes=appt.notes,
            created_at=appt.created_at,
            updated_at=appt.updated_at,
            patient=PatientResponseFromModel(appt.patient) if appt.patient else None,
            doctor=DoctorResponseFromModel(appt.doctor) if appt.doctor else None,
            time_slot=TimeSlotResponseFromModel(
                appt.time_slot,
                appt.doctor.name if appt.doctor else None,
            )
            if appt.time_slot
            else None,
        )
        for appt in appointments
    ]


# ---------------------------------------------------------------------------
# Helper converters -- keep route code clean by centralizing ORM → schema
# ---------------------------------------------------------------------------

def PatientResponseFromModel(patient: Patient):
    """Convert a Patient ORM instance to a PatientResponse schema."""
    from api.schemas import PatientResponse

    return PatientResponse(
        id=patient.id,
        name=patient.name,
        phone=patient.phone,
        email=patient.email,
        insurance_provider=patient.insurance_provider,
        date_of_birth=patient.date_of_birth,
        created_at=patient.created_at,
    )


def DoctorResponseFromModel(doctor: Doctor):
    """Convert a Doctor ORM instance to a DoctorResponse schema."""
    from api.schemas import DoctorResponse

    return DoctorResponse(
        id=doctor.id,
        name=doctor.name,
        specialty=doctor.specialty,
        bio=doctor.bio,
        available_days=doctor.available_days or [],
        consultation_fee=doctor.consultation_fee,
        created_at=doctor.created_at,
    )


def TimeSlotResponseFromModel(slot: TimeSlot, doctor_name: str | None = None):
    """Convert a TimeSlot ORM instance to a TimeSlotResponse schema."""
    return TimeSlotResponse(
        id=slot.id,
        doctor_id=slot.doctor_id,
        doctor_name=doctor_name,
        slot_date=slot.slot_date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        is_available=slot.is_available,
    )
