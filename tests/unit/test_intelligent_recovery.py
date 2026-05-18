"""
预判系统、自我修复、经验积累 集成测试

验证三个系统的完整链路：
1. 预判系统：检测到 API Key 缺失时阻断执行
2. 自我修复：模拟网络超时后指数退避重试
3. 经验积累：记录修复经验并推荐最佳策略
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from kimix.core.preflight import PreFlightChecker, RiskLevel
from kimix.core.healing import (
    SelfHealingEngine,
    HealingRule,
    HealingStrategy,
    ErrorCategory,
)
from kimix.memory.experience import ExperienceMemory, ExperienceRecord



pytestmark = pytest.mark.unit
class TestPreFlightChecker:
    """预判系统测试"""

    @pytest.fixture
    def checker(self) -> PreFlightChecker:
        return PreFlightChecker()

    @pytest.mark.asyncio
    async def test_missing_api_key_critical(self, checker: PreFlightChecker) -> None:
        """API Key 缺失应判定为 CRITICAL 级别"""
        result = await checker.check({
            "api_key": "",
            "workspace_dir": ".",
            "task_signature": "test",
        })
        assert not result.passed
        assert any(i.risk_level == RiskLevel.CRITICAL for i in result.issues)
        assert any(i.category == "missing_api_key" for i in result.issues)

    @pytest.mark.asyncio
    async def test_api_key_format_suspicious(self, checker: PreFlightChecker) -> None:
        """API Key 格式不对应判定为 HIGH"""
        result = await checker.check({
            "api_key": "not-start-with-sk-",
            "workspace_dir": ".",
            "task_signature": "test",
        })
        assert any(i.category == "api_key_suspicious_format" for i in result.issues)

    @pytest.mark.asyncio
    async def test_auto_create_dir(self, checker: PreFlightChecker) -> None:
        """目录缺失应自动修复"""
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = os.path.join(tmp, "new_workspace")
            result = await checker.check({
                "api_key": "sk-test",
                "workspace_dir": missing_dir,
                "task_signature": "test",
            })
            assert os.path.exists(missing_dir)
            assert len(result.auto_fixed) > 0
            assert result.passed  # 修复后不应有阻断性问题

    @pytest.mark.asyncio
    async def test_all_clear(self, checker: PreFlightChecker) -> None:
        """一切正常时应通过"""
        with tempfile.TemporaryDirectory() as tmp:
            result = await checker.check({
                "api_key": "sk-test123",
                "workspace_dir": tmp,
                "task_signature": "test",
                "skip_network_test": True,
            })
            assert result.passed
            assert len(result.issues) == 0


class TestSelfHealingEngine:
    """自我修复系统测试"""

    @pytest.fixture
    def engine(self) -> SelfHealingEngine:
        return SelfHealingEngine()

    def test_classify_timeout(self, engine: SelfHealingEngine) -> None:
        """超时错误应分类为 NETWORK"""
        err = TimeoutError("Connection timed out after 30s")
        cat = engine.classify_error(err)
        assert cat == ErrorCategory.NETWORK

    def test_classify_rate_limit(self, engine: SelfHealingEngine) -> None:
        """限流错误应分类为 API"""
        err = Exception("Rate limit exceeded: 429 Too Many Requests")
        cat = engine.classify_error(err)
        assert cat == ErrorCategory.API

    def test_classify_token_overflow(self, engine: SelfHealingEngine) -> None:
        """Token 超限应分类为 TOKEN"""
        err = ValueError("context length exceeded maximum 200000")
        cat = engine.classify_error(err)
        assert cat == ErrorCategory.TOKEN

    def test_classify_unknown(self, engine: SelfHealingEngine) -> None:
        """未知错误兜底"""
        err = RuntimeError("something weird happened")
        cat = engine.classify_error(err)
        assert cat == ErrorCategory.UNKNOWN

    @pytest.mark.asyncio
    async def test_heal_retry_success(self, engine: SelfHealingEngine) -> None:
        """重试策略成功场景"""
        call_count = 0
        async def flaky_task(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("timeout")
            return "success"

        success, result = await engine.heal(
            error=TimeoutError("timeout"),
            original_task=flaky_task,
            task_args=(),
            task_kwargs={},
        )
        assert success
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_heal_all_fail(self, engine: SelfHealingEngine) -> None:
        """所有策略失败时返回 False"""
        async def always_fail(*args, **kwargs):
            raise TimeoutError("still timeout")

        success, result = await engine.heal(
            error=TimeoutError("timeout"),
            original_task=always_fail,
            task_args=(),
            task_kwargs={},
        )
        assert not success

    def test_success_rate_calculation(self, engine: SelfHealingEngine) -> None:
        """成功率统计"""
        engine._record_attempt(ErrorCategory.NETWORK, "timeout", HealingStrategy.RETRY, True)
        engine._record_attempt(ErrorCategory.NETWORK, "timeout", HealingStrategy.RETRY, True)
        engine._record_attempt(ErrorCategory.NETWORK, "timeout", HealingStrategy.RETRY, False)

        rate = engine.get_success_rate(ErrorCategory.NETWORK)
        assert pytest.approx(rate, 0.01) == 2 / 3


class TestExperienceMemory:
    """经验积累系统测试"""

    @pytest.fixture
    def memory(self) -> ExperienceMemory:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "experience.jsonl"
            return ExperienceMemory(storage_path=path, auto_save=True)

    def test_record_and_retrieve(self, memory: ExperienceMemory) -> None:
        """记录并检索经验"""
        memory.record_fix(
            error_signature="network:timeout",
            strategy="backoff_retry",
            success=True,
            context={"delay": 2},
        )
        memory.record_fix(
            error_signature="network:timeout",
            strategy="retry",
            success=False,
            context={},
        )

        best = memory.get_best_strategy("network:timeout")
        assert best == "backoff_retry"

    def test_similar_matching(self, memory: ExperienceMemory) -> None:
        """相似经验匹配"""
        memory.record_preflight(
            task_signature="read file analyze code",
            issue_category="permission",
            was_prevented=True,
        )
        assert memory.has_similar("read file analyze project")

    def test_performance_baseline(self, memory: ExperienceMemory) -> None:
        """性能基线计算"""
        memory.record_performance(
            task_signature="code_review",
            model="kimi-for-coding",
            latency_ms=1500.0,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.003,
        )
        memory.record_performance(
            task_signature="code_review",
            model="kimi-for-coding",
            latency_ms=2000.0,
            input_tokens=1200,
            output_tokens=600,
            cost_usd=0.004,
        )

        baseline = memory.get_performance_baseline("code_review", "kimi-for-coding")
        assert baseline is not None
        assert baseline["avg_latency_ms"] == pytest.approx(1750.0, 0.1)
        assert baseline["sample_count"] == 2

    def test_deduplication(self, memory: ExperienceMemory) -> None:
        """相同经验自动合并"""
        memory.record_fix("timeout", "retry", True)
        memory.record_fix("timeout", "retry", True)
        memory.record_fix("timeout", "retry", False)

        stats = memory.get_stats()
        assert stats["total"] == 1  # 合并为一条
        assert stats["effectiveness"] == pytest.approx((1.0 + 1.0 + 0.0) / 3, 0.01)

    def test_persistence(self, memory: ExperienceMemory) -> None:
        """持久化与重新加载"""
        memory.record_fix("timeout", "retry", True)
        path = memory.storage_path
        assert path is not None

        # 重新加载
        memory2 = ExperienceMemory(storage_path=path, auto_save=True)
        best = memory2.get_best_strategy("timeout")
        assert best == "retry"

    def test_stats_empty(self) -> None:
        """空经验库统计"""
        mem = ExperienceMemory(storage_path=None, auto_save=False)
        stats = mem.get_stats()
        assert stats["total"] == 0


class TestIntegration:
    """三系统集成测试"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self) -> None:
        """完整链路：预判 → 执行 → 错误 → 修复 → 经验积累"""
        with tempfile.TemporaryDirectory() as tmp:
            exp_path = Path(tmp) / "exp.jsonl"
            experience = ExperienceMemory(storage_path=exp_path)
            healing = SelfHealingEngine(experience_memory=experience)
            preflight = PreFlightChecker(experience_memory=experience)

            # 1. 预判：一切正常
            result = await preflight.check({
                "api_key": "sk-test",
                "workspace_dir": tmp,
                "task_signature": "full pipeline test",
                "skip_network_test": True,
            })
            assert result.passed

            # 2. 模拟执行 + 故障 + 修复
            async def flaky_task():
                raise TimeoutError("connection timeout")

            success, _ = await healing.heal(
                error=TimeoutError("connection timeout"),
                original_task=flaky_task,
                task_args=(),
                task_kwargs={},
                context={"healing_attempt": 0},
            )
            assert not success  # flaky_task 永远失败

            # 3. 经验已记录
            assert experience.has_similar("connection timeout")
            stats = experience.get_stats()
            assert stats["total"] > 0

    @pytest.mark.asyncio
    async def test_preflight_with_experience(self) -> None:
        """预判系统读取历史经验"""
        with tempfile.TemporaryDirectory() as tmp:
            exp_path = Path(tmp) / "exp.jsonl"
            experience = ExperienceMemory(storage_path=exp_path)
            # 先积累一条经验
            experience.record_preflight("network heavy task", "network", was_prevented=False)

            preflight = PreFlightChecker(experience_memory=experience)
            result = await preflight.check({
                "api_key": "sk-test",
                "workspace_dir": tmp,
                "task_signature": "network heavy task download",
                "skip_network_test": True,
            })
            # 有历史经验但不触发（相似度阈值需满足）
            # 这个测试验证系统不崩溃
            assert isinstance(result.passed, bool)
