"""投递会话数据结构。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright


class SubmissionStage(str, Enum):
    """投递流程阶段。"""

    WAITING_LOGIN = "waiting_login"
    """浏览器已打开，等待用户登录。"""

    WAITING_SUBMIT = "waiting_submit"
    """表单已填写，等待用户点击提交。"""

    SUBMITTED = "submitted"
    """投递成功（终止态，随即清理会话）。"""


@dataclass
class SubmissionSession:
    """单个投递会话，按 conversation_id 管理。

    browser 与 page 为 Playwright 对象，仅存活于 BrowserManager 的
    后台专属事件循环中，不跨事件循环传递。
    """

    conversation_id: str
    stage: SubmissionStage
    url: str = ""
    browser: "Browser | None" = None
    page: "Page | None" = None
    playwright: "Playwright | None" = None
    last_active_at: float = 0.0
    lock: "asyncio.Lock | None" = field(default=None)
