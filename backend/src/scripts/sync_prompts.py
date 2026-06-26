"""Sync local agent prompts to LangSmith Prompt Hub.

Usage:
    uv run python src/scripts/sync_prompts.py --dry-run
    uv run python src/scripts/sync_prompts.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Protocol

from langsmith import Client

from core.config import settings


@dataclass(frozen=True)
class PromptSpec:
    identifier: str
    content: str
    description: str


@dataclass(frozen=True)
class SyncOptions:
    environment: str
    prefix: str
    tags: list[str]
    commit_tag: str
    is_public: bool
    dry_run: bool


@dataclass(frozen=True)
class SyncResult:
    identifier: str
    status: str
    url: str | None = None


class PromptHubClient(Protocol):
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
    ) -> str: ...


def build_prompt_object(content: str) -> object:
    """Build a LangChain prompt object before pushing to LangSmith Prompt Hub.

    Using `mustache` avoids accidental f-string variable parsing when the prompt
    contains JSON-like text with `{}`.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.prompts.chat import SystemMessagePromptTemplate

    system_message = SystemMessagePromptTemplate.from_template(
        content,
        template_format="mustache",
    )

    return ChatPromptTemplate.from_messages([system_message])


def load_local_prompt_specs(*, prefix: str) -> list[PromptSpec]:
    """Load prompt constants from local source code.

    Important:
    - This function should import local prompt constants only.
    - Avoid pulling prompts from LangSmith inside `agent.prompts`.
    """
    from agent import prompt_defaults as prompts

    return [
        PromptSpec(
            identifier=f"{prefix}system_prompt",
            content=prompts.DEFAULT_SYSTEM_PROMPT,
            description="Final answer synthesis prompt for the agent.",
        ),
        PromptSpec(
            identifier=f"{prefix}react_prompt",
            content=prompts.DEFAULT_REACT_PROMPT,
            description="ReAct planner prompt for the agent loop.",
        ),
        PromptSpec(
            identifier=f"{prefix}tool_policy_prompt",
            content=prompts.DEFAULT_TOOL_POLICY_PROMPT,
            description="Semantic tool policy classifier prompt.",
        ),
    ]


def validate_prompt_specs(prompt_specs: list[PromptSpec]) -> None:
    if not prompt_specs:
        raise ValueError("No prompts found to sync.")

    seen: set[str] = set()

    for prompt_spec in prompt_specs:
        if not prompt_spec.identifier.strip():
            raise ValueError("Prompt identifier cannot be empty.")

        if prompt_spec.identifier in seen:
            raise ValueError(f"Duplicate prompt identifier: {prompt_spec.identifier}")

        if not prompt_spec.content.strip():
            raise ValueError(f"Prompt content is empty: {prompt_spec.identifier}")

        seen.add(prompt_spec.identifier)


def sync_prompts(
    client: PromptHubClient,
    prompt_specs: list[PromptSpec],
    options: SyncOptions,
) -> list[SyncResult]:
    validate_prompt_specs(prompt_specs)

    results: list[SyncResult] = []

    for prompt_spec in prompt_specs:
        if options.dry_run:
            results.append(
                SyncResult(
                    identifier=prompt_spec.identifier,
                    status="dry-run",
                    url=None,
                )
            )
            continue

        prompt_object = build_prompt_object(prompt_spec.content)

        url = client.push_prompt(
            prompt_spec.identifier,
            object=prompt_object,
            parent_commit_hash="latest",
            is_public=options.is_public,
            description=prompt_spec.description,
            tags=options.tags,
            commit_tags=options.commit_tag,
            commit_description=(
                f"Sync local {options.environment} agent prompt defaults."
            ),
        )

        results.append(
            SyncResult(
                identifier=prompt_spec.identifier,
                status="pushed",
                url=url,
            )
        )

    return results


def create_langsmith_client() -> PromptHubClient:
    if not settings.langsmith_api_key:
        raise SystemExit("LANGSMITH_API_KEY is required to sync prompts.")

    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
    )


def parse_args() -> SyncOptions:
    parser = argparse.ArgumentParser(
        description="Sync local agent prompts to LangSmith Prompt Hub.",
    )

    parser.add_argument(
        "--tag",
        action="append",
        default=None,
        help="Prompt tag. Can be passed multiple times.",
    )

    parser.add_argument(
        "--public",
        action="store_true",
        help="Make prompts public. Defaults to private.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompt identifiers without pushing to LangSmith.",
    )

    args = parser.parse_args()

    environment = settings.app_env
    prefix = f"{environment}_"

    tags = args.tag or ["agent", environment]
    commit_tag = environment

    return SyncOptions(
        environment=environment,
        prefix=prefix,
        tags=tags,
        commit_tag=commit_tag,
        is_public=args.public,
        dry_run=args.dry_run,
    )


def print_results(results: list[SyncResult]) -> None:
    for result in results:
        if result.url:
            print(f"{result.identifier}: {result.status} -> {result.url}")
        else:
            print(f"{result.identifier}: {result.status}")


def main() -> None:
    options = parse_args()
    prompt_specs = load_local_prompt_specs(prefix=options.prefix)

    client: PromptHubClient
    if options.dry_run:
        client = DryRunPromptHubClient()
    else:
        client = create_langsmith_client()

    results = sync_prompts(
        client=client,
        prompt_specs=prompt_specs,
        options=options,
    )

    print_results(results)


class DryRunPromptHubClient:
    def push_prompt(self, *args: object, **kwargs: object) -> str:
        return "dry-run"


if __name__ == "__main__":
    main()
