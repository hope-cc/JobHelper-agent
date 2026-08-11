"""投递成功检测。

启发式判断投递是否成功：页面 URL（忽略 hash）相比原始投递页发生跳转，
或页面文本中出现成功关键字。检测失败一律返回 False，不抛异常。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from playwright.async_api import Page

SUCCESS_KEYWORDS = ["投递成功", "已投递", "提交成功", "申请成功", "投递完成"]


def _url_changed(current: str, original: str) -> bool:
    """比较两 URL 是否不同（忽略 hash）。"""
    try:
        a = urlsplit(current)._replace(fragment="").geturl()
        b = urlsplit(original)._replace(fragment="").geturl()
        return bool(a and b and a != b)
    except Exception:
        return False


async def detect_success(page: "Page", original_url: str) -> bool:
    """检测投递是否成功。

    Args:
        page: 当前页面。
        original_url: 原始投递页 URL，用于判断是否发生跳转。

    Returns:
        检测到成功标识返回 True；页面异常或未检测到返回 False。
    """
    try:
        if _url_changed(page.url, original_url):
            return True

        content = await page.content()
        for keyword in SUCCESS_KEYWORDS:
            if keyword in content:
                return True
    except Exception:
        return False
    return False
