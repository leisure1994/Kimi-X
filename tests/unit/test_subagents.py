"""
子 Agent 系统单元测试

测试子 Agent 的数据模型，包括 AgentRole、TaskPriority、
SubAgentTask、SubAgentHandle 和 SubAgentResult。
"""

from __future__ import annotations

import pytest

from kimix.subagents.models import (
    AgentRole,
    SubAgentHandle,
    SubAgentResult,
    SubAgentTask,
    TaskPriority,
)



pytestmark = pytest.mark.unit
class TestAgentRole:
    """AgentRole 角色枚举测试"""

    def test_role_values(self) -> None:
        """测试角色值"""
        assert AgentRole.EXPLORER == "explorer"
        assert AgentRole.PLANNER == "planner"
        assert AgentRole.CODER == "coder"
        assert AgentRole.REVIEWER == "reviewer"
        assert AgentRole.TESTER == "tester"
        assert AgentRole.DEBUGGER == "debugger"
        assert AgentRole.RESEARCHER == "researcher"
        assert AgentRole.DOCUMENTER == "documenter"

    def test_role_count(self) -> None:
        """测试角色数量"""
        assert len(AgentRole) == 8


class TestTaskPriority:
    """TaskPriority 优先级枚举测试"""

    def test_priority_values(self) -> None:
        """测试优先级值"""
        assert TaskPriority.LOW == 1
        assert TaskPriority.NORMAL == 2
        assert TaskPriority.HIGH == 3
        assert TaskPriority.URGENT == 4

    def test_priority_order(self) -> None:
        """测试优先级排序"""
        assert TaskPriority.LOW < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.URGENT


class TestSubAgentTask:
    """SubAgentTask 任务模型测试"""

    def test_create_task(self) -> None:
        """测试创建任务"""
        task = SubAgentTask(
            role=AgentRole.CODER,
            task_description="编写一个排序函数",
        )
        assert task.role == AgentRole.CODER
        assert task.task_description == "编写一个排序函数"
        assert task.priority == TaskPriority.NORMAL

    def test_create_task_with_priority(self) -> None:
        """测试创建带优先级的任务"""
        task = SubAgentTask(
            role=AgentRole.DEBUGGER,
            task_description="修复 bug",
            priority=TaskPriority.HIGH,
        )
        assert task.priority == TaskPriority.HIGH

    def test_create_task_with_context(self) -> None:
        """测试创建带上下文的任务"""
        task = SubAgentTask(
            role=AgentRole.RESEARCHER,
            task_description="调研新技术",
            context={"topic": "AI"},
        )
        assert task.context["topic"] == "AI"


class TestSubAgentHandle:
    """SubAgentHandle 句柄模型测试"""

    def test_create_handle(self) -> None:
        """测试创建工作进程句柄"""
        handle = SubAgentHandle(task_id="task-001", worker_id="worker-001")
        assert handle.task_id == "task-001"
        assert handle.worker_id == "worker-001"
        assert handle.status == "pending"

    def test_handle_status_running(self) -> None:
        """测试运行中状态"""
        handle = SubAgentHandle(task_id="t1", worker_id="w1", status="running")
        assert handle.status == "running"


class TestSubAgentResult:
    """SubAgentResult 结果模型测试"""

    def test_create_result(self) -> None:
        """测试创建结果"""
        result = SubAgentResult(task_id="task-001", status="completed")
        assert result.task_id == "task-001"
        assert result.status == "completed"

    def test_result_default_usage(self) -> None:
        """测试默认使用统计"""
        result = SubAgentResult(task_id="t1")
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_result_with_evidence(self) -> None:
        """测试带证据的结果"""
        result = SubAgentResult(task_id="t1", status="completed")
        result.evidence.append({"file": "test.py"})
        assert len(result.evidence) == 1

    def test_result_with_execution_log(self) -> None:
        """测试带执行日志的结果"""
        result = SubAgentResult(task_id="t1", status="completed")
        result.execution_log.append("开始执行")
        assert len(result.execution_log) == 1
