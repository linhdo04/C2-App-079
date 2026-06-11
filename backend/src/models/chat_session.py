from sqlalchemy import Index
from sqlmodel import Field

from .base import BaseModel


class ChatSessionModel(BaseModel, table=True):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index(
            "ix_chat_sessions_user_id_updated_at",
            "user_id",
            "updated_at",
        ),
    )

    user_id: int = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
    )
    title: str = Field(
        default="Cuộc trò chuyện mới",
        min_length=1,
        max_length=120,
        nullable=False,
    )
