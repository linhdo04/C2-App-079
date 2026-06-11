import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from api.routes.agent_routes import (
    AskRequest,
    ChatCreateRequest,
    ChatSessionPublic,
    _decode_chat_cursor,
    _encode_chat_cursor,
    _get_active_chat,
    _load_agent_history,
    _title_from_question,
    create_chat,
    create_chat_message,
    delete_chat,
    list_chats,
    stream_chat_message,
)
from models.chat_history import ChatHistoryModel, ChatRole
from models.chat_session import ChatSessionModel
from models.user import UserModel


class FakeScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalars(self) -> "FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return self.value if isinstance(self.value, list) else []


class FakeSession:
    def __init__(self, execute_values: list[Any] | None = None) -> None:
        self.execute_values = execute_values or []
        self.added: list[Any] = []
        self.next_id = 1
        self.statements: list[Any] = []
        self.rollback_count = 0
        self.committed = False

    async def execute(self, statement: Any) -> FakeScalarResult:
        self.statements.append(statement)
        value = self.execute_values.pop(0) if self.execute_values else None
        return FakeScalarResult(value)

    def add(self, value: Any) -> None:
        self.added.append(value)

    def add_all(self, values: list[Any]) -> None:
        self.added.extend(values)

    async def flush(self) -> None:
        for value in self.added:
            if value.id is None:
                value.id = self.next_id
                self.next_id += 1

    async def refresh(self, value: Any) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def commit(self) -> None:
        self.committed = True


class ExpiringUser:
    def __init__(self, user_id: int) -> None:
        self._user_id = user_id
        self.expired = False

    @property
    def id(self) -> int:
        if self.expired:
            raise RuntimeError("expired ORM attribute accessed")
        return self._user_id


class ExpiringSession(FakeSession):
    def __init__(self, user: ExpiringUser, execute_values: list[Any]) -> None:
        super().__init__(execute_values)
        self.user = user

    async def rollback(self) -> None:
        await super().rollback()
        self.user.expired = True


def user_factory(user_id: int = 7) -> UserModel:
    return UserModel(
        id=user_id,
        name="User",
        email="user@example.com",
        password_hash="hash",
    )


def response_chunk_text(chunk: str | bytes | memoryview[int]) -> str:
    if isinstance(chunk, str):
        return chunk
    return bytes(chunk).decode()


@pytest.mark.asyncio
async def test_create_chat_uses_authenticated_user() -> None:
    session = FakeSession()

    response = await create_chat(
        ChatCreateRequest(),
        user_factory(),
        session,  # type: ignore[arg-type]
    )
    chat = response.data

    assert chat.id == 1
    assert chat.title == "Cuộc trò chuyện mới"
    assert session.added[0].user_id == 7


@pytest.mark.asyncio
async def test_get_active_chat_rejects_missing_or_unowned_chat() -> None:
    session = FakeSession([None])

    with pytest.raises(HTTPException) as exc_info:
        await _get_active_chat(session, 99, 7)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_load_agent_history_filters_owner_and_orders_messages() -> None:
    older = ChatHistoryModel(
        user_id=7,
        chat_session_id=10,
        role=ChatRole.USER,
        message="older",
        timestamp=datetime(2026, 6, 10, tzinfo=UTC),
    )
    newer = ChatHistoryModel(
        user_id=7,
        chat_session_id=10,
        role=ChatRole.ASSISTANT,
        message="newer",
        timestamp=datetime(2026, 6, 11, tzinfo=UTC),
    )
    session = FakeSession([[newer, older]])

    history = await _load_agent_history(
        session,  # type: ignore[arg-type]
        10,
        7,
    )

    assert [message.content for message in history] == ["older", "newer"]
    statement = session.statements[0]
    statement_text = str(statement)
    assert "chat_histories.user_id" in statement_text
    assert "chat_histories.chat_session_id" in statement_text
    assert "chat_histories.timestamp DESC" in statement_text
    assert statement._limit_clause.value > 0


@pytest.mark.asyncio
async def test_list_chats_searches_titles_and_message_content() -> None:
    session = FakeSession([[]])

    response = await list_chats(
        user_factory(),
        session,  # type: ignore[arg-type]
        search="lúa",
    )

    statement = str(session.statements[0])
    assert response.data == []
    assert response.meta.count == 0
    assert response.meta.has_more is False
    assert response.meta.next_cursor is None
    assert response.meta.limit == 20
    assert "chat_sessions.title" in statement
    assert "chat_histories.message" in statement
    assert "chat_histories.chat_session_id = chat_sessions.id" in statement


@pytest.mark.asyncio
async def test_list_chats_returns_stable_cursor_page() -> None:
    now = datetime.now(UTC)
    chats = [
        ChatSessionModel(
            id=3,
            user_id=7,
            title="Newest",
            updated_at=now,
        ),
        ChatSessionModel(
            id=2,
            user_id=7,
            title="Same timestamp",
            updated_at=now,
        ),
        ChatSessionModel(
            id=1,
            user_id=7,
            title="Older",
            updated_at=now - timedelta(microseconds=1),
        ),
    ]
    session = FakeSession([chats])

    response = await list_chats(
        user_factory(),
        session,  # type: ignore[arg-type]
        limit=2,
    )

    assert [chat.id for chat in response.data] == [3, 2]
    assert response.meta.count == 2
    assert response.meta.limit == 2
    assert response.meta.has_more is True
    assert response.meta.next_cursor is not None
    decoded = _decode_chat_cursor(response.meta.next_cursor, "")
    assert decoded.updated_at == now
    assert decoded.chat_id == 2
    statement = session.statements[0]
    assert statement._limit_clause.value == 3
    statement_text = str(statement)
    assert "chat_sessions.updated_at DESC, chat_sessions.id DESC" in statement_text


@pytest.mark.asyncio
async def test_list_chats_applies_cursor_tie_breaker() -> None:
    now = datetime.now(UTC)
    cursor = _encode_chat_cursor(
        ChatSessionPublic(
            id=8,
            title="Cursor",
            created_at=now,
            updated_at=now,
        ),
        "lúa",
    )
    session = FakeSession([[]])

    await list_chats(
        user_factory(),
        session,  # type: ignore[arg-type]
        search=" lúa ",
        cursor=cursor,
        limit=20,
    )

    statement_text = str(session.statements[0])
    assert "chat_sessions.updated_at <" in statement_text
    assert "chat_sessions.updated_at =" in statement_text
    assert "chat_sessions.id <" in statement_text


def test_chat_cursor_does_not_expose_search_text() -> None:
    now = datetime.now(UTC)
    sensitive_search = "confidential crop failure"
    cursor = _encode_chat_cursor(
        ChatSessionPublic(
            id=8,
            title="Cursor",
            created_at=now,
            updated_at=now,
        ),
        sensitive_search,
    )

    encoded_payload = cursor.split(".", maxsplit=1)[0]
    padding = "=" * (-len(encoded_payload) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded_payload + padding))

    assert payload["version"] == 2
    assert payload["search_digest"] != sensitive_search
    assert sensitive_search not in json.dumps(payload)
    assert _decode_chat_cursor(cursor, sensitive_search).chat_id == 8


@pytest.mark.asyncio
async def test_list_chats_rejects_invalid_or_mismatched_cursor() -> None:
    session = FakeSession()

    with pytest.raises(HTTPException) as invalid_exc:
        await list_chats(
            user_factory(),
            session,  # type: ignore[arg-type]
            cursor="not-a-cursor",
        )
    assert invalid_exc.value.status_code == 400

    now = datetime.now(UTC)
    cursor = _encode_chat_cursor(
        ChatSessionPublic(
            id=1,
            title="Cursor",
            created_at=now,
            updated_at=now,
        ),
        "rice",
    )
    with pytest.raises(HTTPException) as mismatch_exc:
        await list_chats(
            user_factory(),
            session,  # type: ignore[arg-type]
            search="lúa",
            cursor=cursor,
        )
    assert mismatch_exc.value.status_code == 400

    encoded_payload, encoded_signature = cursor.split(".", maxsplit=1)
    tampered_signature = (
        f"{'A' if encoded_signature[0] != 'A' else 'B'}{encoded_signature[1:]}"
    )
    tampered_cursor = f"{encoded_payload}.{tampered_signature}"
    with pytest.raises(HTTPException) as tampered_exc:
        await list_chats(
            user_factory(),
            session,  # type: ignore[arg-type]
            search="rice",
            cursor=tampered_cursor,
        )
    assert tampered_exc.value.status_code == 400
    assert session.statements == []


@pytest.mark.asyncio
async def test_create_chat_message_saves_question_and_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(
        id=10,
        user_id=7,
        title="Cuộc trò chuyện mới",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = FakeSession([chat, [], chat])

    async def fake_run_agent(
        question: str,
        user_id: int,
        *,
        history: list[Any],
    ) -> str:
        assert question == "Phân tích nhiệt độ và độ ẩm"
        assert user_id == 7
        assert history == []
        return "Nhiệt độ trung bình 30°C, độ ẩm trung bình 70%."

    monkeypatch.setattr("api.routes.agent_routes.run_agent", fake_run_agent)

    envelope = await create_chat_message(
        10,
        AskRequest(question="  Phân tích nhiệt độ và độ ẩm  "),
        user_factory(),
        session,  # type: ignore[arg-type]
    )
    response = envelope.data

    assert response.chat.title == "Phân tích nhiệt độ và độ ẩm"
    assert response.user_message.role == ChatRole.USER
    assert response.user_message.message == "Phân tích nhiệt độ và độ ẩm"
    assert response.assistant_message.role == ChatRole.ASSISTANT
    assert (
        response.assistant_message.message
        == "Nhiệt độ trung bình 30°C, độ ẩm trung bình 70%."
    )
    assert "FOR UPDATE" in str(session.statements[2])
    assert session.statements[2].get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_create_chat_message_does_not_persist_partial_history_on_agent_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Cuộc trò chuyện mới")
    session = FakeSession([chat])

    async def failing_run_agent(question: str, user_id: int) -> str:
        raise RuntimeError("agent unavailable")

    monkeypatch.setattr("api.routes.agent_routes.run_agent", failing_run_agent)

    with pytest.raises(HTTPException) as exc_info:
        await create_chat_message(
            10,
            AskRequest(question="Xin tư vấn"),
            user_factory(),
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 500
    assert session.added == []


@pytest.mark.asyncio
async def test_stream_chat_message_emits_tokens_and_persists_done_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Cuộc trò chuyện mới")
    current_user = ExpiringUser(7)
    session = ExpiringSession(current_user, [chat, [], chat])

    async def fake_stream_agent(
        question: str,
        user_id: int,
        *,
        history: list[Any],
    ) -> Any:
        assert question == "Tư vấn lúa"
        assert user_id == 7
        assert history == []
        yield {
            "event": "status",
            "phase": "routing",
            "message": "Đang phân tích yêu cầu...",
        }
        yield {"event": "token", "content": "Xin "}
        yield {"event": "token", "content": "chào"}

    monkeypatch.setattr(
        "api.routes.agent_routes.stream_agent",
        fake_stream_agent,
    )

    response = await stream_chat_message(
        10,
        AskRequest(question="Tư vấn lúa"),
        current_user,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
    chunks = [response_chunk_text(chunk) async for chunk in response.body_iterator]
    body = "".join(chunks)

    assert (
        'event: status\ndata: {"data": {"phase": "routing", '
        '"message": "Đang phân tích yêu cầu..."}}'
    ) in body
    assert 'event: token\ndata: {"data": {"content": "Xin "}}' in body
    assert 'event: token\ndata: {"data": {"content": "chào"}}' in body
    assert "event: done" in body
    assert '"data": {"chat":' in body
    assert '"message": "Xin chào"' in body
    assert session.rollback_count == 1
    assert session.committed is True
    assert "FOR UPDATE" in str(session.statements[2])
    assert session.statements[2].get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_stream_chat_message_rolls_back_and_emits_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Cuộc trò chuyện mới")
    session = FakeSession([chat])

    async def failing_stream_agent(
        question: str,
        user_id: int,
        *,
        history: list[Any],
    ) -> Any:
        if False:
            yield ""
        raise RuntimeError("stream unavailable")

    monkeypatch.setattr(
        "api.routes.agent_routes.stream_agent",
        failing_stream_agent,
    )

    response = await stream_chat_message(
        10,
        AskRequest(question="Tư vấn lúa"),
        user_factory(),
        session,  # type: ignore[arg-type]
    )
    chunks = [response_chunk_text(chunk) async for chunk in response.body_iterator]
    body = "".join(chunks)

    assert "event: error" in body
    assert '"error": "stream_error"' in body
    assert '"message": "Không thể hoàn tất phản hồi lúc này."' in body
    assert "stream unavailable" not in body
    assert session.rollback_count == 2
    assert session.added == []


@pytest.mark.asyncio
async def test_delete_chat_soft_deletes_chat() -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Chat")
    session = FakeSession([chat])

    response = await delete_chat(
        10,
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert response.status_code == 204
    assert chat.deleted_at is not None


def test_title_from_question_is_normalized_and_limited() -> None:
    assert _title_from_question("  Lịch   gieo trồng  ") == "Lịch gieo trồng"
    assert len(_title_from_question("a" * 100)) == 60
    assert _title_from_question("a" * 100).endswith("...")
