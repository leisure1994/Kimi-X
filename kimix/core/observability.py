"""
可观测性模块 (Observability)

为 Kimi-Agent 提供生产级可观测能力：
- Trace ID 贯穿：每个 turn/session 有唯一追踪 ID
- 结构化 JSON 日志：机器可读、可索引
- 事件流追踪：记录所有 engine 事件的时序
- 性能指标收集：latency、token/s、cost/turn
- 慢查询检测：超过阈值的 turn 自动标记

使用方法:
    >>> from kimix.core.observability import Observability
    >>> obs = Observability(trace_id="trace-abc123", log_json=True)
    >>> obs.event("llm_call_start", {"model": "kimi-for-coding"})
    >>> obs.finish_turn(latency_ms=1500, tokens=2000)
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


@dataclass
class TraceEvent:
    """单个追踪事件"""
    trace_id: str
    timestamp: str
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    parent_span: str | None = None
    span_id: str | None = None


@dataclass
class TurnMetrics:
    """单轮对话指标"""
    trace_id: str
    turn_id: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    token_per_second: float
    model: str
    mode: str
    tool_calls: int
    errors: int
    healing_attempts: int
    preflight_issues: int
    timestamp: str
    is_slow: bool = False  # latency > threshold


class Observability:
    """可观测性追踪器

    提供两种输出模式：
    - console: 彩色结构化输出到终端
    - json: 每行一个 JSON 对象（适合 ELK/Loki 等日志系统）
    """

    SLOW_TURN_THRESHOLD_MS = 5000  # 5 秒以上为慢查询

    def __init__(
        self,
        trace_id: str | None = None,
        session_id: str | None = None,
        log_json: bool = False,
        json_file: Path | str | None = None,
        enable_console: bool = True,
    ) -> None:
        """初始化可观测性追踪器

        Args:
            trace_id: 追踪 ID（不提供则自动生成）
            session_id: 会话 ID（可选）
            log_json: 是否输出 JSON 格式日志
            json_file: JSON 日志文件路径（不提供则输出到 stderr）
            enable_console: 是否输出彩色控制台日志
        """
        self.trace_id = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        self.session_id = session_id
        self.log_json = log_json
        self.enable_console = enable_console
        self.json_file: Path | None = Path(json_file) if json_file else None

        # 运行时状态
        self._current_span: str | None = None
        self._span_stack: list[str] = []
        self._events: list[TraceEvent] = []
        self._turn_metrics: list[TurnMetrics] = []
        self._start_time = time.monotonic()

        # JSON 输出句柄
        self._json_out: TextIO | None = None
        if self.log_json and self.json_file:
            self.json_file.parent.mkdir(parents=True, exist_ok=True)
            self._json_out = open(self.json_file, "a", encoding="utf-8")

    def __enter__(self) -> Observability:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """关闭资源"""
        if self._json_out:
            self._json_out.close()
            self._json_out = None

    def event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """记录一个追踪事件"""
        now = datetime.now(timezone.utc).isoformat()
        span_id = f"span-{uuid.uuid4().hex[:8]}"

        ev = TraceEvent(
            trace_id=self.trace_id,
            timestamp=now,
            event_type=event_type,
            data=data or {},
            duration_ms=duration_ms,
            parent_span=self._current_span,
            span_id=span_id,
        )
        self._events.append(ev)

        if self.enable_console:
            self._print_console(ev)
        if self.log_json:
            self._print_json(ev)

    def span(self, name: str) -> "_SpanContext":
        """创建一个追踪 span（上下文管理器）"""
        return _SpanContext(self, name)

    def finish_turn(
        self,
        turn_id: str,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
        mode: str,
        tool_calls: int = 0,
        errors: int = 0,
        healing_attempts: int = 0,
        preflight_issues: int = 0,
    ) -> TurnMetrics:
        """记录一轮对话的完整指标"""
        total = input_tokens + output_tokens
        tok_per_sec = (output_tokens / (latency_ms / 1000)) if latency_ms > 0 else 0.0
        is_slow = latency_ms > self.SLOW_TURN_THRESHOLD_MS

        metrics = TurnMetrics(
            trace_id=self.trace_id,
            turn_id=turn_id,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost_usd,
            token_per_second=round(tok_per_sec, 2),
            model=model,
            mode=mode,
            tool_calls=tool_calls,
            errors=errors,
            healing_attempts=healing_attempts,
            preflight_issues=preflight_issues,
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_slow=is_slow,
        )
        self._turn_metrics.append(metrics)

        if self.enable_console:
            self._print_turn_summary(metrics)
        if self.log_json:
            self._print_json(metrics)

        return metrics

    def get_session_summary(self) -> dict[str, Any]:
        """获取会话级汇总统计"""
        if not self._turn_metrics:
            return {"trace_id": self.trace_id, "turns": 0}

        total_cost = sum(m.cost_usd for m in self._turn_metrics)
        total_tokens = sum(m.total_tokens for m in self._turn_metrics)
        avg_latency = sum(m.latency_ms for m in self._turn_metrics) / len(self._turn_metrics)
        slow_count = sum(1 for m in self._turn_metrics if m.is_slow)

        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turns": len(self._turn_metrics),
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 2),
            "slow_turns": slow_count,
            "total_errors": sum(m.errors for m in self._turn_metrics),
            "total_healing": sum(m.healing_attempts for m in self._turn_metrics),
            "uptime_seconds": round(time.monotonic() - self._start_time, 2),
        }

    def print_summary(self) -> None:
        """打印会话摘要"""
        summary = self.get_session_summary()
        if self.enable_console:
            print(f"\n📊 会话摘要 [{self.trace_id}]")
            print(f"   轮数: {summary['turns']} | 总 Token: {summary['total_tokens']}")
            print(f"   总成本: ${summary['total_cost_usd']} | 平均延迟: {summary['avg_latency_ms']}ms")
            if summary["slow_turns"] > 0:
                print(f"   ⚠️ 慢查询: {summary['slow_turns']} 轮")
        if self.log_json:
            self._raw_json({
                "type": "session_summary",
                **summary,
            })

    # ── 内部输出 ──

    def _print_console(self, ev: TraceEvent) -> None:
        """彩色控制台输出"""
        ts = ev.timestamp.split("T")[1][:12]
        parent = f" (parent={ev.parent_span})" if ev.parent_span else ""
        dur = f" [{ev.duration_ms:.0f}ms]" if ev.duration_ms else ""
        print(f"  [{ts}] {ev.event_type:<20}{parent}{dur} {json.dumps(ev.data, ensure_ascii=False)[:100]}")

    def _print_turn_summary(self, m: TurnMetrics) -> None:
        """彩色 turn 汇总输出"""
        flag = "⚠️ SLOW" if m.is_slow else ""
        print(f"\n  [{m.timestamp.split('T')[1][:12]}] Turn {m.turn_id} {flag}")
        print(f"    Latency: {m.latency_ms:.0f}ms | Tokens: {m.total_tokens} ({m.input_tokens}in/{m.output_tokens}out)")
        print(f"    Speed: {m.token_per_second:.1f} tok/s | Cost: ${m.cost_usd:.6f}")
        if m.errors > 0:
            print(f"    Errors: {m.errors} | Healing: {m.healing_attempts}")

    def _print_json(self, obj: TraceEvent | TurnMetrics) -> None:
        """输出 JSON 格式日志"""
        data = asdict(obj)
        data["type"] = "trace_event" if isinstance(obj, TraceEvent) else "turn_metrics"
        self._raw_json(data)

    def _raw_json(self, data: dict[str, Any]) -> None:
        """原始 JSON 输出"""
        line = json.dumps(data, ensure_ascii=False, default=str)
        if self._json_out:
            self._json_out.write(line + "\n")
            self._json_out.flush()
        elif self.log_json:
            # 没有文件时输出到 stderr
            print(line, file=sys.stderr)


class _SpanContext:
    """Span 上下文管理器"""

    def __init__(self, obs: Observability, name: str) -> None:
        self.obs = obs
        self.name = name
        self.span_id = f"span-{uuid.uuid4().hex[:8]}"
        self._start: float | None = None

    def __enter__(self) -> "_SpanContext":
        self._start = time.monotonic()
        self.obs._span_stack.append(self.span_id)
        self.obs._current_span = self.span_id
        self.obs.event(f"span_start:{self.name}", {"span_id": self.span_id})
        return self

    def __exit__(self, *args: Any) -> None:
        duration = (time.monotonic() - self._start) * 1000 if self._start else None
        self.obs._span_stack.pop()
        self.obs._current_span = self.obs._span_stack[-1] if self.obs._span_stack else None
        self.obs.event(f"span_end:{self.name}", {"span_id": self.span_id}, duration_ms=duration)
