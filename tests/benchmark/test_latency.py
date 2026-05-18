"""
性能基准测试

测量 Kimi-Agent 关键性能指标：
- 首 token 延迟 (Time To First Token)
- 总延迟 (Total Latency)
- 吞吐量 (Tokens per Second)
- 成本效率 ($/1K tokens)
- 内存增长（100 轮对话后）

运行方式:
    MOONSHOT_API_KEY=sk-xxxxx pytest tests/benchmark/test_latency.py -v
"""

from __future__ import annotations

import asyncio
import os
import time
import tracemalloc
from typing import Any

import pytest

from kimix.llm.client import KimiClient
from kimix.llm.models import Message

pytestmark = pytest.mark.benchmark

SKIP_REASON = "未配置 MOONSHOT_API_KEY 环境变量，跳过性能基准测试"


@pytest.mark.skipif(
    not os.environ.get("MOONSHOT_API_KEY"),
    reason=SKIP_REASON,
)
@pytest.mark.asyncio
@pytest.mark.timeout(120)
class TestLatencyBenchmark:
    """延迟与吞吐量基准测试"""

    @pytest.fixture
    def client(self) -> KimiClient:
        return KimiClient(
            api_key=os.environ["MOONSHOT_API_KEY"],
            thinking=False,
        )

    @pytest.mark.asyncio
    async def test_time_to_first_token(self, client: KimiClient) -> None:
        """首 token 延迟（用户可感知的启动速度）"""
        messages = [Message.user("你好")]

        t0 = time.monotonic()
        first_token_seen = False
        ttft_ms = 0.0

        async for event in client.chat(messages, stream=True):
            if event.get("type") == "content":
                if not first_token_seen:
                    ttft_ms = (time.monotonic() - t0) * 1000
                    first_token_seen = True
                break  # 收到第一个 token 就停

        assert first_token_seen, "未收到任何 token"
        assert ttft_ms < 5000, f"首 token 延迟 {ttft_ms:.0f}ms 超过 5 秒阈值"
        print(f"\n  [BENCH] TTFT: {ttft_ms:.0f}ms")

    @pytest.mark.asyncio
    async def test_total_latency_short(self, client: KimiClient) -> None:
        """短回复总延迟（1 句话，~50 tokens）"""
        messages = [Message.system("请用一句话回复。"), Message.user("你好")]

        t0 = time.monotonic()
        content_parts: list[str] = []
        async for event in client.chat(messages, stream=True):
            if event.get("type") == "content":
                data = event.get("data", "")
                if isinstance(data, str):
                    content_parts.append(data)

        total_ms = (time.monotonic() - t0) * 1000
        output_len = len("".join(content_parts))

        assert total_ms < 15000, f"总延迟 {total_ms:.0f}ms 超过 15 秒阈值"
        print(f"\n  [BENCH] Short Latency: {total_ms:.0f}ms | Output: {output_len} chars")

    @pytest.mark.asyncio
    async def test_tokens_per_second(self, client: KimiClient) -> None:
        """吞吐量：tok/s（生产可用性指标）"""
        messages = [Message.user("请写一段 200 字的自我介绍。")]

        t0 = time.monotonic()
        content_parts: list[str] = []
        output_tokens = 0

        async for event in client.chat(messages, stream=True):
            etype = event.get("type", "")
            if etype == "content":
                data = event.get("data", "")
                if isinstance(data, str):
                    content_parts.append(data)
            elif etype == "usage":
                data = event.get("data")
                if hasattr(data, "output_tokens"):
                    output_tokens = data.output_tokens

        elapsed = time.monotonic() - t0
        full_text = "".join(content_parts)

        # 如果 usage 没给，用字符数估算 (中文字符 ≈ 1.5 tokens)
        if output_tokens == 0:
            output_tokens = int(len(full_text) * 1.5)

        tok_per_sec = output_tokens / elapsed if elapsed > 0 else 0
        assert tok_per_sec > 5, f"吞吐量 {tok_per_sec:.1f} tok/s 低于 5 tok/s 阈值"
        print(f"\n  [BENCH] Throughput: {tok_per_sec:.1f} tok/s | Tokens: {output_tokens} | Time: {elapsed:.1f}s")

    @pytest.mark.asyncio
    async def test_cost_efficiency(self, client: KimiClient) -> None:
        """成本效率：$ / 1K tokens"""
        messages = [Message.user("你好")]

        cost_before = client._cost_tracker.get_session_cost()
        async for event in client.chat(messages, stream=True):
            pass
        cost_after = client._cost_tracker.get_session_cost()

        total_cost = cost_after - cost_before
        # 预估 tokens
        input_tokens = client.count_tokens("你好")
        total_tokens = input_tokens + 50  # 粗略估算输出

        cost_per_1k = (total_cost / total_tokens * 1000) if total_tokens > 0 else 0
        assert cost_per_1k < 0.05, f"成本效率 ${cost_per_1k:.4f}/1K 超过 $0.05/1K"
        print(f"\n  [BENCH] Cost: ${total_cost:.6f} | ~${cost_per_1k:.4f}/1K tokens")

    @pytest.mark.asyncio
    async def test_non_stream_latency(self, client: KimiClient) -> None:
        """非流式延迟（无实时反馈场景）"""
        messages = [Message.user("1+1=?")]

        t0 = time.monotonic()
        response = await client.chat_completion(messages)
        total_ms = (time.monotonic() - t0) * 1000

        assert response.content is not None
        assert total_ms < 20000, f"非流式延迟 {total_ms:.0f}ms 超过 20 秒"
        print(f"\n  [BENCH] Non-stream Latency: {total_ms:.0f}ms")


@pytest.mark.skipif(
    not os.environ.get("MOONSHOT_API_KEY"),
    reason=SKIP_REASON,
)
class TestMemoryBenchmark:
    """内存基准测试（非 async，纯本地测量）"""

    def test_memory_leak_simulation(self) -> None:
        """模拟 100 轮对话后的内存增长（本地 mock，不消耗 API）"""
        import gc

        # 模拟消息上下文增长
        messages: list[dict[str, Any]] = []
        base_text = "这是一个测试消息，用于模拟上下文增长对内存的影响。" * 20  # ~600 chars

        tracemalloc.start()
        baseline, _ = tracemalloc.get_traced_memory()

        for i in range(100):
            messages.append({"role": "user", "content": f"{base_text} [round {i}]"})
            if len(messages) > 20:
                messages = messages[-20:]  # 模拟 context window 截断

        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        growth_mb = (current - baseline) / (1024 * 1024)
        assert growth_mb < 50, f"100 轮模拟后内存增长 {growth_mb:.1f}MB 超过 50MB 阈值"
        print(f"\n  [BENCH] Memory Growth: {growth_mb:.2f}MB (peak: {peak/(1024*1024):.1f}MB)")
