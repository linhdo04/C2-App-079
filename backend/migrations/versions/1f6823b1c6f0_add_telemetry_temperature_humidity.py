"""add telemetry temperature humidity

Revision ID: 1f6823b1c6f0
Revises: 218a5abda747
Create Date: 2026-06-10 00:39:55.293388

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1f6823b1c6f0"
down_revision: str | Sequence[str] | None = "218a5abda747"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "telemetry",
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
    )
    op.add_column(
        "telemetry",
        sa.Column("humidity_percent", sa.Float(), nullable=True),
    )
    op.create_check_constraint(
        "ck_telemetry_temperature_celsius",
        "telemetry",
        "temperature_celsius IS NULL OR temperature_celsius >= -273.15",
    )
    op.create_check_constraint(
        "ck_telemetry_humidity_percent",
        "telemetry",
        "humidity_percent IS NULL OR humidity_percent BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_telemetry_humidity_percent",
        "telemetry",
        type_="check",
    )
    op.drop_constraint(
        "ck_telemetry_temperature_celsius",
        "telemetry",
        type_="check",
    )
    op.drop_column("telemetry", "humidity_percent")
    op.drop_column("telemetry", "temperature_celsius")
