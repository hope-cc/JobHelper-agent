# 基于 Playwright MCP 的简历投递表单自动填写 Spec

## 背景

JobHelper 已有：个人信息管理（`data/personal/profile.json`，含脱敏标记 `masked_basic_fields`）、`getPersonalInfo` 工具（返回脱敏值 `***`）、`@tool` + `ToolRegistry` 工具系统、LangGraph ReAct 循环。现有浏览器工具 `getTextFromURL`/`click` 是**无头、无状态、一次性**的，无法承载「有头打开 → 用户登录 → 填表」这种需要浏览器跨轮次存活、穿插人工介入的流程。

本需求让 agent 基于 **Playwright MCP 服务**（外部启动、有头、持久化 profile），以一组**粒度工具**注册进 registry，由 agent 按 prompt 中描述的工作流直接驱动，完成简历投递表单的自动填写。**不含**此前已删除的原生 `src/browser/` 版本，也**不复用** `tests/browser_mcp`/`scripts/probe_*` 引用的复杂 `src/browser_mcp` 设计（SessionManager 状态机、内部二次 LLM 决策、回读校验等）。

## 目标

- 用户给出投递 URL → agent 以有头方式打开 → 等待用户登录并切到表单页（浏览器仅一个页面）→ 用户回复「继续」
- agent 先 `browser_snapshot` 检查是否有简历 PDF 上传/解析入口；有则从 `data/CV` 上传简历，等待网页解析自动填写相关字段
- agent 再次 `browser_snapshot`，找出未填的输入框/下拉框，调用 `browser_fill_form` 结合 `getPersonalInfo` 的信息填写
- MCP 工具注册到 registry；个人信息保持脱敏（agent 只决策「控件 ref ← 数据键」，真实值由后台替换后传给 MCP）
- `prompt/prompt.py` 增加对该工作流的描述

## 功能需求

### F1 有头打开投递页

- `browser_navigate` 接收投递页 URL，在 MCP 持久化浏览器（有头）中打开该 URL
- URL 非法/加载失败返回明确错误，对话不中断
- 打开成功后提示用户登录，完成后回复「继续」

### F2 跨轮次存活与登录等待

- 浏览器由外部 MCP 服务持有（有头 + 持久化 profile），跨多次工具调用、多个用户轮次保持打开
- 登录期间 agent 不做任何动作，等待用户回复「继续」后才开始填表流程

### F3 表单快照

- `browser_snapshot` 返回当前页面可交互控件列表（每项含 ref、类型、标签、当前值、可选选项）
- 返回内容足以让 agent 识别：简历上传入口、待填的输入框/下拉框、单选/复选选项

### F4 简历上传与解析等待

- `browser_upload_resume` 接收上传控件 `ref` 与可选「简历标识」（`data/CV` 中的文件名或序号）
- `data/CV` **恰有一份** PDF → 直接上传
- `data/CV` **有多份** PDF → **不自动选择**，返回候选清单（文件名列表），由 agent 转达用户询问用哪一份；用户答复后 agent 再次调用并携带所选简历标识上传
- `data/CV` **无** PDF → 返回明确提示
- 上传后固定短等待，供网页解析并自动填写解析出的字段；返回上传结果说明

### F5 脱敏填表（核心）

- `browser_fill_form` 接收 agent 决策的映射列表，每项 = 控件 `ref` + 个人信息**数据键**（如 `basic_info.id_number`）
- 工具在后台从 `profile.json` 读真实值，替换后再调用 MCP 填表原语（`browser_fill` / `browser_select_option` / 点击单选复选）完成填写
- 真实值只出现在传给 MCP 的参数里，不出现在返回给 agent 的文本中（敏感字段报告时显示 `***`）
- 返回填写报告：已填项、失败项、未匹配项
- agent 通过现有 `getPersonalInfo`（返回脱敏值）获知有哪些数据键可用，据此决策映射

### F6 工作流提示

- `prompt/prompt.py` 增加对该工作流的描述，指导 agent 何时打开 URL、等待登录、快照、上传简历、结合 `getPersonalInfo` 填表

## 非功能需求

- **N1 脱敏**：`getPersonalInfo` 保持返回脱敏值；`browser_fill_form` 用数据键取真实值，agent 全程看不到 profile 真实敏感值
- **N2 MCP 服务外部启动**：假设 Playwright MCP 服务已由用户/脚本启动（有头 + 持久化 profile）；连接失败时工具返回明确错误（如「无法连接 Playwright MCP 服务」）
- **N3 注册机制**：新 MCP 工具用 `@tool` 定义在 `src/tools/builtin/` 下，由 `ToolRegistry.discover` 自动注册、启动日志可见
- **N4 错误隔离**：单次工具执行失败不中断对话，错误以文本返回给 LLM
- **N5 简洁性**：不引入 SessionManager 状态机、内部二次 LLM 决策、回读校验等额外逻辑

## 不做的事

- 不自动登录（扫码/短信由用户完成）
- **不自动提交表单、不检测投递成功**（流程到填表为止，提交由用户人工完成）
- 不实现/保留复杂 `src/browser_mcp` 设计；`tests/browser_mcp`、`scripts/probe_*` 同步废弃或改写
- 不做平台专用适配
- 不处理多标签页（约束浏览器仅一个页面）

## 验收标准

- **AC1**：`browser_navigate` 打开投递 URL，MCP 有头浏览器出现并导航到该页
- **AC2**：登录等待期间浏览器跨轮次保持打开不关闭
- **AC3**：`browser_snapshot` 返回控件列表（ref/类型/标签/当前值/选项），可据此识别上传入口与待填字段
- **AC4**：`data/CV` 恰一份 PDF 时直接上传并等待解析；多份 PDF 时返回候选清单并询问用户，用户选择后能按所选简历上传；无 PDF 时返回明确提示
- **AC5**：`browser_fill_form` 按 agent 传入的 ref+数据键 填写，返回已填/失败/未匹配报告
- **AC6**：整个填写流程中 agent 可见输出不含任何 profile 真实敏感值（如证件号）
- **AC7**：`data/CV` 无 PDF 时 `browser_upload_resume` 返回明确提示
- **AC8**：URL 非法/页面加载失败时返回明确错误，对话不中断
- **AC9**：MCP 服务未启动时工具返回明确连接错误提示
- **AC10**：四个工具均在 registry 可见（启动日志列出工具名）
- **AC11**：`prompt/prompt.py` 包含该工作流描述，agent 能按流程依次调用工具
