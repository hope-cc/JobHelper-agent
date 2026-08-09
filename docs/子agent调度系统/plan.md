# 子Agent调度系统 Plan

## 架构概览

在现有工具系统之上新增 `src/sub_agent/` 包，包含两个模块：

```
                        ┌──────────────────────────┐
                        │     ReAct 图（不变）        │
                        │  chat_node ⇄ tool_node    │
                        └──────────┬───────────────┘
                                   │ 调用 dispatch_tasks 工具
                                   ▼
                        ┌──────────────────────────┐
                        │  dispatch_tasks 工具       │
                        │  (src/tools/builtin/)      │
                        │  解析参数 → 创建调度器       │
                        │  → dispatch() → 立即返回    │
                        └──────────┬───────────────┘
                                   │ 创建
                                   ▼
                        ┌──────────────────────────┐
                        │     TaskDispatcher        │
                        │     (src/agent/)           │
                        │                            │
                        │  ┌──────────────┐         │
                        │  │ asyncio.Queue │         │
                        │  │  (task queue) │         │
                        │  └──────┬───────┘         │
                        │         │ pop              │
                        │    ┌────┴────┐             │
                        │    ▼         ▼             │
                        │  Worker1  Worker2  ...     │
                        │    │         │              │
                        │    └────┬────┘             │
                        │         │ on_task_complete  │
                        │         ▼                   │
                        │     callback (调用方实现)    │
                        └───────────────────────────┘
```

| 组件 | 位置 | 职责 |
|------|------|------|
| `TaskDispatcher` | `src/sub_agent/dispatcher.py` | 任务队列管理、Worker 创建、并发控制、结果回调 |
| `dispatch_tasks` 工具 | `src/tools/builtin/dispatch_tasks.py` | 将调度器包装为 LLM 可调用的工具，解析 JSON 参数后创建 Dispatcher |
| 子 agent 执行函数 | 调用方提供（通过 `worker_fn` 注入） | 执行单项任务，返回 TaskResult。Dispatcher 不关心内部实现 |

**核心设计原则：调度器不接触 LLM。** Dispatcher 不知道子 agent 是什么——它只接收一个 `worker_fn: Callable[[TaskItem], Awaitable[TaskResult]]`，调度器负责"何时调、并发几个"，调用方负责"调了之后怎么执行"。

---

## 核心数据结构

### TaskItem

```python
# 任务项。Dispatcher 不定义固定字段，原样透传给 worker_fn。
# 调用方按业务需要构造（如 {"url": "...", "action": "click", "company_name": "..."}）。
TaskItem = dict[str, Any]
```

### TaskResult

```python
@dataclass
class TaskResult:
    """子 agent 完成一项任务后的结果。"""
    task: dict          # 原始 TaskItem，用于结果关联
    output: str         # 子 agent 的文本输出
    success: bool       # 是否成功
    error: str | None   # 失败时的错误信息，成功时为 None
```

### TaskCallback

```python
# 任务完成回调。每完成一项任务调用一次。由调用方注入。
TaskCallback = Callable[["TaskResult"], Awaitable[None]]
```

### TaskDispatcher

```python
class TaskDispatcher:
    """任务调度器。
    
    接收任务列表，按并发上限创建 Worker 协程，每个 Worker
    从队列取任务 → 调用 worker_fn 执行 → 触发 on_task_complete →
    取下一项，直到队列为空。
    """

    def __init__(
        self,
        max_concurrency: int,
        worker_fn: Callable[[TaskItem], Awaitable[TaskResult]],
        on_task_complete: TaskCallback | None = None,
    ): ...

    async def dispatch(self, tasks: list[TaskItem]) -> str:
        """将任务列表放入队列，启动 Worker 协程（后台运行），立即返回摘要。
        
        Returns:
            "已启动 {max_concurrency} 个子 agent 处理 {len(tasks)} 项任务"
        """
        ...

    async def wait_all(self) -> list[TaskResult]:
        """等待所有任务完成，返回全部结果列表。调用方可选调用。"""
        ...

    @property
    def results(self) -> list[TaskResult]:
        """已完成的任务结果（实时累积）。"""
        ...

    @property
    def is_running(self) -> bool:
        """是否仍有未完成的任务。"""
        ...
```

---

## 模块设计

### 模块 A：TaskDispatcher（`src/agent/dispatcher.py`）

**职责：** 任务队列管理、Worker 协程调度、并发控制、结果回调。这是调度系统的核心，与 LLM 和工具系统完全解耦。

**对外接口：**
- `__init__(max_concurrency, worker_fn, on_task_complete=None)` — 构造器，接收并发数、任务执行函数、结果回调
- `async dispatch(tasks: list[dict]) -> str` — 启动调度，填充队列 + 创建 Worker 协程，立即返回摘要字符串
- `async wait_all() -> list[TaskResult]` — 阻塞等待全部任务完成，返回完整结果列表
- `results` (property) — 实时返回已完成的结果
- `is_running` (property) — 是否还有未完成任务

**依赖：** 仅 `asyncio`，无项目内部依赖。

**内部实现要点：**
```python
class TaskDispatcher:
    def __init__(self, max_concurrency, worker_fn, on_task_complete=None):
        self._max_concurrency = max_concurrency
        self._worker_fn = worker_fn
        self._on_task_complete = on_task_complete
        self._queue: asyncio.Queue = asyncio.Queue()
        self._results: list[TaskResult] = []
        self._pending: int = 0           # 未完成任务计数
        self._done_event = asyncio.Event()
        self._worker_tasks: list[asyncio.Task] = []

    async def dispatch(self, tasks):
        for t in tasks:
            await self._queue.put(t)
        self._pending = len(tasks)
        self._done_event.clear()
        # 启动 max_concurrency 个 Worker（实际受任务数限制）
        n = min(self._max_concurrency, len(tasks)) if tasks else 0
        for i in range(n):
            self._worker_tasks.append(asyncio.create_task(self._worker(i)))
        # 调度清理协程
        asyncio.create_task(self._monitor())
        return f"已启动 {n} 个子 agent 处理 {len(tasks)} 项任务"

    async def _worker(self, worker_id):
        while True:
            try:
                task = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                result = await self._worker_fn(task)
            except Exception as exc:
                result = TaskResult(task=task, output=str(exc),
                                    success=False, error=str(exc))
            self._results.append(result)
            self._pending -= 1
            if self._on_task_complete:
                await self._on_task_complete(result)
        # Worker 退出：若所有任务完成则设置 event
        if self._pending <= 0:
            self._done_event.set()

    async def _monitor(self):
        """等待所有 Worker 退出后设置完成信号。"""
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._done_event.set()

    async def wait_all(self):
        await self._done_event.wait()
        return list(self._results)
```

**并发模型说明：**
- `dispatch()` 中 `asyncio.create_task(self._worker(i))` 创建 N 个 Worker 协程，它们在同一个 event loop 中并发运行
- Worker 内部没有显式的 `Semaphore`——并发数由 Worker 数量自然控制。N 个 Worker = 最多 N 个 `worker_fn` 同时执行
- 每个 Worker 内部是串行的：取一个任务 → 执行 → 回调 → 取下一个，直到队列空

### 模块 B：dispatch_tasks 工具（`src/tools/builtin/dispatch_tasks.py`）

**职责：** 将 TaskDispatcher 包装为 LLM 可调用的 `@tool`。解析主 agent 传入的 JSON 参数，构造 Dispatcher 并执行。

**对外接口：**
```python
# Pydantic 参数模型
class DispatchTasksParams(BaseModel):
    tasks: list[dict]              # 任务列表
    max_concurrency: int = 3       # 并发上限，默认 3

# @tool 装饰的函数
@tool(name="dispatch_tasks", description="...")
async def dispatch_tasks(params: DispatchTasksParams) -> str:
    ...
```

**依赖：** `TaskDispatcher`、`worker_fn`（通过模块级变量注入，类似 routes.py 中注入 LLM client 的模式）

**注入机制：**
```python
# 模块级变量，由 main.py 在启动时注入
_worker_fn: Callable | None = None
_on_complete: TaskCallback | None = None

def set_worker_fn(fn): ...
def set_on_complete(cb): ...
```

### 模块 C：调用方集成（`src/sub_agent/worker.py` —— 占位，本期不实现）

**职责：** 提供子 agent 的执行函数 `worker_fn`。调用方在此构造子 agent 的 LLM 客户端、上下文、提示词，执行单项任务并返回 `TaskResult`。

**本期范围：** 只提供一个 mock/stub 实现用于测试，以及清晰的接口约定。真实实现由用户后续完成。

---

## 模块交互

### 整体调用链

```
主 agent (chat_node)
    │ LLM 决定调用 dispatch_tasks
    ▼
tool_node
    │ registry.execute("dispatch_tasks", {...})
    ▼
dispatch_tasks 工具函数
    │ 1. 解析 DispatchTasksParams
    │ 2. 读取注入的 _worker_fn, _on_complete
    │ 3. dispatcher = TaskDispatcher(concurrency, _worker_fn, _on_complete)
    │ 4. await dispatcher.dispatch(tasks)  ← 立即返回
    │ 5. 保存 dispatcher 引用（供 wait_all 或查询状态）
    ▼
Dispatcher.dispatch()
    │ 1. 填充 asyncio.Queue
    │ 2. asyncio.create_task(_worker(0)), _worker(1), ...
    │ 3. asyncio.create_task(_monitor())
    │ 4. return "已启动 N 个子 agent ..."
    ▼
Worker 协程（后台运行）
    │ while queue not empty:
    │   task = queue.get_nowait()
    │   result = await _worker_fn(task)     ← 调用方提供的子 agent 执行
    │   await _on_task_complete(result)      ← 调用方提供的结果回调
    │   queue.task_done()
    ▼
_monitor 协程（后台运行）
    │ await asyncio.gather(*workers)
    │ _done_event.set()
```

### 时序

```
主 agent          dispatch_tasks       TaskDispatcher        Worker1        Worker2
  │                    │                     │                   │              │
  ├──调用工具──────────→│                     │                   │              │
  │                    ├──dispatch(tasks)───→│                   │              │
  │                    │                     ├──create_task()───→│              │
  │                    │                     ├──create_task()──────────────────→│
  │                    │                     ├──create_task(monitor)            │
  │                    │←──"已启动..."───────│                   │              │
  │←──立即返回─────────│                     │                   │              │
  │                    │                     │                   │              │
  │  (主 agent 继续)    │                     │               task1执行          │
  │  可以回复用户        │                     │                   │           task2执行
  │  "已派出3个子agent" │                     │                   │              │
  │                    │                     │                   ├──完成──→回调  │
  │                    │                     │                   │          完成──→回调
  │                    │                     │                   │              │
  │                    │                     │←──全部完成──_monitor              │
```

---

## 文件组织

```
src/
├── sub_agent/                      # 新建 — 子 agent 调度包
│   ├── __init__.py                 # 导出 TaskDispatcher, TaskItem, TaskResult, TaskCallback
│   ├── dispatcher.py               # TaskDispatcher 核心实现
│   └── worker.py                   # 占位 — worker_fn 接口约定 + mock 实现
├── tools/
│   └── builtin/
│       └── dispatch_tasks.py       # 新建 — dispatch_tasks 工具（@tool 装饰）
├── api/
│   └── main.py                     # 修改 — 启动时注入 worker_fn 到 dispatch_tasks 工具
```

---

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 并发控制机制 | Worker 数量 = 并发数，无显式 Semaphore | 每个 Worker 串行取任务，N 个 Worker 自然限制并发为 N。比 Semaphore 更简单，无需锁 |
| 任务队列 | `asyncio.Queue` | 线程安全、内置阻塞等待、标准库、无需额外依赖 |
| 后台执行 | `asyncio.create_task()` | 工具函数内创建后台协程后立即返回，主 agent 不阻塞。符合 spec F4 |
| Worker 退出条件 | `QueueEmpty` 异常 | `get_nowait()` 非阻塞取任务，队列空时 Worker 自然退出。干净无副作用 |
| 完成通知 | `asyncio.Event` + 可选回调 | `_done_event` 供 `wait_all()` 阻塞等待；`on_task_complete` 供逐条推送。两种模式互不冲突 |
| 调度器与 LLM 解耦 | `worker_fn` 注入 | Dispatcher 不知道子 agent 如何工作，只管理并发调度。调用方自由实现 worker_fn |
| 工具参数注入 | 模块级 `set_worker_fn()` | 与现有 `routes.py` 中 `set_llm_client()` 模式一致，保持项目风格 |
| dispatch 返回值 | 摘要字符串 | 工具返回字符串给 LLM 看，与现有 get_text/click 工具风格一致 |
| `_monitor` 协程 | 独立后台协程 | 追踪所有 Worker 完成；完成后设置 event。不与 Worker 逻辑混在一起 |
