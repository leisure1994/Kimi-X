"""
Kimi-Agent (kimix) 核心引擎模块

提供 Agent 主循环、会话管理、上下文管理和事件系统。
"""

from __future__ import annotations

from kimix.core.events import EngineEvent, create_event
from kimix.core.turn import Turn, TurnResult
from kimix.core.context import ContextManager
from kimix.core.session import Session, SessionManager
from kimix.core.engine import AgentEngine, AgentMode
from kimix.core.preflight import PreFlightChecker, PreFlightResult, PreFlightIssue, RiskLevel
from kimix.core.healing import SelfHealingEngine, HealingRule, HealingAttempt, ErrorCategory, HealingStrategy

__all__ = [
    # 事件系统
    "EngineEvent",
    "create_event",
    # 回合管理
    "Turn",
    "TurnResult",
    # 上下文管理
    "ContextManager",
    # 会话管理
    "Session",
    "SessionManager",
    # 核心引擎
    "AgentEngine",
    "AgentMode",
    # 预判与修复
    "PreFlightChecker",
    "PreFlightResult",
    "PreFlightIssue",
    "RiskLevel",
    "SelfHealingEngine",
    "HealingRule",
    "HealingAttempt",
    "ErrorCategory",
    "HealingStrategy",
]
