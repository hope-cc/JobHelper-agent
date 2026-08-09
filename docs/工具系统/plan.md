# 工具系统 Plan

## 架构概览

在现有单节点图上新增 `tool_node` 和条件路由，形成 ReAct 循环。新增 `src/tools/` 下的工具注册与装饰器模块。API 层改为通过图来执行对话（而非直接调 `client.stream()`），利用 LangGraph 的流式事件机制将工具调用过程实时推向前端。

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph                             │
│                                                          │
│   entry ──→ chat_node ──→ [有工具调用?]                  │
│                ↑              │ YES                       │
│                │              ↓                           │
│                └────── tool_node ←─────────────────────┘ │
│                           │ NO → END                      │
└─────────────────────────────────────────────────────────┘
```

| 组件 | 位置 | 职责 |
|------|------|------|
| Tool 装饰器 + 类型 | `src/tools/decorator.py` `types.py` | `@tool` 装饰器、Pydantic 参数提取、ToolEntry 数据结构 |
| 工具注册中心 | `src/tools/registry.py` | 单例，自动发现、注册、查找、执行工具 |
| 扩展 Message | `src/llm/types.py`（修改） | 新增 `tool` 角色和 `ToolCall` 数据结构 |
| LLM 客户端接口 | `src/llm/base.py`（修改） | `stream()` 接受可选 `tools` 参数 |
| Anthropic/OpenAI 适配器 | `src/llm/anthropic.py` `openai.py`（修改） | 将统一工具定义转为协议格式，传入 API |
| ReAct 图 | `src/chat/graph.py`（重写） | chat_node + tool_node + 条件路由 + 轮次限制 |
| SSE 适配器 | `src/api/sse.py`（修改） | 新增工具事件的 SSE 格式化 |
| API 路由 | `src/api/routes.py`（修改） | 改为通过图执行对话 |
| 前端 SSE 解析 | `frontend/src/api/sse.ts`（修改） | 新增工具事件类型处理 |
| 前端消息展示 | `frontend/src/components/`（修改） | 工具调用状态卡片 |

---

## 核心数据结构

### 工具侧

```python
# src/tools/types.py

@dataclass
class ToolEntry:
    """注册中心中的工具条目。"""
    name: str                          # 工具唯一名称，如 "search_jobs"
    description: str                   # 工具描述，传给 LLM
    parameters: dict                   # JSON Schema 格式的参数定义（从 Pydantic 模型自动提取）
    param_model: type[BaseModel]       # 参数 Pydantic 模型类，用于校验和实例化
    fn: Callable                       # 原始 async 函数
```

### LLM 消息侧

```python
# src/llm/types.py —— 扩展部分

@dataclass
class Message:
    """统一消息格式。"""
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None   # assistant 消息可能包含的工具调用
    tool_call_id: str | None = None            # tool 消息对应的 tool_call id

@dataclass
class ToolCall:
    """一次完整的工具调用。"""
    tool_id: str                        # LLM 返回的唯一 ID
    tool_name: str                      # 工具名
    arguments: dict                     # 解析后的 JSON 参数字典
```

### 图状态

```python
# src/chat/graph.py

class ChatState(TypedDict):
    """ReAct 对话图状态。"""
    messages: list[Message]             # 累积全量历史（含 tool_call / tool 消息）
    response: str                       # 本轮最终文本回复
    tool_calls: list[ToolCall]          # 本轮 LLM 产出的工具调用
    loop_count: int                     # 当前 ReAct 循环轮次
```

### LLM 客户端接口

```python
# src/llm/base.py —— 修改部分

class BaseLLMClient(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,  # 新增：工具定义列表
    ) -> AsyncIterator[StreamEvent]:
        ...
```

---

## 模块设计

### 模块 A：工具装饰器（`src/tools/decorator.py`）

**职责：** 提供 `@tool` 装饰器，封装 Pydantic 参数提取、函数包装、执行逻辑。

**对外接口：**
```python
def tool(*, name: str, description: str) -> Callable:
    """装饰器。将 async 函数包装为可被注册中心管理的工具。
    要求被装饰函数的第一个参数是 BaseModel 子类。"""
    ...

class ToolWrapper:
    """装饰后的工具对象。"""
    name: str
    description: str
    param_model: type[BaseModel]

    async def execute(self, arguments: dict) -> str:
        """接收已解析的 JSON 参数字典，校验后调用原函数。"""
```

**依赖：** Pydantic

### 模块 B：工具注册中心（`src/tools/registry.py`）

**职责：** 单例，自动扫描包，收集工具，提供注册、查找、执行能力。

**对外接口：**
```python
class ToolRegistry:
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """获取单例。"""
        ...

    def discover(self, package_path: str = "src.tools.builtin") -> None:
        """自动发现并注册工具。扫描指定包下的所有模块。"""

    def register(self, tool: ToolWrapper) -> None:
        """手动注册一个工具。重名时报错。"""

    def get_tool(self, name: str) -> ToolEntry | None:
        """按名称查找工具。"""

    def list_definitions(self) -> list[dict]:
        """返回所有工具的 LLM 兼容定义列表（name, description, input_schema）。"""

    async def execute(self, name: str, arguments: dict) -> str:
        """执行指定工具。工具不存在时返回错误信息字符串，不抛异常。"""
```

**依赖：** `ToolEntry`、`ToolWrapper`

### 模块 C：LLM 适配器改造（`src/llm/anthropic.py`、`src/llm/openai.py`）

**职责：** 将统一的工具定义列表转换为协议格式，传给 LLM API；保持现有流式 ToolCall 事件不变。

**关键改动：**
- `stream()` 签名新增 `tools: list[dict] | None = None`
- Anthropic: 将 `tools` 转为 Anthropic `tools` 参数格式，清理 `additionalProperties` 等字段
- Anthropic: 补全 tool_id 关联 —— delta 和 end 事件回填 block 的 tool_id
- OpenAI: 将 `tools` 转为 OpenAI `tools` 格式 `[{"type": "function", "function": {...}}]`

### 模块 D：ReAct 图（`src/chat/graph.py` 重写）

**职责：** 实现 ReAct 循环的 LangGraph 图，编排 chat → tool → chat 流程。

**节点：**
- `chat_node`: 调用 `client.stream()` 并传入工具定义，从流中收集所有 StreamEvent。通过 LangGraph `get_stream_writer` 实时透传事件给 API 层。在内存中按 tool_id 拼接 JSON 参数片段，end 后 `json.loads` 解析。输出更新后的 `messages`、`tool_calls`、`loop_count`。
- `tool_node`: 接收 `tool_calls`，逐个执行工具（`registry.execute()`），每次执行结果构造 `ToolResultEvent` 透传。将工具结果以 `tool` 角色消息追加到 `messages`。

**条件路由：**
- 有 `tool_calls` 且 `loop_count < MAX_TOOL_LOOPS(10)` → `tool_node`
- 无 `tool_calls` 或达到上限 → END
- `tool_node` → `chat_node`（固定边）

**对外接口：**
```python
def build_graph(client: BaseLLMClient, registry: ToolRegistry) -> StateGraph:
    """构建 ReAct 对话图。"""
    ...
```

### 模块 E：SSE 适配器（`src/api/sse.py`）

**职责：** 为所有 StreamEvent（含工具事件）生成 SSE 格式输出。

**事件类型映射：**

| 内部事件 | SSE event 名 | data 内容 |
|----------|-------------|-----------|
| `TextChunk` | `text` | `{delta}` |
| `ThinkingChunk` | `thinking` | `{delta}` |
| `ToolCallStartChunk` | `tool_start` | `{tool_id, tool_name}` |
| `ToolCallDeltaChunk` | `tool_delta` | `{tool_id, delta}` |
| `ToolCallEndChunk` | `tool_end` | `{tool_id}` |
| `ToolResultEvent` | `tool_result` | `{tool_id, content}` |

### 模块 F：API 路由改造（`src/api/routes.py`）

**职责：** 改造 `send_message` 端点，改为通过图执行对话。

**改动要点：**
- 不再直接调 `client.stream()`
- 改为构建图 → `graph.astream_events()` → 监听自定义事件 → 转为 SSE
- 路由模块接收注入的 `ToolRegistry`

### 模块 G：前端改造（`frontend/src/`）

**职责：** 解析新的工具 SSE 事件并展示。

**改动文件：**
- `api/sse.ts`: `SSECallbacks` 接口新增 `onToolStart`、`onToolDelta`、`onToolEnd`、`onToolResult` 回调；解析逻辑新增 `tool_start` 等事件类型
- `AppContext.tsx`: 状态新增当前消息的活跃工具调用映射
- `components/MessageBubble.tsx`: 助手消息中渲染 `ToolCallCard` 列表
- `components/ToolCallCard.tsx`: 新建，折叠卡片展示工具名、参数、执行状态（加载中 / 完成 / 错误）

---

## 文件组织

```
src/
├── tools/
│   ├── __init__.py          # 改为导出 ToolRegistry 和 tool 装饰器
│   ├── decorator.py         # 新建 — @tool 装饰器 + ToolWrapper
│   ├── types.py             # 新建 — ToolEntry
│   ├── registry.py          # 新建 — ToolRegistry 单例 + 自动发现
│   └── builtin/             # 新建目录 — 用户在此放置工具函数
│       └── __init__.py
├── llm/
│   ├── __init__.py          # 不变
│   ├── types.py             # 修改 — Message 扩展 role 和 tool_calls 字段
│   ├── base.py              # 修改 — stream() 签名新增 tools 参数
│   ├── factory.py           # 不变
│   ├── anthropic.py         # 修改 — 补全 tool_id + 转换 tools 定义
│   └── openai.py            # 修改 — 转换 tools 定义
├── chat/
│   ├── __init__.py          # 修改 — 导出 build_graph, ChatState
│   └── graph.py             # 重写 — chat_node + tool_node + 条件路由
├── api/
│   ├── __init__.py          # 不变
│   ├── main.py              # 修改 — 启动时初始化 ToolRegistry
│   ├── routes.py            # 修改 — 改为图驱动对话
│   ├── sse.py               # 修改 — 新增工具事件 SSE 格式化
│   └── storage.py           # 不变
frontend/
└── src/
    ├── api/
    │   └── sse.ts           # 修改 — 新增工具事件回调接口和解析逻辑
    ├── AppContext.tsx        # 修改 — 状态新增工具调用信息
    ├── types.ts              # 修改 — 新增工具事件类型
    └── components/
        ├── MessageBubble.tsx # 修改 — 新增 ToolCallCard 子组件
        └── ToolCallCard.tsx  # 新建 — 工具调用折叠卡片
```

---

## 模块交互

### 整体调用链

```
前端                    API 层                    LangGraph 图                 LLM 适配器
 │                       │                         │                            │
 │  POST /messages       │                         │                            │
 ├──────────────────────→│                         │                            │
 │                       │  graph.astream(state)   │                            │
 │                       ├────────────────────────→│                            │
 │                       │                         │  chat_node                 │
 │                       │                         │  client.stream(            │
 │                       │                         │    messages,               │
 │                       │                         │    tools=registry.defs)    │
 │                       │                         ├───────────────────────────→│
 │                       │                         │                            │
 │                       │                         │◄──── StreamEvent 流 ───────┤
 │                       │                         │                            │
 │                       │◄── writer(event) ───────┤                            │
 │                       │                         │  收集 tool_calls           │
 │  SSE: text            │                         │  拼接 JSON 参数            │
 │←──────────────────────│                         │                            │
 │                       │                         │  [有 tool_calls?]          │
 │                       │                         │  → tool_node               │
 │  SSE: tool_start      │                         │                            │
 │←──────────────────────│                         │  registry.execute()        │
 │  SSE: tool_delta      │                         │                            │
 │←──────────────────────│                         │                            │
 │  SSE: tool_end        │                         │                            │
 │←──────────────────────│                         │                            │
 │  SSE: tool_result     │                         │                            │
 │←──────────────────────│                         │                            │
 │                       │                         │  → chat_node (再次)        │
 │                       │                         │  → 无 tool_calls → END     │
 │  SSE: text (最终回复)  │                         │                            │
 │←──────────────────────│                         │                            │
 │  SSE: done            │                         │                            │
 │←──────────────────────│                         │                            │
```

### 流式输出策略

图的 `chat_node` 内部使用 LangGraph `get_stream_writer` 机制：每收到一个 StreamEvent，在节点内部通过 `writer(event)` 实时输出，LangGraph 将其作为自定义事件透传，API 层监听这些事件转换为 SSE。

```python
# chat_node 核心逻辑
async def chat_node(state: ChatState, config: RunnableConfig) -> dict:
    writer = get_stream_writer(config)

    full_text: list[str] = []
    tool_calls_data: dict[str, dict] = {}  # tool_id -> {name, args_json}

    async for event in client.stream(state["messages"], tools=tool_defs):
        writer(event)  # 实时透传给 API 层

        if isinstance(event, TextChunk):
            full_text.append(event.delta)
        elif isinstance(event, ToolCallStartChunk):
            tool_calls_data[event.tool_id] = {"name": event.tool_name, "args_json": ""}
        elif isinstance(event, ToolCallDeltaChunk):
            if event.tool_id in tool_calls_data:
                tool_calls_data[event.tool_id]["args_json"] += event.tool_args_delta
        elif isinstance(event, ToolCallEndChunk):
            pass  # 参数已拼接完整

    # 构建结构化 tool_calls
    tool_calls = []
    for tool_id, data in tool_calls_data.items():
        try:
            arguments = json.loads(data["args_json"])
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append(ToolCall(tool_id=tool_id, tool_name=data["name"], arguments=arguments))

    return {
        "messages": [Message(role="assistant", content="".join(full_text), tool_calls=tool_calls or None)],
        "tool_calls": tool_calls,
        "loop_count": state["loop_count"] + 1,
    }
```

---

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 图节点流式输出方式 | LangGraph `get_stream_writer` | chat_node 内部产生 StreamEvent 时需要实时推到 API 层，`stream_writer` 是 LangGraph 内置的节点级流式透传机制 |
| ToolCall ID 关联 | Anthropic 适配器维护 `_current_tool_id` | 当前 Anthropic delta/end 事件不携带 tool_id，需在 `_map_event` 中跟踪最后发起的 tool_use block ID 并回填 |
| 工具执行顺序 | 串行 `async for` | spec 明确不做并行，按 LLM 返回的工具调用顺序依次执行。执行结果即时逐个 yield 给前端 |
| 图遍历 vs 直接调用 | API 层使用 `graph.astream_events` | 统一 CLI 和 API 的执行路径，两者共用同一张图 |
| 工具参数流式拼接 | 在 chat_node 中按 tool_id 累积 | LLM 适配器逐块产出 JSON 片段，chat_node 在内存中拼接。End 时 `json.loads` 解析，失败则 arguments 置空 |
| Anthropic tools 格式 | 标准 `tools` 参数 | `{"name", "description", "input_schema"}`，去掉 Pydantic 生成的 `"title"` 和 `"additionalProperties"` 字段 |
| 前端工具展示 | 折叠卡片 + 状态标签 | 用 Tailwind CSS 手写，不引入新 UI 库。展示调用状态、工具名、参数摘要、结果/错误 |
| 注册中心生命周期 | 应用启动时创建，模块级单例 | 工具不需要热加载，单例满足需求 |
