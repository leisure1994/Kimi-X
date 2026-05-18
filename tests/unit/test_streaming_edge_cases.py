"""
流式解析边界测试

测试 SSE 解析器的边界条件，包括：
- event_data 为字符串而非字典
- 空 choices 数组
- 异常格式数据
- 多行 SSE 缓冲
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from kimix.llm.streaming import SSEEventParser
from kimix.llm.models import ChatEvent, ChatEventType



pytestmark = pytest.mark.unit
class TestSSEEdgeCases:
    """SSE 流式解析边界测试"""

    @pytest.mark.asyncio
    async def test_empty_choices_with_usage(self):
        """测试空 choices 但包含 usage 的事件"""
        data = {
            "choices": [],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            }
        }
        event = SSEEventParser._process_delta(data)
        assert event is not None
        assert event["type"] == ChatEventType.USAGE

    @pytest.mark.asyncio
    async def test_string_data_thinking(self):
        """测试 thinking 事件的 data 为字符串（非 dict）"""
        # 模拟直接传入字符串（实际 streaming.py 中可能产生）
        data = {
            "choices": [{
                "delta": {"reasoning_content": "思考中..."},
                "finish_reason": None,
            }]
        }
        event = SSEEventParser._process_delta(data)
        assert event is not None
        assert event["type"] == ChatEventType.THINKING
        # data 应该是字符串
        assert isinstance(event["data"], str)

    @pytest.mark.asyncio
    async def test_string_data_content(self):
        """测试 content 事件的 data 为字符串"""
        data = {
            "choices": [{
                "delta": {"content": "你好"},
                "finish_reason": None,
            }]
        }
        event = SSEEventParser._process_delta(data)
        assert event is not None
        assert event["type"] == ChatEventType.CONTENT
        assert isinstance(event["data"], str)
        assert event["data"] == "你好"

    @pytest.mark.asyncio
    async def test_missing_delta_fields(self):
        """测试 delta 中没有任何字段"""
        data = {
            "choices": [{
                "delta": {},
                "finish_reason": None,
            }]
        }
        event = SSEEventParser._process_delta(data)
        # 应该返回 None（没有有效数据）
        assert event is None

    @pytest.mark.asyncio
    async def test_error_event(self):
        """测试 API 返回错误"""
        data = {
            "error": {
                "message": "Rate limit exceeded",
                "type": "rate_limit_error",
            }
        }
        event = SSEEventParser._process_delta(data)
        assert event is not None
        assert event["type"] == ChatEventType.ERROR
        assert "Rate limit" in event["data"]

    @pytest.mark.asyncio
    async def test_finish_reason_only(self):
        """测试仅包含 finish_reason 的 chunk"""
        data = {
            "choices": [{
                "delta": {},
                "finish_reason": "stop",
            }]
        }
        event = SSEEventParser._process_delta(data)
        assert event is not None
        assert event["type"] == ChatEventType.DONE

    @pytest.mark.asyncio
    async def test_sse_buffer_split(self):
        """测试 SSE 数据被分割到多个 chunk"""
        # 模拟数据被分割的情况
        chunks = [
            'data: {"choices": [{"delta": {"content": "Hel',
            'lo"}, "finish_reason": null}]}\n\n',
        ]
        
        parser = SSEEventParser()
        events = []
        buffer = ""
        
        for chunk in chunks:
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                event = SSEEventParser._parse_line(line.strip())
                if event is not None:
                    events.append(event)
        
        assert len(events) > 0


class TestChatEventModel:
    """ChatEvent Pydantic 模型测试"""

    def test_create_with_string_data(self):
        """测试创建 thinking 事件，data 为字符串"""
        event = ChatEvent(type=ChatEventType.THINKING, data="思考内容")
        assert event.type == ChatEventType.THINKING
        assert event.data == "思考内容"

    def test_create_with_dict_data(self):
        """测试创建 usage 事件，data 为字典"""
        usage_data = {"prompt_tokens": 100, "completion_tokens": 50}
        event = ChatEvent(type=ChatEventType.USAGE, data=usage_data)
        assert event.type == ChatEventType.USAGE
        assert event.data == usage_data

    def test_dict_like_access(self):
        """测试兼容 dict-like 访问"""
        event = ChatEvent(type=ChatEventType.CONTENT, data="test")
        assert event.get("type") == ChatEventType.CONTENT
        assert event.get("data") == "test"
        assert event.get("nonexistent", "default") == "default"

    def test_bracket_access(self):
        """测试 bracket 访问"""
        event = ChatEvent(type=ChatEventType.DONE, data={"finish_reason": "stop"})
        assert event["type"] == ChatEventType.DONE
        assert event["data"]["finish_reason"] == "stop"

    def test_invalid_thinking_data_type(self):
        """测试 thinking 事件的 data 类型验证"""
        with pytest.raises(ValueError):
            ChatEvent(type=ChatEventType.THINKING, data=123)

    def test_invalid_content_data_type(self):
        """测试 content 事件的 data 类型验证"""
        with pytest.raises(ValueError):
            ChatEvent(type=ChatEventType.CONTENT, data=["list"])
