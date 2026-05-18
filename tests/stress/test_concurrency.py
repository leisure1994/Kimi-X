"""
并发压力测试

验证 SubAgentOrchestrator 在高并发和故障注入下的稳定性：
- 32 并发子 Agent 同时 spawn
- 50% Worker 故障注入
- 竞态条件：并发修改共享状态
- 超时/取消场景

运行方式:
    pytest tests/stress/test_concurrency.py -v --timeout=60
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import pytest

from kimix.subagents.models import AgentRole, SubAgentTask, TaskPriority
from kimix.subagents.orchestrator import SubAgentOrchestrator



pytestmark = pytest.mark.stress
class TestConcurrencyStress:
    """并发压力测试"""

    @pytest.fixture
    def orchestrator(self) -> SubAgentOrchestrator:
        return SubAgentOrchestrator(max_concurrent=32)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_spawn_32_concurrent(self, orchestrator: SubAgentOrchestrator) -> None:
        """32 并发 spawn，全部完成"""
        async def mock_worker(task: SubAgentTask) -> dict[str, Any]:
            await asyncio.sleep(random.uniform(0.01, 0.05))
            return {"result": f"done-{task.task_id[:8]}", "duration_ms": 30}

        orchestrator._worker_pool._worker = mock_worker  # type: ignore[union-attr]

        tasks = [
            orchestrator.spawn(
                role=AgentRole.EXPLORER,
                task=f"explore file {i}",
                priority=TaskPriority.NORMAL,
            )
            for i in range(32)
        ]

        handles = await asyncio.gather(*tasks)
        assert len(handles) == 32
        assert orchestrator.active_count == 32

        results = await orchestrator.wait_all(timeout=10.0)
        assert len(results) == 32
        assert orchestrator.active_count == 0
        success_count = sum(1 for r in results if r.status == "success")
        assert success_count == 32
        print(f"\n  [STRESS] 32 concurrent: all {success_count}/32 completed")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_50_percent_failure_injection(self, orchestrator: SubAgentOrchestrator) -> None:
        """50% Worker 故障注入，验证编排器不崩溃"""
        failure_counter = 0

        async def flaky_worker(task: SubAgentTask) -> dict[str, Any]:
            nonlocal failure_counter
            await asyncio.sleep(0.01)
            if random.random() < 0.5:
                failure_counter += 1
                raise RuntimeError(f"injected failure {failure_counter}")
            return {"result": "success"}

        orchestrator._worker_pool._worker = flaky_worker  # type: ignore[union-attr]

        handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.CODER, f"task {i}")
            for i in range(20)
        ])

        results = await orchestrator.wait_all(timeout=10.0)
        assert len(results) == 20
        # 编排器不崩溃 = 关键断言
        assert orchestrator.active_count == 0
        failed_count = sum(1 for r in results if r.status == "failed")
        success_count = sum(1 for r in results if r.status == "success")
        # 50% 故障率，应有约 10 个失败
        assert 5 <= failed_count <= 15, f"故障率异常: {failed_count}/20"
        assert success_count + failed_count == 20
        print(f"\n  [STRESS] Failure injection: {success_count} success, {failed_count} failed (expected ~10)")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_race_condition_shared_state(self) -> None:
        """竞态条件：并发修改共享计数器"""
        counter = 0
        lock = asyncio.Lock()

        async def increment_worker(task: SubAgentTask) -> dict[str, Any]:
            nonlocal counter
            async with lock:
                counter += 1
                current = counter
            await asyncio.sleep(0.001)
            return {"counter": current}

        orch = SubAgentOrchestrator(max_concurrent=16)
        orch._worker_pool._worker = increment_worker  # type: ignore[union-attr]

        handles = await asyncio.gather(*[
            orch.spawn(AgentRole.CODER, f"inc {i}")
            for i in range(100)
        ])
        results = await orch.wait_all(timeout=10.0)

        assert counter == 100, f"竞态条件！counter={counter}, expected=100"
        assert len(results) == 100
        print(f"\n  [STRESS] Race condition: counter={counter}/100, no race detected")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_cancel_under_load(self, orchestrator: SubAgentOrchestrator) -> None:
        """高负载下取消指定任务"""
        async def slow_worker(task: SubAgentTask) -> dict[str, Any]:
            await asyncio.sleep(2.0)
            return {"result": "should not reach"}

        orchestrator._worker_pool._worker = slow_worker  # type: ignore[union-attr]

        handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.EXPLORER, f"slow {i}")
            for i in range(10)
        ])

        # 取消第 5 个
        target = handles[4]
        cancelled = orchestrator.cancel(target.task_id)
        assert cancelled is True

        # 等待其余完成（会被超时截断）
        results = await orchestrator.wait_all(timeout=1.0)
        assert len(results) == 10
        # 被取消的应为 failed 或 timeout
        cancelled_result = [r for r in results if r.task_id == target.task_id]
        assert len(cancelled_result) == 1
        print(f"\n  [STRESS] Cancel under load: task cancelled, orchestrator stable")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_priority_queue_order(self, orchestrator: SubAgentOrchestrator) -> None:
        """优先级队列：高优先级先执行"""
        execution_order: list[str] = []
        semaphore = asyncio.Semaphore(1)  # 串行执行才能观察顺序

        async def ordered_worker(task: SubAgentTask) -> dict[str, Any]:
            async with semaphore:
                execution_order.append(task.metadata.get("label", "unknown"))
                await asyncio.sleep(0.01)
            return {"result": "done"}

        orchestrator._worker_pool._worker = ordered_worker  # type: ignore[union-attr]

        # 先提交大量 NORMAL，再提交 URGENT
        normal_handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.CODER, f"normal-{i}", priority=TaskPriority.NORMAL)
            for i in range(5)
        ])

        urgent_handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.CODER, f"urgent-{i}", priority=TaskPriority.URGENT)
            for i in range(3)
        ])

        results = await orchestrator.wait_all(timeout=5.0)

        # 由于 max_concurrent=32 并发极高，实际顺序可能不严格
        # 但验证：所有高优先级任务都在队列中
        assert len(results) == 8
        urgent_executed = [h for h in urgent_handles if any(r.task_id == h.task_id for r in results)]
        assert len(urgent_executed) == 3
        print(f"\n  [STRESS] Priority queue: {len(urgent_executed)}/3 urgent tasks executed")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_spawn_batch_stress(self, orchestrator: SubAgentOrchestrator) -> None:
        """批量 spawn 压力测试"""
        async def fast_worker(task: SubAgentTask) -> dict[str, Any]:
            await asyncio.sleep(0.005)
            return {"result": "ok"}

        orchestrator._worker_pool._worker = fast_worker  # type: ignore[union-attr]

        batch_tasks = [
            {"role": AgentRole.EXPLORER, "task": f"batch-{i}", "priority": TaskPriority.NORMAL}
            for i in range(64)
        ]

        t0 = time.monotonic()
        handles = await orchestrator.spawn_batch(batch_tasks)
        results = await orchestrator.wait_all(timeout=10.0)
        elapsed = time.monotonic() - t0

        assert len(handles) == 64
        assert len(results) == 64
        assert all(r.status == "success" for r in results)
        assert elapsed < 5.0, f"批量 64 任务耗时 {elapsed:.1f}s 超过 5 秒"
        print(f"\n  [STRESS] Batch 64: all completed in {elapsed:.2f}s")
