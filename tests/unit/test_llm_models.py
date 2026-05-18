"""
LLM 数据模型单元测试

测试 Message、ToolCall、Usage、ChatEvent 等核心数据模型的创建和序列化。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# 绕过 kimix.llm.__init__ 直接导入 models（避免加载 tiktoken）
_models_spec = importlib.util.spec_from_file_location(
    "kimix_llm_models", Path(__file__).parent.parent.parent / "kimix" / "llm" / "models.py"
)
_models_module = importlib.util.module_from_spec(_models_spec)
sys.modules["kimix_llm_models"] = _models_module
_models_spec.loader.exec_module(_models_module)

from kimix_llm_models import (
    APIError,
    AuthenticationError,
    ChatEvent,
    ChatEventType,
    FinishReason,
    Message,
    MessageRole,
    NetworkError,
    RateLimitError,
    ThinkingConfig,
    TimeoutError,
    TokenLimitError,
    ToolCall,
    ToolCallFunction,
    Usage,
)



pytestmark = pytest.mark.unit
class TestMessage:
    """Message 模型测试"""

    def test_message_creation(self) -> None:
        """测试创建消息"""
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.name is None

    def test_message_system(self) -> None:
        """测试系统消息"""
        msg = Message.system("You are a helpful assistant")
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are a helpful assistant"

    def test_message_user(self) -> None:
        """测试用户消息"""
        msg = Message.user("What is Python?")
        assert msg.role == MessageRole.USER
        assert msg.content == "What is Python?"

    def test_message_assistant(self) -> None:
        """测试助手消息"""
        msg = Message.assistant("Python is a programming language")
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Python is a programming language"

    def test_message_tool(self) -> None:
        """测试工具消息"""
        msg = Message(role=MessageRole.TOOL, content="result", tool_call_id="tc_1")
        assert msg.role == MessageRole.TOOL
        assert msg.tool_call_id == "tc_1"

    def test_message_to_dict(self) -> None:
        """测试消息序列化为字典"""
        msg = Message.user("Hello")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"

    def test_message_with_tool_calls(self) -> None:
        """测试带工具调用的消息"""
        tool_call = ToolCall(id="tc_1", function=ToolCallFunction(name="test", arguments="{}"))
        msg = Message.assistant("Using tool", tool_calls=[tool_call])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "tc_1"


class TestToolCall:
    """ToolCall 模型测试"""

    def test_tool_call_creation(self) -> None:
        """测试创建工具调用"""
        func = ToolCallFunction(name="file_read", arguments='{"path": "/tmp/test"}')
        tc = ToolCall(id="tc_001", function=func)
        assert tc.id == "tc_001"
        assert tc.function.name == "file_read"

    def test_tool_call_serialization(self) -> None:
        """测试工具调用序列化"""
        func = ToolCallFunction(name="test", arguments="{}")
        tc = ToolCall(id="tc_1", function=func)
        d = tc.to_dict()
        assert d["id"] == "tc_1"
        assert d["function"]["name"] == "test"


class TestUsage:
    """Usage 模型测试"""

    def test_usage_creation(self) -> None:
        """测试创建 Usage"""
        usage = Usage(prompt_tokens=100, completion_tokens=50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_usage_zero(self) -> None:
        """测试零 token 使用"""
        usage = Usage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0


class TestChatEvent:
    """ChatEvent 模型测试"""

    def test_chat_event_creation(self) -> None:
        """测试创建聊天事件"""
        event = ChatEvent(
            type=ChatEventType.CONTENT,
            content="Hello",
        )
        assert event["type"] == ChatEventType.CONTENT
        assert event["content"] == "Hello"

    def test_chat_event_tool_call(self) -> None:
        """测试工具调用事件"""
        event = ChatEvent(
            type=ChatEventType.TOOL_CALL,
            tool_calls=[{"id": "tc_1", "function": {"name": "test"}}],
        )
        assert event["type"] == ChatEventType.TOOL_CALL
        assert len(event["tool_calls"]) == 1


class TestExceptions:
    """异常类测试"""

    def test_api_error(self) -> None:
        """测试 API 错误"""
        err = APIError("API request failed", status_code=500)
        assert str(err) == "API request failed"
        assert err.status_code == 500

    def test_authentication_error(self) -> None:
        """测试认证错误"""
        err = AuthenticationError("Invalid API key")
        assert str(err) == "Invalid API key"

    def test_rate_limit_error(self) -> None:
        """测试限流错误"""
        err = RateLimitError("Rate limit exceeded", retry_after=30)
        assert err.retry_after == 30

    def test_network_error(self) -> None:
        """测试网络错误"""
        err = NetworkError("Connection timeout")
        assert str(err) == "Connection timeout"

    def test_timeout_error(self) -> None:
        """测试超时错误"""
        err = TimeoutError("Request timed out after 30s")
        assert "timed out" in str(err)

    def test_token_limit_error(self) -> None:
        """测试 Token 限制错误"""
        err = TokenLimitError("Token limit exceeded", max_tokens=256000)
        assert err.max_tokens == 256000


class TestThinkingConfig:
    """ThinkingConfig 测试"""

    def test_default_thinking(self) -> None:
        """测试默认思考配置"""
        cfg = ThinkingConfig()
        assert cfg.type == "disabled"

    def test_enabled_thinking(self) -> None:
        """测试启用思考"""
        cfg = ThinkingConfig(type="enabled")
        assert cfg.type == "enabled"
