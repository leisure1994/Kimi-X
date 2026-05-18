"""
LLM 客户端包 - Kimi API 客户端层。

提供与 Kimi k2.6 模型交互的完整客户端功能，包括：
- KimiClient: 核心异步 API 客户端
- CostTracker: Token 使用成本追踪
- Streaming: SSE 流式响应处理
- Models: 数据模型定义

典型用法:
    from kimix.llm import KimiClient, CostTracker

    client = KimiClient(api_key="your-api-key")
    async for event in client.chat([Message.user("你好")]):
        print(event)
"""

from __future__ import annotations

# 核心客户端
from .client import KimiClient

# 成本追踪
from .cost_tracker import CostTracker, Pricing, UsageRecord

# 数据模型
from .models import (
    APIError,
    AuthenticationError,
    ChatCompletionConfig,
    ChatEvent,
    ChatEventType,
    ChatResponse,
    FinishReason,
    LLMError,
    Message,
    MessageRole,
    NetworkError,
    RateLimitError,
    ThinkingConfig,
    TimeoutError,
    TokenLimitError,
    ToolCall,
    ToolCallFunction,
    ToolResult,
    Usage,
)

# 流式处理
from .streaming import (
    SSEEventParser,
    StreamingDispatcher,
    StreamingEventAggregator,
    ThinkingContentExtractor,
    create_sse_event_stream,
)

__all__ = [
    # 核心客户端
    "KimiClient",

    # 成本追踪
    "CostTracker",
    "UsageRecord",

    # 数据模型 - 核心
    "Message",
    "MessageRole",
    "ToolCall",
    "ToolCallFunction",
    "ToolResult",
    "Usage",
    "ChatEvent",
    "ChatEventType",
    "ChatResponse",

    # 数据模型 - 配置
    "ChatCompletionConfig",
    "ThinkingConfig",
    "FinishReason",

    # 数据模型 - 异常
    "LLMError",
    "APIError",
    "AuthenticationError",
    "RateLimitError",
    "TokenLimitError",
    "NetworkError",
    "TimeoutError",

    # 数据模型 - 定价
    "Pricing",

    # 流式处理
    "SSEEventParser",
    "StreamingEventAggregator",
    "StreamingDispatcher",
    "ThinkingContentExtractor",
    "create_sse_event_stream",
]
