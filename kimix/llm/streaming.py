"""
SSE 流式响应处理器模块。

提供 Kimi API SSE (Server-Sent Events) 流式响应的解析、事件分发、
thinking content 与 response content 分离功能。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from .models import (
    ChatEvent,
    ChatEventType,
    FinishReason,
    Message,
    ToolCall,
    ToolCallFunction,
    ToolResult,
    Usage,
)

logger = logging.getLogger(__name__)

# SSE 事件前缀常量
SSE_DATA_PREFIX = "data: "
SSE_DONE_MARKER = "[DONE]"


class SSEEventParser:
    """
    SSE 事件解析器。

    负责将 SSE 原始字节流解析为结构化的事件对象。
    处理 data:、event:、id:、retry: 等 SSE 字段。
    """

    @staticmethod
    async def parse_stream(
        response_stream: AsyncIterator[str],
    ) -> AsyncIterator[ChatEvent]:
        """
        解析 SSE 流并生成结构化事件。

        Args:
            response_stream: SSE 原始文本异步迭代器

        Yields:
            ChatEvent: 结构化聊天事件
        """
        buffer = ""
        async for chunk in response_stream:
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                event = SSEEventParser._parse_line(line.strip())
                if event is not None:
                    yield event

    @staticmethod
    def _parse_line(line: str) -> ChatEvent | None:
        """
        解析单行 SSE 数据。

        Args:
            line: SSE 单行文本

        Returns:
            解析成功返回 ChatEvent，无需处理返回 None
        """
        # 空行或注释行
        if not line or line.startswith(":"):
            return None

        # 只处理 data: 前缀的行
        if not line.startswith(SSE_DATA_PREFIX):
            return None

        data_str = line[len(SSE_DATA_PREFIX):]

        # [DONE] 标记
        if data_str == SSE_DONE_MARKER:
            return ChatEvent(type=ChatEventType.DONE, data={})

        # 解析 JSON 数据
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            logger.warning(f"SSE JSON 解析失败: {e}, 原始数据: {data_str[:200]}")
            return ChatEvent(
                type=ChatEventType.ERROR,
                data=f"JSON 解析错误: {e}",
            )

        return SSEEventParser._process_delta(data)

    @staticmethod
    def _process_delta(data: dict[str, Any]) -> ChatEvent | None:
        """
        处理 OpenAI 兼容格式的 delta 消息。

        Args:
            data: SSE 事件中的 JSON 数据

        Returns:
            结构化 ChatEvent 或 None
        """
        # 检查是否有错误
        if "error" in data:
            error_info = data["error"]
            error_msg = error_info.get("message", str(error_info))
            return ChatEvent(type=ChatEventType.ERROR, data=error_msg)

        choices = data.get("choices", [])
        if not choices:
            # 可能是 usage 事件（在 choices 为空时）
            usage_data = data.get("usage")
            if usage_data:
                return SSEEventParser._extract_usage_event(usage_data)
            return None

        choice = choices[0]
        delta = choice.get("delta", {})

        # 检查 finish_reason
        finish_reason = choice.get("finish_reason")
        if finish_reason:
            return ChatEvent(
                type=ChatEventType.DONE,
                data={"finish_reason": finish_reason},
            )

        # 处理 reasoning_content（thinking 内容）
        reasoning_content = delta.get("reasoning_content")
        if reasoning_content:
            return ChatEvent(
                type=ChatEventType.THINKING,
                data=reasoning_content,
            )

        # 处理普通 content
        content = delta.get("content")
        if content:
            return ChatEvent(
                type=ChatEventType.CONTENT,
                data=content,
            )

        # 处理 tool_calls
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            return SSEEventParser._process_tool_calls(tool_calls)

        # 检查 usage（某些 API 在最后一个 chunk 中返回 usage）
        usage_data = data.get("usage")
        if usage_data:
            return SSEEventParser._extract_usage_event(usage_data)

        return None

    @staticmethod
    def _extract_usage_event(usage_data: dict[str, Any]) -> ChatEvent:
        """
        从 usage 数据中提取 Usage 事件。

        Args:
            usage_data: 原始 usage 字典

        Returns:
            USAGE 类型 ChatEvent
        """
        try:
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                cached_tokens=usage_data.get("prompt_tokens_details", {}).get("cached_tokens")
                if isinstance(usage_data.get("prompt_tokens_details"), dict)
                else None,
            )
            return ChatEvent(type=ChatEventType.USAGE, data=usage)
        except Exception as e:
            logger.warning(f"Usage 解析失败: {e}")
            return ChatEvent(
                type=ChatEventType.USAGE,
                data=Usage(),
            )

    @staticmethod
    def _process_tool_calls(tool_calls: list[dict[str, Any]]) -> ChatEvent | None:
        """
        处理工具调用 delta。

        Args:
            tool_calls: 工具调用列表

        Returns:
            TOOL_CALL 类型 ChatEvent 或 None
        """
        if not tool_calls:
            return None

        # 处理首个 tool_call
        tc = tool_calls[0]
        try:
            function_data = tc.get("function", {})
            tool_call = ToolCall(
                id=tc.get("id", ""),
                type="function",
                function=ToolCallFunction(
                    name=function_data.get("name", ""),
                    arguments=function_data.get("arguments", ""),
                ),
            )
            return ChatEvent(type=ChatEventType.TOOL_CALL, data=tool_call)
        except Exception as e:
            logger.warning(f"Tool call 解析失败: {e}")
            return ChatEvent(
                type=ChatEventType.ERROR,
                data=f"工具调用解析错误: {e}",
            )


class StreamingEventAggregator:
    """
    流式事件聚合器。

    将 SSE 流式事件聚合为完整的响应，分离 thinking 和 content，
    收集 tool_calls 和 usage 信息。
    """

    def __init__(self) -> None:
        """初始化聚合器状态"""
        self.thinking_parts: list[str] = []
        self.content_parts: list[str] = []
        self.tool_calls: list[ToolCall] = []
        self.usage: Usage | None = None
        self.finish_reason: FinishReason | None = None
        self._pending_tool_calls: dict[str, dict[str, Any]] = {}

    def consume(self, event: ChatEvent) -> None:
        """
        消费一个流式事件，更新聚合状态。

        Args:
            event: 流式聊天事件
        """
        event_type = event.get("type")
        data = event.get("data")

        if event_type == ChatEventType.THINKING:
            if isinstance(data, str):
                self.thinking_parts.append(data)

        elif event_type == ChatEventType.CONTENT:
            if isinstance(data, str):
                self.content_parts.append(data)

        elif event_type == ChatEventType.TOOL_CALL:
            if isinstance(data, ToolCall):
                self._merge_tool_call(data)

        elif event_type == ChatEventType.USAGE:
            if isinstance(data, Usage):
                self.usage = data

        elif event_type == ChatEventType.DONE:
            if isinstance(data, dict) and "finish_reason" in data:
                reason = data["finish_reason"]
                try:
                    self.finish_reason = FinishReason(reason)
                except ValueError:
                    self.finish_reason = FinishReason.NULL

        elif event_type == ChatEventType.ERROR:
            logger.error(f"流式事件错误: {data}")

    def _merge_tool_call(self, tc: ToolCall) -> None:
        """
        合并工具调用 delta。

        SSE 流中 tool_call 可能被分割为多个片段，
        需要按 id 合并。

        Args:
            tc: 工具调用片段
        """
        tc_id = tc.id

        if tc_id and tc_id not in self._pending_tool_calls:
            # 新的 tool_call
            self._pending_tool_calls[tc_id] = {
                "id": tc_id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            self.tool_calls.append(tc)
        elif tc_id and tc_id in self._pending_tool_calls:
            # 追加到已有的 tool_call
            pending = self._pending_tool_calls[tc_id]
            # 追加 name（可能分段）
            if tc.function.name:
                pending["name"] += tc.function.name
            # 追加 arguments（可能分段）
            if tc.function.arguments:
                pending["arguments"] += tc.function.arguments
            # 更新已有的 ToolCall 对象
            for existing_tc in self.tool_calls:
                if existing_tc.id == tc_id:
                    existing_tc.function.name = pending["name"]
                    existing_tc.function.arguments = pending["arguments"]
                    break

    @property
    def thinking(self) -> str:
        """获取完整的 thinking 内容"""
        return "".join(self.thinking_parts)

    @property
    def content(self) -> str:
        """获取完整的 response 内容"""
        return "".join(self.content_parts)

    def is_tool_call(self) -> bool:
        """判断响应是否为工具调用"""
        return len(self.tool_calls) > 0

    def get_result(self) -> dict[str, Any]:
        """
        获取聚合后的完整结果。

        Returns:
            包含 thinking, content, tool_calls, usage, finish_reason 的字典
        """
        return {
            "thinking": self.thinking,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
        }


class StreamingDispatcher:
    """
    流式事件分发器。

    将解析后的 SSE 事件分发到多个通道，支持：
    - 实时事件流（供 UI 展示）
    - Thinking 内容收集
    - Content 内容收集
    - Tool call 收集
    """

    def __init__(self) -> None:
        """初始化分发器"""
        self.aggregator = StreamingEventAggregator()
        self._event_handlers: list[Any] = []

    def register_handler(self, handler: Any) -> None:
        """
        注册事件处理器。

        Args:
            handler: 事件处理函数或回调对象
        """
        self._event_handlers.append(handler)

    async def dispatch(
        self,
        event_stream: AsyncIterator[ChatEvent],
    ) -> AsyncIterator[ChatEvent]:
        """
        分发流式事件到所有处理器，同时产生事件流。

        Args:
            event_stream: 输入事件流

        Yields:
            每个输入事件（透传）
        """
        async for event in event_stream:
            # 聚合事件
            self.aggregator.consume(event)

            # 通知所有处理器
            for handler in self._event_handlers:
                try:
                    if hasattr(handler, "on_event"):
                        handler.on_event(event)
                    elif callable(handler):
                        handler(event)
                except Exception as e:
                    logger.warning(f"事件处理器错误: {e}")

            yield event

    def get_aggregator(self) -> StreamingEventAggregator:
        """获取当前聚合器状态（用于获取最终结果）"""
        return self.aggregator


class ThinkingContentExtractor:
    """
    Thinking 内容提取器。

    专门用于从流式事件中提取和分离 thinking 内容。
    Kimi k2.6 在 thinking 模式下会输出 reasoning_content 字段。
    """

    @staticmethod
    async def extract_thinking_and_content(
        event_stream: AsyncIterator[ChatEvent],
    ) -> AsyncIterator[ChatEvent]:
        """
        从事件流中提取并标记 thinking 和 content。

        这是一个透传处理器，保持事件流不变，
        主要用于文档说明 thinking/content 分离机制。

        Args:
            event_stream: 输入事件流

        Yields:
            标记后的 ChatEvent
        """
        async for event in event_stream:
            # 透传，不做修改
            # thinking 和 content 已在解析阶段分离
            yield event


def create_sse_event_stream(
    raw_stream: AsyncIterator[str],
) -> AsyncIterator[ChatEvent]:
    """
    创建 SSE 事件流的便捷函数。

    将原始 SSE 字节流转换为结构化 ChatEvent 流。

    Args:
        raw_stream: 原始 SSE 文本流

    Returns:
        结构化 ChatEvent 异步迭代器
    """
    return SSEEventParser.parse_stream(raw_stream)
