"""Seed database with sample doctors, time slots, and patients.

Populates the Sunrise Health Clinic database with realistic data:

- **8 doctors** across different specialties
- **50+ time slots** spread over the next 2 weeks (Mon-Fri, 9am-5pm, 30-min)
- **5 sample patients** with contact and insurance information

The script is idempotent: if doctors already exist it prints a message and
exits cleanly rather than inserting duplicates.

Usage::

    python scripts/seed_data.py
"""

import asyncio
import random
import sys
import os
import uuid
from datetime import date, time, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from sqlalchemy import select, func

from api.database import async_session_maker, engine, Base
from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog  # noqa: F401


# ---------------------------------------------------------------------------
# Seed definitions
# ---------------------------------------------------------------------------

DOCTORS: list[dict] = [
    {
        "name": "Dr. Sarah Patel",
        "specialty": "Cardiology",
        "bio": (
            "Dr. Sarah Patel is a board-certified cardiologist with over 15 years of "
            "experience in diagnosing and treating cardiovascular diseases. She completed "
            "her fellowship at Johns Hopkins and specializes in preventive cardiology, "
            "heart failure management, and echocardiography. Dr. Patel is known for her "
            "compassionate approach and takes the time to educate patients about heart "
            "health and lifestyle modifications."
        ),
        "available_days": ["Monday", "Wednesday", "Friday"],
        "consultation_fee": 200.00,
    },
    {
        "name": "Dr. James Wilson",
        "specialty": "General Practice",
        "bio": (
            "Dr. James Wilson is a family medicine physician who has served the community "
            "for over 20 years. He earned his medical degree from Stanford University and "
            "completed his residency at UCSF. Dr. Wilson provides comprehensive primary "
            "care for patients of all ages, from routine check-ups and vaccinations to "
            "managing chronic conditions like diabetes and hypertension. He believes in "
            "building long-term relationships with his patients."
        ),
        "available_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "consultation_fee": 120.00,
    },
    {
        "name": "Dr. Priya Sharma",
        "specialty": "Pediatrics",
        "bio": (
            "Dr. Priya Sharma is a pediatrician dedicated to providing exceptional care "
            "for infants, children, and adolescents. She graduated from Harvard Medical "
            "School and completed her pediatric residency at Boston Children's Hospital. "
            "Dr. Sharma specializes in developmental assessments, childhood immunizations, "
            "and managing common pediatric illnesses. She is passionate about childhood "
            "nutrition and preventive health education for families."
        ),
        "available_days": ["Monday", "Tuesday", "Thursday"],
        "consultation_fee": 150.00,
    },
    {
        "name": "Dr. Michael Chen",
        "specialty": "Dermatology",
        "bio": (
            "Dr. Michael Chen is a board-certified dermatologist specializing in medical "
            "and cosmetic dermatology. He completed his dermatology residency at NYU "
            "Langone Health and has published extensively on skin cancer prevention. "
            "Dr. Chen treats a wide range of skin conditions including acne, eczema, "
            "psoriasis, and performs skin cancer screenings. He also offers cosmetic "
            "procedures such as mole removal and laser treatments."
        ),
        "available_days": ["Tuesday", "Wednesday", "Friday"],
        "consultation_fee": 175.00,
    },
    {
        "name": "Dr. Emily Rodriguez",
        "specialty": "OB-GYN",
        "bio": (
            "Dr. Emily Rodriguez is an experienced obstetrician-gynecologist who provides "
            "comprehensive women's health care. She earned her MD from Columbia University "
            "and completed her OB-GYN residency at Mount Sinai Hospital. Dr. Rodriguez "
            "specializes in prenatal care, high-risk pregnancies, minimally invasive "
            "gynecological surgery, and reproductive health. She is committed to "
            "empowering women through personalized, evidence-based care."
        ),
        "available_days": ["Monday", "Wednesday", "Thursday"],
        "consultation_fee": 225.00,
    },
    {
        "name": "Dr. David Kim",
        "specialty": "Orthopedics",
        "bio": (
            "Dr. David Kim is an orthopedic surgeon specializing in sports medicine and "
            "joint reconstruction. He completed his orthopedic surgery residency at the "
            "Hospital for Special Surgery in New York and a sports medicine fellowship "
            "at the Andrews Sports Medicine Institute. Dr. Kim treats fractures, ligament "
            "injuries, arthritis, and performs knee and shoulder surgeries. He works with "
            "athletes at all levels to restore mobility and prevent future injuries."
        ),
        "available_days": ["Tuesday", "Thursday", "Friday"],
        "consultation_fee": 200.00,
    },
    {
        "name": "Dr. Aisha Hassan",
        "specialty": "Internal Medicine",
        "bio": (
            "Dr. Aisha Hassan is an internist with a focus on adult preventive medicine "
            "and chronic disease management. She graduated from the University of "
            "Pennsylvania School of Medicine and completed her internal medicine residency "
            "at Massachusetts General Hospital. Dr. Hassan excels at managing complex "
            "medical conditions including diabetes, hypertension, thyroid disorders, and "
            "respiratory diseases. She emphasizes a holistic approach that incorporates "
            "nutrition, exercise, and mental health."
        ),
        "available_days": ["Monday", "Wednesday", "Friday"],
        "consultation_fee": 160.00,
    },
    {
        "name": "Dr. Robert Thompson",
        "specialty": "ENT",
        "bio": (
            "Dr. Robert Thompson is a board-certified otolaryngologist (ENT specialist) "
            "with expertise in treating ear, nose, and throat disorders. He completed his "
            "ENT residency at the Mayo Clinic and has over 12 years of clinical experience. "
            "Dr. Thompson treats conditions such as sinusitis, hearing loss, tonsillitis, "
            "sleep apnea, and voice disorders. He also performs minimally invasive sinus "
            "surgery and ear tube placements. He is known for his thorough diagnostic "
            "approach and patient-friendly explanations."
        ),
        "available_days": ["Monday", "Tuesday", "Thursday"],
        "consultation_fee": 180.00,
    },
]

PATIENTS: list[dict] = [
    {
        "name": "Maria Garcia",
        "phone": "+15551001001",
        "email": "maria.garcia@email.com",
        "insurance_provider": "Aetna",
        "date_of_birth": date(1985, 3, 15),
    },
    {
        "name": "James Thompson",
        "phone": "+15551002002",
        "email": "james.t@email.com",
        "insurance_provider": "BlueCross BlueShield",
        "date_of_birth": date(1978, 7, 22),
    },
    {
        "name": "Priya Desai",
        "phone": "+15551003003",
        "email": "priya.d@email.com",
        "insurance_provider": "UnitedHealthcare",
        "date_of_birth": date(1992, 11, 8),
    },
    {
        "name": "Robert Johnson",
        "phone": "+15551004004",
        "email": "rob.johnson@email.com",
        "insurance_provider": "Cigna",
        "date_of_birth": date(1970, 1, 30),
    },
    {
        "name": "Sarah Kim",
        "phone": "+15551005005",
        "email": "sarah.kim@email.com",
        "insurance_provider": "Medicare",
        "date_of_birth": date(1955, 6, 12),
    },
]

# Day name to weekday number mapping (Monday=0 .. Friday=4)
DAY_NAME_TO_NUM: dict[str, int] = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}


def _generate_slots_for_doctor(
    doctor_id: str,
    available_days: list[str],
    start_date: date,
    num_weeks: int = 2,
) -> list[TimeSlot]:
    """Generate 30-minute time slots for a doctor over *num_weeks* weeks.

    Slots run from 09:00 to 17:00 (last slot starts at 16:30) on each of the
    doctor's available weekdays.  Approximately 20% of generated slots are
    randomly marked as unavailable to simulate pre-existing bookings.

    Args:
        doctor_id: FK to the Doctor record.
        available_days: List of weekday names (e.g. ["Monday", "Wednesday"]).
        start_date: First date to begin generating from.
        num_weeks: Number of weeks of slots to create.

    Returns:
        List of ``TimeSlot`` ORM instances ready for bulk insertion.
    """
    slots: list[TimeSlot] = []
    end_date = start_date + timedelta(weeks=num_weeks)
    current_date = start_date

    while current_date < end_date:
        weekday_num = current_date.weekday()
        day_name = current_date.strftime("%A")

        if day_name in available_days and weekday_num < 5:
            # Generate 30-minute slots from 9:00 to 16:30 (last slot ends 17:00)
            hour = 9
            minute = 0
            while hour < 17:
                start_t = time(hour, minute)
                # Calculate end time (30 min later)
                end_minute = minute + 30
                end_hour = hour
                if end_minute >= 60:
                    end_minute -= 60
                    end_hour += 1
                end_t = time(end_hour, end_minute)

                # ~20% of slots are pre-booked (unavailable)
                is_available = random.random() > 0.20

                slots.append(
                    TimeSlot(
                        id=str(uuid.uuid4()),
                        doctor_id=doctor_id,
                        slot_date=current_date,
                        start_time=start_t,
                        end_time=end_t,
                        is_available=is_available,
                    )
                )

                minute += 30
                if minute >= 60:
                    minute = 0
                    hour += 1

        current_date += timedelta(days=1)

    return slots


async def seed_doctors(session) -> list[Doctor]:
    """Insert the 8 clinic doctors if they do not already exist.

    Args:
        session: Active async SQLAlchemy session.

    Returns:
        List of Doctor ORM instances (newly created or already existing).
    """
    result = await session.execute(select(func.count()).select_from(Doctor))
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("Doctors already seeded ({} found), skipping", existing_count)
        result = await session.execute(select(Doctor))
        return list(result.scalars().all())

    doctors: list[Doctor] = []
    for doc_data in DOCTORS:
        doctor = Doctor(
            id=str(uuid.uuid4()),
            name=doc_data["name"],
            specialty=doc_data["specialty"],
            bio=doc_data["bio"],
            available_days=doc_data["available_days"],
            consultation_fee=doc_data["consultation_fee"],
        )
        session.add(doctor)
        doctors.append(doctor)
        logger.debug("  Added doctor: {} ({})", doctor.name, doctor.specialty)

    await session.flush()
    logger.info("Seeded {} doctors", len(doctors))
    return doctors


async def seed_time_slots(session, doctors: list[Doctor]) -> int:
    """Generate and insert time slots for all doctors over the next 2 weeks.

    Args:
        session: Active async SQLAlchemy session.
        doctors: List of Doctor ORM instances to generate slots for.

    Returns:
        Total number of time slots inserted.
    """
    result = await session.execute(select(func.count()).select_from(TimeSlot))
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("Time slots already seeded ({} found), skipping", existing_count)
        return existing_count

    # Start from tomorrow so slots are always in the future
    start_date = date.today() + timedelta(days=1)
    total_slots = 0

    for doctor in doctors:
        slots = _generate_slots_for_doctor(
            doctor_id=doctor.id,
            available_days=doctor.available_days,
            start_date=start_date,
            num_weeks=2,
        )
        for slot in slots:
            session.add(slot)
        total_slots += len(slots)
        logger.debug(
            "  Generated {} slots for {} (available days: {})",
            len(slots),
            doctor.name,
            doctor.available_days,
        )

    await session.flush()
    logger.info("Seeded {} time slots across {} doctors", total_slots, len(doctors))
    return total_slots


async def seed_patients(session) -> list[Patient]:
    """Insert the 5 sample patients if they do not already exist.

    Args:
        session: Active async SQLAlchemy session.

    Returns:
        List of Patient ORM instances.
    """
    result = await session.execute(select(func.count()).select_from(Patient))
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("Patients already seeded ({} found), skipping", existing_count)
        result = await session.execute(select(Patient))
        return list(result.scalars().all())

    patients: list[Patient] = []
    for pat_data in PATIENTS:
        patient = Patient(
            id=str(uuid.uuid4()),
            name=pat_data["name"],
            phone=pat_data["phone"],
            email=pat_data["email"],
            insurance_provider=pat_data["insurance_provider"],
            date_of_birth=pat_data["date_of_birth"],
        )
        session.add(patient)
        patients.append(patient)
        logger.debug(
            "  Added patient: {} ({})", patient.name, patient.insurance_provider
        )

    await session.flush()
    logger.info("Seeded {} patients", len(patients))
    return patients


async def seed_sample_appointments(
    session, doctors: list[Doctor], patients: list[Patient]
) -> int:
    """Create a few sample appointments to demonstrate the booking workflow.

    Books 3 appointments by pairing the first 3 patients with available slots
    from different doctors. Marks each consumed slot as unavailable.

    Args:
        session: Active async SQLAlchemy session.
        doctors: List of Doctor ORM instances.
        patients: List of Patient ORM instances.

    Returns:
        Number of appointments created.
    """
    result = await session.execute(select(func.count()).select_from(Appointment))
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("Appointments already seeded ({} found), skipping", existing_count)
        return existing_count

    visit_types = ["general", "followup", "specialist"]
    appointments_created = 0

    # Book appointments for the first 3 patients with different doctors
    pairings = [
        (0, 1, "Annual check-up and blood pressure monitoring"),
        (1, 0, "Follow-up on recent cardiac stress test results"),
        (2, 2, "Child wellness visit and vaccination update"),
    ]

    for patient_idx, doctor_idx, notes in pairings:
        if patient_idx >= len(patients) or doctor_idx >= len(doctors):
            continue

        patient = patients[patient_idx]
        doctor = doctors[doctor_idx]

        # Find an available slot for this doctor
        slot_result = await session.execute(
            select(TimeSlot)
            .where(TimeSlot.doctor_id == doctor.id)
            .where(TimeSlot.is_available == True)  # noqa: E712
            .limit(1)
        )
        slot = slot_result.scalar_one_or_none()

        if slot is None:
            logger.warning(
                "No available slot for {} -- skipping appointment", doctor.name
            )
            continue

        appointment = Appointment(
            id=str(uuid.uuid4()),
            patient_id=patient.id,
            doctor_id=doctor.id,
            slot_id=slot.id,
            visit_type=visit_types[appointments_created % len(visit_types)],
            status="scheduled",
            notes=notes,
        )
        session.add(appointment)

        # Mark the slot as taken
        slot.is_available = False

        appointments_created += 1
        logger.debug(
            "  Booked {} with {} on {} at {}",
            patient.name,
            doctor.name,
            slot.slot_date,
            slot.start_time,
        )

    await session.flush()
    logger.info("Seeded {} sample appointments", appointments_created)
    return appointments_created


async def seed_sample_call_logs(session, patients: list[Patient]) -> int:
    """Insert a few sample call log entries for the admin dashboard.

    Creates 3 representative call logs with transcripts, summaries, and
    analytics metadata so the dashboard has data to display immediately.

    Args:
        session: Active async SQLAlchemy session.
        patients: List of Patient ORM instances (used for phone numbers).

    Returns:
        Number of call logs created.
    """
    result = await session.execute(select(func.count()).select_from(CallLog))
    existing_count = result.scalar_one()

    if existing_count > 0:
        logger.info("Call logs already seeded ({} found), skipping", existing_count)
        return existing_count

    call_logs_data = [
        {
            "patient_phone": patients[0].phone if patients else "+15551001001",
            "duration_seconds": 185,
            "transcript": (
                "Maya: Hi, this is Maya at Sunrise Health Clinic. How can I help you today?\n"
                "Patient: Hi, I'd like to book an appointment with Dr. Wilson for a general check-up.\n"
                "Maya: Sure thing! Let me check Dr. Wilson's availability. One moment please.\n"
                "Maya: I have several openings next week. Would Tuesday at 10:00 AM or Thursday at 2:30 PM work for you?\n"
                "Patient: Tuesday at 10 sounds perfect.\n"
                "Maya: Great! I have you down for Tuesday at 10:00 AM with Dr. James Wilson for a general check-up. "
                "Can I confirm your name and phone number?\n"
                "Patient: Maria Garcia, 555-100-1001.\n"
                "Maya: Got it. Your appointment is confirmed. You'll receive a reminder the day before. "
                "Is there anything else I can help with?\n"
                "Patient: No, that's all. Thank you!\n"
                "Maya: You're welcome, Maria! Have a great day."
            ),
            "summary": "Patient Maria Garcia booked a general check-up with Dr. James Wilson for next Tuesday at 10:00 AM.",
            "tools_used": ["check_available_slots", "book_appointment"],
            "escalated": False,
            "sentiment_score": 0.85,
        },
        {
            "patient_phone": patients[1].phone if len(patients) > 1 else "+15551002002",
            "duration_seconds": 142,
            "transcript": (
                "Maya: Hi, this is Maya at Sunrise Health Clinic. How can I help you today?\n"
                "Patient: I need to cancel my appointment. Something came up at work.\n"
                "Maya: Of course, I understand. Let me pull up your appointment. Could I get your phone number?\n"
                "Patient: It's 555-100-2002.\n"
                "Maya: I see you have an appointment with Dr. Sarah Patel on Wednesday. "
                "Would you like me to cancel that?\n"
                "Patient: Yes, please cancel it.\n"
                "Maya: Done! Your appointment with Dr. Patel has been cancelled. "
                "Would you like me to help you reschedule for another day?\n"
                "Patient: Not right now, I'll call back later.\n"
                "Maya: No problem at all. Feel free to call back anytime. Have a good day!"
            ),
            "summary": "Patient James Thompson cancelled his appointment with Dr. Sarah Patel. Declined to reschedule at this time.",
            "tools_used": ["cancel_appointment"],
            "escalated": False,
            "sentiment_score": 0.45,
        },
        {
            "patient_phone": patients[2].phone if len(patients) > 2 else "+15551003003",
            "duration_seconds": 210,
            "transcript": (
                "Maya: Hi, this is Maya at Sunrise Health Clinic. How can I help you today?\n"
                "Patient: Hi, I have a question about my insurance. Does the clinic accept UnitedHealthcare?\n"
                "Maya: Great question! Yes, we do accept UnitedHealthcare. We accept most major insurance plans "
                "including Aetna, BlueCross BlueShield, UnitedHealthcare, Cigna, and Medicare.\n"
                "Patient: What's the copay for a specialist visit?\n"
                "Maya: For UnitedHealthcare, specialist visit copays typically range from $30 to $50 depending "
                "on your specific plan. I'd recommend checking your plan details or calling UnitedHealthcare "
                "directly for the exact amount. We can also verify your benefits when you come in.\n"
                "Patient: Okay, and what are your clinic hours?\n"
                "Maya: We're open Monday through Friday from 9:00 AM to 5:00 PM. We're closed on weekends "
                "and major holidays.\n"
                "Patient: Perfect, thanks for all the info!\n"
                "Maya: You're welcome! Would you like to book an appointment while you're on the line?\n"
                "Patient: Not today, but maybe soon. Thanks!\n"
                "Maya: Sounds good. Call us anytime. Have a wonderful day!"
            ),
            "summary": "Patient Priya Desai inquired about UnitedHealthcare insurance acceptance, specialist copays, and clinic hours. No appointment booked.",
            "tools_used": ["search_clinic_info"],
            "escalated": False,
            "sentiment_score": 0.78,
        },
    ]

    logs_created = 0
    for log_data in call_logs_data:
        call_log = CallLog(
            id=str(uuid.uuid4()),
            patient_phone=log_data["patient_phone"],
            duration_seconds=log_data["duration_seconds"],
            transcript=log_data["transcript"],
            summary=log_data["summary"],
            tools_used=log_data["tools_used"],
            escalated=log_data["escalated"],
            sentiment_score=log_data["sentiment_score"],
        )
        session.add(call_log)
        logs_created += 1

    await session.flush()
    logger.info("Seeded {} sample call logs", logs_created)
    return logs_created


async def seed_all() -> None:
    """Run the complete seeding pipeline.

    Creates all tables (idempotent), then seeds doctors, time slots, patients,
    sample appointments, and sample call logs in order.
    """
    logger.info("Starting database seed...")

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        try:
            doctors = await seed_doctors(session)
            total_slots = await seed_time_slots(session, doctors)
            patients = await seed_patients(session)
            appointments_count = await seed_sample_appointments(session, doctors, patients)
            call_logs_count = await seed_sample_call_logs(session, patients)

            await session.commit()

            logger.info(
                "Seed complete: {} doctors, {} slots, {} patients, {} appointments, {} call logs",
                len(doctors),
                total_slots,
                len(patients),
                appointments_count,
                call_logs_count,
            )
        except Exception as exc:
            await session.rollback()
            logger.error("Seeding failed, rolled back: {}", exc)
            raise

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_all())
