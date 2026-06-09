from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.agent import graph as _graph
from agent.agent import run_agent

# `graph` is a runtime object from the agent library; mypy's static type
# inference does not expose the `run` method. Cast to `Any` to silence type
# checker while preserving runtime behavior.
graph: Any = cast(Any, _graph)

router = APIRouter()


class AskRequest(BaseModel):
    question: str


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
