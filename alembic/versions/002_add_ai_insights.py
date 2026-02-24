"""Add ai_insights JSON column to call_logs.

Stores structured AI-generated analytics for each call: topics, intent,
action items, language detected, key moments, and recommendations.
Populated asynchronously by the qwen3-next:80b-cloud model after each call.

Revision ID: 002
Revises: 001
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Revision identifiers used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ai_insights column to call_logs table."""
    op.add_column(
        "call_logs",
        sa.Column("ai_insights", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove ai_insights column from call_logs table."""
    op.drop_column("call_logs", "ai_insights")
