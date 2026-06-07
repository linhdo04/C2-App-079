from sqlmodel import Field

from .base import BaseModel


class UserModel(BaseModel, table=True):
    __tablename__ = "users"

    name: str = Field(nullable=False)
    email: str = Field(unique=True, nullable=False)
