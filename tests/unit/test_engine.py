"""
核心引擎单元测试

测试 AgentEngine 的初始化、模式切换、认知分析、
统计信息获取等功能。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kimix.core.engine import AgentEngine, AgentMode



pytestmark = pytest.mark.unit
class TestAgentEngineInit:
    """AgentEngine 初始化测试"""

    def test_engine_init_default(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试默认初始化"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        assert engine.mode == AgentMode.AGENT
        assert engine.llm_client is mock_llm_client
        assert engine.tool_registry is mock_tool_registry

    def test_engine_init_with_mode(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试指定模式初始化"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry, mode=AgentMode.EXPLORE)
        assert engine.mode == AgentMode.EXPLORE

    def test_engine_init_with_memory(self, mock_llm_client: Any, mock_tool_registry: Any, mock_memory_manager: Any) -> None:
        """测试带记忆管理器初始化"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry, memory=mock_memory_manager)
        assert engine.memory is mock_memory_manager

    def test_engine_init_stats_zero(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试初始统计为零"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        stats = engine.get_stats()
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["total_cost_usd"] == 0.0


class TestAgentEngineMode:
    """AgentEngine 模式切换测试"""

    def test_switch_mode_valid(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试切换到有效模式"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        engine.switch_mode(AgentMode.EXPLORE)
        assert engine.mode == AgentMode.EXPLORE

    def test_switch_mode_all_modes(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试切换到所有可用模式"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        for mode in AgentMode:
            engine.switch_mode(mode)
            assert engine.mode == mode


class TestAgentEngineCognitiveAnalysis:
    """AgentEngine 认知分析测试"""

    def test_analysis_simple_qa(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试简单问答分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("什么是Python？")
        assert result.task_type == "simple_qa"
        assert result.complexity == "low"

    def test_analysis_file_read(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试文件读取分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("读取 README.md")
        assert result.task_type == "file_read"

    def test_analysis_file_write(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试文件写入分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("创建 main.py")
        assert result.task_type == "file_write"

    def test_analysis_shell_command(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试 Shell 命令分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("运行 ls -la")
        assert result.task_type == "shell_exec"

    def test_analysis_dangerous_command(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试危险命令分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("rm -rf /")
        assert result.risk_level == "critical"

    def test_analysis_code_refactor(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试代码重构分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("重构这个项目")
        assert result.complexity == "high"

    def test_analysis_git_operation(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试 Git 操作分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("git commit -m test")
        assert result.task_type == "git_operation"

    def test_analysis_architecture(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试架构设计分析"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = engine.cognitive_analysis("设计微服务架构")
        assert result.task_type == "architecture_design"


class TestAgentEngineShutdown:
    """AgentEngine 关闭测试"""

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试关闭引擎"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        await engine.shutdown()
        stats = engine.get_stats()
        assert stats["is_running"] is False


class TestAgentEngineExecuteTools:
    """AgentEngine 工具执行测试"""

    @pytest.mark.asyncio
    async def test_execute_tools_empty(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试执行空工具列表"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        result = await engine.execute_tools([])
        assert result == []
