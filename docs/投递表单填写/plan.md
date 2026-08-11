# 投递表单填写工具 Plan

## 架构概览

在现有工具系统之上**新增机制而不改动其架构**。核心是 `src/browser/` 模块，含三块：

1. **后台事件循环 + 浏览器会话注册表**（`BrowserManager` 单例）——按 `conversation_id` 管理 `SubmissionSession`，每个会话持有一个有头浏览器。Playwright 全部跑在专属后台事件循环里，保证跨轮次存活
2. **单个有状态工具** `submitApplication`（放在 `src/tools/builtin/` 自动注册）——薄壳，每次调用：读 ContextVar 拿会话ID → 交给 BrowserManager 推进状态机 → 返回指引文本
3. **会话ID透传**（ContextVar）——`routes.py` 的 `event_generator` 里设置，异步上下文一路透传到工具函数

```
routes.py(send_message)
   └─ set ContextVar(conversation_id)
   └─ graph.astream
        └─ tool_node
             └─ registry.execute("submitApplication", {url, action})
                  └─ submit_tool.py 读 ContextVar
                       └─ BrowserManager.submit(conversation_id, url, action)
                            └─ 后台专属事件循环里执行:
                               创建/查找 SubmissionSession → 推进状态机 → 返回文本
```

## 核心数据结构

```python
# src/browser/session.py

class SubmissionStage(str, Enum):
    WAITING_LOGIN = "waiting_login"      # 浏览器已打开，等待用户登录
    WAITING_SUBMIT = "waiting_submit"    # 表单已填写，等待用户提交
    SUBMITTED = "submitted"              # 投递成功（终止态，随即清理会话）

@dataclass
class SubmissionSession:
    conversation_id: str    # 会话标识（registry key）
    stage: SubmissionStage  # 当前阶段
    url: str                # 目标投递页 URL
    browser: Browser        # Playwright 浏览器（有头，保持打开）
    page: Page              # 当前页面
    last_active_at: float   # 最近活跃时间，用于空闲超时
    lock: asyncio.Lock      # 会话级互斥，防止并发调用竞态
```

## 工具接口

```python
# src/tools/builtin/submit_application.py

class Params(BaseModel):
    url: str = Field(default="", description="投递页URL，首次调用必填")
    action: str = Field(default="continue", description="continue=继续推进, cancel=取消投递")

@tool(
    name="submitApplication",
    description=(
        "填写并提交简历投递表单。首次调用传入投递页URL，以有头方式打开浏览器并提示用户登录；"
        "之后用户回复「继续」「已提交」时再次调用本工具推进流程（无需重复传URL），"
        "工具会根据当前进度自动检测表单、按个人信息填写、检测投递成功。"
        "用户要取消时传 action='cancel'。"
    ),
)
async def submitApplication(params: Params) -> ToolResult: ...
```

## 状态机

```
无会话(首次,url) ──→ WAITING_LOGIN ──(检测到表单)──→ WAITING_SUBMIT ──(检测到成功)──→ SUBMITTED
     │                     │                              │                        │
     │                     └─(表单没出现)→ 返回纠错提示       └─(没检测到)→ 返回未确认    └─ 关闭浏览器+清理会话
     │                 再次调用/换新URL → 重启新会话
     └─(url缺失)→ 返回错误    (action=cancel) ──→ 关闭浏览器+清理会话
```

## 模块设计

### 模块 A：`BrowserManager`（src/browser/manager.py）

**职责：** 会话注册表 + 后台事件循环 + 生命周期管理（创建/关闭/空闲清扫）。

- 单例。构造时启动后台线程，线程内 `new_event_loop()` + `run_forever()`，该循环持有全部 Playwright 对象
- `async submit(conversation_id, url, action) -> str`：`run_coroutine_threadsafe` 把 `_handle` 丢进后台循环，`await asyncio.wrap_future()` 桥回调用方循环
- `async _handle(...)`：会话级 `asyncio.Lock` 内执行状态机推进
- 空闲清扫：后台循环内定时任务（每 60s）扫描 `last_active_at`，超 10 分钟未活跃 → 关闭浏览器并移除
- 关键点：**Playwright 对象只存活于后台循环**，不跨循环传递

### 模块 B：`SubmissionSession`（src/browser/session.py）

**职责：** 单个投递会话的数据 + 阶段常量。被 BrowserManager 持有。

### 模块 C：ContextVar（src/browser/context.py）

```python
_current_conversation: ContextVar[str] = ContextVar("current_conversation", default="")
```

**修改 `routes.py`：** 在 `send_message` 的 `event_generator()` 函数体开头 `_current_conversation.set(conversation_id)`（必须设在生成器体内而非外层，保证与图执行同异步上下文）。

### 模块 D：表单检测与填写（src/browser/fill.py）

**职责：** `detect_form(page) -> bool` 与 `fill_form(page) -> dict`。

- `detect_form`：页面可填控件（input/select/textarea）数量 ≥ 阈值（如 3）且含「提交」按钮 → 判定表单已出现
- `fill_form`：遍历表单控件，找每个控件的关联标签（`label[for]`、`aria-label`、邻近文本），归一化后对照**字段匹配表**，从 `profile.json` 取真实值填入；填入后在报告里对 `masked_basic_fields` 对应键显示 `***`
- 字段匹配表集中定义、可扩展：标量字段（姓名/手机/邮箱/性别/年龄/所在地/家乡/证件号码/自我评价…）直接填；经历类列表字段（教育/实习/项目…）v1 尽力匹配单行实例，结构复杂（多行重复区）则归入未匹配清单

### 模块 E：投递成功检测（src/browser/detect.py）

**职责：** `detect_success(page, original_url) -> bool`。

- 启发式：URL 变化（忽略 hash）或页面文本含「投递成功 / 已投递 / 提交成功 / 申请成功」等关键字
- 带超时保护，检测失败不抛异常

### 模块 F：记录接口（src/browser/recorder.py）

**职责：** `record_application_result(session, result: dict) -> None`，本期空实现（`pass`），签名与数据结构预留，供后续「投递进度」模块接入。

### 模块 G：工具壳（src/tools/builtin/submit_application.py）

**职责：** `@tool` 装饰器定义 + URL 基础校验 + 调 `BrowserManager.submit` + 包装 `ToolResult`。不包含任何浏览器逻辑。

## 模块交互

```
轮次1  用户:「帮我投递 https://xxx」
       agent → submitApplication(url) → 打开浏览器导航 → 返回「请扫码登录，完成后回复『继续』」
轮次2  用户:「已登录」
       agent → submitApplication() → 检测表单存在 → fill_form 读profile填写 → 返回「已填:…未匹配:…
                                    请检查，点提交后回复『已提交』」
轮次3  用户:「已提交」
       agent → submitApplication() → detect_success → 记录接口(空) → 关闭浏览器清理会话
                                    → 返回「投递成功」
```

## 文件组织

```
src/browser/
├── __init__.py              # 新建 — 导出模块内工具所需的公共符号
├── context.py               # 新建 — ContextVar
├── session.py               # 新建 — SubmissionSession / SubmissionStage
├── manager.py               # 新建 — BrowserManager 单例 + 后台循环 + 生命周期
├── fill.py                  # 新建 — detect_form / fill_form + 字段匹配表
├── detect.py                # 新建 — detect_success
└── recorder.py              # 新建 — record_application_result（预留空实现）
src/tools/builtin/submit_application.py  # 新建 — @tool submitApplication 工具壳
src/api/routes.py            # 修改 — event_generator 内设置 ContextVar
src/tools/builtin/open_browser.py        # 顺带修复 docstring 复制粘贴错误（非本功能，属清理）
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 状态持久化 | 服务端 `BrowserManager` 注册表（key=conversation_id） | 图每次请求重建，LangGraph state 不跨轮次；浏览器对象不可序列化，不宜入 state |
| 会话ID透传 | ContextVar，在 `event_generator` 体内设置 | 工具签名与注册中心不改，改动最小；同异步上下文自然透传 |
| 浏览器存活 | 后台线程专属事件循环持有 Playwright | Playwright 对象绑定创建它的 loop，跨请求 loop 可能切换，需固定 loop |
| 工具形态 | 单个有状态工具 + 阶段状态机 | 已与用户确认；LLM 职责简单，状态机集中可测 |
| 阶段推进 | 状态机 + 页面真实状态检测 | 不盲信用户措辞，表单没出现就提示，更稳 |
| 表单填写 | 通用标签匹配（label ↔ profile键映射） | 不做平台专用适配，集中扩展 |
| 成功检测 | 启发式（关键字 + URL 变化） | 本期简化，spec 明确后续细化 |
| 记录接口 | `recorder.py` 空实现 | spec F6 预留，不落库 |
| 会话清理 | 完成/取消即关 + 空闲 10 分钟清扫 | 防资源泄漏 |
| 并发安全 | 会话级 `asyncio.Lock`（后台循环内） | 防止同一会话并发调用竞态 |
