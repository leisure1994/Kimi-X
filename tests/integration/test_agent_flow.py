"""
Agent 集成测试

测试完整的 Agent 流程，包括引擎初始化、模式切换、
LLM 调用、工具执行和事件流生成。
所有 LLM 调用均使用 Mock，不依赖外部 API。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kimix.core.engine import AgentEngine, AgentMode
from kimix.core.turn import Turn



pytestmark = pytest.mark.integration
class TestAgentEngineFlow:
    """Agent 引擎完整流程测试"""

    @pytest.mark.asyncio
    async def test_engine_run_simple_query(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试引擎处理简单查询"""
        mock_llm_client.responses = [
            {"type": "content", "data": {"text": "Hello!"}},
            {"type": "usage", "data": {"input_tokens": 10, "output_tokens": 5}},
        ]
        engine = AgentEngine(mock_llm_client, mock_tool_registry, mode=AgentMode.AGENT)
        await engine.initialize(project_path=".")
        events = []
        async for event in engine.run("Hello"):
            events.append(event)
        assert len(events) > 0
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_engine_mode_switch(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试引擎模式切换"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry, mode=AgentMode.EXPLORE)
        assert engine.mode == AgentMode.EXPLORE
        engine.switch_mode(AgentMode.AGENT)
        assert engine.mode == AgentMode.AGENT
        engine.switch_mode(AgentMode.YOLO)
        assert engine.mode == AgentMode.YOLO

    @pytest.mark.asyncio
    async def test_engine_run_not_initialized(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试未初始化的引擎返回错误"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        events = []
        async for event in engine.run("test"):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "error"

    @pytest.mark.asyncio
    async def test_engine_shutdown(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试关闭引擎"""
        engine = AgentEngine(mock_llm_client, mock_tool_registry)
        await engine.shutdown()
        stats = engine.get_stats()
        assert stats["is_running"] is False

    @pytest.mark.asyncio
    async def test_explore_mode_blocks_write(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试探索模式阻止写入操作"""
        from kimix.modes.explore import ExploreMode
        mode = ExploreMode()
        assert mode.should_approve("file_write") is True  # True = 需要审批
        assert mode.should_approve("file_read") is False  # False = 无需审批

    @pytest.mark.asyncio
    async def test_yolo_mode_auto_approve(self, mock_llm_client: Any, mock_tool_registry: Any) -> None:
        """测试 YOLO 模式自动通过"""
        from kimix.modes.yolo import YoloMode
        mode = YoloMode()
        assert mode.should_approve("file_delete") is False
        assert mode.should_approve("shell") is False
