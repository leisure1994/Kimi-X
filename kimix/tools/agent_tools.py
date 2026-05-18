"""
子 Agent 工具集（预留接口）

提供子 Agent 的打开、评估和关闭操作。这些工具是预留接口，
实际实现需要配合子 Agent 编排器使用。

当前为占位实现，展示了完整接口设计。后续与子 Agent 系统集成时
会替换为实际逻辑。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 子 Agent 状态存储（临时内存存储，后续由编排器管理）
# ---------------------------------------------------------------------------

# agent_id -> agent_info 的全局映射
_agent_registry: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# 1. AgentOpenTool
# ---------------------------------------------------------------------------


class AgentOpenTool(AbstractTool):
    """打开（创建）子 Agent

    创建一个新的子 Agent 实例，分配角色和任务。
    子 Agent 在后台独立运行，可通过返回的 agent_id 进行后续交互。

    当前为预留接口，返回模拟的 Agent ID。
    """

    name = "agent_open"
    description = (
        "创建并启动一个子 Agent 来处理特定任务。"
        "子 Agent 会在后台独立运行，返回一个 agent_id 用于后续交互。"
        "支持的角色: explorer, planner, coder, reviewer, tester, debugger, researcher, documenter"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": "子 Agent 角色",
                "enum": [
                    "explorer",
                    "planner",
                    "coder",
                    "reviewer",
                    "tester",
                    "debugger",
                    "researcher",
                    "documenter",
                ],
            },
            "task": {
                "type": "string",
                "description": "分配给子 Agent 的任务描述",
            },
            "context": {
                "type": "string",
                "description": "额外的上下文信息（文件路径、代码片段等），可选",
                "default": "",
            },
        },
        "required": ["role", "task"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        role = params["role"]
        task = params["task"]
        extra_context = params.get("context", "")

        if not task.strip():
            return ToolResult.fail("任务描述不能为空")

        # 生成唯一 Agent ID
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"

        # 记录 Agent 信息（临时存储）
        agent_info = {
            "id": agent_id,
            "role": role,
            "task": task,
            "context": extra_context,
            "status": "created",
            "work_dir": context.work_dir,
            "result": None,
        }
        _agent_registry[agent_id] = agent_info

        logger.info("子 Agent 已创建: %s (role=%s)", agent_id, role)

        # TODO: 实际集成时，这里应调用 SubAgentOrchestrator.spawn()
        # from ..subagents.orchestrator import SubAgentOrchestrator
        # orchestrator = SubAgentOrchestrator(...)
        # handle = await orchestrator.spawn(role=AgentRole(role), task=task, context=...)

        return ToolResult.ok(
            f"子 Agent 已创建\n"
            f"ID: {agent_id}\n"
            f"角色: {role}\n"
            f"任务: {task[:200]}{'...' if len(task) > 200 else ''}\n"
            f"\n[预留接口] 子 Agent 尚未实际启动，"
            f"后续版本将集成 SubAgentOrchestrator 实现后台执行。",
            agent_id=agent_id,
            role=role,
            status="created",
        )


# ---------------------------------------------------------------------------
# 2. AgentEvalTool
# ---------------------------------------------------------------------------


class AgentEvalTool(AbstractTool):
    """评估/查询子 Agent 状态

    查询指定子 Agent 的执行状态和结果。
    如果子 Agent 已完成，返回其结果摘要。
    """

    name = "agent_eval"
    description = (
        "查询子 Agent 的当前状态和结果。"
        "如果 Agent 已完成任务，返回结果摘要；"
        "如果仍在执行中，返回当前进度。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "子 Agent 的唯一标识符",
            },
        },
        "required": ["agent_id"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        agent_id = params["agent_id"]

        if agent_id not in _agent_registry:
            return ToolResult.fail(f"子 Agent 不存在: {agent_id}")

        agent = _agent_registry[agent_id]

        # TODO: 实际集成时，这里应查询 SubAgentOrchestrator 获取真实状态
        # handle = orchestrator.get_handle(agent_id)
        # status = await handle.get_status()
        # result = await handle.get_result()

        status = agent.get("status", "unknown")
        role = agent.get("role", "unknown")
        task = agent.get("task", "")

        lines = [
            f"# 子 Agent 状态",
            f"ID: {agent_id}",
            f"角色: {role}",
            f"状态: {status}",
            f"任务: {task[:200]}{'...' if len(task) > 200 else ''}",
        ]

        if agent.get("result"):
            lines.extend([
                "",
                "# 执行结果",
                str(agent["result"])[:2000],
            ])

        lines.extend([
            "",
            "[预留接口] 当前返回的是模拟状态，",
            "后续版本将集成 SubAgentOrchestrator 实现真实状态查询。",
        ])

        return ToolResult.ok(
            "\n".join(lines),
            agent_id=agent_id,
            status=status,
            role=role,
        )


# ---------------------------------------------------------------------------
# 3. AgentCloseTool
# ---------------------------------------------------------------------------


class AgentCloseTool(AbstractTool):
    """关闭子 Agent

    终止子 Agent 的执行并释放资源。
    可以选择是否等待 Agent 完成当前任务后再关闭。
    """

    name = "agent_close"
    description = (
        "关闭子 Agent，释放其占用的资源。"
        "如果 Agent 仍在执行中，可以选择强制终止或等待完成。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "要关闭的子 Agent ID",
            },
            "force": {
                "type": "boolean",
                "description": "是否强制终止，默认 false（等待完成后再关闭）",
                "default": False,
            },
        },
        "required": ["agent_id"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        agent_id = params["agent_id"]
        force = params.get("force", False)

        if agent_id not in _agent_registry:
            return ToolResult.fail(f"子 Agent 不存在: {agent_id}")

        agent = _agent_registry[agent_id]

        # TODO: 实际集成时，这里应调用 SubAgentOrchestrator.cancel()
        # orchestrator = SubAgentOrchestrator(...)
        # await orchestrator.cancel(handle, force=force)

        agent["status"] = "closed"

        # 从注册表中移除
        del _agent_registry[agent_id]

        action = "强制终止" if force else "正常关闭"
        logger.info("子 Agent %s 已%s", agent_id, action)

        return ToolResult.ok(
            f"子 Agent 已{action}\n"
            f"ID: {agent_id}\n"
            f"角色: {agent.get('role', 'unknown')}\n"
            f"\n[预留接口] 后续版本将集成 SubAgentOrchestrator 实现真正的终止控制。",
            agent_id=agent_id,
            action=action,
        )
