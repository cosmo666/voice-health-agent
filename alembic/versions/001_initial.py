"""Initial database schema.

Creates the five core tables for the Sunrise Health Clinic:

- **doctors**: Physicians with specialties, bios, and availability schedules
- **patients**: Registered patients with contact and insurance information
- **time_slots**: 30-minute bookable appointment windows per doctor
- **appointments**: Booked visits linking patients, doctors, and time slots
- **call_logs**: Voice call transcripts with analytics metadata

Revision ID: 001
Revises: None (initial migration)
Create Date: 2026-02-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Revision identifiers used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all five database tables."""

    # ── doctors ───────────────────────────────────────────────────────────
    op.create_table(
        "doctors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("specialty", sa.String(100), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("available_days", sa.JSON(), nullable=False),
        sa.Column("consultation_fee", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ── patients ──────────────────────────────────────────────────────────
    op.create_table(
        "patients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, unique=True, index=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("insurance_provider", sa.String(200), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ── time_slots ────────────────────────────────────────────────────────
    op.create_table(
        "time_slots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_date", sa.Date(), nullable=False, index=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    # ── appointments ──────────────────────────────────────────────────────
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(36),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id",
            sa.String(36),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "slot_id",
            sa.String(36),
            sa.ForeignKey("time_slots.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("visit_type", sa.String(20), nullable=False, server_default="general"),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, onupdate=sa.func.now()),
    )

    # ── call_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "call_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_phone", sa.String(20), nullable=False, index=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcript", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tools_used", sa.JSON(), nullable=False),
        sa.Column(
            "escalated", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("call_logs")
    op.drop_table("appointments")
    op.drop_table("time_slots")
    op.drop_table("patients")
    op.drop_table("doctors")
