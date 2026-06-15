# 5.6 Streaming Response

AI agents thường mất nhiều giây để sinh câu trả lời. Streaming response (phản hồi luồng) giúp người dùng thấy câu trả lời từng phần ngay khi LLM sinh ra, thay vì chờ đến khi hoàn thành.

## SSE (Server-Sent Events) Pattern

SSE là chuẩn web cho server push data đến client. FastAPI hỗ trợ SSE qua StreamingResponse:

```python
from fastapi.responses import StreamingResponse
import asyncio
import json

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream response từ agent."""

    async def event_generator():
        """Generator tạo SSE events."""
        try:
            # Gửi status bắt đầu
            yield f"data: {json.dumps({'type': 'start'})}\n\n"

            # Stream từ agent
            async for chunk in agent.astream(request.message):
                event = {
                    "type": "token",
                    "content": chunk,
                }
                yield f"data: {json.dumps(event)}\n\n"

            # Gửi status kết thúc
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            error_event = {
                "type": "error",
                "message": "Lỗi khi xử lý. Vui lòng thử lại.",
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx: disable buffering
        },
    )
```

## Async Generators với LangGraph

LangGraph hỗ trợ streaming qua `astream` và `astream_events`:

```python
from langchain_core.messages import HumanMessage

@app.post("/api/v1/agent/stream")
async def agent_stream(request: ChatRequest):
    """Stream response từ LangGraph agent."""

    async def stream_generator():
        """Stream tokens từ LangGraph agent."""
        config = {
            "configurable": {
                "thread_id": request.conversation_id or "default",
            }
        }

        inputs = {
            "messages": [HumanMessage(content=request.message)]
        }

        async for event in agent.astream_events(inputs, config, version="v2"):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                # Token mới từ LLM
                token = event["data"]["chunk"].content
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            elif kind == "on_tool_start":
                # Agent bắt đầu gọi tool
                tool_name = event.get("name", "unknown")
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"

            elif kind == "on_tool_end":
                # Tool hoàn thành
                tool_name = event.get("name", "unknown")
                output = str(event["data"].get("output", ""))[:200]
                yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name, 'preview': output})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
    )
```

> 🔑 ĐIỂM CHÍNH: Streaming là "must-have" cho AI chat applications. Người dùng không muốn nhìn vào màn hình trống trong 10-30 giây. SSE là chuẩn đơn giản nhất — client chỉ cần EventSource hoặc fetch với ReadableStream.
