# Agent Architecture

## Overview

AI Agent cho hệ thống C2-App-079 được xây dựng để hỗ trợ nông nghiệp Việt Nam thông qua việc tích hợp LangChain, LangGraph, và Google Gemini LLM.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     User Interface                       │
│                  (HTTP POST /agent/ask)                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Endpoint                        │
│              (agent_routes.py: /agent/ask)               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   Agent Layer                            │
│              (agent.py: run_agent)                       │
│                                                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │         LangGraph StateGraph                       │  │
│  │                                                     │  │
│  │  Entry ──▶ Database Node ──▶ END                  │  │
│  │              │                                      │  │
│  │              ├──▶ Search Node (optional)           │  │
│  │              ├──▶ Weather Node (optional)          │  │
│  │              └──▶ Analysis Node (optional)         │  │
│  └───────────────────────────────────────────────────┘  │
│                                                           │
│              Google Gemini 2.0 Flash LLM                 │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│   Tools Layer    │   │  External APIs   │
└──────────────────┘   └──────────────────┘
         │                       │
    ┌────┼────┬─────┬──────┐   │
    ▼    ▼    ▼     ▼      ▼   ▼
┌─────┬─────┬─────┬─────┬─────┬─────┐
│ DB  │Web  │Wea- │Ana- │Tavi-│Open-│
│Query│Srch │ther │lysis│ ly  │Meteo│
└─────┴─────┴─────┴─────┴─────┴─────┘
```

## Core Components

### 1. Agent Core (`agent.py`)

**Purpose**: Main entry point cho agent execution

**Key Functions**:
```python
async def run_agent(question: str) -> str
```

**Responsibilities**:
- Khởi tạo agent state từ user question
- Invoke LangGraph workflow
- Trả về câu trả lời cuối cùng
- Error handling và logging

**Flow**:
1. Nhận question từ API endpoint
2. Tạo initial state: `{"messages": [HumanMessage(content=question)]}`
3. Gọi `graph.ainvoke(initial_state)`
4. Extract câu trả lời từ messages[-1].content
5. Return answer string

### 2. LangGraph Workflow (`graph.py`)

**Purpose**: Định nghĩa workflow và routing logic

**Components**:
```python
def create_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("search", web_search_node)
    workflow.add_node("database", query_crop_database_node)
    workflow.add_node("weather", get_weather_forecast_node)
    
    # Define edges
    workflow.set_entry_point("database")
    workflow.add_edge("database", END)
    
    return workflow.compile()
```

**Current Workflow**:
- Entry point: `database` node
- Simple linear flow: User Question → Database Query → END
- Future: Conditional routing dựa trên intent classification

### 3. State Management (`state.py`)

**Purpose**: Define agent state structure

```python
class AgentState(TypedDict):
    messages: Annotated[list[dict[str, Any]], add_messages]
```

**State Evolution**:
1. Initial: `[HumanMessage("user question")]`
2. After tool: `[HumanMessage(...), ToolMessage("tool result")]`
3. Final: Messages list với tất cả conversation history

### 4. Agent Nodes (`nodes.py`)

**Purpose**: Wrappers cho tools để tích hợp vào graph

**Pattern**:
```python
async def tool_node(state: AgentState) -> AgentState:
    # 1. Extract query from state
    messages = state["messages"]
    query = messages[-1].content
    
    # 2. Invoke tool
    result = await tool.ainvoke({"query": query})
    
    # 3. Return updated state
    return {"messages": [ToolMessage(content=result, tool_call_id="tool_id")]}
```

**Available Nodes**:
- `web_search_node`: Web search tool wrapper
- `query_crop_database_node`: Database tool wrapper
- `get_weather_forecast_node`: Weather tool wrapper

### 5. Tools Layer (`tools/`)

Chi tiết về các tools:

#### Database Tool (`database.py`)
```python
@tool
async def query_crop_database(query: str) -> str
```

**Capabilities**:
- Query Postgres database
- Handle user, crop, mission data
- Natural language to SQL (future)

**Current Implementation**:
- Simple keyword matching
- Returns user list if query contains "user"
- Fallback: "Chưa có dữ liệu"

#### Web Search Tool (`search.py`)
```python
@tool
def web_search(query: str) -> str
```

**Capabilities**:
- Search agricultural information
- Price data, techniques, diseases
- Powered by Tavily API

**Returns**:
- Top 5 search results
- Format: "- Title: Content"

#### Weather Tool (`weather.py`)
```python
@tool
async def get_weather_forecast(location: str, days: int = 7) -> str
```

**Capabilities**:
- Forecast for agricultural regions
- Temperature min/max, precipitation
- Up to 7 days forecast

**Implementation**:
1. Geocoding (location → lat/lon)
2. Fetch forecast from Open-Meteo
3. Format results for Vietnamese users

#### Analysis Tool (`analysis.py`)
```python
async def analyze_crop_data(data: dict[str, Any]) -> str
```

**Capabilities**:
- Analyze crop yield data
- Calculate production estimates
- Provide recommendations

**Input Data**:
- `crop_name`: Tên cây trồng
- `area`: Diện tích (ha)
- `yield_per_ha`: Năng suất (tấn/ha)
- `season`: Vụ mùa

### 6. Prompts (`prompts.py`)

**Purpose**: System prompt định hướng agent behavior

**Key Characteristics**:
- Domain: Nông nghiệp Việt Nam
- Tone: Chuyên nghiệp, thực tế
- Priorities: Internal data first, then external
- Output: Practical recommendations

## Data Flow

### Request Flow

```
User Question
    │
    ├─▶ FastAPI Route (/agent/ask)
    │       │
    │       └─▶ run_agent(question)
    │               │
    │               ├─▶ Create initial state
    │               │       messages: [HumanMessage(question)]
    │               │
    │               ├─▶ graph.ainvoke(state)
    │               │       │
    │               │       ├─▶ Entry: database node
    │               │       │       │
    │               │       │       ├─▶ Extract query from message
    │               │       │       ├─▶ query_crop_database.ainvoke(query)
    │               │       │       │       │
    │               │       │       │       └─▶ Postgres query
    │               │       │       │
    │               │       │       └─▶ Return ToolMessage(result)
    │               │       │
    │               │       └─▶ END
    │               │
    │               └─▶ Extract answer from messages[-1]
    │
    └─▶ Response: {"answer": "..."}
```

### State Evolution Example

**Initial State**:
```python
{
    "messages": [
        HumanMessage(content="Cho tôi thông tin về lúa nước")
    ]
}
```

**After Database Node**:
```python
{
    "messages": [
        HumanMessage(content="Cho tôi thông tin về lúa nước"),
        ToolMessage(content="Chưa có dữ liệu mùa vụ", tool_call_id="database")
    ]
}
```

## Configuration

### Environment Variables

```bash
# LLM
GEMINI_API_KEY=your_gemini_key

# Tools
TAVILY_API_KEY=your_tavily_key

# Database
DATABASE_URL=postgresql+asyncpg://...
```

### Model Configuration

```python
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    api_key=settings.gemini_api_key
)
```

## Integration Points

### 1. FastAPI Integration

```python
# src/api/routes/agent_routes.py
@router.post("/agent/ask")
async def ask(req: AskRequest) -> dict[str, Any]:
    result = await run_agent(req.question)
    return {"answer": result}
```

### 2. Database Integration

```python
# Tools connect to SQLModel/Postgres
async with db_session() as session:
    result = await session.execute(select(UserModel))
```

### 3. External API Integration

- **Tavily**: Web search API
- **Open-Meteo**: Weather forecast API
- **Google Gemini**: LLM API

## Design Decisions

### Why LangGraph?

**Pros**:
- Explicit workflow definition
- Easy to debug and visualize
- Support for complex routing logic
- State management built-in

**Cons**:
- More boilerplate than simple chains
- Steeper learning curve

**Decision**: LangGraph cho phép scale agent với complex workflows trong tương lai.

### Why Google Gemini?

**Pros**:
- Fast inference (gemini-2.0-flash)
- Good multilingual support (Vietnamese)
- Competitive pricing
- Function calling support

**Alternatives Considered**:
- OpenAI GPT-4: More expensive, similar quality
- Claude: Good but less Vietnamese support
- Open-source LLMs: Require hosting infrastructure

### Tool Design Pattern

**Pattern**: LangChain @tool decorator

**Benefits**:
- Auto schema generation
- Async support
- Error handling
- Easy testing

**Example**:
```python
@tool
async def my_tool(param: str) -> str:
    """Tool description for LLM."""
    result = await some_async_operation(param)
    return result
```

## Testing Strategy

### Unit Tests

```python
# Test individual tools
async def test_query_database():
    result = await query_crop_database.ainvoke({"query": "users"})
    assert "người dùng" in result.lower()
```

### Integration Tests

```python
# Test agent end-to-end
async def test_agent_run():
    answer = await run_agent("test question")
    assert isinstance(answer, str)
    assert len(answer) > 0
```

### Manual Testing

```bash
# Via test script
python test_agent.py

# Via API
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

## Performance Considerations

### Latency Sources

1. **LLM API Call**: 1-2 seconds
2. **Tool Execution**: 0.1-1 second
3. **Network I/O**: 0.1-0.5 seconds

**Total**: ~2-4 seconds per request

### Optimization Strategies

1. **Caching**:
   - Cache common queries
   - Cache tool results (with TTL)
   
2. **Async Execution**:
   - All tools async where possible
   - Parallel tool execution (future)

3. **Prompt Optimization**:
   - Minimize system prompt length
   - Clear, concise instructions

### Scalability

**Current Capacity**:
- Sequential request handling
- No queueing mechanism

**Future Improvements**:
- Request queue with Celery
- Response streaming
- Multi-agent parallelization

## Error Handling

### Error Categories

1. **Tool Errors**:
   - Database connection failures
   - API timeouts
   - Invalid parameters

2. **LLM Errors**:
   - API key issues
   - Rate limiting
   - Invalid responses

3. **Graph Errors**:
   - State corruption
   - Node failures
   - Routing errors

### Handling Strategy

```python
try:
    result = await graph.ainvoke(state)
except ToolError as e:
    logger.error(f"Tool failed: {e}")
    return "Xin lỗi, công cụ tạm thời không khả dụng"
except LLMError as e:
    logger.error(f"LLM failed: {e}")
    return "Xin lỗi, tôi không thể xử lý câu hỏi lúc này"
except Exception as e:
    logger.exception("Unexpected error")
    raise HTTPException(500, detail=str(e))
```

## Future Enhancements

### Short-term (1-2 months)

1. **Conditional Routing**:
   - Intent classification
   - Dynamic tool selection
   - Multi-tool orchestration

2. **Conversation Memory**:
   - Store chat history
   - Context-aware responses
   - Multi-turn dialogues

3. **More Tools**:
   - Soil data tool
   - Crop recommendation tool
   - Price prediction tool

### Medium-term (3-6 months)

1. **RAG Integration**:
   - Vector database (Pinecone/Weaviate)
   - Document embeddings
   - Semantic search

2. **Streaming Responses**:
   - Real-time output
   - Better UX
   - Token-by-token generation

3. **Multi-language Support**:
   - English interface
   - Auto language detection

### Long-term (6+ months)

1. **Multi-agent System**:
   - Specialized agents per domain
   - Agent collaboration
   - Hierarchical planning

2. **Fine-tuned Models**:
   - Domain-specific LLM
   - Custom embeddings
   - Local deployment option

3. **Advanced Analytics**:
   - Agent performance metrics
   - Tool usage analytics
   - User feedback loop

## References

- [LangChain Documentation](https://python.langchain.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Google Gemini API](https://ai.google.dev/)
- [Tavily API](https://tavily.com/)
- [Open-Meteo API](https://open-meteo.com/)

## Changelog

- **2026-06-07**: Initial architecture with LangGraph, 4 tools, basic workflow
- **Future**: TBD based on requirements
