"""投递结果记录接口（预留）。

本期为空实现，不落库。后续「投递进度」模块在此接入存储。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import SubmissionSession


def record_application_result(
    session: "SubmissionSession | None", result: dict
) -> None:
    """记录一次投递结果。

    Args:
        session: 本次投递的会话（保留参数，便于后续扩展）。
        result: 投递结果数据，具体结构待「投递进度」模块定义。

    本期为空实现，仅保证调用不报错、不落库。
    """
    pass
