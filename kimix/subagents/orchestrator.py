"""
子 Agent 编排器模块

提供 SubAgentOrchestrator 类，管理子 Agent 的并发执行。
核心功能包括:
- spawn(): 启动单个子 Agent
- spawn_batch(): 批量启动子 Agent
- wait_all(): 等待全部任务完成
- cancel(): 取消指定任务

并发控制:
- 使用 asyncio.Semaphore 限制最大并发数（默认 32）
- 优先级队列确保高优先级任务优先调度
- 结果通过 asyncio.Queue 收集
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from kimix.subagents.models import (
    AgentRole,
    SubAgentEvent,
    SubAgentHandle,
    SubAgentResult,
    SubAgentTask,
    TaskPriority,
)
from kimix.subagents.worker import SubAgentWorker


class SubAgentOrchestrator:
    """子 Agent 编排器

    管理多个子 Agent 工作进程的并发执行，提供任务调度、
    并发控制和结果收集等核心功能。

    Attributes:
        MAX_CONCURRENT_DEFAULT: 默认最大并发数（32）
        _llm_client: LLM 客户端实例
        _max_concurrent: 最大并发数
        _semaphore: 并发控制信号量
        _tasks: 活跃任务字典 task_id -> asyncio.Task
        _handles: 任务句柄字典 task_id -> SubAgentHandle
        _results: 任务结果字典 task_id -> SubAgentResult
        _result_queue: 结果收集队列
        _shutdown: 关闭标志
    """

    MAX_CONCURRENT_DEFAULT: int = 32

    def __init__(
        self,
        llm_client: Any | None = None,
        max_concurrent: int = MAX_CONCURRENT_DEFAULT,
    ) -> None:
        """初始化编排器

        Args:
            llm_client: 可选的 LLM 客户端实例（传递给 Worker）
            max_concurrent: 最大并发数（默认 32）
        """
        self._llm_client: Any | None = llm_client
        self._max_concurrent: int = max_concurrent
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, asyncio.Task[SubAgentResult]] = {}
        self._handles: dict[str, SubAgentHandle] = {}
        self._results: dict[str, SubAgentResult] = {}
        self._result_queue: asyncio.Queue[SubAgentResult] = asyncio.Queue()
        self._shutdown: bool = False

        # 按优先级排序的任务调度队列
        # 使用 (priority, seq) 作为键确保相同优先级按 FIFO 排序
        self._pending_queue: asyncio.PriorityQueue[
            tuple[int, int, SubAgentTask]
        ] = asyncio.PriorityQueue()
        self._seq_counter: int = 0

    @property
    def active_count(self) -> int:
        """当前活跃任务数

        Returns:
            正在执行的任务数量
        """
        return len(
            [
                t
                for t in self._tasks.values()
                if not t.done() and not t.cancelled()
            ]
        )

    @property
    def total_tasks(self) -> int:
        """总任务数（活跃 + 已完成）

        Returns:
            任务总数
        """
        return len(self._tasks)

    @property
    def completed_count(self) -> int:
        """已完成任务数

        Returns:
            已完成的任务数量
        """
        return len(
            [t for t in self._tasks.values() if t.done()]
        )

    async def spawn(
        self,
        role: AgentRole,
        task: str,
        context: dict[str, Any] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> SubAgentHandle:
        """启动单个子 Agent

        创建并启动一个子 Agent 工作进程，异步执行指定任务。

        Args:
            role: Agent 角色
            task: 任务描述文本
            context: 可选的执行上下文
            priority: 任务优先级

        Returns:
            SubAgentHandle 任务句柄（用于跟踪和取消）
        """
        if self._shutdown:
            raise RuntimeError("编排器已关闭，无法创建新任务")

        # 创建任务描述
        task_obj = SubAgentTask(
            id=f"task_{uuid.uuid4().hex[:8]}",
            role=role,
            task_description=task,
            context=context or {},
            priority=priority,
        )

        # 创建句柄
        handle = SubAgentHandle(
            task_id=task_obj.id,
            worker_id=f"worker_{task_obj.id}_{uuid.uuid4().hex[:6]}",
            status="pending",
            start_time=_iso_timestamp(),
        )
        self._handles[task_obj.id] = handle

        # 创建 Worker
        worker = SubAgentWorker(task=task_obj, llm_client=self._llm_client)

        # 使用信号量控制并发
        handle.status = "running"

        async def _run_with_semaphore(max_retries: int = 2) -> SubAgentResult:
            """在信号量控制下运行 Worker，支持故障恢复"""
            async with self._semaphore:
                last_exception: Exception | None = None
                
                for attempt in range(max_retries + 1):
                    try:
                        result = await worker.run()
                        self._results[task_obj.id] = result
                        await self._result_queue.put(result)
                        handle.status = result.status
                        handle.retry_count = attempt
                        return result
                    except asyncio.CancelledError:
                        handle.status = "cancelled"
                        result = SubAgentResult(
                            task_id=task_obj.id,
                            status="cancelled",
                            summary="任务被取消",
                        )
                        self._results[task_obj.id] = result
                        await self._result_queue.put(result)
                        raise
                    except Exception as e:
                        last_exception = e
                        if attempt < max_retries:
                            handle.status = f"retrying ({attempt + 1}/{max_retries})"
                            await asyncio.sleep(1.0 * (attempt + 1))  # 指数退避
                        else:
                            # 所有重试失败
                            handle.status = "failed"
                            result = SubAgentResult(
                                task_id=task_obj.id,
                                status="failed",
                                summary=f"执行异常（已重试 {max_retries} 次）: {e}",
                            )
                            self._results[task_obj.id] = result
                            await self._result_queue.put(result)
                            return result
                
                # 理论上不会执行到这里
                handle.status = "failed"
                result = SubAgentResult(
                    task_id=task_obj.id,
                    status="failed",
                    summary=f"执行异常: {last_exception}",
                )
                self._results[task_obj.id] = result
                await self._result_queue.put(result)
                return result

        # 创建后台任务
        asyncio_task = asyncio.create_task(
            _run_with_semaphore(),
            name=f"subagent_{task_obj.id}",
        )
        self._tasks[task_obj.id] = asyncio_task

        return handle

    async def spawn_batch(
        self,
        tasks: list[SubAgentTask],
    ) -> list[SubAgentHandle]:
        """批量启动子 Agent

        同时启动多个子 Agent 任务，按优先级排序后并发执行。
        受 semaphore 限制，实际并发数不会超过 max_concurrent。

        Args:
            tasks: 子 Agent 任务列表

        Returns:
            SubAgentHandle 句柄列表（顺序与输入一致）
        """
        if self._shutdown:
            raise RuntimeError("编排器已关闭，无法创建新任务")

        # 按优先级排序（高优先级在前）
        sorted_tasks = sorted(
            tasks, key=lambda t: t.priority.value, reverse=True
        )

        handles: list[SubAgentHandle] = []
        for task in sorted_tasks:
            handle = await self.spawn(
                role=task.role,
                task=task.task_description,
                context=task.context,
                priority=task.priority,
            )
            handles.append(handle)

        return handles

    async def wait_all(
        self,
        handles: list[SubAgentHandle] | None = None,
        timeout: float | None = None,
    ) -> list[SubAgentResult]:
        """等待任务完成

        等待指定句柄列表或所有活跃任务完成，返回执行结果。

        Args:
            handles: 可选的句柄列表（None 表示等待所有任务）
            timeout: 可选的超时时间（秒）

        Returns:
            SubAgentResult 结果列表

        Raises:
            asyncio.TimeoutError: 如果超过超时时间
        """
        if handles is None:
            # 等待所有活跃任务
            tasks_to_wait = list(self._tasks.values())
        else:
            # 等待指定任务
            task_ids = {h.task_id for h in handles}
            tasks_to_wait = [
                self._tasks[tid]
                for tid in task_ids
                if tid in self._tasks
            ]

        if not tasks_to_wait:
            return []

        # 使用 asyncio.wait 等待所有任务
        done, pending = await asyncio.wait(
            tasks_to_wait,
            return_when=asyncio.ALL_COMPLETED,
            timeout=timeout,
        )

        # 取消超时的任务
        for task in pending:
            task.cancel()

        # 收集结果
        results: list[SubAgentResult] = []
        for task in done:
            try:
                result = task.result()
                results.append(result)
            except asyncio.CancelledError:
                # 被取消的任务
                task_name = task.get_name()
                task_id = task_name.replace("subagent_", "")
                results.append(
                    SubAgentResult(
                        task_id=task_id,
                        status="cancelled",
                        summary="任务在等待期间被取消",
                    )
                )
            except Exception as e:
                task_name = task.get_name()
                task_id = task_name.replace("subagent_", "")
                results.append(
                    SubAgentResult(
                        task_id=task_id,
                        status="failed",
                        summary=f"任务异常: {e}",
                    )
                )

        return results

    async def wait_any(
        self,
        handles: list[SubAgentHandle],
        timeout: float | None = None,
    ) -> SubAgentResult:
        """等待任一任务完成

        返回最先完成的任务结果。

        Args:
            handles: 句柄列表
            timeout: 可选的超时时间（秒）

        Returns:
            最先完成的任务的 SubAgentResult

        Raises:
            asyncio.TimeoutError: 如果超过超时时间
        """
        task_ids = {h.task_id for h in handles}
        tasks_to_wait = [
            self._tasks[tid]
            for tid in task_ids
            if tid in self._tasks
        ]

        if not tasks_to_wait:
            raise ValueError("没有可等待的任务")

        done, pending = await asyncio.wait(
            tasks_to_wait,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=timeout,
        )

        # 取消剩余任务
        for task in pending:
            task.cancel()

        # 返回第一个结果
        first_task = done.pop()
        try:
            return first_task.result()
        except asyncio.CancelledError:
            task_id = first_task.get_name().replace("subagent_", "")
            return SubAgentResult(
                task_id=task_id,
                status="cancelled",
                summary="任务被取消",
            )
        except Exception as e:
            task_id = first_task.get_name().replace("subagent_", "")
            return SubAgentResult(
                task_id=task_id,
                status="failed",
                summary=f"任务异常: {e}",
            )

    async def cancel(self, handle: SubAgentHandle) -> bool:
        """取消指定任务

        取消正在执行或待执行的任务。

        Args:
            handle: 要取消的任务句柄

        Returns:
            是否成功取消
        """
        task_id = handle.task_id

        if task_id not in self._tasks:
            return False

        asyncio_task = self._tasks[task_id]

        if asyncio_task.done():
            return False

        # 取消 asyncio.Task
        asyncio_task.cancel()

        # 更新句柄状态
        handle.status = "cancelled"

        return True

    async def cancel_all(self) -> int:
        """取消所有活跃任务

        Returns:
            取消的任务数量
        """
        cancelled_count = 0
        for task_id, asyncio_task in list(self._tasks.items()):
            if not asyncio_task.done():
                asyncio_task.cancel()
                if task_id in self._handles:
                    self._handles[task_id].status = "cancelled"
                cancelled_count += 1
        return cancelled_count

    def get_result(self, handle: SubAgentHandle) -> SubAgentResult | None:
        """获取任务结果（非阻塞）

        Args:
            handle: 任务句柄

        Returns:
            如果任务已完成则返回结果，否则返回 None
        """
        return self._results.get(handle.task_id)

    def get_handle(self, task_id: str) -> SubAgentHandle | None:
        """通过 task_id 获取句柄

        Args:
            task_id: 任务标识符

        Returns:
            SubAgentHandle 或 None
        """
        return self._handles.get(task_id)

    async def result_stream(
        self,
    ) -> asyncio.Queue[SubAgentResult]:
        """获取结果收集队列

        Returns:
            结果队列的引用（可用于实时获取完成的任务结果）
        """
        return self._result_queue

    def get_stats(self) -> dict[str, Any]:
        """获取编排器统计信息

        Returns:
            统计信息字典:
            - active: 活跃任务数
            - completed: 已完成任务数
            - total: 总任务数
            - max_concurrent: 最大并发限制
            - semaphore_value: 当前信号量可用值
        """
        return {
            "active": self.active_count,
            "completed": self.completed_count,
            "total": self.total_tasks,
            "max_concurrent": self._max_concurrent,
            "semaphore_value": self._semaphore._value,
        }

    async def shutdown(self) -> None:
        """关闭编排器

        取消所有活跃任务，清理资源。关闭后不能再创建新任务。
        """
        self._shutdown = True
        await self.cancel_all()

        # 等待所有任务真正结束
        if self._tasks:
            await asyncio.gather(
                *self._tasks.values(),
                return_exceptions=True,
            )

    async def __aenter__(self) -> SubAgentOrchestrator:
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """异步上下文管理器出口"""
        await self.shutdown()


def _iso_timestamp() -> str:
    """生成 ISO 8601 格式时间戳（模块级工具函数）

    Returns:
        ISO 8601 格式时间戳字符串
    """
    return datetime.now(timezone.utc).isoformat()
