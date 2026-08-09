# 工具系统 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/tools/decorator.py` | `@tool` 装饰器 + `ToolWrapper` 类 |
| 新建 | `src/tools/types.py` | `ToolEntry` 数据结构 |
| 新建 | `src/tools/registry.py` | `ToolRegistry` 单例 + 自动发现 + 执行 |
| 修改 | `src/tools/__init__.py` | 导出 `tool`、`ToolRegistry`、`ToolEntry` |
| 新建 | `src/tools/builtin/__init__.py` | 内置工具包入口，用户在此目录添加工具 |
| 修改 | `src/llm/types.py` | `Message` 扩展 `tool` 角色、新增 `ToolCall`、新增 `ToolResultEvent` |
| 修改 | `src/llm/base.py` | `stream()` 签名新增 `tools` 参数 |
| 修改 | `src/llm/anthropic.py` | 补全 tool_id 关联 + 转换 tools 定义 |
| 修改 | `src/llm/openai.py` | 转换 tools 定义为 OpenAI 格式 |
| 重写 | `src/chat/graph.py` | chat_node + tool_node + 条件路由 |
| 修改 | `src/chat/__init__.py` | 导出 `build_graph`、`ChatState` |
| 修改 | `src/api/sse.py` | 新增工具事件 SSE 格式化 |
| 修改 | `src/api/routes.py` | 改为图驱动对话，注入 ToolRegistry |
| 修改 | `src/api/main.py` | 启动时初始化 ToolRegistry |
| 修改 | `frontend/src/api/sse.ts` | 新增工具事件回调接口 + 解析 |
| 修改 | `frontend/src/types.ts` | 新增 `ToolCallInfo` 类型 |
| 修改 | `frontend/src/AppContext.tsx` | 新增工具调用状态管理 |
| 新建 | `frontend/src/components/ToolCallCard.tsx` | 工具调用折叠卡片 |
| 修改 | `frontend/src/components/MessageBubble.tsx` | 嵌入 ToolCallCard |

---

## T1: 创建工具类型定义

**文件：** `src/tools/types.py`
**依赖：** 无
**步骤：**
1. 用 `@dataclass` 定义 `ToolEntry`，字段：`name: str`、`description: str`、`parameters: dict`、`param_model: type[BaseModel]`、`fn: Callable`
2. `parameters` 注释说明这是 JSON Schema 格式
3. 添加模块 docstring

**验证：** `python -c "from src.tools.types import ToolEntry"` 无报错

---

## T2: 创建工具装饰器

**文件：** `src/tools/decorator.py`
**依赖：** T1
**步骤：**
1. 定义 `tool(*, name: str, description: str)` 函数，返回装饰器闭包
2. 装饰器内部检查被装饰函数的第一参数类型注解是否为 `BaseModel` 子类，否则抛 `TypeError`
3. 从 Pydantic 模型 `model_json_schema()` 提取 JSON Schema
4. 清理 Schema 中的 `"title"` 和 `"additionalProperties"` 顶层字段（Anthropic/OpenAI 不兼容）
5. 实现 `ToolWrapper` 类，包含 `name`、`description`、`param_model`、`_fn` 属性
6. `ToolWrapper.execute(self, arguments: dict) -> str`：用 `self.param_model(**arguments)` 校验 → `await self._fn(params)` → 返回 `str`；异常时返回 `"[工具执行错误] {exception}"` 不抛
7. 装饰器返回 `ToolWrapper` 实例

**验证：** 临时写一个 Pydantic 模型和 async 函数，加 `@tool` 装饰，调用 `execute()` 确认返回正确字符串

---

## T3: 创建工具注册中心

**文件：** `src/tools/registry.py`
**依赖：** T1, T2
**步骤：**
1. 实现 `ToolRegistry` 类，`__init__` 中创建 `_tools: dict[str, ToolEntry]`
2. `get_instance()` 类方法：模块级单例，`_instance` 类变量
3. `register(tool: ToolWrapper)` → 从 ToolWrapper 提取字段构造 `ToolEntry`，存入 `_tools`；重名抛 `ValueError`
4. `discover(package_path: str = "src.tools.builtin")` → 用 `importlib.import_module` + `pkgutil.walk_packages` 扫描包下所有模块，`import_module` 后用 `dir()` 找出 `ToolWrapper` 实例并调用 `register()`；已存在的跳过不报错
5. `get_tool(name: str) -> ToolEntry | None`
6. `list_definitions() -> list[dict]` → 遍历 `_tools`，返回 `[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in _tools.values()]`
7. `async execute(name: str, arguments: dict) -> str` → 查找 ToolEntry → 调用其 `fn` 指向的 `ToolWrapper.execute()` → 工具不存在时返回 `"[工具不存在] {name}"` 字符串

**验证：** 手动创建 2 个 ToolWrapper 注册 → `list_definitions()` 返回 2 条 → `execute()` 正确返回

---

## T4: 更新 tools 包导出

**文件：** `src/tools/__init__.py`
**依赖：** T2, T3
**步骤：**
1. `from .decorator import tool`
2. `from .registry import ToolRegistry`
3. `from .types import ToolEntry`
4. 设 `__all__ = ["tool", "ToolRegistry", "ToolEntry"]`

**验证：** `python -c "from src.tools import tool, ToolRegistry, ToolEntry"` 无报错

---

## T5: 创建 builtin 目录入口

**文件：** `src/tools/builtin/__init__.py`
**依赖：** T4
**步骤：**
1. 创建文件，添加包 docstring
2. `__all__: list[str] = []`（用户自行添加工具后可选填入）

**验证：** `python -c "import src.tools.builtin"` 无报错

---

## T6: 扩展 Message 类型

**文件：** `src/llm/types.py`
**依赖：** 无
**步骤：**
1. 新增 `ToolCall` 数据类：`tool_id: str`、`tool_name: str`、`arguments: dict`
2. `Message` 新增字段：`tool_calls: list[ToolCall] | None = None`、`tool_call_id: str | None = None`
3. `Message.role` 的 `Literal` 扩展为 `"user" | "assistant" | "tool"`
4. 新增 `ToolResultEvent` 数据类：`tool_id: str`、`content: str`
5. 将 `ToolResultEvent` 加入 `StreamEvent` 联合类型
6. 检查所有现有 `Message(...)` 构造处（`routes.py`、`graph.py`、`app.py`）——本次不改，后续任务中逐步适配

**验证：** `python -c "from src.llm.types import Message, ToolCall, ToolResultEvent; m=Message(role='tool', content='x', tool_call_id='abc')"` 无报错

---

## T7: 修改 BaseLLMClient 接口

**文件：** `src/llm/base.py`
**依赖：** T6
**步骤：**
1. `stream()` 抽象方法签名新增 `tools: list[dict] | None = None`
2. 更新 docstring 说明 `tools` 为 `[{"name": str, "description": str, "input_schema": dict}]` 格式
3. 保持 `@abstractmethod`

**验证：** `python -c "from src.llm.base import BaseLLMClient"` 无报错（子类暂时会有类型检查警告，后续任务修复）

---

## T8: 改造 Anthropic 适配器

**文件：** `src/llm/anthropic.py`
**依赖：** T6, T7
**步骤：**
1. `stream()` 接收 `tools` 参数
2. 若 `tools` 不为空，构建 Anthropic 格式的 `tools` 列表传入 `stream_kwargs`：
   ```python
   stream_kwargs["tools"] = [
       {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
       for t in tools
   ]
   ```
3. 实例化时初始化 `self._current_tool_id: str | None = None`
4. `_map_event` 中：`content_block_start` 的 `tool_use` 时记录 `self._current_tool_id = block.id`
5. `input_json_delta` 产出 `ToolCallDeltaChunk` 时填入 `tool_id=self._current_tool_id or ""`
6. `content_block_stop` 产出 `ToolCallEndChunk` 时填入 `tool_id=self._current_tool_id or ""`，然后重置 `self._current_tool_id = None`
7. 导入 `ToolCallDeltaChunk`、`ToolCallEndChunk`（已导入，确认字段使用正确）

**验证：** 临时脚本构造带 tools 的 AnthropicAdapter，确认 API 调用不报错

---

## T9: 改造 OpenAI 适配器

**文件：** `src/llm/openai.py`
**依赖：** T6, T7
**步骤：**
1. `stream()` 接收 `tools` 参数
2. 若 `tools` 不为空，构建 OpenAI 格式的 `tools` 列表传入 `chat.completions.create()`：
   ```python
   openai_tools = [
       {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
       for t in tools
   ]
   ```
3. 将 `openai_tools` 传入 `self.client.chat.completions.create()` 的 `tools` 参数

**验证：** 临时脚本构造带 tools 的 OpenAIAdapter，确认 API 调用不报错

---

## T10: 重写 chat_node

**文件：** `src/chat/graph.py`
**依赖：** T6, T7, T8, T9, T4
**步骤：**
1. 更新 `ChatState` TypedDict：`messages: list[Message]`、`response: str`、`tool_calls: list[ToolCall]`、`loop_count: int`
2. 定义 `MAX_TOOL_LOOPS = 10`
3. 实现 `async def chat_node(state: ChatState, config: RunnableConfig, *, client: BaseLLMClient, tool_defs: list[dict]) -> dict`：
   - 获取 `writer = get_stream_writer(config)`（从 `langgraph.config` 导入）
   - 初始化 `full_text: list[str] = []`、`tool_calls_data: dict[str, dict[str, str]] = {}`
   - `async for event in client.stream(state["messages"], tools=tool_defs):`
     - `writer(event)` 透传
     - `TextChunk` → `full_text.append(event.delta)`
     - `ToolCallStartChunk` → `tool_calls_data[event.tool_id] = {"name": event.tool_name, "args_json": ""}`
     - `ToolCallDeltaChunk` → 若 id 在 dict 中，`tool_calls_data[event.tool_id]["args_json"] += event.tool_args_delta`
     - `ToolCallEndChunk` → 不额外操作
     - `ThinkingChunk` → 透传即可（已在 writer 中处理）
   - 遍历结束后，对 `tool_calls_data` 中每个条目 `json.loads(args_json)` 构造 `ToolCall`；`JSONDecodeError` 时 `arguments = {}`
   - 构建 `assistant_msg = Message(role="assistant", content="".join(full_text), tool_calls=tool_calls or None)`
   - 返回 `{"messages": [assistant_msg], "tool_calls": tool_calls, "loop_count": state["loop_count"] + 1}`

**验证：** 单元检查——函数签名与 LangGraph `add_node` 要求兼容

---

## T11: 实现 tool_node

**文件：** `src/chat/graph.py`（同 T10）
**依赖：** T10
**步骤：**
1. 实现 `async def tool_node(state: ChatState, config: RunnableConfig, *, registry: ToolRegistry) -> dict`：
   - 获取 `writer = get_stream_writer(config)`
   - `tool_messages: list[Message] = []`
   - `for tc in state["tool_calls"]:`
     - `result = await registry.execute(tc.tool_name, tc.arguments)`
     - `writer(ToolResultEvent(tool_id=tc.tool_id, content=result))` 透传执行结果
     - `tool_messages.append(Message(role="tool", content=result, tool_call_id=tc.tool_id))`
   - 返回 `{"messages": tool_messages, "tool_calls": [], "response": ""}`

**验证：** 单元检查——`ToolResultEvent` 导入正确，函数签名正确

---

## T12: 实现条件路由和 build_graph

**文件：** `src/chat/graph.py`（同 T10）
**依赖：** T10, T11
**步骤：**
1. 实现 `def _should_continue(state: ChatState) -> str`：
   - `if state["tool_calls"] and state.get("loop_count", 0) < MAX_TOOL_LOOPS: return "tool_node"`
   - `return END`
   - 从 `langgraph.graph import END`
2. 重写 `def build_graph(client: BaseLLMClient, registry: ToolRegistry) -> StateGraph`：
   - 创建 `StateGraph(ChatState)`
   - `tool_defs = registry.list_definitions()`
   - `graph.add_node("chat_node", ...)` — 闭包绑定 `client`、`tool_defs`
   - `graph.add_node("tool_node", ...)` — 闭包绑定 `registry`
   - `graph.set_entry_point("chat_node")`
   - `graph.add_conditional_edges("chat_node", _should_continue, {"tool_node": "tool_node", END: END})`
   - `graph.add_edge("tool_node", "chat_node")`
   - `return graph.compile()`

**验证：** `build_graph(client, registry)` 返回编译后的图对象，无异常

---

## T13: 更新 chat 包导出

**文件：** `src/chat/__init__.py`
**依赖：** T12
**步骤：**
1. `from .graph import build_graph, ChatState`
2. `__all__ = ["build_graph", "ChatState"]`

**验证：** `python -c "from src.chat import build_graph, ChatState"` 无报错

---

## T14: 改造 SSE 适配器

**文件：** `src/api/sse.py`
**依赖：** T6
**步骤：**
1. 导入 `ToolCallStartChunk`、`ToolCallDeltaChunk`、`ToolCallEndChunk`、`ToolResultEvent`
2. 在 `to_sse()` 函数中新增 4 个 `isinstance` 分支：
   - `ToolCallStartChunk` → SSE event `"tool_start"`, data: `{"tool_id": e.tool_id, "tool_name": e.tool_name}`
   - `ToolCallDeltaChunk` → SSE event `"tool_delta"`, data: `{"tool_id": e.tool_id, "delta": e.tool_args_delta}`
   - `ToolCallEndChunk` → SSE event `"tool_end"`, data: `{"tool_id": e.tool_id}`
   - `ToolResultEvent` → SSE event `"tool_result"`, data: `{"tool_id": e.tool_id, "content": e.content}`

**验证：** `python -c "from src.api.sse import to_sse; print(to_sse(ToolCallStartChunk('id1', 'test_tool')))"` 输出正确 SSE 字符串

---

## T15: 改造 API 路由——图驱动对话

**文件：** `src/api/routes.py`
**依赖：** T13, T14
**步骤：**
1. 导入 `build_graph`、`ChatState`、`ToolRegistry`
2. 新增模块变量 `_registry: ToolRegistry | None = None` 和 `set_registry()` / `_get_registry()` 函数
3. 重写 `send_message` 的 `event_generator()` 内部逻辑：
   - 构建初始 `ChatState`: `{"messages": messages, "response": "", "tool_calls": [], "loop_count": 0}`
   - 获取 `graph = build_graph(client, registry)`
   - 使用 `graph.astream_events(initial_state, version="v2")` 监听图事件
   - 过滤 `on_chat_model_stream` 或自定义事件 → 调用 `to_sse(event)` → `yield`
   - 图执行完毕后，提取最终 `response` 存入 storage
   - `yield "event: done\ndata: {}\n\n"`

**验证：** 启动后端，发送一条纯文本消息，前端正常收到回复（此时无工具，行为与改造前一致）

---

## T16: 改造 API 入口

**文件：** `src/api/main.py`
**依赖：** T4, T15
**步骤：**
1. 导入 `ToolRegistry`
2. 在 `main()` 中，创建 client 之后：
   - `registry = ToolRegistry.get_instance()`
   - `registry.discover("src.tools.builtin")`
   - `print(f"已加载 {len(registry.list_definitions())} 个工具")`（若无工具则打印提示）
   - `set_registry(registry)` 注入到 routes 模块

**验证：** 启动后端，日志中看到 "已加载 X 个工具"

---

## T17: 改造 CLI 对话循环

**文件：** `src/cli/app.py`
**依赖：** T13
**步骤：**
1. 导入 `build_graph`、`ChatState`、`ToolRegistry`
2. 在 `chat_loop` 中改为使用图执行对话（统一路径）
3. 工具调用时终端输出 `[调用工具: {tool_name}]` 和相关状态

**验证：** 终端对话中发起需要工具的请求，确认工具被调用并返回结果

---

## T18: 前端——新增 SSE 工具事件

**文件：** `frontend/src/api/sse.ts`
**依赖：** T14
**步骤：**
1. 在 `SSECallbacks` 接口新增 4 个回调：
   - `onToolStart?: (toolId: string, toolName: string) => void`
   - `onToolDelta?: (toolId: string, delta: string) => void`
   - `onToolEnd?: (toolId: string) => void`
   - `onToolResult?: (toolId: string, content: string) => void`
2. 在 `parseSSEStream` 的事件分发中新增 4 个 case：
   - `"tool_start"` → 解析 data 中的 `tool_id`、`tool_name` → 调用 `onToolStart`
   - `"tool_delta"` → 解析 `tool_id`、`delta` → 调用 `onToolDelta`
   - `"tool_end"` → 解析 `tool_id` → 调用 `onToolEnd`
   - `"tool_result"` → 解析 `tool_id`、`content` → 调用 `onToolResult`

**验证：** TypeScript 编译通过（`npx tsc --noEmit` 在 frontend 目录）

---

## T19: 前端——新增类型定义

**文件：** `frontend/src/types.ts`
**依赖：** 无
**步骤：**
1. 新增 `ToolCallState` 接口：
   ```typescript
   export interface ToolCallState {
     toolId: string;
     toolName: string;
     argsJson: string;       // 累积的 JSON 参数字符串
     result: string | null;  // null = 尚未返回
     status: "running" | "done" | "error";
   }
   ```

**验证：** TypeScript 编译通过

---

## T20: 前端——状态管理

**文件：** `frontend/src/AppContext.tsx`
**依赖：** T19
**步骤：**
1. `AppState` 接口新增字段 `activeToolCalls: Record<string, ToolCallState>`（以 toolId 为 key）
2. Action 类型新增 4 个：
   - `TOOL_START` — payload: `{toolId, toolName}`
   - `TOOL_DELTA` — payload: `{toolId, delta}`
   - `TOOL_END` — payload: `{toolId}`
   - `TOOL_RESULT` — payload: `{toolId, content}`（同时设 status 为 done/error）
3. `appReducer` 中实现对应 case

**验证：** TypeScript 编译通过

---

## T21: 前端——ToolCallCard 组件

**文件：** `frontend/src/components/ToolCallCard.tsx`
**依赖：** T19
**步骤：**
1. 实现折叠卡片组件，接收 `ToolCallState` prop
2. 默认折叠（只显示工具名 + 状态标签）
3. 展开后显示：参数（尝试 `JSON.parse` 格式化，失败则显示原文）、返回结果
4. 状态标签：running → 绿色 Spinner、done → 绿色对勾、error → 红色叉号
5. 全部用 Tailwind CSS 实现，不引入额外 UI 库

**验证：** 在浏览器中手动渲染确认组件显示正确（可在开发阶段用 mock 数据）

---

## T22: 前端——集成到 MessageBubble

**文件：** `frontend/src/components/MessageBubble.tsx`
**依赖：** T20, T21
**步骤：**
1. 接收新增的 `toolCalls: ToolCallState[]` prop
2. 在消息内容下方渲染 `ToolCallCard` 列表
3. 工具调用在文本内容之前展示（用户先看到工具操作）

**验证：** 完整流程——发送消息 → 后端调用工具 → 前端展示 ToolCallCard → 最终回复

---

## 执行顺序

```
T1 ──→ T2 ──→ T3 ──→ T4 ──→ T5
                              ↓
T6 ──→ T7 ──→ T8 ──→ T9 ──→ T10 ──→ T11 ──→ T12 ──→ T13
         ↓                                              ↓
T14 ──→ T15 ──→ T16 ──→ T17 (可并行于 T14-T16)

T18 ──→ T19 ──→ T20 ──→ T21 ──→ T22
(前端可在后端完成后开始)
```

**总任务数：22 个**
