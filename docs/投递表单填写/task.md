# 投递表单填写工具 Tasks

> Python 解释器：`D:\coding\Anaconda\envs\agent\python.exe`（以下简称 `PY`）

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/browser/__init__.py` | 包骨架 |
| 新建 | `src/browser/context.py` | ContextVar（会话ID透传） |
| 新建 | `src/browser/session.py` | SubmissionStage / SubmissionSession |
| 新建 | `src/browser/recorder.py` | 记录接口预留（空实现） |
| 新建 | `src/browser/fill.py` | 表单检测 + 字段匹配填写 + 字段匹配表 |
| 新建 | `src/browser/detect.py` | 投递成功检测 |
| 新建 | `src/browser/manager.py` | BrowserManager 单例 + 后台循环 + 状态机 + 生命周期 |
| 新建 | `src/tools/builtin/submit_application.py` | submitApplication 工具壳 |
| 修改 | `src/api/routes.py` | event_generator 内设置 ContextVar |
| 修改 | `src/tools/builtin/open_browser.py` | 修复 docstring 复制粘贴错误（清理项） |

## T1: 创建 src/browser 包骨架

**文件：** `src/browser/__init__.py`
**依赖：** 无
**步骤：**
1. 创建 `src/browser/` 目录
2. 新建 `__init__.py`，留包级 docstring（说明本包负责投递表单填写的浏览器会话管理）

**验证：** `PY -c "import src.browser"` 成功无报错

## T2: ContextVar

**文件：** `src/browser/context.py`
**依赖：** 无
**步骤：**
1. 定义 `_current_conversation: ContextVar[str]`，默认 `""`
2. 提供 `set_current_conversation(cid)` / `get_current_conversation()` 两个辅助函数

**验证：** `PY -c "from src.browser.context import set_current_conversation, get_current_conversation; set_current_conversation('c1'); assert get_current_conversation()=='c1'"` 通过

## T3: 会话数据结构

**文件：** `src/browser/session.py`
**依赖：** T1
**步骤：**
1. 定义 `SubmissionStage(str, Enum)`：`WAITING_LOGIN` / `WAITING_SUBMIT` / `SUBMITTED`
2. 定义 `@dataclass SubmissionSession`：conversation_id、stage、url、browser、page、last_active_at、lock（asyncio.Lock），字段类型与 plan.md 一致

**验证：** `PY -c "from src.browser.session import SubmissionSession, SubmissionStage; s=SubmissionSession(conversation_id='c1', stage=SubmissionStage.WAITING_LOGIN, url='', browser=None, page=None, last_active_at=0.0, lock=None); assert s.stage is SubmissionStage.WAITING_LOGIN"` 通过

## T4: 记录接口（预留空实现）

**文件：** `src/browser/recorder.py`
**依赖：** T3
**步骤：**
1. 定义 `record_application_result(session, result: dict) -> None`
2. 函数体 `pass`，docstring 说明：预留接口，供后续「投递进度」模块接入，本期不落库

**验证：** `PY -c "from src.browser.recorder import record_application_result; record_application_result(None, {}); print('ok')"` 输出 ok 不报错

## T5: 表单检测与填写

**文件：** `src/browser/fill.py`
**依赖：** T1
**步骤：**
1. 定义集中式字段匹配表 `FIELD_MAP`：中文标签模式（如「姓名」「手机」「邮箱」「性别」「学校」「学历」「公司」「自我评价」…）→ profile 键路径
2. 实现纯函数 `match_field(label_text, profile) -> (key, value) | None`（不含浏览器，可单测）
3. 实现 `detect_form(page) -> bool`：可填控件数量 ≥ 3 且含「提交」按钮
4. 实现 `fill_form(page) -> dict`：遍历表单控件 → 取关联标签 → 匹配 → 填真实值 → 返回 `{"filled": [...], "unmatched": [...], "report": str}`
5. 报告生成时对 `masked_basic_fields` 中出现的键值显示 `***`
6. 个人信息不存在（`profile_storage.load()` 返回 None）时返回引导提示文本

**验证：** 用桩 page 对象（含 input/select、label、提交按钮）调用 `fill_form`，断言报告包含已填字段与未匹配字段；敏感字段值显示 `***`；`detect_form` 对控件少的页面返回 False

## T6: 投递成功检测

**文件：** `src/browser/detect.py`
**依赖：** T1
**步骤：**
1. 定义成功关键字列表：投递成功 / 已投递 / 提交成功 / 申请成功 等
2. 实现 `detect_success(page, original_url) -> bool`：页面 URL（忽略 hash）与 original_url 不同，或页面文本含任一关键字 → True
3. 页面访问异常时捕获并返回 False，不抛异常

**验证：** 用桩 page（可控 `.url` 与 `.content()`）分别测：含关键字 → True；无关键字且 URL 未变 → False；`content()` 抛异常 → False

## T7: BrowserManager

**文件：** `src/browser/manager.py`
**依赖：** T2, T3, T4, T5, T6
**步骤：**
1. 单例 `get_instance()`
2. 构造时启动后台线程：`new_event_loop()` + `run_forever()`（daemon 线程）
3. `async submit(conversation_id, url, action) -> str`：`run_coroutine_threadsafe(self._handle(...), self._loop)` + `await asyncio.wrap_future(...)`
4. `async _handle(...)`：
   - action == "cancel" → 关闭会话 → 返回「已取消投递」
   - 无会话：url 为空 → 返回错误；否则校验 url 格式、启动有头浏览器导航、创建会话（stage=WAITING_LOGIN）→ 返回登录指引
   - stage=WAITING_LOGIN：`detect_form` 未过 → 返回纠错提示；已过 → `fill_form` 填写 → stage=WAITING_SUBMIT → 返回填写报告+提交指引
   - stage=WAITING_SUBMIT：`detect_success` 为真 → stage=SUBMITTED → 调 `record_application_result` → 关闭清理 → 返回「投递成功」；为假 → 返回未确认提示
   - 会话已有且传入不同 url → 关闭旧会话，按新 url 重启新会话
   - 全程在会话级 `asyncio.Lock` 内执行
5. 空闲清扫：后台循环内每 60s 扫描，`now - last_active_at > 600` → 关闭浏览器并移除

**验证：** 无会话且 url 为空调用 → 返回错误文本不崩溃；带真实 url 调用 → 本机弹出有头浏览器窗口（手动确认），随后 `action="cancel"` → 窗口关闭

## T8: 工具壳

**文件：** `src/tools/builtin/submit_application.py`
**依赖：** T7
**步骤：**
1. 定义 `Params(BaseModel)`：`url`（默认 ""）、`action`（默认 "continue"，注释注明 continue/cancel）
2. `@tool(name="submitApplication", description=plan.md 中的描述)` 装饰 async 函数
3. 函数内：URL 基础格式校验（非空、含协议头）→ 调 `BrowserManager.get_instance().submit(cid, url, action)` → 包装 `ToolResult`（错误时 `is_error=True`）
4. 通过 `src.browser.context.get_current_conversation()` 拿会话ID

**验证：** `PY -c "from src.tools.registry import ToolRegistry; r=ToolRegistry(); r.discover(); assert 'submitApplication' in [t['name'] for t in r.list_definitions()]"` 通过

## T9: routes.py 注入 ContextVar

**文件：** `src/api/routes.py`
**依赖：** T2
**步骤：**
1. 导入 `src.browser.context.set_current_conversation`
2. 在 `send_message` 的 `event_generator()` **函数体开头**调用 `set_current_conversation(conversation_id)`（必须设在生成器体内，确保与图执行同异步上下文）

**验证：** 启动后端，任意发一条消息正常返回 SSE 流；代码 review 确认 set 调用在生成器体内而非外层

## T10: 修复 open_browser.py docstring

**文件：** `src/tools/builtin/open_browser.py`
**依赖：** 无
**步骤：**
1. 将模块 docstring 从「getPersonalInfo 工具…」改为正确的 openBrowser 描述（当前是复制粘贴错误）

**验证：** 读取文件确认 docstring 与实际功能一致

## 执行顺序

```
T1 → T2 → T3 → T4 ─┐
                T5 ─┴→ T7 → T8 → T9 → T10
                T6 ─┘（T5/T6 可并行）
```
