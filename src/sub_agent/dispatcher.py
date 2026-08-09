"""任务调度器。

提供 TaskDispatcher 类，通过客户端池（Client Pool）管理并发。
每个任务 spawn 为独立协程，通过 acquire/release 机制获取空闲
LLM 客户端执行，无空闲时自动挂起等待。

子任务结果存入 asyncio.Queue，由调用方通过 drain_results() 主动
拉取，而非通过回调推送。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.llm.base import BaseLLMClient
from src.llm.types import ProviderConfig
from src.sub_agent.types import TaskItem, TaskResult
from src.sub_agent.worker import sub_agent_executor


# ---- 调度器 ----

class TaskDispatcher:
    """任务调度器（客户端池模式）。

    维护一个 LLM 客户端池，每个任务被 spawn 为独立协程。
    协程通过 acquire() 获取空闲客户端，执行完成后 release() 归还。

    结果存入 asyncio.Queue，由 drain_results() 拉取清空。

    Usage::

        dispatcher = TaskDispatcher()
        dispatcher.set_provider_config(config)
        dispatcher.set_worker_num(3)

        await dispatcher.dispatch(batch)   # 启动协程，立即返回
        # ... 后续用户消息时 ...
        results = dispatcher.drain_results()  # 拉取已完成的结果
        await dispatcher.wait_all()         # 等待全部完成
        await dispatcher.shutdown()         # 取消未完成任务并清理
    """

    def __init__(self):
        self._pool_size: int = 1

        self._pending: int = 0
        self._done_event = asyncio.Event()
        self._done_event.set()  # 初始状态：无任务，视为已完成

        self._sub_agents: list[BaseLLMClient] = []
        self._worker_fn = None

        # 客户端池状态
        self._busy: list[bool] = []
        self._condition = asyncio.Condition()

        # 结果队列：子任务完成后 put，调用方通过 drain_results() get
        self._result_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

        # 追踪进行中的任务协程，用于 shutdown 时取消
        self._task_futures: set[asyncio.Task] = set()

    # ---- 依赖注入 ----

  

    def set_provider_config(self, config: ProviderConfig) -> None:
        self._provider_config = config

    def set_worker_num(self, num_workers: int) -> None:
        """设置客户端池大小（即并发上限）。"""
        if num_workers < 1:
            raise ValueError(f"num_workers 不能小于 1: {num_workers}")
        self._pool_size = num_workers

    def create_worker_clients(self) -> None:
        """为客户端池创建 LLM 实例（数量 = pool_size）。"""
        from src.llm.factory import create_client

        self._sub_agents = [
            create_client(self._provider_config) for _ in range(self._pool_size)
        ]
        self._busy = [False] * self._pool_size

    # ---- 公共接口 ----

    async def dispatch(self, tasks: list[TaskItem]) -> str:
        """向调度器追加任务，立即返回。

        为每个任务 spawn 一个协程，协程自动从客户端池获取空闲
        客户端执行。若所有客户端都忙，协程挂起等待。

        可多次调用——每次调用追加任务。
        """
        if not tasks:
            return "任务列表为空，未追加任务"

        if not self._sub_agents:
            self.create_worker_clients()


        self._pending += len(tasks)
        self._done_event.clear()

        for t in tasks:
            fut = asyncio.create_task(self._execute_task(t))
            self._task_futures.add(fut)
            fut.add_done_callback(self._task_futures.discard)

        busy_count = sum(self._busy)
        idle_count = self._pool_size - busy_count
        return (
            f"已追加 {len(tasks)} 项任务，"
            f"当前 {idle_count} 空闲 / {busy_count} 繁忙，"
            f"待处理: {self._pending} 项"
        )

    def drain_results(self) -> list[TaskResult]:
        """取出并清空所有已完成的任务结果。非阻塞。

        应在每次用户发消息时调用，取出上一轮派遣的子任务结果。
        取出的结果不再保留——每条结果只被消费一次。
        """
        results: list[TaskResult] = []
        while not self._result_queue.empty():
            try:
                results.append(self._result_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return results

    async def wait_all(self) -> list[TaskResult]:
        """阻塞等待所有任务完成，返回剩余未 drain 的结果列表。"""
        await self._done_event.wait()
        return self.drain_results()

    async def shutdown(self) -> None:
        """关闭调度器：取消所有未完成的任务协程并等待结束。"""
        for fut in self._task_futures:
            fut.cancel()
        if self._task_futures:
            await asyncio.gather(*self._task_futures, return_exceptions=True)
        self._task_futures.clear()
        self._done_event.set()

    @property
    def is_running(self) -> bool:
        """是否仍有未完成的任务。"""
        return self._pending > 0

    @property
    def idle_count(self) -> int:
        """空闲客户端数量。"""
        return sum(1 for b in self._busy if not b)

    @property
    def busy_count(self) -> int:
        """繁忙客户端数量。"""
        return sum(self._busy)

    # ---- 客户端池 ----

    async def _acquire(self) -> int:
        """从池中获取一个空闲客户端，阻塞直到有可用。"""
        async with self._condition:
            while True:
                for i, busy in enumerate(self._busy):
                    if not busy:
                        self._busy[i] = True
                        return i
                await self._condition.wait()

    async def _release(self, idx: int) -> None:
        """归还客户端，通知等待者。"""
        async with self._condition:
            self._busy[idx] = False
            self._condition.notify()

    # ---- 任务执行 ----

    async def _execute_task(self, task: dict) -> None:
        """单个任务生命周期：acquire -> 执行 -> release -> 入队。

        结果放入 _result_queue，由 drain_results() 消费。
        """
        idx = await self._acquire()
        try:
            result = await sub_agent_executor(task, self._sub_agents[idx])
        except Exception as exc:
            result = TaskResult(
                task=task,
                output=str(exc),
                success=False,
                error=str(exc),
            )
        finally:
            await self._release(idx)

        await self._result_queue.put(result)
        self._pending -= 1

        if self._pending <= 0:
            self._done_event.set()


# ---- 全局单例 ----

task_dispatcher = TaskDispatcher()
