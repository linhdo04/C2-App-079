from enum import StrEnum

from sqlalchemy import CheckConstraint, String
from sqlmodel import Field

from .base import BaseModel


class UserRole(StrEnum):
    OPERATOR = "operator"
    ADMIN = "admin"


class UserModel(BaseModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('operator', 'admin')",
            name="ck_users_role",
        ),
    )

    name: str = Field(nullable=False)
    email: str = Field(unique=True, nullable=False)
    password_hash: str = Field(nullable=False, repr=False, exclude=True)
    role: UserRole = Field(
        default=UserRole.OPERATOR,
        sa_type=String,
        nullable=False,
    )
