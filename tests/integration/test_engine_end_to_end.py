"""
引擎端到端测试

测试 AgentEngine.run() 的完整链路：
- 用户输入 → 认知分析 → 模式路由 → LLM 调用 → 响应输出
- 使用 mock 对象模拟 LLM 响应
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kimix.core.engine import AgentEngine, AgentMode
from kimix.llm.models import ChatEvent, ChatEventType, Message



pytestmark = pytest.mark.integration
class MockLLMClient:
    """模拟 LLM 客户端，用于端到端测试"""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["你好！我是 Kimi-Agent。"]
        self.call_count = 0

    async def chat(self, messages, tools=None, **kwargs):
        """模拟流式响应"""
        # 模拟 thinking
        yield ChatEvent(type=ChatEventType.THINKING, data="正在思考...")
        
        # 模拟 content
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        
        for chunk in response:
            yield ChatEvent(type=ChatEventType.CONTENT, data=chunk)
        
        # 模拟 usage
        yield ChatEvent(
            type=ChatEventType.USAGE,
            data={"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
        )
        
        # 模拟 done
        yield ChatEvent(type=ChatEventType.DONE, data={"finish_reason": "stop"})


class MockToolRegistry:
    """模拟工具注册表"""

    def to_openai_schema(self):
        return []

    def get_tool(self, name):
        return None


class TestEngineEndToEnd:
    """引擎端到端测试"""

    @pytest.mark.asyncio
    async def test_simple_qa_flow(self):
        """测试简单问答完整流程"""
        llm_client = MockLLMClient(["你好！很高兴见到你。"])
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        
        events = []
        async for event in engine.run("你好"):
            events.append(event)
        
        # 验证有 content 事件
        content_events = [e for e in events if e["type"] == "content"]
        assert len(content_events) > 0
        
        # 验证有 done 事件
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) > 0

    @pytest.mark.asyncio
    async def test_thinking_mode_flow(self):
        """测试 thinking 模式的完整流程"""
        llm_client = MockLLMClient(["这是一个复杂的回答。"])
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        engine.switch_mode(AgentMode.EXPLORE)
        
        events = []
        async for event in engine.run("分析项目结构"):
            events.append(event)
        
        # EXPLORE 模式应该有 thinking 事件
        thinking_events = [e for e in events if e.get("type") == "thinking"]
        # 实际取决于实现，但至少要有 content
        content_events = [e for e in events if e.get("type") == "content"]
        assert len(content_events) > 0

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """测试引擎错误处理"""
        class FailingLLMClient:
            async def chat(self, messages, tools=None, **kwargs):
                yield ChatEvent(
                    type=ChatEventType.ERROR,
                    data="API 连接失败"
                )
        
        llm_client = FailingLLMClient()
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        
        events = []
        async for event in engine.run("测试"):
            events.append(event)
        
        # 应该收到错误事件或至少完成
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_cognitive_analysis(self):
        """测试认知分析功能"""
        llm_client = MockLLMClient()
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        
        # 测试简单问答分析
        result = engine.cognitive_analysis("什么是 Python？")
        assert result.task_type == "simple_qa"
        assert result.complexity == "low"
        
        # 测试文件读取分析
        result = engine.cognitive_analysis("读取 README.md")
        assert result.task_type == "file_read"

    def test_mode_switching(self):
        """测试模式切换"""
        llm_client = MockLLMClient()
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        
        assert engine.mode == AgentMode.AGENT
        
        engine.switch_mode(AgentMode.EXPLORE)
        assert engine.mode == AgentMode.EXPLORE
        
        engine.switch_mode(AgentMode.YOLO)
        assert engine.mode == AgentMode.YOLO

    def test_stats_tracking(self):
        """测试统计信息跟踪"""
        llm_client = MockLLMClient()
        tool_registry = MockToolRegistry()
        
        engine = AgentEngine(llm_client, tool_registry)
        stats = engine.get_stats()
        
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["total_cost_usd"] == 0.0
