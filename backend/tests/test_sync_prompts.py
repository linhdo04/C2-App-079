from typing import Any

from langsmith.utils import LangSmithConflictError

from scripts import sync_prompts as subject


def test_load_local_prompt_specs_includes_intent_router() -> None:
    prompt_specs = subject.load_local_prompt_specs(prefix="local_")

    identifiers = [prompt_spec.identifier for prompt_spec in prompt_specs]

    assert "local_intent_router_prompt" in identifiers
    assert "local_search_filter_prompt" in identifiers


def test_sync_prompts_continues_when_prompt_is_unchanged(
    monkeypatch: Any,
) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.identifiers: list[str] = []

        def push_prompt(
            self,
            prompt_identifier: str,
            *,
            object: object | None = None,
            parent_commit_hash: str = "latest",
            is_public: bool | None = None,
            description: str | None = None,
            readme: str | None = None,
            tags: list[str] | None = None,
            commit_tags: str | list[str] | None = None,
            commit_description: str | None = None,
        ) -> str:
            self.identifiers.append(prompt_identifier)
            if prompt_identifier == "local_system_prompt":
                raise LangSmithConflictError("Nothing to commit")
            return f"https://example.test/{prompt_identifier}"

    monkeypatch.setattr(subject, "build_prompt_object", lambda content: content)

    prompt_specs = [
        subject.PromptSpec(
            identifier="local_system_prompt",
            content="system",
            description="System prompt.",
        ),
        subject.PromptSpec(
            identifier="local_react_prompt",
            content="react",
            description="ReAct prompt.",
        ),
    ]
    options = subject.SyncOptions(
        environment="local",
        prefix="local_",
        tags=["agent", "local"],
        commit_tag="local",
        is_public=False,
        dry_run=False,
    )
    client = FakeClient()

    results = subject.sync_prompts(
        client=client,
        prompt_specs=prompt_specs,
        options=options,
    )

    assert client.identifiers == ["local_system_prompt", "local_react_prompt"]
    assert results == [
        subject.SyncResult(identifier="local_system_prompt", status="unchanged"),
        subject.SyncResult(
            identifier="local_react_prompt",
            status="pushed",
            url="https://example.test/local_react_prompt",
        ),
    ]
