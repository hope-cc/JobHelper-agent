# 基于 Playwright MCP 的简历投递表单自动填写 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/browser_mcp/__init__.py` | 包导出 |
| 新建 | `src/browser_mcp/client.py` | MCP 短连接 call_tool 原语 |
| 新建 | `src/browser_mcp/fill.py` | parse_snapshot / 控件判定 / 脱敏取值 |
| 新建 | `src/browser_mcp/upload.py` | 简历扫描 / 多份解析 / 上传等待 |
| 新建 | `src/tools/builtin/browser_navigate.py` | 有头打开投递页工具 |
| 新建 | `src/tools/builtin/browser_snapshot.py` | 表单快照工具 |
| 新建 | `src/tools/builtin/browser_upload_resume.py` | 上传简历工具 |
| 新建 | `src/tools/builtin/browser_fill_form.py` | 脱敏填表工具 |
| 修改 | `src/prompt/prompt.py` | 增加投递工作流描述 |
| 改写 | `tests/browser_mcp/` | 保留 parse/upload/脱敏单测，删 llm_fill/manager/session/catalog/verify |
| 改写 | `scripts/probe_mcp_form.py` | 端到端验证脚本（废弃 probe_e2e/probe_llm_upload/snapshot_probe） |

## T1: src/browser_mcp/client.py

**文件：** `src/browser_mcp/client.py`
**依赖：** 无
**步骤：**
1. 定义 `DEFAULT_MCP_URL = "http://127.0.0.1:8931/mcp"`
2. 实现 `async def call_tool(name: str, args: dict) -> tuple[str, bool]`
   - `from mcp import ClientSession` + `from mcp.client.streamable_http import streamable_http_client`
   - `async with streamable_http_client(url) as ...: async with ClientSession(...) as session: await session.initialize(); result = await session.call_tool(name, args)`
   - 将 result.content 里的文本块拼接；`result.isError` 作为 is_error
   - 连接/初始化失败捕获异常，返回 `("无法连接 Playwright MCP 服务（{url}），请确认已用 npx @playwright/mcp --port 8931 启动", True)`

**验证：** `python -c "import src.browser_mcp.client"` 无导入错误（MCP 服务未启动时，仅调用 call_tool 才报连接错误）

## T2: src/browser_mcp/fill.py

**文件：** `src/browser_mcp/fill.py`
**依赖：** T1（无硬依赖，可并行）
**步骤：**
1. 定义 `Element` dataclass：ref/role/name/value/selected/options
2. 实现 `parse_snapshot(text) -> list[Element]`：解析 MCP snapshot 文本（兼容 `test_parse.py` 已有断言的各种格式：值后缀、引号值、combobox option 缩进行、[checked]、radio 组、旧格式 `[ref=2] textbox "姓名"`）
3. 实现 `is_upload_candidate(el)`：role=file，或 role=button 且 name 含「选择文件/上传简历/上传附件/Upload/上传」等
4. 实现 `is_action_button(el)`：name 含「提交/搜索/登录」等动作词
5. 实现 `is_fillable(el)`：textbox/textarea/combobox
6. 实现 `is_option_el(el)`：radio/checkbox
7. 实现 `resolve_profile_value(profile, data_key)`：支持 `basic_info.x`、`education[i].y` 列表、顶层键（`self_evaluation`）
8. 实现 `display_value(data_key, value, profile)`：data_key 的首段（如 `basic_info.id_number` → `basic_info.id_number` 前缀命中 `masked_basic_fields` 键）显示 `***`
9. 实现 `match_combobox_value(options, value)`：精确或包含匹配 option value，返回匹配项 value

**验证：** `D:/coding/Anaconda/envs/agent/python.exe -m pytest tests/browser_mcp/test_parse.py -q` 通过

## T3: src/browser_mcp/upload.py

**文件：** `src/browser_mcp/upload.py`
**依赖：** T2（find_upload_control 用 Element）
**步骤：**
1. `DATA_CV_DIR = <项目根>/data/CV`
2. `list_resume_pdfs() -> list[Path]`：扫描 `.pdf`，按修改时间倒序
3. `find_upload_control(elements) -> Element | None`：首个 `is_upload_candidate`
4. `resolve_resume(spec: str) -> Path | list[Path] | str`：
   - spec 为空：0 份 → 返回提示 str；1 份 → 返回 Path；多份 → 返回候选 list[Path]
   - spec 为文件名 → 匹配返回 Path；匹配不到 → 提示 str
   - spec 为序号（1 起）→ 返回对应 Path；越界 → 提示 str
5. `async upload_and_wait(client, ref, path)`：调 `client.call_tool("browser_upload_file", {"ref": ref, "files": [str(path)]})`，随后 `await asyncio.sleep(5)` 等待解析，返回 (text, err)

**验证：** `python -m pytest tests/browser_mcp/test_upload.py -q` 通过（data/CV 当前含 PDF）

## T4: 四个粒度工具

**文件：** `src/tools/builtin/browser_navigate.py` / `browser_snapshot.py` / `browser_upload_resume.py` / `browser_fill_form.py`
**依赖：** T1/T2/T3
**步骤：**
1. `browser_navigate`：Params{url}；urlparse 校验 scheme/netloc；调 `call_tool("browser_navigate", {"url": url})`；返回结果 +「请登录并切到表单页，完成后回复『继续』」
2. `browser_snapshot`：无参；调 `call_tool("browser_snapshot", {})` → `parse_snapshot` → 过滤出 is_fillable / is_upload_candidate / is_option_el 的控件 → 紧凑文本（每行 `[ref] 类型 名称 当前值(或空) [上传候选]`）
3. `browser_upload_resume`：Params{ref="", resume=""}；`list_resume_pdfs` → `resolve_resume`；多份 → 返回候选清单文本（引导用户选择后回复序号或文件名）；单份 → ref 为空时先 snapshot 找 find_upload_control；调 `upload_and_wait`；返回结果
4. `browser_fill_form`：Params{items:[{ref, data_key}]}；加载 `profile_storage.load()`（空 → 返回「请先保存个人信息」）；调 `call_tool("browser_snapshot", {})` → parse_snapshot 建 ref→Element 映射；逐项：
   - resolve 真实值；无值 → 未匹配（「数据键无值」）
   - ref 不在映射 → 未匹配（「无效 ref」）
   - textbox/textarea → `browser_fill {ref, value}`；combobox → match 后 `browser_select_option {ref, values:[v]}`（匹配不到→未匹配「选项不匹配」）；radio → 从 options/组内找对应值 ref 后 `browser_click`；checkbox → 值命中「是/同意/1」等时 `browser_click`
   - 报告：已填 / 失败 / 未匹配；敏感 data_key 显示 `***`
   - 每个工具用 `@tool` 装饰、`ToolResult` 返回、异常捕获返回 is_error

**验证：** 启动后端后 registry 日志列出 4 个新工具；`python -c "from src.tools.registry import ToolRegistry; ToolRegistry.get_instance().discover(); print([d['name'] for d in ToolRegistry.get_instance().list_definitions()])"` 含 4 个工具名

## T5: prompt.py 工作流描述

**文件：** `src/prompt/prompt.py`
**依赖：** T4
**步骤：**
1. 新增 `SubmitFlow` 常量，描述：browser_navigate 打开并提示登录 → 用户回复「继续」后 browser_snapshot → 有上传入口则 browser_upload_resume（多份先询问用户）→ 再 browser_snapshot 找未填字段 → getPersonalInfo 取数据键 → browser_fill_form 按 ref+数据键 填表并汇报
2. 在 `build_system_prompt()` 的拼接中加入 `SubmitFlow`

**验证：** `python -c "from src.prompt.prompt import build_system_prompt; print(build_system_prompt())"` 输出包含工作流描述

## T6: 改写测试与探针

**文件：** `tests/browser_mcp/`、`scripts/`
**依赖：** T2/T3/T4
**步骤：**
1. `tests/browser_mcp/test_parse.py`：保留（对齐 T2）
2. `tests/browser_mcp/test_upload.py`：保留（对齐 T3）
3. 新增 `tests/browser_mcp/test_fill_tools.py`：脱敏取值（resolve_profile_value/display_value/match_combobox_value/控件判定）
4. 删除 `test_llm_fill.py`、`test_verify.py`、`test_catalog.py`
5. 删除 `scripts/probe_e2e.py`、`scripts/probe_llm_upload.py`、`scripts/snapshot_probe.py`；新增 `scripts/probe_mcp_form.py`（连接真实 MCP，本地 data: 表单页跑一遍 snapshot→upload→fill，打印报告）
6. 删除 `scripts/cleanup_mcp.ps1`（如已无用）

**验证：** `python -m pytest tests/browser_mcp -q` 全部通过

## T7: 端到端验证

**文件：** 无
**依赖：** T1-T6
**步骤：**
1. 启动 Playwright MCP：`npx @playwright/mcp --port 8931`（有头）
2. 运行 `scripts/probe_mcp_form.py`，观察 snapshot/upload/fill 流程输出
3. 启动后端 `python -m src.api.main`，确认日志列出 4 个工具；启动前端，在聊天中给投递 URL，观察 agent 按工作流调用工具

**验证：** probe 脚本各环节 PASS；后端日志含 4 个工具名

## 执行顺序

```
T1 → T2 → T3 → T4 → T5
          ↘
T2 → T6（依赖 T2/T3/T4）→ T7
```
