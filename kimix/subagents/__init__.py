"""
Kimi-Agent 子 Agent 编排系统

提供智能子 Agent 并发执行能力，包括:
- SubAgentOrchestrator: 编排器（并发控制、任务调度、结果收集）
- SubAgentWorker: 工作进程（异步执行、进度事件、取消支持）
- AgentRole: Agent 角色枚举（EXPLORER/PLANNER/CODER/REVIEWER/TESTER/DEBUGGER/RESEARCHER/DOCUMENTER）
- TaskPriority: 任务优先级枚举（LOW/NORMAL/HIGH/URGENT）
- SubAgentTask/SubAgentHandle/SubAgentResult: 数据模型

使用示例:
    >>> from kimix.subagents import SubAgentOrchestrator, AgentRole
    >>> orchestrator = SubAgentOrchestrator(max_concurrent=32)
    >>> handle = await orchestrator.spawn(
    ...     role=AgentRole.EXPLORER,
    ...     task="分析项目结构",
    ...     context={"project_path": "."},
    ... )
    >>> results = await orchestrator.wait_all([handle])
"""

from __future__ import annotations

from kimix.subagents.models import (
    AgentRole,
    SubAgentHandle,
    SubAgentResult,
    SubAgentTask,
    TaskPriority,
)
from kimix.subagents.orchestrator import SubAgentOrchestrator
from kimix.subagents.worker import SubAgentWorker

__all__ = [
    "AgentRole",
    "TaskPriority",
    "SubAgentTask",
    "SubAgentHandle",
    "SubAgentResult",
    "SubAgentWorker",
    "SubAgentOrchestrator",
]
