"""Test fixtures and configuration for the Voice Health Agent test suite.

Provides:
- Async in-memory SQLite engine and sessions for isolated test runs
- httpx AsyncClient wired to the FastAPI app with DB dependency overrides
- Pre-built sample data fixtures for Doctor, Patient, TimeSlot, Appointment, CallLog
"""

import asyncio
import uuid
from datetime import date, time, datetime, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from api.database import Base
from api.dependencies import get_db
from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog
from api.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create a shared event loop for the entire test session.

    This avoids creating a new loop per test and prevents
    'attached to a different loop' errors with async fixtures.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create an async in-memory SQLite engine for testing.

    Tables are created before the test and dropped after, ensuring
    a pristine database for every test function.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session bound to the in-memory engine."""
    session_maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with the FastAPI app and overridden DB.

    The ``get_db`` dependency from ``api.dependencies`` is replaced so
    all route handlers use the in-memory test database instead of the
    real ``clinic.db`` file.
    """
    session_maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_doctor(db_session: AsyncSession) -> Doctor:
    """Create and persist a sample cardiologist."""
    doctor = Doctor(
        id=str(uuid.uuid4()),
        name="Dr. Sarah Patel",
        specialty="Cardiology",
        bio="Board certified cardiologist with 15 years of experience.",
        available_days=["Monday", "Wednesday", "Friday"],
        consultation_fee=150.0,
    )
    db_session.add(doctor)
    await db_session.commit()
    await db_session.refresh(doctor)
    return doctor


@pytest_asyncio.fixture
async def sample_doctor_b(db_session: AsyncSession) -> Doctor:
    """Create a second sample doctor for multi-doctor tests."""
    doctor = Doctor(
        id=str(uuid.uuid4()),
        name="Dr. James Wilson",
        specialty="General Practice",
        bio="Family physician with broad primary care expertise.",
        available_days=["Monday", "Tuesday", "Thursday"],
        consultation_fee=100.0,
    )
    db_session.add(doctor)
    await db_session.commit()
    await db_session.refresh(doctor)
    return doctor


@pytest_asyncio.fixture
async def sample_patient(db_session: AsyncSession) -> Patient:
    """Create and persist a sample patient."""
    patient = Patient(
        id=str(uuid.uuid4()),
        name="John Smith",
        phone="+15551234567",
        email="john@example.com",
        insurance_provider="BlueCross",
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)
    return patient


@pytest_asyncio.fixture
async def sample_slot(db_session: AsyncSession, sample_doctor: Doctor) -> TimeSlot:
    """Create an available time slot for tomorrow with the sample doctor."""
    tomorrow = date.today() + timedelta(days=1)
    slot = TimeSlot(
        id=str(uuid.uuid4()),
        doctor_id=sample_doctor.id,
        slot_date=tomorrow,
        start_time=time(10, 0),
        end_time=time(10, 30),
        is_available=True,
    )
    db_session.add(slot)
    await db_session.commit()
    await db_session.refresh(slot)
    return slot


@pytest_asyncio.fixture
async def sample_slot_b(db_session: AsyncSession, sample_doctor: Doctor) -> TimeSlot:
    """Create a second available time slot (afternoon) for the same doctor."""
    tomorrow = date.today() + timedelta(days=1)
    slot = TimeSlot(
        id=str(uuid.uuid4()),
        doctor_id=sample_doctor.id,
        slot_date=tomorrow,
        start_time=time(14, 0),
        end_time=time(14, 30),
        is_available=True,
    )
    db_session.add(slot)
    await db_session.commit()
    await db_session.refresh(slot)
    return slot


@pytest_asyncio.fixture
async def sample_appointment(
    db_session: AsyncSession,
    sample_patient: Patient,
    sample_doctor: Doctor,
    sample_slot: TimeSlot,
) -> Appointment:
    """Create a scheduled appointment linking the sample patient, doctor, and slot."""
    appointment = Appointment(
        id=str(uuid.uuid4()),
        patient_id=sample_patient.id,
        doctor_id=sample_doctor.id,
        slot_id=sample_slot.id,
        visit_type="general",
        status="scheduled",
        notes="Regular checkup",
    )
    # Mark slot as booked
    sample_slot.is_available = False
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest_asyncio.fixture
async def sample_call_log(db_session: AsyncSession) -> CallLog:
    """Create a sample call log record."""
    call_log = CallLog(
        id=str(uuid.uuid4()),
        patient_phone="+15551234567",
        duration_seconds=120,
        transcript=(
            "Patient: I'd like to book an appointment.\n"
            "Maya: Sure, let me check availability for you."
        ),
        summary="Patient requested appointment booking",
        tools_used=["check_available_slots", "book_appointment"],
        escalated=False,
        sentiment_score=0.8,
    )
    db_session.add(call_log)
    await db_session.commit()
    await db_session.refresh(call_log)
    return call_log
