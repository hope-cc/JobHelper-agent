"""子 Agent 调度系统。

提供 TaskDispatcher 任务调度器和相关类型，以及子 agent 执行器。

核心组件：
- TaskDispatcher: 任务调度器，基于客户端池管理并发
- TaskResult: 任务执行结果
- sub_agent_executor: 子 agent 执行器，轻量 ReAct 循环
"""

from .dispatcher import TaskDispatcher
from .types import TaskItem, TaskResult
from .worker import sub_agent_executor

__all__ = [
    "TaskDispatcher",
    "TaskResult",
    "TaskItem",
    "sub_agent_executor",
]
