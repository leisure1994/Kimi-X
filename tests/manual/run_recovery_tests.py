import asyncio
import sys
import tempfile
from pathlib import Path

# 手动运行智能恢复测试的关键用例

from kimix.core.preflight import PreFlightChecker, RiskLevel
from kimix.core.healing import SelfHealingEngine, HealingStrategy, ErrorCategory
from kimix.memory.experience import ExperienceMemory

async def run_tests():
    passed = 0
    failed = 0

    # Test 1: 预判 - API Key 缺失
    try:
        checker = PreFlightChecker()
        result = await checker.check({"api_key": "", "workspace_dir": ".", "task_signature": "test"})
        assert not result.passed
        assert any(i.risk_level == RiskLevel.CRITICAL for i in result.issues)
        print("✅ Test 1: 预判 API Key 缺失 CRITICAL")
        passed += 1
    except Exception as e:
        print(f"❌ Test 1: {e}")
        failed += 1

    # Test 2: 预判 - 自动创建目录
    try:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = f"{tmp}/new_workspace"
            result = await checker.check({
                "api_key": "sk-test",
                "workspace_dir": missing_dir,
                "task_signature": "test",
                "skip_network_test": True,
            })
            assert os.path.exists(missing_dir), f"目录未创建: {missing_dir}"
            assert len(result.auto_fixed) > 0, f"auto_fixed={result.auto_fixed}"
            print("✅ Test 2: 预判自动创建目录")
            passed += 1
    except Exception as e:
        import traceback
        print(f"❌ Test 2: {e}")
        traceback.print_exc()
        failed += 1

    # Test 3: 预判 - 一切正常
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = await checker.check({
                "api_key": "sk-test123",
                "workspace_dir": tmp,
                "task_signature": "test",
                "skip_network_test": True,
            })
            assert result.passed
            assert len(result.issues) == 0
            print("✅ Test 3: 预判全部通过")
            passed += 1
    except Exception as e:
        print(f"❌ Test 3: {e}")
        failed += 1

    # Test 4: 修复 - 分类超时
    try:
        engine = SelfHealingEngine()
        err = TimeoutError("Connection timed out")
        cat = engine.classify_error(err)
        assert cat == ErrorCategory.NETWORK
        print("✅ Test 4: 错误分类 NETWORK")
        passed += 1
    except Exception as e:
        print(f"❌ Test 4: {e}")
        failed += 1

    # Test 5: 修复 - 重试成功
    try:
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
        assert success and result == "success"
        print("✅ Test 5: 修复重试成功")
        passed += 1
    except Exception as e:
        print(f"❌ Test 5: {e}")
        failed += 1

    # Test 6: 经验 - 记录与最佳策略
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exp.jsonl"
            memory = ExperienceMemory(storage_path=path)
            memory.record_fix("network:timeout", "backoff_retry", True)
            memory.record_fix("network:timeout", "retry", False)
            best = memory.get_best_strategy("network:timeout")
            assert best == "backoff_retry"
            print("✅ Test 6: 经验最佳策略推荐")
            passed += 1
    except Exception as e:
        print(f"❌ Test 6: {e}")
        failed += 1

    # Test 7: 经验 - 性能基线
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exp.jsonl"
            memory = ExperienceMemory(storage_path=path)
            memory.record_performance("code_review", "kimi", 1500, 1000, 500, 0.003)
            memory.record_performance("code_review", "kimi", 2000, 1200, 600, 0.004)
            baseline = memory.get_performance_baseline("code_review", "kimi")
            assert baseline is not None
            assert baseline["avg_latency_ms"] == 1750.0
            print("✅ Test 7: 经验性能基线")
            passed += 1
    except Exception as e:
        print(f"❌ Test 7: {e}")
        failed += 1

    # Test 8: 经验 - 持久化
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "exp.jsonl"
            memory = ExperienceMemory(storage_path=path)
            memory.record_fix("timeout", "retry", True)
            memory2 = ExperienceMemory(storage_path=path)
            best = memory2.get_best_strategy("timeout")
            assert best == "retry"
            print("✅ Test 8: 经验持久化加载")
            passed += 1
    except Exception as e:
        print(f"❌ Test 8: {e}")
        failed += 1

    # Test 9: 集成 - 完整链路
    try:
        with tempfile.TemporaryDirectory() as tmp:
            exp_path = Path(tmp) / "exp.jsonl"
            experience = ExperienceMemory(storage_path=exp_path)
            healing = SelfHealingEngine(experience_memory=experience)
            preflight = PreFlightChecker(experience_memory=experience)

            result = await preflight.check({
                "api_key": "sk-test",
                "workspace_dir": tmp,
                "task_signature": "full pipeline test",
                "skip_network_test": True,
            })
            assert result.passed, f"preflight failed: {result.issues}"

            async def always_fail(*args, **kwargs):
                raise TimeoutError("timeout")
            success, _ = await healing.heal(
                error=TimeoutError("timeout"),
                original_task=always_fail,
                task_args=(),
                task_kwargs={},
            )
            assert experience.has_similar("network:timeout"), "experience not recorded"
            print("✅ Test 9: 集成完整链路")
            passed += 1
    except Exception as e:
        import traceback
        print(f"❌ Test 9: {e}")
        traceback.print_exc()
        failed += 1

    print(f"\n{'='*40}")
    print(f"结果: {passed}/{passed+failed} 通过")
    if failed == 0:
        print("✅ 全部通过！")
    else:
        print(f"⚠️ {failed} 项失败")
    return failed == 0

if __name__ == "__main__":
    import os
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
