"""
工作模式单元测试

测试各工作模式（Explore、Plan、Agent、Auto、YOLO）的
工具审批逻辑和基本功能。
"""

from __future__ import annotations

from typing import Any

import pytest

from kimix.modes.agent import AgentMode as AgentModeClass
from kimix.modes.auto import AutoMode
from kimix.modes.base import ApprovalLevel, BaseMode
from kimix.modes.explore import ExploreMode
from kimix.modes.plan import PlanMode
from kimix.modes.yolo import YoloMode



pytestmark = pytest.mark.unit
class TestBaseMode:
    """BaseMode 基类测试"""

    def test_base_mode_not_instantiable(self) -> None:
        """测试基类不能直接实例化"""
        with pytest.raises(TypeError):
            BaseMode()


class TestExploreMode:
    """ExploreMode 探索模式测试"""

    def test_mode_info(self) -> None:
        """测试模式信息"""
        mode = ExploreMode()
        info = mode.get_mode_info()
        assert info["name"] == "explore"
        assert info["supports_thinking"] is True

    def test_readonly_tool_no_approval(self) -> None:
        """测试只读工具无需审批"""
        mode = ExploreMode()
        assert mode.should_approve("file_read") is False

    def test_write_tool_requires_approval(self) -> None:
        """测试写入工具需要审批"""
        mode = ExploreMode()
        assert mode.should_approve("file_write") is True

    def test_is_readonly_tool(self) -> None:
        """测试只读工具判断"""
        mode = ExploreMode()
        assert mode.is_readonly_tool("file_read") is True
        assert mode.is_readonly_tool("file_write") is False

    def test_repr(self) -> None:
        """测试字符串表示"""
        mode = ExploreMode()
        assert "ExploreMode" in repr(mode)


class TestPlanMode:
    """PlanMode 规划模式测试"""

    def test_mode_info(self) -> None:
        """测试模式信息"""
        mode = PlanMode()
        info = mode.get_mode_info()
        assert info["name"] == "plan"
        assert info["supports_thinking"] is True

    def test_readonly_tool_no_approval(self) -> None:
        """测试只读工具无需审批"""
        mode = PlanMode()
        assert mode.should_approve("file_read") is False

    def test_plan_template_exists(self) -> None:
        """测试计划模板存在"""
        mode = PlanMode()
        assert "计划" in mode.PLAN_TEMPLATE or "执行计划" in mode.PLAN_TEMPLATE


class TestAgentMode:
    """AgentMode 代理模式测试"""

    def test_mode_info(self) -> None:
        """测试模式信息"""
        mode = AgentModeClass()
        info = mode.get_mode_info()
        assert info["name"] == "agent"

    def test_readonly_tool_no_approval(self) -> None:
        """测试只读工具无需审批"""
        mode = AgentModeClass()
        assert mode.should_approve("file_read") is False

    def test_destructive_tool_requires_approval(self) -> None:
        """测试破坏性工具需要审批"""
        mode = AgentModeClass()
        assert mode.should_approve("file_delete") is True

    def test_auto_approve_safe_tools(self) -> None:
        """测试安全工具自动通过"""
        mode = AgentModeClass()
        assert mode._is_auto_approved("file_read") is True
        assert mode._is_auto_approved("git_status") is True

    def test_is_readonly_tool(self) -> None:
        """测试只读工具判断"""
        mode = AgentModeClass()
        assert mode.is_readonly_tool("file_read") is True
        assert mode.is_readonly_tool("shell") is False


class TestAutoMode:
    """AutoMode 自动模式测试"""

    def test_mode_info(self) -> None:
        """测试模式信息"""
        mode = AutoMode()
        info = mode.get_mode_info()
        assert info["name"] == "auto"

    def test_risk_score_safe_tool(self) -> None:
        """测试安全工具的风险评分"""
        mode = AutoMode()
        score = mode._calculate_risk_score("file_read")
        assert score < mode.APPROVAL_THRESHOLD_LOW

    def test_risk_score_write_tool(self) -> None:
        """测试写入工具的风险评分"""
        mode = AutoMode()
        score = mode._calculate_risk_score("file_write")
        assert score >= mode.APPROVAL_THRESHOLD_LOW
        assert score < mode.APPROVAL_THRESHOLD_HIGH

    def test_should_approve_safe(self) -> None:
        """测试安全工具无需审批"""
        mode = AutoMode()
        assert mode.should_approve("file_read") is False


class TestYoloMode:
    """YoloMode YOLO 模式测试"""

    def test_mode_info(self) -> None:
        """测试模式信息"""
        mode = YoloMode()
        info = mode.get_mode_info()
        assert info["name"] == "yolo"
        assert info["supports_thinking"] is False

    def test_should_approve_always_false(self) -> None:
        """测试 YOLO 模式下所有工具不审批"""
        mode = YoloMode()
        assert mode.should_approve("file_read") is False
        assert mode.should_approve("file_delete") is False
        assert mode.should_approve("shell") is False

    def test_is_extremely_dangerous(self) -> None:
        """测试极度危险命令检测"""
        mode = YoloMode()
        assert mode._is_extremely_dangerous("shell", '{"command": "rm -rf /"}') is True
        assert mode._is_extremely_dangerous("shell", '{"command": "ls"}') is False

    def test_blocked_commands_list(self) -> None:
        """测试阻断命令列表不为空"""
        mode = YoloMode()
        assert len(mode.BLOCKED_COMMANDS) > 0
