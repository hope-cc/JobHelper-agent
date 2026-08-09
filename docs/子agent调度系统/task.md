# 子Agent调度系统 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/sub_agent/__init__.py` | 包入口，导出核心类型 |
| 新建 | `src/sub_agent/dispatcher.py` | TaskDispatcher、TaskResult、TaskCallback |
| 新建 | `src/sub_agent/worker.py` | worker_fn 接口约定 + mock 占位实现 |
| 新建 | `src/tools/builtin/dispatch_tasks.py` | dispatch_tasks 工具（@tool 装饰，参数注入） |
| 修改 | `src/api/main.py` | 启动时注入 mock worker_fn |

---

## T1: 创建 agent 包入口

**文件：** `src/sub_agent/__init__.py`
**依赖：** 无
**步骤：**
1. 从 `dispatcher` 模块导入 `TaskDispatcher`、`TaskResult`、`TaskCallback`
2. 从 `worker` 模块导入 `create_mock_worker`
3. 在 `__all__` 中导出

**验证：** `D:\coding\Anaconda\envs\agent\python.exe -c "from src.sub_agent import TaskDispatcher, TaskResult, TaskCallback; print('OK')"` 成功执行（dispatcher.py 创建后重跑）

---

## T2: 实现 TaskDispatcher 核心

**文件：** `src/sub_agent/dispatcher.py`
**依赖：** 无
**步骤：**
1. 定义 `TaskResult` 数据类（`task: dict`、`output: str`、`success: bool`、`error: str | None`）
2. 定义 `TaskCallback` 类型别名（`Callable[[TaskResult], Awaitable[None]]`）
3. 实现 `TaskDispatcher.__init__()`：
   - 接收 `max_concurrency: int`、`worker_fn: Callable`、`on_task_complete: TaskCallback | None`
   - 创建 `asyncio.Queue()`、`_results: list`、`_pending: int = 0`、`_done_event: asyncio.Event`、`_worker_tasks: list`
4. 实现 `dispatch(tasks: list[dict]) -> str`：
   - 遍历 tasks 入队 `await self._queue.put(t)`
   - 设置 `_pending = len(tasks)`
   - 清空 `_done_event`
   - 计算 Worker 数量 `n = min(max_concurrency, len(tasks)) if tasks else 0`
   - `asyncio.create_task(self._worker(i))` 创建 N 个 Worker
   - `asyncio.create_task(self._monitor())` 创建监控协程
   - 返回摘要字符串
5. 实现 `_worker(worker_id: int)`：
   - while True: `get_nowait()` 取任务，`QueueEmpty` 则 break
   - try: `result = await self._worker_fn(task)`
   - except: 构造 `TaskResult(success=False, error=str(exc))`
   - `self._results.append(result)`、`self._pending -= 1`
   - 如果有 `_on_task_complete`，await 调用
   - 退出循环后检查 `_pending <= 0` → `_done_event.set()`
6. 实现 `_monitor()`：
   - 如果有 `_worker_tasks`，`await asyncio.gather(*self._worker_tasks, return_exceptions=True)`
   - `self._done_event.set()`
7. 实现 `wait_all() -> list[TaskResult]`：await `_done_event.wait()`，返回 `list(self._results)`
8. 实现 `results` property：返回 `list(self._results)`
9. 实现 `is_running` property：返回 `self._pending > 0`

**验证：**
```python
# 快速单元测试
import asyncio
from src.sub_agent.dispatcher import TaskDispatcher, TaskResult

async def mock_worker(task):
    await asyncio.sleep(0.01)
    return TaskResult(task=task, output=f"done: {task['id']}", success=True, error=None)

async def test():
    dispatcher = TaskDispatcher(max_concurrency=2, worker_fn=mock_worker)
    tasks = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]
    msg = await dispatcher.dispatch(tasks)
    print(msg)  # 应打印 "已启动 2 个子 agent 处理 5 项任务"
    results = await dispatcher.wait_all()
    print(f"完成 {len(results)} 项")  # 应为 5
    assert len(results) == 5
    assert all(r.success for r in results)
    print("PASS")

asyncio.run(test())
```

---

## T3: 创建 mock worker 占位

**文件：** `src/sub_agent/worker.py`
**依赖：** T2（使用 `TaskResult`）
**步骤：**
1. 定义 `create_mock_worker()` 函数，返回一个 `worker_fn`
2. `worker_fn` 接收 `task: dict`，`await asyncio.sleep(0.05)` 模拟耗时
3. 返回 `TaskResult(task=task, output=f"[mock] 完成: {task}", success=True, error=None)`
4. 添加文档字符串说明真实 `worker_fn` 需要满足的接口约定

**验证：**
```python
import asyncio
from src.sub_agent.dispatcher import TaskDispatcher
from src.sub_agent.worker import create_mock_worker

async def test():
    d = TaskDispatcher(max_concurrency=3, worker_fn=create_mock_worker())
    msg = await d.dispatch([{"url": "test1"}, {"url": "test2"}])
    results = await d.wait_all()
    assert len(results) == 2
    print("PASS")
asyncio.run(test())
```

---

## T4: 实现 dispatch_tasks 工具

**文件：** `src/tools/builtin/dispatch_tasks.py`
**依赖：** T2、T3
**步骤：**
1. 定义 `DispatchTasksParams(BaseModel)`：
   - `tasks: list[dict]` — 任务列表
   - `max_concurrency: int = 3` — 并发上限
2. 模块级变量：`_worker_fn: Callable | None = None`、`_on_complete: TaskCallback | None = None`
3. 实现 `set_worker_fn(fn)` 和 `set_on_complete(cb)` 注入函数
4. 实现 `_get_worker_fn()` — 未注入时抛出 `RuntimeError`
5. 用 `@tool(name="dispatch_tasks", description="派发批量任务...")` 装饰 `dispatch_tasks` 函数
6. 函数内部：
   - `dispatcher = TaskDispatcher(params.max_concurrency, _worker_fn, _on_complete)`
   - `return await dispatcher.dispatch(params.tasks)`
7. 模块加载时自动注册到 `ToolRegistry`（通过 `ToolRegistry.discover()` 自动发现）

**验证：** `D:\coding\Anaconda\envs\agent\python.exe -c "from src.tools.builtin.dispatch_tasks import dispatch_tasks; print(type(dispatch_tasks).__name__)"` 输出 `ToolWrapper`

---

## T5: 集成到启动流程

**文件：** `src/api/main.py`
**依赖：** T4
**步骤：**
1. 在 `main()` 函数中，`registry.discover("src.tools.builtin")` 之后
2. 导入 `from src.sub_agent.worker import create_mock_worker`
3. 导入 `from src.tools.builtin.dispatch_tasks import set_worker_fn`
4. 调用 `set_worker_fn(create_mock_worker())`，注入 mock worker

**验证：** 启动后端 `D:\coding\Anaconda\envs\agent\python.exe run.py`，日志显示检测到 `dispatch_tasks` 工具（工具数应 +1）

## 执行顺序

```
T1 → T2 → T3 → T4 → T5
```
