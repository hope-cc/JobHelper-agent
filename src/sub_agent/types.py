"""子 Agent 调度系统的共享类型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TaskItem = dict[str, Any]


@dataclass
class TaskResult:
    """子 agent 完成一项任务后的结果。"""

    task: dict
    """原始 TaskItem，用于结果关联。"""

    output: str
    """子 agent 的文本输出。"""

    success: bool
    """是否成功完成。"""

    error: str | None = None
    """失败时的错误信息，成功时为 None。"""
