# 工具系统 Spec

## 背景
JobHelper 目前是一个单节点 LangGraph 对话应用，LLM 适配层虽然已能解析流式工具调用事件（`ToolCallStartChunk`、`ToolCallDeltaChunk`、`ToolCallEndChunk`），但上层完全不处理这些事件——图只收文本、API 只转文本、CLI 只印文本。`src/tools/` 目录为空。要让 AI 真正能查数据、做操作，需要补上工具系统。

## 目标
- 提供统一的工具注册中心，支持自动发现 `src/tools/builtin/` 下用 `@tool` 装饰器定义的工具函数
- 将 LangGraph 图从单节点改造为标准 ReAct 循环（chat → tool → chat），LLM 可连续调用多个工具直至给出最终回复
- LLM 客户端接口支持传入工具定义，流式输出中正确拼接 JSON 参数
- 前端能接收并展示工具调用和工具返回的事件
- 工具函数接口清晰，用户只需写 Pydantic 模型 + 异步函数 + 装饰器即可新增工具

## 功能需求
- **F1：工具装饰器** — 提供 `@tool` 装饰器，接收 `name` 和 `description` 参数。被装饰的函数第一个参数必须是一个 Pydantic BaseModel 子类（工具参数），返回 `str`。装饰器自动从 Pydantic 模型提取 JSON Schema 作为工具的参数定义。
- **F2：自动发现注册** — 注册中心在初始化时自动扫描 `src/tools/builtin/` 包下所有模块，收集被 `@tool` 装饰的函数，建立 `tool_name → tool_entry` 的映射。工具入口包含：name、description、parameters JSON Schema、可调用函数。
- **F3：工具定义注入 LLM** — `BaseLLMClient.stream()` 方法接受可选的工具定义列表，适配器将其转换为各协议要求的格式（Anthropic: `tools` 参数，OpenAI: `tools` 参数）传给 API。
- **F4：流式 JSON 参数拼接** — LLM 适配器在流式响应中正确处理工具调用的 JSON 参数增量拼接。使用者（图节点）接收到完整的 `ToolCallStartChunk(tool_id, tool_name)` → 若干 `ToolCallDeltaChunk(tool_id, partial_json)` → `ToolCallEndChunk(tool_id)` 序列，累计拼接出完整 JSON 参数字符串。
- **F5：ReAct 工具节点** — LangGraph 图中新增 `tool_node`，接收 LLM 产出的工具调用，从注册中心查找对应工具，用拼接好的 JSON 参数调用工具，将返回结果以 `tool` 角色消息追加到对话历史。
- **F6：条件路由** — 图中 `chat_node` 之后加入条件边：如果 LLM 回复中包含工具调用，路由到 `tool_node`；否则路由到结束。`tool_node` 执行完成后路由回 `chat_node`，形成循环。
- **F7：Message 类型扩展** — 扩展 `Message` 数据类，支持 `tool` 角色和 `ToolCall` 结构化字段，承载多轮工具交互的完整历史。
- **F8：SSE 工具事件转发** — `sse.py` 中为 `ToolCallStartChunk`、`ToolCallDeltaChunk`、`ToolCallEndChunk` 及工具执行结果生成对应的 SSE 事件（`tool_start`、`tool_delta`、`tool_end`、`tool_result`），API 路由通过图执行过程中产出的事件推送给前端。
- **F9：前端工具状态展示** — 前端 SSE 解析器处理新增的工具事件类型，在对话界面中以折叠卡片展示工具调用过程（工具名、参数、返回摘要），调用期间显示加载状态。

## 非功能需求
- **N1：可扩展性** — 新增工具只需在 `src/tools/builtin/` 下新建 `.py` 文件，写 Pydantic 模型 + async 函数 + 加 `@tool` 装饰器，无需修改注册中心、图、API 或前端代码。
- **N2：协议透明** — 工具定义和调用逻辑不依赖具体 LLM 协议。同一套工具可同时用于 Anthropic 和 OpenAI 适配器，协议差异由适配器内部消化。
- **N3：错误隔离** — 单个工具执行失败不应中断整个对话。工具异常被捕获后以错误消息形式作为 `tool_result` 回传给 LLM，让 LLM 决定如何向用户解释。
- **N4：最大工具调用轮次** — ReAct 循环设置上限（默认 10 轮），防止 LLM 陷入无限工具调用循环。
- **N5：向后兼容** — 不传工具定义时，`BaseLLMClient.stream()` 行为与当前完全一致。CLI 和 API 在未配置工具的情况下可正常运行。

## 不做的事
- **不做**：具体工具函数的业务实现（搜索职位、查天气等）。用户自行实现。
- **不做**：工具的权限控制、速率限制、审计日志。留到后续迭代。
- **不做**：前端工具调用的丰富 UI（如进度条、参数可视化卡片）。本期只做基础的折叠/展开状态展示。
- **不做**：工具的异步并行调用。单轮内多个工具调用按顺序执行。
- **不做**：工具的热加载/卸载。注册发生在应用启动时，运行期不动态变更。

## 验收标准
- **AC1：** 在 `src/tools/builtin/` 下新建一个示例工具（如 `get_current_time`），用 `@tool` 装饰器定义，重启后端后 LLM 能识别并调用该工具，返回正确结果。
- **AC2：** 发起一次需要工具调用的对话，SSE 事件流中按序出现 `tool_start` → `tool_delta`（可能多次）→ `tool_end` → `tool_result` 事件，前端界面可见工具调用状态变化。
- **AC3：** LLM 在一次对话中连续调用 2 个不同工具，工具结果正确回传，LLM 综合两个结果给出最终回复。
- **AC4：** 工具函数抛出异常时，异常信息被包装为 `tool_result` 回传，对话正常继续不崩溃。
- **AC5：** 不传工具定义时，现有对话功能（纯文本问答）行为不变。
