# 投递表单下拉框选项探测与填写 Spec

## 背景

投递表单（如 zhiye.com）的下拉选择框不是标准 `<select>`/combobox：快照中表现为 `generic [cursor=pointer]` 元素（子元素显示「请选择」或当前值），展开后是 `list`/`listitem` 结构。现有 `browser_fill_form` 对下拉框走 `browser_select_option`，且 `parse_snapshot` 无法识别这类 generic 下拉框，导致下拉框无法填写。

已验证：这类非标准下拉框**可由程序按结构特征可靠识别**——`generic [cursor=pointer]` 且子树含 `list` 容器。对真实快照实测 24/24 识别、13 个非下拉框（上传简历区、「至今」切换钮等）零误报；「请选择」即未填。

已具备：`browser_snapshot`、`browser_click`、`browser_upload_resume`、`browser_fill_form`、`getPersonalInfo`、`browser_mcp` 持久会话与 `call_tool`、脱敏显示体系。

## 目标

新增两个自定义工具：程序自动识别下拉框并探测选项列表；按目标值点击填写。**LLM 不参与下拉框识别**，只负责决定「填哪个、填什么值」。

## 功能需求

- **F1 程序识别**：`browser_probe_dropdowns` 从快照自动识别全部下拉框候选（规则：`generic [cursor=pointer]` 且子树含 `list`），提取每个候选的 {ref, 字段标签, 当前值, 是否已填}。无需 LLM 传入 ref；可选 `refs` 参数仅用于限定探测范围。
- **F2 选项探测**：对每个未填候选，程序逐个：点击展开 → 等待渲染 → 快照 → **裁切为仅该下拉框的子树** → 提取选项列表（选项值 + 可点击 ref）；探测后点击收起，保持页面整洁。已填候选不展开、直接列出。返回全部候选清单及未填者的选项。
- **F3 下拉填写**：`browser_fill_dropdowns` 接收 LLM 传入的 {ref, 目标值} 列表（ref 来自探测工具返回），对每个：点击展开 → 等待渲染 → 快照 → 裁切 → 匹配目标值 → 点击对应选项。程序校验传入 ref 是否为有效下拉框。
- **F4 鲁棒性**：识别阶段纯程序化、不依赖 LLM；填写阶段对无效 ref、非下拉框 ref、目标值不匹配、无可选项逐项报告、跳过该项、不抛异常中断，其余项继续。
- **F5 脱敏**：目标值支持两种来源——`data_key`（后台解析真实值，敏感值以 *** 显示）与字面量 `value`；任何返回文本（含错误信息）不得泄露敏感真实值。
- **F6 集成**：更新 `SubmitFlow` 与 `browser_snapshot` 工具描述，说明下拉框由 `browser_probe_dropdowns` 自动识别，LLM 只需用探测结果决策填写。
- **F7 选项提取**：从展开子树提取 {选项值, 可点击 ref}；无 ref 的选项标注「不可点击」，无法点击时如实报告。

## 非功能需求

- **N1** 每次点击后等待渲染完成使用固定短延迟（常量，约 0.5s）。
- **N2** 快照裁切基于缩进子树提取 `[ref=X]` 之后的深层节点，避免整页内容交给模型。
- **N3** 工具为异步函数，复用 `src.browser_mcp.client.call_tool`，遵循 `@tool` + pydantic Params + ToolResult 模式。

## 不做的事

- 不修改 `browser_fill_form` 的 combobox 分支；下拉框统一走两个新工具。
- 不专门处理日历/日期/级联等特殊控件（探测到无可选项即如实报告）。
- 不新增文本定位（text locator）点击能力；点击目标必须是快照中可点击的 ref。
- LLM 不参与下拉框识别，但「填哪个下拉框、填什么值」的决策仍由 LLM 负责（程序无法替代）。

## 验收标准

- **AC1** 给定含 generic 下拉框的模拟快照，`browser_probe_dropdowns` **无参调用**即识别全部候选，未填者返回选项列表。
- **AC2** 给定 {ref, 目标值}，`browser_fill_dropdowns` 点击展开后选中匹配选项，报告「已选」。
- **AC3** 传入无效/无关 ref、目标值不匹配、无可选项时逐项报告，不中断其他项。
- **AC4** data_key 解析出的敏感值不泄露在返回文本中（含错误信息）。
- **AC5** 单元测试通过；checklist 的端到端场景在真实页面验证「识别→探测→填写」闭环。
- **AC6** SubmitFlow 与 `browser_snapshot` 描述已更新，agent 按流程使用两个新工具。
