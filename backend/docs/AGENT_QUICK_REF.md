# AI Agent Quick Reference

## API Endpoint

```bash
POST /agent/ask
Content-Type: application/json

{
  "question": "string"
}
```

## Tools Available

| Tool | Function | Type | Description |
|------|----------|------|-------------|
| Database | `query_crop_database` | async | Query Postgres cho user/crop data |
| Web Search | `web_search` | sync | Tìm kiếm qua Tavily API |
| Weather | `get_weather_forecast` | async | Dự báo thời tiết Open-Meteo |
| Analysis | `analyze_crop_data` | async | Phân tích dữ liệu canh tác |

## Quick Commands

```bash
# Start server
make run

# Test agent
python test_agent.py

# Lint code
ruff check src/agent/

# Type check
mypy src/agent/

# Test API
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

## Environment Variables

```bash
GEMINI_API_KEY=<required>
TAVILY_API_KEY=<required>
DATABASE_URL=<required>
```

## File Structure

```
src/agent/
├── agent.py       # run_agent(question: str) -> str
├── graph.py       # LangGraph workflow
├── nodes.py       # Tool wrappers
├── state.py       # AgentState TypedDict
├── prompts.py     # System prompt
└── tools/
    ├── database.py
    ├── search.py
    ├── weather.py
    └── analysis.py
```

## Code Examples

### Run Agent
```python
from agent import run_agent

answer = await run_agent("Dự báo thời tiết Hà Nội")
```

### Use Tools Directly
```python
from agent.tools import query_crop_database, web_search

# Async tool
result = await query_crop_database.ainvoke({"query": "users"})

# Sync tool
result = web_search.invoke({"query": "giá lúa"})
```

### Add New Tool
```python
# 1. Create tool in src/agent/tools/my_tool.py
from langchain_core.tools import tool

@tool
async def my_tool(param: str) -> str:
    """Tool description."""
    return f"Result: {param}"

# 2. Export in src/agent/tools/__init__.py
from .my_tool import my_tool
__all__ = [..., "my_tool"]

# 3. Create node in src/agent/nodes.py
async def my_tool_node(state: AgentState) -> AgentState:
    query = state["messages"][-1].content
    result = await my_tool.ainvoke({"param": query})
    return {"messages": [ToolMessage(content=result, tool_call_id="my_tool")]}

# 4. Add to graph in src/agent/graph.py
workflow.add_node("my_tool", my_tool_node)
```

## Documentation Links

- API Docs: [`docs/api/agent.md`](api/agent.md)
- Architecture: [`docs/architecture/agent-architecture.md`](architecture/agent-architecture.md)
- Build Summary: [`docs/BUILD_SUMMARY.md`](BUILD_SUMMARY.md)

## Common Issues

### Issue: "StructuredTool object is not callable"
**Solution**: Use `.invoke()` or `.ainvoke()` instead of calling directly

### Issue: Type errors with messages
**Solution**: Use `BaseMessage` from `langchain_core.messages`

### Issue: Graph has no attribute 'run'
**Solution**: Use `.invoke()` or `.ainvoke()` on compiled graph

### Issue: Line too long
**Solution**: Ruff max line length is 88 chars

## Performance

- **Average Response Time**: 2-4 seconds
- **LLM Call**: ~1-2s
- **Tool Execution**: ~0.1-1s
- **Network I/O**: ~0.1-0.5s

## Next Steps

1. Read [API docs](api/agent.md) for detailed endpoint info
2. Read [Architecture docs](architecture/agent-architecture.md) for system design
3. Test with `test_agent.py`
4. Add custom tools as needed
5. Implement conditional routing for multi-tool workflows
