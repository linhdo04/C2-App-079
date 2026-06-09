"""add_user_password_hash

Revision ID: 31c9ab7d2c7f
Revises: 956e21bcf9c5
Create Date: 2026-06-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "31c9ab7d2c7f"
down_revision: Union[str, Sequence[str], None] = "956e21bcf9c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_PASSWORD_HASH = "!legacy-user-no-password!"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute(
        sa.text("UPDATE users SET password_hash = :legacy_hash").bindparams(
            legacy_hash=LEGACY_PASSWORD_HASH
        )
    )
    op.alter_column("users", "password_hash", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "password_hash")
