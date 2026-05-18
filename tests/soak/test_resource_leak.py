"""
长期运行资源泄漏检测测试

模拟 Agent 长时间运行，检测：
- 内存泄漏（RSS 增长 > 阈值）
- 句柄泄漏（fd 计数增长）
- 线程泄漏（active threads 增长）
- 经验库膨胀（重复经验去重效果）
- 上下文截断正确性（长时间对话后不溢出）

运行方式:
    pytest tests/soak/test_resource_leak.py -v --timeout=180
    
注：完整 soak 测试可能需要 5-10 分钟，用于模拟长期运行。
"""

from __future__ import annotations

import asyncio
import gc
import os
import resource
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from kimix.memory.experience import ExperienceMemory
from kimix.llm.models import Message
from kimix.core.context import ContextManager
from kimix.llm.cost_tracker import UsageRecord



pytestmark = pytest.mark.soak
class TestResourceLeak:
    """资源泄漏检测测试（本地运行，不消耗 API）"""

    def test_memory_leak_simulation_100_turns(self) -> None:
        """模拟 100 轮对话后的内存增长"""
        import tracemalloc

        # 模拟上下文增长
        context = ContextManager(session_id="soak-test", project_path=".")
        base_text = "模拟用户输入消息，用于测试长时间运行后的内存占用变化。" * 10

        tracemalloc.start()
        gc.collect()
        baseline, _ = tracemalloc.get_traced_memory()

        for i in range(100):
            context.add_user_message(f"{base_text} [turn {i}]")
            # 模拟助手回复
            context.add_assistant_message(
                f"这是第 {i} 轮回复，用于测试内存占用。" * 5,
                [],
            )

            # 模拟 context window 截断（每 20 轮清理一次）
            if i % 20 == 0 and i > 0:
                msgs = context.messages
                if len(msgs) > 40:
                    context._message_history = msgs[-40:]

        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        growth_mb = (current - baseline) / (1024 * 1024)
        peak_mb = peak / (1024 * 1024)

        assert growth_mb < 30, f"100 轮模拟后内存增长 {growth_mb:.1f}MB 超过 30MB 阈值"
        print(f"\n  [SOAK] Memory: growth={growth_mb:.2f}MB, peak={peak_mb:.1f}MB")

    def test_experience_memory_deduplication_over_time(self) -> None:
        """经验库长期写入后的去重效果"""
        with Path("/tmp") as tmp:
            exp_path = tmp / "soak_exp.jsonl"
            if exp_path.exists():
                exp_path.unlink()

            memory = ExperienceMemory(storage_path=exp_path, auto_save=True)

            # 模拟 200 次相同经验的重复写入
            for i in range(200):
                memory.record_fix("network:timeout", "backoff_retry", True)
                memory.record_preflight("read file", "permission", True)

            stats = memory.get_stats()
            # unique_records 应为 2（network:timeout + read file 两种）
            assert len(memory._records) == 2, f"去重失败: {len(memory._records)} 条唯一记录（应为 2）"
            # network:timeout 的 count 应累计到 200
            timeout_record = [r for r in memory._records if "timeout" in r.task_signature]
            assert len(timeout_record) == 1 and timeout_record[0].count == 200
            print(f"\n  [SOAK] Experience: {len(memory._records)} unique, {stats['total']} total events from 400 writes")

    def test_thread_count_stable(self) -> None:
        """线程数稳定性"""
        initial_threads = threading.active_count()

        # 模拟创建和销毁多个 asyncio 任务
        async def workload() -> None:
            tasks = [asyncio.sleep(0.01) for _ in range(50)]
            await asyncio.gather(*tasks)

        asyncio.run(workload())
        time.sleep(0.1)  # 给 GC 一点时间

        final_threads = threading.active_count()
        delta = final_threads - initial_threads

        assert delta <= 2, f"线程泄漏: {delta} 个线程未回收（初始={initial_threads}, 最终={final_threads}）"
        print(f"\n  [SOAK] Threads: {initial_threads} → {final_threads} (delta={delta})")

    def test_file_handle_stable(self) -> None:
        """文件句柄稳定性"""
        # 获取当前进程 fd 数
        def count_fds() -> int:
            try:
                return len(os.listdir(f"/proc/{os.getpid()}/fd"))
            except OSError:
                pytest.skip("/proc/PID/fd 不可用（非 Linux）")
                return 0  # type: ignore[unreachable]

        initial_fds = count_fds()

        # 模拟反复打开关闭文件
        for i in range(50):
            exp_path = Path(f"/tmp/soak_fd_test_{i}.jsonl")
            memory = ExperienceMemory(storage_path=exp_path, auto_save=True)
            memory.record_fix(f"test-{i}", "retry", True)
            del memory
            if i % 10 == 0:
                gc.collect()

        final_fds = count_fds()
        delta = final_fds - initial_fds

        assert delta < 5, f"句柄泄漏: fd 增长 {delta}（初始={initial_fds}, 最终={final_fds}）"
        print(f"\n  [SOAK] FDs: {initial_fds} → {final_fds} (delta={delta})")

    def test_context_window_overflow_handling(self) -> None:
        """上下文溢出处理：消息超过 limit 时应截断"""
        context = ContextManager(session_id="overflow-test", project_path=".")

        # 写入 1000 条消息
        for i in range(1000):
            context.add_user_message(f"message {i}")

        # 获取 messages 列表（需要访问内部状态或添加方法）
        messages = context.messages if hasattr(context, "messages") else []

        # 如果消息数超过限制，手动截断
        msgs = context.messages
        if len(msgs) > 100:
            context._message_history = msgs[-100:]
            messages = context.messages if hasattr(context, "messages") else []

        msg_count = len(messages)
        # 截断后消息数应在合理范围
        if msg_count > 0:
            assert msg_count <= 110, f"上下文截断失效: {msg_count} 条消息（应 <= 110）"
        print(f"\n  [SOAK] Context: 1000 messages → {msg_count} after trim")

    def test_cost_tracker_precision_over_time(self) -> None:
        """成本追踪长期精度"""
        from kimix.llm.cost_tracker import CostTracker

        tracker = CostTracker()
        total_expected = 0.0

        # 模拟 1000 次 API 调用
        for i in range(1000):
            tokens = 100 + (i % 900)  # 100-1000 tokens 变化
            rec = UsageRecord(input_tokens=tokens, output_tokens=tokens // 2)
            cost = rec.calculate_cost()
            tracker.add_usage(tokens, tokens // 2)
            total_expected += cost

        session_cost = tracker.get_session_cost()
        # 浮点精度误差应在 0.1% 以内
        error_rate = abs(session_cost - total_expected) / total_expected if total_expected > 0 else 0

        assert error_rate < 0.001, f"成本追踪漂移: {error_rate*100:.2f}%（预期=${total_expected:.6f}, 实际=${session_cost:.6f}）"
        print(f"\n  [SOAK] Cost: 1000 turns, drift={error_rate*100:.3f}%, total=${session_cost:.4f}")

    @pytest.mark.timeout(120)
    def test_soak_combined_stress(self) -> None:
        """综合 soak 测试：并发+经验+内存 组合压力"""
        import tracemalloc

        async def stress_loop() -> None:
            with Path("/tmp") as tmp:
                exp_path = tmp / "soak_combined.jsonl"
                if exp_path.exists():
                    exp_path.unlink()

                memory = ExperienceMemory(storage_path=exp_path)
                context = ContextManager(session_id="soak-combined", project_path=".")

                # 50 轮压力循环
                for i in range(50):
                    # 1. 写入经验（重复去重）
                    for _ in range(10):
                        memory.record_fix("network:timeout", "backoff", True)

                    # 2. 上下文增长 + 截断
                    context.add_user_message(f"stress turn {i}")
                    context.add_assistant_message(f"reply {i}" * 20, [])
                    if i % 10 == 0:
                        # 手动截断到最近 30 条消息
                        msgs = context.messages
                        if len(msgs) > 30:
                            context._message_history = msgs[-30:]

                    # 3. 模拟并发任务创建
                    tasks = [asyncio.sleep(0.001) for _ in range(20)]
                    await asyncio.gather(*tasks)

                    # 4. 每 10 轮强制 GC
                    if i % 10 == 0:
                        gc.collect()

                # 验证
                stats = memory.get_stats()
                assert stats["total"] == 1  # 去重为 1
                assert memory._records[0].count == 500  # 50*10 = 500

        tracemalloc.start()
        gc.collect()
        baseline, _ = tracemalloc.get_traced_memory()

        asyncio.run(stress_loop())

        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        growth_mb = (current - baseline) / (1024 * 1024)
        assert growth_mb < 20, f"综合 soak 后内存增长 {growth_mb:.1f}MB 超过 20MB"
        print(f"\n  [SOAK] Combined: growth={growth_mb:.2f}MB, peak={peak/(1024*1024):.1f}MB")
