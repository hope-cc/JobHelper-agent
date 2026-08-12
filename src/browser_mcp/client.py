"""Playwright MCP 客户端辅助。

对外部启动的 Playwright MCP 服务（`npx @playwright/mcp --port 8931`）提供
工具调用原语。浏览器与页面状态由 MCP 服务端持有，且**只在同一个 MCP 会话
内跨调用存活**（会话终止时页面会被重置），因此这里维护一个**共享的持久
会话**，用 asyncio.Lock 串行化所有调用，避免多个调用/会话互相干扰。
"""

from __future__ import annotations

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

DEFAULT_MCP_URL = "http://localhost:8931/mcp"

_session: ClientSession | None = None
_transport_cm = None
_lock: asyncio.Lock | None = None


class McpConnectError(Exception):
    """连接 Playwright MCP 服务失败。"""


def _get_lock() -> asyncio.Lock:
    """延迟创建锁，绑定到首次使用的运行事件循环。"""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _friendly_error() -> str:
    return (
        f"无法连接 Playwright MCP 服务（{DEFAULT_MCP_URL}），请确认已用 "
        f"`npx @playwright/mcp --port 8931 --user-data-dir <你的浏览器profile目录>` "
        f"启动服务后再试。"
    )


async def _connect() -> None:
    """建立持久会话（transport + ClientSession + initialize）。

    连接失败时清理残留状态后抛出 McpConnectError。
    """
    global _session, _transport_cm
    cm = streamable_http_client(DEFAULT_MCP_URL, terminate_on_close=False)
    _transport_cm = cm
    try:
        read, write = await cm.__aenter__()
    except BaseException:
        try:
            await cm.__aexit__(None, None, None)
        except BaseException:
            pass
        _transport_cm = None
        raise McpConnectError() from None
    _session = await ClientSession(read, write).__aenter__()
    await _session.initialize()


async def _disconnect() -> None:
    """关闭持久会话与 transport。"""
    global _session, _transport_cm
    if _session is not None:
        try:
            await _session.__aexit__(None, None, None)
        except BaseException:
            pass
        _session = None
    if _transport_cm is not None:
        try:
            await _transport_cm.__aexit__(None, None, None)
        except BaseException:
            pass
        _transport_cm = None


async def _ensure_connected() -> None:
    """确保持久会话已建立；连接失败抛 McpConnectError。"""
    if _session is None:
        try:
            await _connect()
        except McpConnectError:
            raise
        except (Exception, asyncio.CancelledError):
            raise McpConnectError() from None


async def call_tool(name: str, args: dict | None = None) -> tuple[str, bool]:
    """调用 Playwright MCP 工具，返回 (内容文本, is_error)。

    共享持久会话并串行执行；会话失效时自动断开重连后重试一次。
    服务器未启动/连接失败时返回明确错误文本（is_error=True），不抛异常中断对话。
    """
    async with _get_lock():
        try:
            await _ensure_connected()
            result = await _session.call_tool(name, args or {})
        except McpConnectError:
            return _friendly_error(), True
        except (Exception, BaseExceptionGroup):
            # 会话中途失效：清理后重连一次
            await _disconnect()
            try:
                await _ensure_connected()
                result = await _session.call_tool(name, args or {})
            except (Exception, BaseExceptionGroup):
                return _friendly_error(), True
        except asyncio.CancelledError:
            raise

    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    text = "\n".join(parts)
    is_error = bool(getattr(result, "isError", False))
    # Playwright MCP 会把「工具不存在/执行失败」以 "### Error" 文本块返回且 isError=False
    if not is_error and text.lstrip().startswith("### Error"):
        is_error = True
    return text, is_error


async def close() -> None:
    """关闭持久会话，供应用退出时调用，避免事件循环退出时异步生成器被强制关闭产生告警。"""
    async with _get_lock():
        await _disconnect()
