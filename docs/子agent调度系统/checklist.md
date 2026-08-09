# 子Agent调度系统 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性
- [ ] TaskDispatcher 类已实现且可导入（验证：`python -c "from src.sub_agent.dispatcher import TaskDispatcher, TaskResult; print('OK')"`）
- [ ] `dispatch_tasks` 工具已通过 @tool 装饰并自动注册（验证：启动后端，日志显示工具数 +1）
- [ ] mock worker_fn 可正常执行（验证：T3 的单元测试通过）

## 功能验证

### 并发控制
- [ ] 5 项任务 + 并发数=2 时，最多同时 2 个 worker 在执行（验证：在 mock worker 中加日志/计数器，观察并发峰值不超过 2）
- [ ] 5 项任务 + 并发数=3 时，3 个 worker 各处理至少 1 项任务（验证：`wait_all()` 返回 5 条结果，每个 worker_id 出现在至少一条日志中）

### 任务派发与完成信号
- [ ] 任务按 worker 完成顺序触发回调，非提交顺序（验证：各任务 mock 不同耗时，检查 `on_task_complete` 回调的调用顺序）
- [ ] 所有任务完成后 `wait_all()` 返回（验证：T2 单元测试中 `assert len(results) == 5`）

### 错误隔离
- [ ] 一项任务抛异常时，其余任务继续执行并正常完成（验证：mock 中第 2 项 raise，其余 4 项应成功完成，异常任务的 `success=False`）

### 工具调用
- [ ] `dispatch_tasks` 工具被主 agent 调用后立即返回，不阻塞（验证：调用前后打印时间戳，间隔应 < 50ms）
- [ ] 空任务列表时工具返回合理信息，不抛异常（验证：`dispatch([])` 返回摘要字符串，无异常）

### 调度器生命周期
- [ ] `is_running` 在 dispatch 后为 True，全部完成后为 False（验证：T2 单元测试中分别断言）
- [ ] `results` 属性实时累积已完成结果（验证：在 `on_task_complete` 回调中检查 `len(dispatcher.results)` 递增）

## 编译与测试
- [ ] `python -c "import src.sub_agent"` 无导入错误
- [ ] `python -c "import src.tools.builtin.dispatch_tasks"` 无导入错误
- [ ] 后端服务 `python run.py` 正常启动

## 端到端场景
- [ ] **场景 1：** 通过后端 API 发送"帮我把这 3 个公司链接的内容抓下来"，主 agent 调用 `dispatch_tasks` 工具 → 返回"已启动 N 个子 agent" → mock worker 完成回调触发 → 全部任务完成后状态正确
- [ ] **场景 2：** 任务列表中包含一项无效任务（mock worker 抛异常），调度器继续处理其余任务，异常任务的 `TaskResult.success=False`
