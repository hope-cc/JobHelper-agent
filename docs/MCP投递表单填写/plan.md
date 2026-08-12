# 基于 Playwright MCP 的简历投递表单自动填写 Plan

## 架构概览

在现有工具系统上**新增四个粒度工具 + 一个共享 MCP 辅助模块**，不改动工具系统架构（`@tool` + `ToolRegistry` + ReAct 循环）。

```
src/browser_mcp/（共享辅助，新建）
  client.py   — MCP 短连接 call_tool 原语
  fill.py     — parse_snapshot / 控件判定 / profile 脱敏取值
  upload.py   — 简历扫描 / 多份解析 / 上传+等待

src/tools/builtin/（四个粒度工具，新建，自动注册进 registry）
  browser_navigate.py      — 有头打开投递页
  browser_snapshot.py      — 返回表单控件快照
  browser_upload_resume.py — 上传 data/CV 简历并等待解析
  browser_fill_form.py     — 按 ref+数据键 脱敏填表

src/prompt/prompt.py       — 增加投递工作流描述
tests/browser_mcp/ + scripts/  — 改写/废弃对齐简化设计
```

## 核心数据结构

```python
# fill.py —— 快照解析结果
@dataclass
class Element:
    ref: str
    role: str            # textbox / combobox / radio / checkbox / button / file ...
    name: str            # 标签，如「姓名」「选择文件」
    value: str = ""
    selected: bool = False
    options: list[dict] = field(default_factory=list)  # 下拉/单选 [{value, selected}]

# browser_fill_form.py —— 填表映射项
@dataclass
class FillItem:
    ref: str         # 控件 ref（来自 browser_snapshot）
    data_key: str    # 个人信息数据键，如 basic_info.id_number / education[0].school_name / self_evaluation
```

## 模块设计

### A. MCP 客户端辅助 `src/browser_mcp/client.py`
- `DEFAULT_MCP_URL = "http://127.0.0.1:8931/mcp"`
- `async call_tool(name, args) -> (text, is_error)`：`streamable_http_client` + `ClientSession` 短连接调用；连接失败返回明确错误「无法连接 Playwright MCP 服务…」。
- 关键点：**每次调用短连接、无共享状态**，浏览器/登录态由 MCP 服务端持有（`--user-data-dir` 持久化），天然跨轮次存活且并发安全。

### B. 快照解析与填表辅助 `src/browser_mcp/fill.py`
- `parse_snapshot(text) -> list[Element]`：解析 MCP `browser_snapshot` 输出（复用 `test_parse.py` 已校验的格式）
- `is_upload_candidate(el)` / `is_fillable(el)`：上传入口 / 可填控件判定
- `resolve_profile_value(profile, data_key) -> str | None`：取真实值（支持 `basic_info.x`、`education[i].y`、`self_evaluation`）
- `display_value(data_key, value, profile) -> str`：敏感键（`masked_basic_fields`）显示 `***`
- `match_combobox_value(options, value)`：下拉选项匹配（含前缀包含）

### C. 简历上传辅助 `src/browser_mcp/upload.py`
- `list_resume_pdfs() -> list[Path]`：`data/CV` 下 PDF，修改时间倒序
- `find_upload_control(elements) -> Element | None`：首个上传候选
- `resolve_resume(spec)`：无 spec → 0 份提示 / 1 份直接返回 / 多份返回候选清单；有 spec → 按文件名或序号匹配
- `async upload_and_wait(client, ref, path)`：MCP `browser_upload_file` {ref, files:[path]} + 固定短等待（约 5s）供网页解析

### D. `browser_navigate`（`src/tools/builtin/browser_navigate.py`）
- Params: `{url}`；URL 基础校验；调 MCP `browser_navigate`；返回「已打开，请登录后回复继续」。

### E. `browser_snapshot`（`src/tools/builtin/browser_snapshot.py`）
- 无参；调 MCP `browser_snapshot` → `parse_snapshot` → 过滤出可交互控件、标记上传候选 → 紧凑文本返回。

### F. `browser_upload_resume`（`src/tools/builtin/browser_upload_resume.py`）
- Params: `{ref, resume}`；多份→返回候选清单；单份→上传+等待解析；无→提示。

### G. `browser_fill_form`（`src/tools/builtin/browser_fill_form.py`）
- Params: `{items: [{ref, data_key}]}`
- 流程：加载 profile → 重新 snapshot 确认各 ref 的 role → 逐项 resolve 真实值并按 role 填：
  - textbox/textarea → MCP `browser_fill` {ref, value}
  - combobox → MCP `browser_select_option` {ref, values:[匹配值]}（匹配不到→未匹配）
  - radio/checkbox → MCP `browser_click` 对应选项 ref
- 返回脱敏报告：已填 / 失败 / 未匹配。

### H. prompt 工作流 `src/prompt/prompt.py`
- 新增小节：browser_navigate 打开并提示登录 → 回复「继续」后 snapshot → 有上传入口则 upload（多份先问用户）→ 再 snapshot 找未填字段 → getPersonalInfo → browser_fill_form 填表。

## 模块交互

```
用户:「帮我投递 https://xxx」
agent → browser_navigate(url) ──→ 有头浏览器打开，提示登录
用户:「继续」
agent → browser_snapshot() ─────→ 控件列表（含上传候选）
agent → browser_upload_resume(ref) ── 单份→上传+等待解析 / 多份→候选清单→询问用户→再传 resume
agent → browser_snapshot() ─────→ 未填字段
agent → getPersonalInfo() ──────→ 数据键 + 脱敏值
agent → browser_fill_form([{ref,data_key},…]) ──→ 后台真实值→MCP 填表→脱敏报告
```

## 文件组织

```
src/browser_mcp/
├── __init__.py              # 新建
├── client.py                # 新建
├── fill.py                  # 新建
└── upload.py                # 新建
src/tools/builtin/
├── browser_navigate.py      # 新建
├── browser_snapshot.py      # 新建
├── browser_upload_resume.py # 新建
└── browser_fill_form.py     # 新建
src/prompt/prompt.py         # 修改 — 增加工作流描述
tests/browser_mcp/           # 改写 — 保留 parse/upload/脱敏取值单测，删除 llm_fill/manager/session/catalog/verify
scripts/probe_*.py           # 废弃 3 个引用已删除模块的探针；新增 probe_mcp_form.py 端到端验证
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| MCP 连接 | **共享持久会话**（`streamable_http_client` + 单例 `ClientSession`，asyncio.Lock 串行化） | 实测发现：Playwright MCP 在客户端会话终止时重置页面，短连接无法跨调用保留浏览器状态；持久会话 + 串行锁同时满足状态保留与并发安全 |
| 浏览器存活 | 外部 `npx @playwright/mcp --port 8931 --user-data-dir <data/browser-profile>` 有头启动 | 登录态持久化、跨轮次存活；沿用探针方式 |
| 脱敏 | getPersonalInfo 返回脱敏值；browser_fill_form 用 data_key 后台取真实值，报告脱敏显示 | 满足「agent 决策映射、后台替换」 |
| 多份简历 | 返回候选清单，agent 询问用户选择 | 已确认需求 |
| 上传后等待 | 先 `browser_click` 打开文件选择器 + `browser_file_upload {paths}`，随后固定短等待（约 5s） | Playwright MCP 上传工具为 `browser_file_upload`（接收 paths，无 ref）；点击→上传→等待解析 |
| 填充原语 | textbox/textarea→`browser_fill_form`（MCP）；combobox→`browser_select_option`；radio/checkbox→`browser_click` | 实测：MCP `browser_fill_form` 对文本/下拉正确、对单选执行 uncheck（有 bug），故单选/复选用 click |
| 状态管理 | 无 SessionManager / 无内部二次 LLM / 无回读校验 | 符合「不要写太复杂」 |
| 工具命名 | browser_navigate / browser_snapshot / browser_upload_resume / browser_fill_form | 贴合描述，与 MCP 原生名区分 |
| 应用退出 | FastAPI lifespan 关闭时调用 `client.close()` | 避免事件循环退出时异步生成器被强制关闭产生告警 |
