import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from agent.agent import run_agent, stream_agent
from agent.react import ConversationMessage
from agent.reasoners import classify_llm_error
from api.dependencies import get_current_user
from api.responses import CollectionMeta, CollectionResponse, DataResponse
from core import settings
from infrastructure.database.postgres import get_session
from models.base import get_utc_now
from models.chat_history import ChatHistoryModel, ChatRole
from models.chat_session import ChatSessionModel
from models.user import UserModel

router = APIRouter()
logger = structlog.get_logger(__name__)


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


class AgentAnswerPublic(BaseModel):
    answer: str


class ChatCursorMeta(CollectionMeta):
    limit: int
    has_more: bool
    next_cursor: str | None


class ChatListResponse(CollectionResponse[ChatSessionPublic]):
    meta: ChatCursorMeta


class ChatCursor(BaseModel):
    version: int
    updated_at: datetime
    chat_id: int
    search_digest: str


def _chat_search_digest(search: str) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"chat-cursor-search:{search}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _encode_chat_cursor(chat: ChatSessionPublic, search: str) -> str:
    payload = (
        ChatCursor(
            version=2,
            updated_at=chat.updated_at,
            chat_id=chat.id,
            search_digest=_chat_search_digest(search),
        )
        .model_dump_json()
        .encode()
    )
    signature = hmac.digest(
        settings.jwt_secret_key.encode(),
        payload,
        hashlib.sha256,
    )
    encoded_payload = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def _decode_chat_cursor(cursor: str, search: str) -> ChatCursor:
    try:
        encoded_payload, encoded_signature = cursor.split(".", maxsplit=1)
        payload_padding = "=" * (-len(encoded_payload) % 4)
        signature_padding = "=" * (-len(encoded_signature) % 4)
        payload = base64.b64decode(
            encoded_payload + payload_padding,
            altchars=b"-_",
            validate=True,
        )
        signature = base64.b64decode(
            encoded_signature + signature_padding,
            altchars=b"-_",
            validate=True,
        )
        expected_signature = hmac.digest(
            settings.jwt_secret_key.encode(),
            payload,
            hashlib.sha256,
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Invalid cursor signature")
        decoded = ChatCursor.model_validate_json(payload)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor",
        ) from exc

    valid_search = hmac.compare_digest(
        decoded.search_digest,
        _chat_search_digest(search),
    )
    if decoded.version != 2 or decoded.chat_id <= 0 or not valid_search:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor",
        )
    return decoded


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


async def _load_agent_history(
    session: AsyncSession,
    chat_id: int,
    user_id: int,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ChatHistoryModel)
        .where(
            cast(
                ColumnElement[bool],
                ChatHistoryModel.chat_session_id == chat_id,
            ),
            cast(ColumnElement[bool], ChatHistoryModel.user_id == user_id),
            cast(
                ColumnElement[bool],
                cast(Any, ChatHistoryModel.deleted_at).is_(None),
            ),
            cast(
                ColumnElement[bool],
                cast(Any, ChatHistoryModel.role).in_(
                    [ChatRole.USER, ChatRole.ASSISTANT, ChatRole.SYSTEM]
                ),
            ),
        )
        .order_by(cast(Any, ChatHistoryModel.timestamp).desc())
        .limit(settings.agent_memory_max_messages)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        ConversationMessage(role=cast(Any, message.role), content=message.message)
        for message in messages
    ]


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/agent/ask", response_model=DataResponse[AgentAnswerPublic])
async def ask(
    req: AskRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> DataResponse[AgentAnswerPublic]:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        result = await run_agent(req.question, current_user.id)
        return DataResponse(data=AgentAnswerPublic(answer=result))
    except Exception as exc:  # pragma: no cover - bubble up runtime errors
        classification = classify_llm_error(exc)
        logger.warning(
            "agent_ask_error",
            error_code=classification.error_code,
            http_status=classification.http_status,
            exc_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=classification.http_status,
            detail=classification.message,
        ) from exc


@router.post(
    "/agent/chats",
    response_model=DataResponse[ChatSessionPublic],
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    req: ChatCreateRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[ChatSessionPublic]:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    title = req.title.strip() if req.title is not None else "Cuộc trò chuyện mới"
    chat = ChatSessionModel(user_id=current_user.id, title=title)
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    return DataResponse(data=ChatSessionPublic.model_validate(chat))


@router.get(
    "/agent/chats",
    response_model=ChatListResponse,
)
async def list_chats(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=120)] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ChatListResponse:
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

    if cursor is not None:
        decoded_cursor = _decode_chat_cursor(cursor, normalized_search)
        statement = statement.where(
            or_(
                cast(
                    ColumnElement[bool],
                    ChatSessionModel.updated_at < decoded_cursor.updated_at,
                ),
                and_(
                    cast(
                        ColumnElement[bool],
                        ChatSessionModel.updated_at == decoded_cursor.updated_at,
                    ),
                    cast(
                        ColumnElement[bool],
                        cast(Any, ChatSessionModel.id) < decoded_cursor.chat_id,
                    ),
                ),
            )
        )

    result = await session.execute(
        statement.order_by(
            cast(Any, ChatSessionModel.updated_at).desc(),
            cast(Any, ChatSessionModel.id).desc(),
        ).limit(limit + 1)
    )
    fetched_chats = [
        ChatSessionPublic.model_validate(chat) for chat in result.scalars().all()
    ]
    has_more = len(fetched_chats) > limit
    chats = fetched_chats[:limit]
    next_cursor = (
        _encode_chat_cursor(chats[-1], normalized_search)
        if has_more and chats
        else None
    )
    return ChatListResponse(
        data=chats,
        meta=ChatCursorMeta(
            count=len(chats),
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
        ),
    )


@router.get(
    "/agent/chats/{chat_id}",
    response_model=DataResponse[ChatDetailPublic],
)
async def get_chat(
    chat_id: int,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[ChatDetailPublic]:
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
    return DataResponse(
        data=ChatDetailPublic(
            id=cast(int, chat.id),
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            messages=[
                ChatMessagePublic.model_validate(message)
                for message in messages_result.scalars().all()
            ],
        )
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
    response_model=DataResponse[ChatMessageResponse],
)
async def create_chat_message(
    chat_id: int,
    req: AskRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[ChatMessageResponse]:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await _get_active_chat(session, chat_id, current_user.id)
    history = await _load_agent_history(session, chat_id, current_user.id)
    question = req.question.strip()
    try:
        answer = await run_agent(
            question,
            current_user.id,
            session_id=str(chat_id),
            history=history,
        )
    except Exception as exc:
        classification = classify_llm_error(exc)
        logger.warning(
            "agent_error_after_retries",
            chat_id=chat_id,
            error_code=classification.error_code,
            http_status=classification.http_status,
            exc_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=classification.http_status,
            detail=classification.message,
        ) from exc

    return DataResponse(
        data=await _persist_chat_exchange(
            session,
            chat_id,
            current_user.id,
            question,
            answer,
        )
    )


@router.post("/agent/chats/{chat_id}/messages/stream")
async def stream_chat_message(
    chat_id: int,
    req: AskRequest,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    user_id = current_user.id
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await _get_active_chat(session, chat_id, user_id)
    history = await _load_agent_history(session, chat_id, user_id)
    # Release the read-only transaction before the potentially long LLM stream.
    # Persistence revalidates ownership and locks the latest chat row.
    await session.rollback()
    question = req.question.strip()

    async def event_stream() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        try:
            async for event in stream_agent(
                question,
                user_id,
                session_id=str(chat_id),
                history=history,
            ):
                event_name = event["event"]
                if event_name == "token":
                    content = event.get("content", "")
                    answer_parts.append(content)
                    yield _sse_event("token", {"data": {"content": content}})
                else:
                    yield _sse_event(
                        "status",
                        {
                            "data": {
                                key: value
                                for key, value in event.items()
                                if key != "event"
                            }
                        },
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
                {"data": result.model_dump(mode="json")},
            )
        except Exception as exc:
            await session.rollback()
            classification = classify_llm_error(exc)
            logger.warning(
                "agent_stream_error_after_retries",
                chat_id=chat_id,
                error_code=classification.error_code,
                http_status=classification.http_status,
                exc_type=type(exc).__name__,
            )
            yield _sse_event(
                "error",
                {
                    "error": classification.error_code,
                    "message": classification.message,
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
