"""浏览器会话管理器。

单例。为每个 conversation_id 维护一个投递会话（SubmissionSession），
每个会话持有一个有头浏览器。Playwright 对象全部运行在后台专属事件循环中，
保证浏览器跨多次工具调用和多个用户轮次存活。

对外仅暴露 submit(conversation_id, url, action) 异步接口。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from playwright.async_api import async_playwright

if TYPE_CHECKING:
    from playwright.async_api import Page

from src.browser.detect import detect_success
from src.browser.fill import detect_form, fill_form
from src.browser.recorder import record_application_result
from src.browser.session import SubmissionSession, SubmissionStage

logger = logging.getLogger(__name__)

# 空闲超时（秒）与清扫间隔（秒）
IDLE_TIMEOUT_SECONDS = 600.0
SWEEP_INTERVAL_SECONDS = 60.0
GOTO_TIMEOUT_MS = 20000
DETECT_TIMEOUT_SECONDS = 15.0


class BrowserManager:
    """投递会话注册表 + 后台事件循环 + 生命周期管理。"""

    _instance: BrowserManager | None = None

    def __init__(self) -> None:
        self._sessions: dict[str, SubmissionSession] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_background_loop,
            name="browser-manager",
            daemon=True,
        )
        self._thread.start()
        if not self._loop_ready.wait(timeout=5.0) or self._loop is None:
            raise RuntimeError("后台事件循环启动失败")

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        """获取全局唯一实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---- 后台事件循环 ----

    def _run_background_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.create_task(self._idle_sweeper())
        self._loop_ready.set()
        self._loop.run_forever()

    async def _idle_sweeper(self) -> None:
        """定期清扫超时未活跃的会话，防止浏览器泄漏。"""
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            now = time.time()
            expired = [
                s
                for s in self._sessions.values()
                if now - s.last_active_at > IDLE_TIMEOUT_SECONDS
            ]
            for session in expired:
                async with session.lock:
                    await self._close_locked_session(session)

    # ---- 对外接口 ----

    async def submit(self, conversation_id: str, url: str, action: str) -> str:
        """推进指定会话的投递流程，返回给用户的文本结果。

        Args:
            conversation_id: 会话 ID（ContextVar 注入）。
            url: 投递页 URL，仅首次调用或更换新职位时使用。
            action: "continue" 继续推进；"cancel" 取消投递。

        Returns:
            给用户的状态与指引文本。
        """
        if self._loop is None:
            return "[submitApplication] 浏览器管理器未就绪，请重启后端。"
        future = asyncio.run_coroutine_threadsafe(
            self._handle(conversation_id, url, action), self._loop
        )
        return await asyncio.wrap_future(future)

    # ---- 状态机 ----

    async def _handle(self, conversation_id: str, url: str, action: str) -> str:
        """在后台事件循环中执行：查找/创建会话，按阶段推进。"""
        session = self._sessions.get(conversation_id)

        if session is None:
            if action == "cancel":
                return "当前没有进行中的投递流程。"
            return await self._open_new_session(conversation_id, url)

        async with session.lock:
            session.last_active_at = time.time()

            if action == "cancel":
                await self._close_locked_session(session)
                return "已取消投递，浏览器已关闭。如需投递新职位，请提供新的URL。"

            if url and url != session.url:
                # 投递新职位：关闭当前会话，重新打开新 URL
                await self._close_locked_session(session)
                return await self._open_new_session(conversation_id, url)

            if session.stage == SubmissionStage.WAITING_LOGIN:
                return await self._advance_after_login(session)

            if session.stage == SubmissionStage.WAITING_SUBMIT:
                return await self._advance_after_submit(session)

            return "该投递流程已结束，如需投递新职位，请提供新的URL。"

    async def _advance_after_login(self, session: SubmissionSession) -> str:
        """WAITING_LOGIN：检测表单是否出现（含用户手动打开的新标签页），出现则自动填写。"""
        if session.page is None or session.browser is None:
            return "[submitApplication] 浏览器会话异常，请重新发起投递。"

        form_page = await self._find_form_page(session)
        if form_page is None:
            return (
                "未检测到简历表单。若登录后停留在岗位列表页，请在浏览器中手动点击"
                "目标岗位进入投递页面（当前标签页或新标签页均可），待表单出现后回复「继续」。"
            )

        # 表单可能位于用户手动打开的新标签页，切换到该页面，
        # 并以表单页 URL 作为后续「投递成功」检测的跳转基准
        session.page = form_page
        session.url = form_page.url or session.url

        result = await fill_form(session.page)
        session.stage = SubmissionStage.WAITING_SUBMIT
        return result["report"]

    async def _find_form_page(self, session: SubmissionSession) -> "Page | None":
        """在当前页与浏览器全部标签页中轮询查找简历表单，返回承载表单的页面。

        登录后用户可能停留在岗位列表页，表单由其手动点击岗位后在
        新标签页（或当前标签页）中打开，因此需要扫描上下文内的所有页面。
        检测超时或未发现表单时返回 None。
        """
        deadline = time.time() + DETECT_TIMEOUT_SECONDS
        while time.time() < deadline:
            if session.page is not None and await self._safe_detect_form(session.page):
                return session.page

            if session.browser is not None:
                for context in session.browser.contexts:
                    for page in context.pages:
                        if page is session.page:
                            continue
                        if await self._safe_detect_form(page):
                            return page

            await asyncio.sleep(1)
        return None

    async def _safe_detect_form(self, page: "Page") -> bool:
        """带超时的表单检测，页面异常或超时一律返回 False。"""
        try:
            return await asyncio.wait_for(detect_form(page), timeout=3.0)
        except Exception:
            return False

    async def _advance_after_submit(self, session: SubmissionSession) -> str:
        """WAITING_SUBMIT：检测投递是否成功，成功则结束会话。"""
        if session.page is None:
            return "[submitApplication] 浏览器会话异常，请重新发起投递。"
        try:
            success = await asyncio.wait_for(
                detect_success(session.page, session.url),
                timeout=DETECT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return "检测投递结果超时，请确认已点击「提交」后回复「已提交」。"
        if not success:
            return "未检测到投递成功的明确标识，请确认已在浏览器中点击「提交」后，再回复「已提交」。"
        session.stage = SubmissionStage.SUBMITTED
        try:
            record_application_result(
                session,
                {
                    "conversation_id": session.conversation_id,
                    "url": session.url,
                    "status": "submitted",
                },
            )
        except Exception:
            logger.exception("投递结果记录接口异常（预留接口，不影响流程）")
        await self._close_locked_session(session)
        return "投递成功"

    # ---- 会话创建与清理 ----

    async def _open_new_session(self, conversation_id: str, url: str) -> str:
        """首次调用或更换新职位：校验 URL 并以有头方式打开浏览器。"""
        if not url:
            return (
                "[submitApplication] 首次调用需要提供投递页URL，"
                "例如：帮我投递 https://example.com/jobs/123"
            )
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return (
                "[submitApplication] URL 格式不正确，必须包含协议头"
                f"(如 http:// 或 https://): '{url}'"
            )

        playwright = None
        browser = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        except Exception as exc:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass
            logger.warning(
                "打开投递页失败 conversation=%s url=%s err=%s",
                conversation_id,
                url,
                exc,
            )
            return f"[submitApplication] 打开网页失败: {exc}"

        session = SubmissionSession(
            conversation_id=conversation_id,
            stage=SubmissionStage.WAITING_LOGIN,
            url=url,
            browser=browser,
            page=page,
            playwright=playwright,
            last_active_at=time.time(),
            lock=asyncio.Lock(),
        )
        self._sessions[conversation_id] = session
        logger.info("投递会话已打开 conversation=%s url=%s", conversation_id, url)
        return (
            f"浏览器已打开: {url}\n"
            "请用手机扫码或短信登录该平台，登录并进入简历表单页面后，回复「继续」。"
        )

    async def _close_locked_session(self, session: SubmissionSession) -> None:
        """关闭会话并清理资源。调用方须已持有 session.lock。"""
        self._sessions.pop(session.conversation_id, None)
        try:
            if session.playwright is not None:
                await session.playwright.stop()
            elif session.browser is not None:
                await session.browser.close()
        except Exception:
            logger.warning(
                "关闭浏览器异常 conversation=%s", session.conversation_id, exc_info=True
            )
