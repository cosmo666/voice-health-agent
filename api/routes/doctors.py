"""Doctor listing and filtering endpoints for the Sunrise Health Clinic API.

Provides read-only access to the doctor directory with optional
specialty-based filtering for the voice agent and admin dashboard.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models import Doctor
from api.schemas import DoctorResponse

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


@router.get("/", response_model=list[DoctorResponse])
async def list_doctors(
    specialty: Optional[str] = Query(
        None,
        description="Filter by medical specialty (case-insensitive partial match)",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[DoctorResponse]:
    """Return all clinic doctors, optionally filtered by specialty.

    The specialty filter performs a case-insensitive substring match, so
    searching for "cardio" will match "Cardiology".

    Args:
        specialty: Optional specialty substring filter.

    Returns:
        List of DoctorResponse objects ordered by name.
    """
    logger.info("Listing doctors: specialty_filter={}", specialty)

    stmt = select(Doctor).order_by(Doctor.name)

    if specialty:
        stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty}%"))

    result = await db.execute(stmt)
    doctors = result.scalars().all()

    logger.info("Found {} doctors", len(doctors))

    return [
        DoctorResponse(
            id=doc.id,
            name=doc.name,
            specialty=doc.specialty,
            bio=doc.bio,
            available_days=doc.available_days or [],
            consultation_fee=doc.consultation_fee,
            created_at=doc.created_at,
        )
        for doc in doctors
    ]
