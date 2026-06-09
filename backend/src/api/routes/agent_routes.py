import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from agent.agent import graph as _graph
from agent.agent import run_agent, stream_agent
from api.dependencies import get_current_user
from infrastructure.database.postgres import get_session
from models.base import get_utc_now
from models.chat_history import ChatHistoryModel, ChatRole
from models.chat_session import ChatSessionModel
from models.user import UserModel

# `graph` is a runtime object from the agent library; mypy's static type
# inference does not expose the `run` method. Cast to `Any` to silence type
# checker while preserving runtime behavior.
graph: Any = cast(Any, _graph)

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)


class ChatCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)


class ChatSessionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: ChatRole
    message: str
    timestamp: datetime


class ChatDetailPublic(ChatSessionPublic):
    messages: list[ChatMessagePublic]


class ChatMessageResponse(BaseModel):
    chat: ChatSessionPublic
    user_message: ChatMessagePublic
    assistant_message: ChatMessagePublic


def _active_chat_statement(
    chat_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> Any:
    statement = select(ChatSessionModel).where(
        cast(ColumnElement[bool], ChatSessionModel.id == chat_id),
        cast(ColumnElement[bool], ChatSessionModel.user_id == user_id),
        cast(ColumnElement[bool], cast(Any, ChatSessionModel.deleted_at).is_(None)),
    )
    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    return statement


async def _get_active_chat(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> ChatSessionModel:
    result = await session.execute(
        _active_chat_statement(
            chat_id,
            user_id,
            for_update=for_update,
        )
    )
    chat = cast(ChatSessionModel | None, result.scalar_one_or_none())
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )
    return chat


def _title_from_question(question: str) -> str:
    normalized = " ".join(question.split())
    if len(normalized) <= 60:
        return normalized
    return f"{normalized[:57].rstrip()}..."


async def _persist_chat_exchange(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
    question: str,
    answer: str,
) -> ChatMessageResponse:
    chat = await _get_active_chat(
        session,
        chat_id,
        user_id,
        for_update=True,
    )
    now = get_utc_now()
    user_message = ChatHistoryModel(
        user_id=user_id,
        chat_session_id=chat_id,
        role=ChatRole.USER,
        message=question,
        timestamp=now,
    )
    assistant_message = ChatHistoryModel(
        user_id=user_id,
        chat_session_id=chat_id,
        role=ChatRole.ASSISTANT,
        message=answer,
    )
    if chat.title == "Cuộc trò chuyện mới":
        chat.title = _title_from_question(question)
    chat.updated_at = now
    session.add_all([chat, user_message, assistant_message])
    await session.flush()
    await session.refresh(chat)
    await session.refresh(user_message)
    await session.refresh(assistant_message)

    return ChatMessageResponse(
        chat=ChatSessionPublic.model_validate(chat),
        user_message=ChatMessagePublic.model_validate(user_message),
        assistant_message=ChatMessagePublic.model_validate(assistant_message),
    )


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/agent/ask")
async def ask(req: AskRequest) -> dict[str, Any]:
    """Endpoint để hỏi agent bằng ngôn ngữ tự nhiên.

    Trả về JSON: {"answer": "..."}
    """
    try:
        # Prefer the async helper which normalizes sync/async implementations
        result = await run_agent(req.question)
        return {"answer": result}
    except Exception as exc:  # pragma: no cover - bubble up runtime errors
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/agent/chats",
    response_model=ChatSessionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    req: ChatCreateRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatSessionModel:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    title = req.title.strip() if req.title is not None else "Cuộc trò chuyện mới"
    chat = ChatSessionModel(user_id=current_user.id, title=title)
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    return chat


@router.get("/agent/chats", response_model=list[ChatSessionPublic])
async def list_chats(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: str | None = None,
) -> list[ChatSessionModel]:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    statement = select(ChatSessionModel).where(
        cast(ColumnElement[bool], ChatSessionModel.user_id == current_user.id),
        cast(ColumnElement[bool], cast(Any, ChatSessionModel.deleted_at).is_(None)),
    )
    normalized_search = search.strip() if search is not None else ""
    if normalized_search:
        pattern = f"%{normalized_search}%"
        message_match = exists(
            select(cast(Any, ChatHistoryModel.id)).where(
                cast(
                    ColumnElement[bool],
                    ChatHistoryModel.chat_session_id == ChatSessionModel.id,
                ),
                cast(
                    ColumnElement[bool],
                    cast(Any, ChatHistoryModel.deleted_at).is_(None),
                ),
                cast(
                    ColumnElement[bool],
                    cast(Any, ChatHistoryModel.message).ilike(pattern),
                ),
            )
        )
        statement = statement.where(
            or_(
                cast(Any, ChatSessionModel.title).ilike(pattern),
                message_match,
            )
        )

    result = await session.execute(
        statement.order_by(cast(Any, ChatSessionModel.updated_at).desc())
    )
    return list(result.scalars().all())


@router.get("/agent/chats/{chat_id}", response_model=ChatDetailPublic)
async def get_chat(
    chat_id: int,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatDetailPublic:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    chat = await _get_active_chat(session, chat_id, current_user.id)
    messages_result = await session.execute(
        select(ChatHistoryModel)
        .where(
            cast(
                ColumnElement[bool],
                ChatHistoryModel.chat_session_id == chat_id,
            ),
            cast(
                ColumnElement[bool],
                cast(Any, ChatHistoryModel.deleted_at).is_(None),
            ),
        )
        .order_by(cast(Any, ChatHistoryModel.timestamp).asc())
    )
    return ChatDetailPublic(
        id=cast(int, chat.id),
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[
            ChatMessagePublic.model_validate(message)
            for message in messages_result.scalars().all()
        ],
    )


@router.delete(
    "/agent/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat(
    chat_id: int,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    chat = await _get_active_chat(session, chat_id, current_user.id)
    chat.deleted_at = get_utc_now()
    session.add(chat)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/agent/chats/{chat_id}/messages",
    response_model=ChatMessageResponse,
)
async def create_chat_message(
    chat_id: int,
    req: AskRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatMessageResponse:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await _get_active_chat(session, chat_id, current_user.id)
    question = req.question.strip()
    try:
        answer = await run_agent(question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return await _persist_chat_exchange(
        session,
        chat_id,
        current_user.id,
        question,
        answer,
    )


@router.post("/agent/chats/{chat_id}/messages/stream")
async def stream_chat_message(
    chat_id: int,
    req: AskRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await _get_active_chat(session, chat_id, current_user.id)
    question = req.question.strip()
    user_id = current_user.id

    async def event_stream() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        try:
            async for event in stream_agent(question):
                event_name = event["event"]
                if event_name == "token":
                    content = event.get("content", "")
                    answer_parts.append(content)
                    yield _sse_event("token", {"content": content})
                else:
                    yield _sse_event(
                        "status",
                        {key: value for key, value in event.items() if key != "event"},
                    )

            answer = "".join(answer_parts)
            if not answer:
                raise RuntimeError("Agent returned an empty response")

            result = await _persist_chat_exchange(
                session,
                chat_id,
                user_id,
                question,
                answer,
            )
            await session.commit()
            yield _sse_event(
                "done",
                result.model_dump(mode="json"),
            )
        except Exception as exc:
            await session.rollback()
            yield _sse_event("error", {"detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
