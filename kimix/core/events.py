"""
事件定义模块

定义 Agent 引擎中使用的所有事件类型和辅助函数。
事件是引擎与外部（UI、日志等）通信的主要机制，支持 SSE 流式输出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from datetime import datetime, timezone


# 引擎事件类型
EventType = Literal[
    "thinking",       # 模型的思考过程（reasoning content）
    "content",        # 模型的响应内容
    "tool_call",      # 模型请求调用工具
    "tool_result",    # 工具执行结果
    "tool_start",     # 工具开始执行
    "tool_end",       # 工具执行结束
    "error",          # 错误事件
    "done",           # 完成事件
    "mode_switch",    # 模式切换事件
    "cost_update",    # 成本更新事件
    "warning",        # 警告事件
    "notice",         # 通知事件
    "preflight_alert", # 预判警报
]


@dataclass
class EngineEvent:
    """引擎事件结构

    所有事件均遵循此格式，便于 SSE 流式传输和统一处理。
    支持属性访问和字典访问两种方式。

    Attributes:
        type: 事件类型，见 EventType
        data: 事件载荷，类型根据 event.type 变化
        timestamp: 事件产生时间（ISO 格式字符串）
    """
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问（兼容旧代码）"""
        if key == "type":
            return self.type
        elif key == "data":
            return self.data
        elif key == "timestamp":
            return self.timestamp
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """支持 dict.get() 式访问"""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return key in ("type", "data", "timestamp")

    def __iter__(self):
        yield "type", self.type
        yield "data", self.data
        yield "timestamp", self.timestamp

    def keys(self):
        return ["type", "data", "timestamp"]

    def values(self):
        return [self.type, self.data, self.timestamp]

    def items(self):
        return [("type", self.type), ("data", self.data), ("timestamp", self.timestamp)]

    def __repr__(self) -> str:
        return f"EngineEvent(type={self.type!r}, data={self.data!r})"


def create_event(
    event_type: EventType,
    data: dict[str, Any] | None = None,
) -> EngineEvent:
    """创建标准化引擎事件

    工厂函数，用于统一创建事件，自动填充时间戳。

    Args:
        event_type: 事件类型
        data: 事件数据字典，不同事件类型对应不同结构

    Returns:
        EngineEvent 对象（支持 .type / .data / .timestamp 属性访问和 dict 式访问）
    """
    return EngineEvent(
        type=event_type,
        data=data or {},
    )


# 便捷创建函数，减少重复代码

def create_thinking_event(text: str) -> EngineEvent:
    """创建思考事件"""
    return create_event("thinking", {"text": text})


def create_content_event(text: str) -> EngineEvent:
    """创建内容事件"""
    return create_event("content", {"text": text})


def create_tool_call_event(tool_calls: list[dict]) -> EngineEvent:
    """创建工具调用事件"""
    return create_event("tool_call", {"tool_calls": tool_calls})


def create_tool_result_event(
    tool_call_id: str,
    name: str,
    result: Any,
    error: str | None = None,
) -> EngineEvent:
    """创建工具结果事件"""
    return create_event("tool_result", {
        "tool_call_id": tool_call_id,
        "name": name,
        "result": result,
        "error": error,
    })


def create_tool_start_event(
    tool_call_id: str,
    name: str,
    params: dict[str, Any],
) -> EngineEvent:
    """创建工具开始事件"""
    return create_event("tool_start", {
        "tool_call_id": tool_call_id,
        "name": name,
        "params": params,
    })


def create_tool_end_event(
    tool_call_id: str,
    name: str,
    duration_ms: int,
) -> EngineEvent:
    """创建工具结束事件"""
    return create_event("tool_end", {
        "tool_call_id": tool_call_id,
        "name": name,
        "duration_ms": duration_ms,
    })


def create_error_event(
    message: str,
    code: str = "UNKNOWN_ERROR",
    recoverable: bool = False,
) -> EngineEvent:
    """创建错误事件"""
    return create_event("error", {
        "message": message,
        "code": code,
        "recoverable": recoverable,
    })


def create_done_event(
    turn_id: str,
    usage: dict[str, Any] | None = None,
) -> EngineEvent:
    """创建完成事件"""
    return create_event("done", {
        "turn_id": turn_id,
        "usage": usage or {},
    })


def create_mode_switch_event(
    from_mode: str,
    to_mode: str,
    reason: str = "",
) -> EngineEvent:
    """创建模式切换事件"""
    return create_event("mode_switch", {
        "from": from_mode,
        "to": to_mode,
        "reason": reason,
    })


def create_cost_update_event(
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> EngineEvent:
    """创建成本更新事件"""
    return create_event("cost_update", {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    })
