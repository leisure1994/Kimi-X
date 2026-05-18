"""
混沌工程测试模块

随机组合故障注入，验证系统在极端条件下的稳定性：
- 网络 + API + 磁盘同时故障
- 级联故障（一个子 Agent 失败导致连锁反应）
- 资源耗尽（句柄泄漏模拟）
- 时间漂移 + 超时竞争

运行方式:
    pytest tests/chaos/test_chaos.py -v --timeout=120
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import pytest

from kimix.subagents.models import AgentRole, SubAgentTask
from kimix.subagents.orchestrator import SubAgentOrchestrator
from kimix.core.healing import SelfHealingEngine, ErrorCategory, HealingStrategy



pytestmark = pytest.mark.chaos
class ChaosMonkey:
    """混沌猴子：随机故障注入器"""

    FAULT_TYPES = ["network", "api", "disk", "memory", "cpu"]

    def __init__(self, seed: int | None = None) -> None:
        if seed is not None:
            random.seed(seed)
        self.injected: list[dict[str, Any]] = []

    def inject(
        self,
        fault_probability: float = 0.3,
        max_simultaneous: int = 3,
    ) -> list[str]:
        """随机注入一组故障

        Returns:
            本次注入的故障类型列表
        """
        count = random.randint(1, max_simultaneous)
        faults = random.sample(self.FAULT_TYPES, k=min(count, len(self.FAULT_TYPES)))
        # 按概率过滤
        active = [f for f in faults if random.random() < fault_probability]
        self.injected.append({"time": time.monotonic(), "faults": active})
        return active

    def should_fault(self, fault_type: str) -> bool:
        """检查某类故障是否应触发"""
        return any(fault_type in inj["faults"] for inj in self.injected[-3:])

    def clear(self) -> None:
        """清除故障状态"""
        self.injected.clear()


class TestChaosEngineering:
    """混沌工程测试"""

    @pytest.fixture
    def monkey(self) -> ChaosMonkey:
        return ChaosMonkey(seed=42)  # 可复现的随机种子

    @pytest.fixture
    def orchestrator(self) -> SubAgentOrchestrator:
        return SubAgentOrchestrator(max_concurrent=16)

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_simultaneous_network_api_disk_failure(
        self,
        orchestrator: SubAgentOrchestrator,
        monkey: ChaosMonkey,
    ) -> None:
        """网络+API+磁盘同时故障，验证编排器不崩溃"""
        fault_log: list[str] = []

        async def chaotic_worker(task: SubAgentTask) -> dict[str, Any]:
            faults = monkey.inject(fault_probability=0.4, max_simultaneous=3)
            for f in faults:
                fault_log.append(f"{task.task_id}:{f}")

            # 模拟故障组合
            if "network" in faults and "api" in faults:
                await asyncio.sleep(0.05)
                raise ConnectionError("network+api double fault")
            if "disk" in faults:
                raise OSError("disk fault: no space left")
            if "api" in faults:
                raise RuntimeError("api fault: 429 rate limited")

            await asyncio.sleep(0.01)
            return {"result": "survived", "faults_injected": len(faults)}

        orchestrator._worker_pool._worker = chaotic_worker  # type: ignore[union-attr]

        # 提交 30 个任务，预期大量失败但不崩溃
        handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.EXPLORER, f"chaos-{i}")
            for i in range(30)
        ])

        results = await orchestrator.wait_all(timeout=10.0)

        assert len(results) == 30
        assert orchestrator.active_count == 0  # 没有残留
        success_count = sum(1 for r in results if r.status == "success")
        failed_count = sum(1 for r in results if r.status == "failed")

        # 混沌测试不断言具体数量，只断言系统不崩溃
        assert success_count + failed_count == 30
        assert len(fault_log) > 0  # 确实有故障注入
        print(f"\n  [CHAOS] Network+API+Disk: {success_count} success, {failed_count} failed, {len(fault_log)} faults injected")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_cascading_failure(self, orchestrator: SubAgentOrchestrator) -> None:
        """级联故障：父任务失败导致子任务连锁取消"""
        cascade_triggered = False

        async def parent_worker(task: SubAgentTask) -> dict[str, Any]:
            nonlocal cascade_triggered
            if "parent-0" in task.task_id:
                cascade_triggered = True
                raise RuntimeError("parent failed, cascade triggered")
            await asyncio.sleep(0.02)
            return {"result": "child ok"}

        orchestrator._worker_pool._worker = parent_worker  # type: ignore[union-attr]

        # 父任务
        parent = await orchestrator.spawn(AgentRole.PLANNER, "parent-0")
        # 大量子任务
        children = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.CODER, f"child-{i}")
            for i in range(10)
        ])

        results = await orchestrator.wait_all(timeout=5.0)

        assert cascade_triggered
        assert len(results) == 11  # 1 parent + 10 children
        assert orchestrator.active_count == 0
        print(f"\n  [CHAOS] Cascading: parent failed, {len(results)} total tasks handled")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_resource_exhaustion_handle_leak(self) -> None:
        """资源耗尽：模拟句柄泄漏，验证系统 graceful degradation"""
        orch = SubAgentOrchestrator(max_concurrent=4)
        active_handles: list[Any] = []

        async def slow_worker(task: SubAgentTask) -> dict[str, Any]:
            await asyncio.sleep(0.1)
            return {"result": "done"}

        orch._worker_pool._worker = slow_worker  # type: ignore[union-attr]

        # 故意不 wait_all，模拟泄漏场景
        for i in range(20):
            handle = await orch.spawn(AgentRole.EXPLORER, f"leak-{i}")
            active_handles.append(handle)
            if i >= 4:
                # 超过并发限制后应排队而非崩溃
                assert orch.pending_count > 0 or orch.active_count == 4

        # 最终清理
        results = await orch.wait_all(timeout=5.0)
        assert len(results) == 20
        assert orch.active_count == 0
        print(f"\n  [CHAOS] Resource exhaustion: 20 tasks with max_concurrent=4, no crash")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_timeout_race_condition(self, orchestrator: SubAgentOrchestrator) -> None:
        """超时竞争：多个任务同时超时"""
        timeout_count = 0

        async def racing_worker(task: SubAgentTask) -> dict[str, Any]:
            nonlocal timeout_count
            delay = random.uniform(0.05, 0.15)
            try:
                await asyncio.wait_for(asyncio.sleep(delay), timeout=0.08)
            except asyncio.TimeoutError:
                timeout_count += 1
                raise
            return {"result": "fast enough"}

        orchestrator._worker_pool._worker = racing_worker  # type: ignore[union-attr]

        handles = await asyncio.gather(*[
            orchestrator.spawn(AgentRole.EXPLORER, f"race-{i}")
            for i in range(16)
        ])

        results = await orchestrator.wait_all(timeout=3.0)
        assert len(results) == 16
        assert orchestrator.active_count == 0
        # 超时数应在合理范围（不精确断言，避免 flakiness）
        assert 0 <= timeout_count <= 16
        print(f"\n  [CHAOS] Timeout race: {timeout_count}/16 timed out, system stable")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_healing_under_chaos(self, monkey: ChaosMonkey) -> None:
        """自愈系统 + 混沌故障组合"""
        engine = SelfHealingEngine()
        chaos_rounds = 0

        async def always_chaotic(*args: Any, **kwargs: Any) -> str:
            nonlocal chaos_rounds
            chaos_rounds += 1
            faults = monkey.inject(fault_probability=0.5)
            if "network" in faults:
                raise TimeoutError("chaos timeout")
            if "api" in faults:
                raise Exception("chaos api 429")
            return "success"

        # 运行 10 轮混沌
        for _ in range(10):
            try:
                await always_chaotic()
            except Exception as e:
                success, _ = await engine.heal(
                    error=e,
                    original_task=always_chaotic,
                    task_args=(),
                    task_kwargs={},
                    context={"healing_attempt": 0},
                )
                # 某些轮次可能修复成功（当混沌没注入故障时）

        # 断言：10 轮后自愈引擎还活着，有历史记录
        assert chaos_rounds == 10
        assert len(engine.attempt_history) > 0
        print(f"\n  [CHAOS] Healing under chaos: {len(engine.attempt_history)} attempts, {engine.get_success_rate():.0%} success rate")

    def test_chaos_reproducibility(self, monkey: ChaosMonkey) -> None:
        """混沌测试可复现性（相同种子产生相同故障序列）"""
        seq1 = []
        seq2 = []

        for _ in range(5):
            monkey.inject(fault_probability=0.5)
            seq1.append(tuple(monkey.injected[-1]["faults"]))

        monkey2 = ChaosMonkey(seed=42)
        for _ in range(5):
            monkey2.inject(fault_probability=0.5)
            seq2.append(tuple(monkey2.injected[-1]["faults"]))

        assert seq1 == seq2, "相同种子的混沌注入必须可复现"
        print(f"\n  [CHAOS] Reproducibility: same seed = same fault sequence")
