"""Structured-output helpers for chat model integrations."""

from typing import Any, TypeVar, cast

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def bind_structured_output(llm: Any, schema: type[SchemaT]) -> Any:
    """Bind a chat model to emit output matching a Pydantic schema.

    Prefer LangChain's provider-neutral structured output API used by
    langchain-deepseek, forcing JSON mode so DeepSeek does not receive
    function/tool-calling schemas for internal classifier/router prompts. Fall
    back to the legacy provider `bind` kwargs so older tests/fakes and
    compatible providers keep working.
    """
    with_structured_output = getattr(llm, "with_structured_output", None)
    if callable(with_structured_output):
        return with_structured_output(schema, method="json_mode")
    return cast(Any, llm).bind(
        response_mime_type="application/json",
        response_schema=schema.model_json_schema(),
    )
