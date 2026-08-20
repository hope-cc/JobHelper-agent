"""任务调度器。

提供 TaskDispatcher 类，通过客户端池（Client Pool）管理并发。
每个任务 spawn 为独立协程，通过 acquire/release 机制获取空闲
LLM 客户端执行，无空闲时自动挂起等待。

子任务结果存入 asyncio.Queue，由调用方通过 drain_results() 主动
拉取，而非通过回调推送。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from src.llm.base import BaseLLMClient
from src.llm.types import ProviderConfig
from src.rag.store import job_vector_store
from src.sub_agent.types import TaskItem, TaskResult
from src.sub_agent.worker import sub_agent_executor

import time

# ---- 结果解析辅助 ----

def _parse_jobs_json(output: str) -> list[dict]:
    """容错解析子 agent 输出的职位 JSON 数组。

    处理 LLM 输出不稳定情况：``` 代码围栏包裹、整体为单个对象；
    非法 JSON 返回空列表（调用方跳过并记录）。
    """
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


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

        # 结果队列：子任务完成后 put，后台消费协程自动取出并入向量库
        self._result_queue: asyncio.Queue[TaskResult] = asyncio.Queue()

        # 追踪进行中的任务协程，用于 shutdown 时取消
        self._task_futures: set[asyncio.Task] = set()

        # 后台消费协程：自动检测 _result_queue，有新结果即解析入库
        self._consumer_task: asyncio.Task | None = None

        # 「公司+职位」去重集合，防止重复入向量库；启动时从向量库重建
        self._known_jobs: set[tuple[str, str]] = set()
        self._known_jobs_loaded: bool = False

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

        # 懒启动后台消费协程 + 重建去重集合
        self._ensure_consumer()
        self._load_known_jobs()

        if self._pending == 0:
            print(time.time(), "调度器开始处理任务")

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
        """（已废弃）结果由后台消费协程自动入库，不再主动拉取。

        保留空实现以兼容旧调用方——结果队列已被后台协程消费。
        """
        return []

    async def wait_all(self) -> list[TaskResult]:
        """阻塞等待所有任务完成。结果已由后台消费，不再返回。"""
        await self._done_event.wait()
        return []

    async def shutdown(self) -> None:
        """关闭调度器：取消所有未完成的任务协程与后台消费协程。"""
        for fut in self._task_futures:
            fut.cancel()
        if self._task_futures:
            await asyncio.gather(*self._task_futures, return_exceptions=True)
        self._task_futures.clear()

        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None

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

    # ---- 结果自动入库 ----

    def _ensure_consumer(self) -> None:
        """幂等懒启动后台消费协程，自动检测 _result_queue。

        无需用户发消息触发——子任务结果一入队即被消费并入向量库。
        首次 dispatch 时启动；shutdown 时取消。
        """
        if self._consumer_task is not None and not self._consumer_task.done():
            return
        self._consumer_task = asyncio.create_task(self._consumer_loop())

    async def _consumer_loop(self) -> None:
        while True:
            result = await self._result_queue.get()
            await self._ingest_result(result)

    async def _ingest_result(self, result: TaskResult) -> None:
        """解析一条子任务结果，逐职位写入向量库（带去重）。"""
        if not result.success:
            return

        jobs = _parse_jobs_json(result.output)
        for job in jobs:
            company = str(job.get("公司", "") or "").strip()
            position = str(job.get("职位", "") or "").strip()
            if not company or not position:
                continue  # 缺公司/职位的记录不入库

            key = (company, position)
            if key in self._known_jobs:
                continue  # 已存在，跳过（去重）

            try:
                ok = job_vector_store.add_job(job)
            except Exception:
                ok = False
            if ok:
                self._known_jobs.add(key)

    def _load_known_jobs(self) -> None:
        """从向量库现有记录重建「公司+职位」去重集合（进程内只重建一次）。"""
        if self._known_jobs_loaded:
            return
        try:
            for rec in job_vector_store.all_records():
                meta = rec.get("metadata", {})
                company = str(meta.get("company", "") or "").strip()
                position = str(meta.get("position", "") or "").strip()
                if company and position:
                    self._known_jobs.add((company, position))
        except Exception:
            pass
        self._known_jobs_loaded = True


# ---- 全局单例 ----

task_dispatcher = TaskDispatcher()
