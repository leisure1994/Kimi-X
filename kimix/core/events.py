"""
事件定义模块

定义 Agent 引擎中使用的所有事件类型和辅助函数。
事件是引擎与外部（UI、日志等）通信的主要机制，支持 SSE 流式输出。
"""

from __future__ import annotations

from typing import TypedDict, Any, Literal
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
]


class EngineEvent(TypedDict):
    """引擎事件结构
    
    所有事件均遵循此格式，便于 SSE 流式传输和统一处理。
    
    Attributes:
        type: 事件类型，见 EventType
        data: 事件载荷，类型根据 event.type 变化
        timestamp: 事件产生时间（ISO 格式字符串）
    
    Examples:
        >>> event: EngineEvent = {
        ...     "type": "content",
        ...     "data": {"text": "你好！"},
        ...     "timestamp": "2024-01-01T00:00:00",
        ... }
    """
    type: EventType
    data: dict[str, Any]
    timestamp: str


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
        完整的 EngineEvent 字典
    
    Examples:
        >>> event = create_event("content", {"text": "Hello"})
        >>> event["type"]
        'content'
        
        >>> error_event = create_event("error", {
        ...     "message": "文件未找到",
        ...     "code": "FILE_NOT_FOUND",
        ... })
    
    各事件类型的 data 结构规范:
        - thinking: {"text": str} - 思考文本片段
        - content: {"text": str} - 响应文本片段
        - tool_call: {"tool_calls": list[dict]} - 工具调用列表
        - tool_result: {"tool_call_id": str, "name": str, "result": Any, "error": str | None}
        - tool_start: {"tool_call_id": str, "name": str, "params": dict}
        - tool_end: {"tool_call_id": str, "name": str, "duration_ms": int}
        - error: {"message": str, "code": str, "recoverable": bool}
        - done: {"turn_id": str, "usage": dict | None}
        - mode_switch: {"from": str, "to": str, "reason": str}
        - cost_update: {"input_tokens": int, "output_tokens": int, "cost_usd": float}
    """
    return EngineEvent(
        type=event_type,
        data=data or {},
        timestamp=datetime.now(timezone.utc).isoformat(),
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
