# 工具系统 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] [工具装饰器] `@tool` 装饰器可正常使用（验证：`python -c "from src.tools import tool"` 无报错）
- [ ] [工具类型] `ToolEntry` 数据类可导入（验证：`python -c "from src.tools.types import ToolEntry"` 无报错）
- [ ] [注册中心] `ToolRegistry` 单例可获取并发现工具（验证：`registry.discover()` 后 `list_definitions()` 返回已注册工具列表）
- [ ] [Message 扩展] 支持 `role="tool"` 和 `tool_calls` 字段（验证：构造含 tool 角色和 ToolCall 的消息无报错）
- [ ] [LLM 接口] `stream()` 接受 `tools` 参数（验证：`BaseLLMClient` 签名包含该参数）
- [ ] [Anthropic 适配器] tools 参数正确转换为 Anthropic 格式并传入 API（验证：有 API key 时调用不报错，LLM 能返回 tool_use）
- [ ] [OpenAI 适配器] tools 参数正确转换为 OpenAI 格式并传入 API（验证：有 API key 时调用不报错，LLM 能返回 tool_calls）
- [ ] [Anthropic tool_id] 流式工具调用的 delta 和 end 事件携带正确的 tool_id（验证：工具调用流中 tool_id 一致性）
- [ ] [chat_node] 正确收集和拼接流式 JSON 参数（验证：多位参数键值的 JSON 片段拼出有效 JSON）
- [ ] [tool_node] 从注册中心查找并执行工具（验证：LLM 发起工具调用后 tool_node 正确返回 tool 消息）
- [ ] [条件路由] 有 tool_calls → tool_node，无 → END（验证：单轮无工具调用直接结束，有工具调用进入 tool_node）
- [ ] [循环上限] `MAX_TOOL_LOOPS` 达到上限时强制结束（验证：连续 10 次工具调用后图终止）
- [ ] [SSE 适配器] 新增 4 种工具事件生成正确 SSE 格式（验证：`to_sse()` 各种工具事件输出正确 event/data 字符串）
- [ ] [API 路由] 图驱动对话正常工作（验证：发送消息，收到 SSE 流回复）
- [ ] [CLI] 终端对话支持工具调用（验证：终端中发起工具诉求，看到工具调用提示和结果）
- [ ] [前端 SSE] 解析工具事件不报错（验证：浏览器 console 无 SSE 解析错误）
- [ ] [前端状态] 工具调用状态正确更新（验证：React DevTools 中看到 activeToolCalls 变化）
- [ ] [ToolCallCard] 组件渲染正常（验证：界面中出现可折叠的工具调用卡片）

## 集成

- [ ] [tools → registry] 装饰器生成的 ToolWrapper 能被注册中心正确注册（验证：register() 后 list_definitions() 包含该工具）
- [ ] [registry → graph] 注册中心输出的工具定义能被 chat_node 正确传入 LLM（验证：`registry.list_definitions()` 返回值直接作为 `tools` 参数传递）
- [ ] [chat_node → tool_node] 图状态中的 `tool_calls` 被 tool_node 正确消费（验证：tool_node 读取 state["tool_calls"] 执行对应工具）
- [ ] [graph → sse] 图节点通过 `stream_writer` 产出的事件被 `sse.py` 正确格式化（验证：同一种事件在图流和直接调 client 流中产生相同 SSE 输出）
- [ ] [backend → frontend] SSE 工具事件被前端解析和渲染（验证：完整端到端流程）

## 编译与测试

- [ ] 项目所有 Python 模块可正常导入（验证：`python -c "import src"` 及各级子模块）
- [ ] 前端 TypeScript 编译通过（验证：`cd frontend && npx tsc --noEmit`）
- [ ] 前端 Vite 构建通过（验证：`cd frontend && npm run build`）
- [ ] 无 Python 语法错误（验证：`python -m py_compile` 对所有改动的 .py 文件）

## 端到端场景

- [ ] **场景 1：单工具调用** — 用户在 `src/tools/builtin/` 下创建一个 `get_current_time` 工具，重启后端，前端发送 "现在几点了？" → LLM 调用 `get_current_time` → 前端显示折叠卡片（running → done）→ LLM 回复包含正确时间信息
- [ ] **场景 2：多工具连续调用** — 用户创建两个工具（如 `search_jobs` + `get_weather`），前端发送综合问题 → LLM 依次调用两个工具 → 前端显示两张工具调用卡片 → LLM 综合结果回答
- [ ] **场景 3：工具异常处理** — 工具函数内部 `raise Exception("数据库连接失败")` → 工具卡片显示红色错误标签 → LLM 收到 `[工具执行错误] 数据库连接失败` 文本 → LLM 向用户解释工具出错了
- [ ] **场景 4：纯文本对话** — 不注册任何工具（或问了不需要工具的问题如 "你好"）→ 对话正常进行，无工具调用卡片，behavior 与改造前一致
- [ ] **场景 5：参数拼接验证** — 工具参数包含嵌套 JSON（如 `{"filter": {"city": "北京", "salary": {"min": 10000}}}`）→ LLM 流式返回多段 JSON 片段 → 最终拼接出正确完整的参数字典 → 工具接收到正确的 arguments
