from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from api.routes.agent_routes import (
    AskRequest,
    ChatCreateRequest,
    _get_active_chat,
    _title_from_question,
    create_chat,
    create_chat_message,
    delete_chat,
    list_chats,
    stream_chat_message,
)
from models.chat_history import ChatRole
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
        self.rolled_back = False
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
        self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True


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

    chat = await create_chat(
        ChatCreateRequest(),
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert chat.id == 1
    assert chat.user_id == 7
    assert chat.title == "Cuộc trò chuyện mới"


@pytest.mark.asyncio
async def test_get_active_chat_rejects_missing_or_unowned_chat() -> None:
    session = FakeSession([None])

    with pytest.raises(HTTPException) as exc_info:
        await _get_active_chat(session, 99, 7)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_chats_searches_titles_and_message_content() -> None:
    session = FakeSession([[]])

    chats = await list_chats(
        user_factory(),
        session,  # type: ignore[arg-type]
        search="lúa",
    )

    statement = str(session.statements[0])
    assert chats == []
    assert "chat_sessions.title" in statement
    assert "chat_histories.message" in statement
    assert "chat_histories.chat_session_id = chat_sessions.id" in statement


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
    session = FakeSession([chat, chat])

    async def fake_run_agent(question: str) -> str:
        assert question == "Dự báo thời tiết Hà Nội"
        return "Trời có mưa nhẹ."

    monkeypatch.setattr("api.routes.agent_routes.run_agent", fake_run_agent)

    response = await create_chat_message(
        10,
        AskRequest(question="  Dự báo thời tiết Hà Nội  "),
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert response.chat.title == "Dự báo thời tiết Hà Nội"
    assert response.user_message.role == ChatRole.USER
    assert response.user_message.message == "Dự báo thời tiết Hà Nội"
    assert response.assistant_message.role == ChatRole.ASSISTANT
    assert response.assistant_message.message == "Trời có mưa nhẹ."
    assert "FOR UPDATE" in str(session.statements[1])
    assert session.statements[1].get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_create_chat_message_does_not_persist_partial_history_on_agent_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Cuộc trò chuyện mới")
    session = FakeSession([chat])

    async def failing_run_agent(question: str) -> str:
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
    session = FakeSession([chat, chat])

    async def fake_stream_agent(question: str) -> Any:
        assert question == "Tư vấn lúa"
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
        user_factory(),
        session,  # type: ignore[arg-type]
    )
    chunks = [response_chunk_text(chunk) async for chunk in response.body_iterator]
    body = "".join(chunks)

    assert (
        'event: status\ndata: {"phase": "routing", '
        '"message": "Đang phân tích yêu cầu..."}'
    ) in body
    assert 'event: token\ndata: {"content": "Xin "}' in body
    assert 'event: token\ndata: {"content": "chào"}' in body
    assert "event: done" in body
    assert '"message": "Xin chào"' in body
    assert session.rolled_back is False
    assert session.committed is True


@pytest.mark.asyncio
async def test_stream_chat_message_rolls_back_and_emits_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = ChatSessionModel(id=10, user_id=7, title="Cuộc trò chuyện mới")
    session = FakeSession([chat])

    async def failing_stream_agent(question: str) -> Any:
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
    assert "stream unavailable" in body
    assert session.rolled_back is True
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
