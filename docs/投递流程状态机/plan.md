# 投递流程状态机 Plan

## 架构概览

在现有 `chat_node → [条件] → tool_node` 的 ReAct 图基础上，**叠加一个确定性投递流程子图**：

```
                    ┌─────────────────────────── 普通对话 ReAct ───────────────────────────┐
entry_router ──► chat_node ──(有工具调用?)──► tool_node ──(非投递工具)────────────────────► chat_node
                   ▲                              │
                   │                    (调用 browser_navigate 成功)
                   │                              ▼
                   │                      submit_flow 子图（确定性状态机）
                   │       ┌────────── 由 current_stage 条件边控制 ──────────┐
                   └───────┤ snapshot_form → upload_resume → resume_uploaded │
                           │ → fill_profile_fields → probe_dropdowns →        │
                           │   fill_dropdowns  → completed                    │
                           └──────────────────────────────────────────────────┘
```

- **共用入口**：`entry_router` 检查持久化的 `submit_flow` 状态，有未完成流程 → 直接进入流程节点；无 → 进入普通 `chat_node`。
- **进入时机**：普通 ReAct 中 LLM 调用 `browser_navigate` 且成功 → `tool_node` 初始化 `submit_flow` 状态并跳转流程入口。
- **LLM 决策点**：流程内两个需要语义理解的节点（`fill_profile`、`fill_dropdowns`）在内部发起一次**受控 LLM 调用**（无工具、无历史、direct 文案），产出映射计划，再由节点调用浏览器工具执行。
- **持久化**：流程状态序列化进会话 JSON（`data/conversations/*.json` 的 `submit_flow` 字段），跨轮恢复。

## 核心数据结构

### SubmitFlowStage
```python
SubmitFlowStage = Literal[
    "waiting_login",         # 已打开投递页，等用户登录后回复
    "form_detected",         # 已识别表单结构
    "resume_uploaded",       # 简历已上传
    "waiting_resume_choice", # 已拿到多份简历候选，等用户选择
    "basic_filled",          # 基础字段已填
    "dropdowns_probed",      # 下拉框已探测
    "completed",             # 全部完成
]
```

### SubmitFlowState（dict 形态，TypedDict 不透出）
```python
class SubmitFlowState(TypedDict, total=False):
    job_url: str                       # 投递页 URL
    current_stage: SubmitFlowStage
    form_fields: list[dict]            # 首次 snapshot 解析出的表单字段（含 ref/type/label）
    unfilled_fields: list[dict]        # 最近一次快照后的未填字段
    has_upload_entry: bool             # 是否有简历上传入口
    uploaded_resume: str               # 已上传简历文件名
    resume_candidates: list[str]       # 多份简历时的候选文件名
    personal_info: dict                # 脱敏视图（敏感值为 ***）
    dropdowns: list[dict]              # 探测到的下拉框 [{ref, label, display, options}]
    fill_plan: list[dict]              # 表单填充计划 [{ref, data_key}]
    dropdown_fill_plan: list[dict]     # 下拉填充计划 [{ref, data_key|value}]
```

### ChatState（graph.py 扩展）
```python
class ChatState(TypedDict):
    messages: list[Message]
    response: str
    tool_calls: NotRequired[list[ToolCall]]
    loop_count: NotRequired[int]
    submit_flow: NotRequired[SubmitFlowState]   # ★ 新增：投递流程状态
```

## 模块设计

### src/chat/graph.py（改造）
**职责：** 图构建、路由、节点接入。
- 新增 `entry_router(state)` 条件入口：`state` 含 `submit_flow` 且有 `job_url` → 返回 `submit_flow_graph`；否则返回 `chat_node`。
- 新增条件边：`chat_node` 检测到 `browser_navigate` 工具调用成功 → 进入流程；`tool_node` 在流程中 → 进入下一流程节点而不是回 `chat_node`。
- 保留原 `chat_node`/`tool_node`/`_should_continue`，普通对话路径不变。

### src/chat/submit_flow.py（新建）
- 定义 `SubmitFlowState`、`SubmitFlowStage`。
- **8 个流程节点函数**（每个 `async def node(state, config) -> dict` 或通过装饰器注册）：
  1. `navigate_and_wait`：已由 tool_node 完成 navigate，此节点只写等待文案、置 `waiting_login`。
  2. `snapshot_form`：调 `browser_snapshot`，解析 `form_fields`、判断 `has_upload_entry`，置 `form_detected`。
  3. `upload_resume`：检查是否有上传入口；无 → 直接跳过；多份简历 → 返回候选清单 + `waiting_resume_choice`；单份 → 调用 `browser_upload_resume`，置 `resume_uploaded`。
  4. `waiting_resume_choice`：等用户回复；收到选择后调 `browser_upload_resume(resume=...)`，置 `resume_uploaded`。
  5. `snapshot_again`：再次 snapshot，刷新 `unfilled_fields`。
  6. `get_personal_info`：调 `getPersonalInfo`，保存**脱敏视图**到 `submit_flow.personal_info`（不进 messages）。
  7. `fill_form`：对 `unfilled_fields` 做 LLM 映射 → `fill_plan`，调 `browser_fill_form(items=fill_plan)`，置 `basic_filled`。
  8. `fill_dropdowns`：对 `dropdowns` 做 LLM 映射 → `dropdown_fill_plan`，调 `browser_fill_dropdowns`，置 `completed`。
- **LLM 决策点**：新建 `mapping_llm_call(client, system_prompt, user_context) -> list[dict]`，请求 LLM 产出去键映射计划（JSON），并在 failure 时重试/降级为「跳过该项并记录」。
- **错误传播**：任何节点工具调用失败 → `user_message += 错误说明`，并清理 `submit_flow`（回到普通对话）。

### src/chat/mapping_functions.py（新建，LLM 决策专用）
- `build_fill_prompt(fields, personal_info_masked) -> str`：把已脱敏的个人信息键目录 + 未填字段转成决策提示。
- `build_dropdown_prompt(dropdowns, personal_info_masked) -> str`。
- `parse_plan(plan_text) -> list[dict]`：解析 LLM 返回的 JSON 映射计划。
- `call_decision(client: BaseLLMClient, prompt) -> dict`：调用 `client.stream(system=..., messages=[user])` 收集文本、提取 JSON。**仅此模块访问真实个人信息脱敏视图**，value 不写入 messages。

### src/api/storage.py（扩展）
- 新增 `get_submit_flow(conversation_id) -> dict | None`。
- 新增 `save_submit_flow(conversation_id, state: dict)`（写入 conv JSON 的 `"submit_flow"` 字段）。
- 新增 `clear_submit_flow(conversation_id)`。

### src/api/routes.py（改造）
- `send_message`：从 storage 读取 `submit_flow` 注入 initial_state；图运行结束后若 `submit_flow` 变化则写回 storage。

### src/prompt/prompt.py（改造）
- `SubmitFlow` 文案更新：描述状态机接管后的分工（browser_navigate 后由系统自动推进，无需逐一调用）。
- 新增 `submit_flow_toolset()` 生成仅限流程期的工具名单，供 `chat_node` 动态削减 tool_defs（流程进行中禁止其他工具）。

## 模块交互（一次完整投递的时序）

```
用户: “帮我投递 https://..."
   │  entry_router：无 submit_flow → chat_node
   ▼
chat_node (LLM+全工具) → 产出 browser_navigate(url)
   ▼
tool_node：执行 browser_navigate 成功
   │  初始化 submit_flow={job_url, current_stage="waiting_login"}
   ▼
navigate_and_wait → 写文案「请登录后回复继续」 → waiting_login
   ▼
（图结束，等待用户；submit_flow 已持久化）
用户回复 “继续”
   ▼ entry_router：有 flow → submit_flow_graph
snapshot_form → browser_snapshot → form_fields / has_upload_entry → form_detected
   ▼
upload_resume → 单份 cv.pdf → browser_upload_resume → resume_uploaded
   ▼
snapshot_again → browser_snapshot → unfilled_fields 刷新
   ▼
get_personal_info → getPersonalInfo（脱敏）→ personal_info
   ▼
fill_form ── LLM决策点：unfilled_fields + personal_info(masked) → fill_plan
        └► browser_fill_form(items=fill_plan) → basic_filled
   ▼
probe_dropdowns → browser_probe_dropdowns → dropdowns → dropdowns_probed
   ▼
fill_dropdowns ── LLM决策点：dropdowns + personal_info(masked) → dropdown_fill_plan
        └► browser_fill_dropdowns → completed
   ▼
（写最终汇报文案，save submit_flow，图停止）
```

## 文件组织
```
src/
├── chat/
│   ├── graph.py          — 图构建、路由、tool_defs 裁剪（改造）
│   ├── submit_flow.py    — 8 个流程节点 + SubmitFlowState（新建）
│   └── mapping_fallback.py — LLM 映射决策点（新建）
├── llm/
│   ├── base.py           — 不变（仍为唯一 LLM 流式接口）
│   └── ...
├── api/
│   ├── storage.py        — 增加 submit_flow 读写（扩展）
│   └── routes.py         — 注入/写回 submit_flow（改造）
└── prompt/
    └── prompt.py         — SubmitFlow 文案更新，流程工具名单（改造）
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 状态机入口 | entry_router 条件路由 | 普通对话与投递流程同图共存，路由基于持久化状态 |
| 状态机器控制 | current_stage 决定边 | 符合用户给定流程，节点无顺序耦合 |
| 进入时机 | LLM 调 browser_navigate 成功回退 | 由 LLM 判断意图（需求方确认），成功后机器接管 |
| 持久化 | 会话 JSON `submit_flow` 字段，不用 checkpointer | 无新依赖；现有会话存储天然支持并查、服务重启恢复 |
| 敏感值 | state 存脱敏视图，真实值只由工具读 profile.json | 不写 messages、不进 LLM 上下文，token 最小化 |
| LLM 决策点 | 无工具、无历史、独立 prompt 单次调用 | 避免 LLM 在流程中途自由发挥，只做受限映射 |
| 失败处理 | 工具错误即终止流程、清状态、回普通对话 | 保证确定性退出，不留卡死的半成品状态 |
| intent 检测 | 非 LLM 词法判断，直接看是否调用了 browser_navigate | 简单可靠，符合「LLM 决定进不进入」的用户意图 |
| 工具集裁剪 | 流程中 chat_node 只暴露流程工具 | 防止 LLM 在流程中途调用无关工具干扰浏览器状态 |