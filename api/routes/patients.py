"""Patient lookup and registration endpoints for the Sunrise Health Clinic API.

Provides patient management for the voice agent (lookup by phone during calls)
and the admin dashboard (viewing patient records).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models import Patient
from api.schemas import PatientCreate, PatientResponse

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("/", response_model=list[PatientResponse])
async def lookup_patient(
    phone: str = Query(..., description="Patient phone number to search for"),
    db: AsyncSession = Depends(get_db),
) -> list[PatientResponse]:
    """Look up a patient by phone number.

    Returns a list with zero or one patient matching the exact phone number.
    The voice agent uses this to identify returning callers.

    Args:
        phone: Exact phone number to match.

    Returns:
        List containing the matching PatientResponse, or empty list if not found.
    """
    logger.info("Looking up patient by phone: {}", phone)

    result = await db.execute(
        select(Patient).where(Patient.phone == phone)
    )
    patient: Patient | None = result.scalar_one_or_none()

    if patient is None:
        logger.info("No patient found with phone: {}", phone)
        return []

    logger.info("Found patient: id={}, name={}", patient.id, patient.name)

    return [
        PatientResponse(
            id=patient.id,
            name=patient.name,
            phone=patient.phone,
            email=patient.email,
            insurance_provider=patient.insurance_provider,
            date_of_birth=patient.date_of_birth,
            created_at=patient.created_at,
        )
    ]


@router.post("/", response_model=PatientResponse, status_code=201)
async def create_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_db),
) -> PatientResponse:
    """Register a new patient.

    Creates a patient record with the provided details. Phone numbers must
    be unique -- attempting to register a duplicate phone returns HTTP 409.

    Args:
        body: Patient registration details.

    Returns:
        The newly created PatientResponse.

    Raises:
        HTTPException 409: A patient with this phone number already exists.
    """
    logger.info("Creating patient: name={}, phone={}", body.name, body.phone)

    # Check for existing patient with the same phone
    existing_result = await db.execute(
        select(Patient).where(Patient.phone == body.phone)
    )
    existing: Patient | None = existing_result.scalar_one_or_none()

    if existing is not None:
        logger.warning(
            "Duplicate phone number rejected: phone={}, existing_patient_id={}",
            body.phone,
            existing.id,
        )
        raise HTTPException(
            status_code=409,
            detail=f"A patient with phone number '{body.phone}' already exists (id={existing.id}).",
        )

    patient = Patient(
        name=body.name,
        phone=body.phone,
        email=body.email,
        insurance_provider=body.insurance_provider,
        date_of_birth=body.date_of_birth,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info("Patient created: id={}, name={}", patient.id, patient.name)

    return PatientResponse(
        id=patient.id,
        name=patient.name,
        phone=patient.phone,
        email=patient.email,
        insurance_provider=patient.insurance_provider,
        date_of_birth=patient.date_of_birth,
        created_at=patient.created_at,
    )
