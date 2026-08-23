# 投递流程状态机 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/chat/submit_flow.py` | SubmitFlowState、8 个流程节点、流程构建辅助 |
| 新建 | `src/chat/mapping_functions.py` | LLM args 映射决策点（fill / dropdown 的 plan 生成） |
| 修改 | `src/chat/graph.py` | entry_router、状态机旁路、tool_defs 裁剪 |
| 修改 | `src/api/storage.py` | submit_flow 的 get/save/clear |
| 修改 | `src/api/routes.py` | 注入/写回 submit_flow |
| 修改 | `src/prompt/prompt.py` | SubmitFlow 文案更新 + submit_flow_toolset |
| 修改 | `tests/chat/test_submit_flow_reminder.py` | 适配去掉 reminder 注入的新逻辑 |
| 新建 | `tests/chat/test_submit_flow_state_machine.py` | 状态机行为测试 |

## T1: storage.py 增加 submit_flow 读写

**文件：** `src/api/storage.py`
**依赖：** 无
**步骤：**
1. 定义 `SUBMIT_FLOW_KEY = "submit_flow"`。
2. 增加 `get_submit_flow(conversation_id) -> dict | None`：读会话 JSON，返回其中的 `submit_flow` 字段；无会话或无该字段返回 None。
3. 增加 `save_submit_flow(conversation_id, state: dict) -> None`：写入会话 JSON 的 `submit_flow` 字段并落盘。
4. 增加 `clear_submit_flow(conversation_id) -> None`：删除该字段并落盘。

**验证：** `python -c "from src.api.storage import get_submit_flow,save_submit_flow,clear_submit_flow; ..."` 跑通增查删。

## T2: mapping_functions.py —— LLM 映射决策点

**文件：** `src/chat/mapping_functions.py`
**依赖：** T1（不直接，但节点依赖）
**步骤：**
1. 定义 `build_fill_prompt(fields, personal_keys, personal_info_masked) -> str`：构造成「未填字段 + 可用个人信息键」的决策提示，要求返回 JSON 映射 `[{ref, data_key}]`。
2. 定义 `build_dropdown_prompt(dropdowns, personal_info_masked) -> str`：构造「下拉框+选项清单+脱敏信息」的决策提示，要求返回 `[{ref, data_key 或 value}]`。
3. 实现 `async call_decision(client, prompt) -> dict`：
   - 用 `client.stream(system=decision_system, messages=[Message(role="user", content=prompt)])` 收集 TextChunk；
   - 提取 ```json ...``` 或裸 JSON 解析为 dict；
   - 异常时返回 `{}`（由调用方降级）。
4. 实现 `build_fill_plan(fields, decision) -> list`、`build_dropdown_plan(dropdowns, decision) -> list` 归一化输出的边界（过滤无 data_key 的项）。

**验证：** 单测：mock client.stream 返回一段 JSON 文本，断言 run_decision 解析正确；返回垃圾文本时返回 `{}`。

## T3: submit_flow.py —— 节点定义

**文件：** `src/chat/submit_flow.py`
**依赖：** T2
**步骤：**
1. 定义 `SubmitFlowStage`（Literal）与 `SubmitFlowState`（TypedDict）。
2. 实现每个节点函数（接受 `state, client, registry` 等注入参数）：
   - `navigate_and_wait`：写文案、置 `waiting_login`。
   - `snapshot_form`：注册中心调 `browser_snapshot`，解析 form_fields / has_upload_entry。
   - `upload_resume`：无上传入口→跳过；候选多份→`waiting_resume_choice` + 返回候选；单份→上传、`resume_uploaded`。
   - `waiting_resume_choice`：从用户消息提取序号/文件名，调 `browser_upload_resume(resume=...)`。
   - `snapshot_again`、`get_personal_info`、`fill_form`、`fill_dropdowns` 类似。
3. `fill_form`/`fill_dropdowns` 内部调用 T2 的 decision 函数生成 fill_plan / dropdown_fill_plan，再调对应工具。
4. 任何工具失败 → 返回带错误说明、`submit_flow` 清空的终止状态（外部函数取空则视为普通对话）。

**验证：** T5 的整体测试覆盖；单节点逻辑先以 unit 构造函数直接调用验证纯逻辑分支。

## T4: graph.py 集成状态机

**文件：** `src/chat/graph.py`
**依赖：** T3
**步骤：**
1. `ChatState` 增加 `submit_flow: NotRequired[SubmitFlowState]`。
2. 增加 `entry_router(state) -> str`：`state` 有 `submit_flow` 且 `job_url` 非空 → 返回流程入口节点名；否则 `chat_node`。
3. `chat_node` 后新增条件边：若 LLM 本轮产出 `browser_navigate` 工具调用 → 先走 `tool_node`，成功后进入流程；否则仍走原 `_should_continue`。
4. 新增节点注册：`submit_flow` 子图中的 8 节点；`tool_node` 结束 `/`节点之后根据 `submit_flow.current_stage` 路由到对应流程节点。
5. 流程期 `tool_defs` 裁剪：进入流程后 `chat_node` 的用户消息不带全工具，只带流程必需工具（`browser_snapshot`、`browser_upload_resume`、`getPersonalInfo`、`browser_fill_form`、`browser_probe_dropdowns`、`browser_fill_dropdowns`）。
6. 移除/停用旧的 `<system-reminder>` 注入逻辑（不再需要）。

**验证：** 跑现有测试保证非投递路径不 regression；新增流程测试通过；`_SUBMIT_FLOW_NEXT` 相关不再在 graph 中被引用。

## T5: prompt.py 更新

**文件：** `src/prompt/prompt.py`
**依赖：** T4
**步骤：**
1. 改写 `SubmitFlow` 段：说明 browser_navigate 由系统接管后续；流程进行时不要求 LLM 重复调用。
2. 新增 `submit_flow_toolset() -> set[str]`：返回流程允许的工具名单。
3. 移除对 `_SUBMIT_FLOW_TOOLS` / `_SUBMIT_FLOW_NEXT` 的依赖（按 T4 后 graph 已不需 reminder 注入；保留均可）。

**验证：** `build_system_prompt()` 仍能构建出完整 prompt，`submit_flow_toolset()` 返回值符合预期。

## T6: routes.py 注入/持久化

**文件：** `src/api/routes.py`
**依赖：** T4
**步骤：**
1. `send_message` 从 `storage.get_submit_flow(conversation_id)` 读取，注入 `initial_state`.
2. 用新 hook：图流结束后，若 final state 的 `submit_flow` 与读入的不一致 → `storage.save_submit_flow`；`submit_flow` 为空 → `clear_submit_flow`.

**验证：** 用实际会话跑一遍投递（mock 浏览器）观察会话 JSON 中出现/消失 `submit_flow` 字段。

## T7: 测试适配与新增

**文件：** `tests/chat/test_submit_flow_reminder.py`、`tests/chat/test_submit_flow_state_machine.py`
**依赖：** T4
**步骤：**
1. 删除/改写旧 `test_submit_flow_reminder`（不再断言 system-reminder 注入）。
2. 新增 `test_submit_flow_state_machine.py`：
   - 构造 mock `client`，第一轮 LLM 返回 `browser_navigate` 调用，断言进入流程、`submit_flow` 含 job_url。
   - mock registry.execute 返回固定 snapshot/json，逐步跑完 `waiting_login → … → completed`，断言每阶段 transition 与 state 字段。
   - 多份简历：断言 `waiting_resume_choice`、再回复序号继续。
   - 失败分支：mock 工具返回 error，断言 `submit_flow` 清空且 output 含错误。
   - 映射点：mock client.stream 返回 `[{"ref":..,"data_key":..}]`，断言 `fill_plan` 正确。

**验证：** `python -m pytest tests/chat -x` 全绿。

## 执行顺序

```
T1 → T2 → T3 → T4 → T5 → T6 → T7
```

全部串行，依赖单一；每步完成后即可 commit。