"""
Kimi API 客户端模块。

提供与 Kimi API（OpenAI 兼容）交互的异步客户端。
支持 SSE 流式响应、工具调用、thinking 模式控制、完善的错误处理和重试机制。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, TypeVar

import openai
import tiktoken

from .cost_tracker import CostTracker
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
from .streaming import SSEEventParser, StreamingEventAggregator

logger = logging.getLogger(__name__)

T = TypeVar("T")


# 重试配置
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # 秒
RETRY_MAX_DELAY = 60.0  # 秒
RETRY_MULTIPLIER = 2.0  # 指数退避乘数

# 超时配置
DEFAULT_TIMEOUT = 120.0  # 秒


class RetryConfig:
    """重试配置"""
    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        base_delay: float = RETRY_BASE_DELAY,
        max_delay: float = RETRY_MAX_DELAY,
        multiplier: float = RETRY_MULTIPLIER,
        retryable_errors: tuple[type[Exception], ...] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.retryable_errors = retryable_errors or (
            RateLimitError,
            NetworkError,
            TimeoutError,
            APIError,
        )


def _is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否可重试。

    Args:
        error: 捕获的异常

    Returns:
        可重试返回 True
    """
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, (NetworkError, TimeoutError)):
        return True
    if isinstance(error, APIError):
        # 5xx 错误或特定状态码可重试
        if error.status_code and error.status_code >= 500:
            return True
        if error.status_code in (429, 408, 502, 503, 504):
            return True
    return False


def _calculate_retry_delay(attempt: int, config: RetryConfig) -> float:
    """
    计算重试延迟（指数退避 + 抖动）。

    Args:
        attempt: 当前重试次数（从 1 开始）
        config: 重试配置

    Returns:
        延迟秒数
    """
    import random
    delay = config.base_delay * (config.multiplier ** (attempt - 1))
    delay = min(delay, config.max_delay)
    # 添加随机抖动（0-25%）
    jitter = delay * random.uniform(0, 0.25)
    return delay + jitter


def _translate_openai_error(error: openai.OpenAIError) -> LLMError:
    """
    将 OpenAI SDK 异常转换为项目内部异常。

    Args:
        error: OpenAI SDK 异常

    Returns:
        对应的内部异常
    """
    if isinstance(error, openai.AuthenticationError):
        return AuthenticationError(
            f"API 认证失败: {error}",
            status_code=getattr(error, "status_code", None),
        )
    if isinstance(error, openai.RateLimitError):
        return RateLimitError(
            f"API 限流: {error}",
            status_code=getattr(error, "status_code", None),
        )
    if isinstance(error, openai.APITimeoutError):
        return TimeoutError(f"请求超时: {error}")
    if isinstance(error, openai.APIConnectionError):
        return NetworkError(f"网络连接失败: {error}")
    if isinstance(error, openai.BadRequestError):
        status = getattr(error, "status_code", None)
        if status == 413 or "maximum context length" in str(error).lower():
            return TokenLimitError(
                f"Token 超限: {error}",
                status_code=status,
                response_body=getattr(error, "body", None),
            )
        return APIError(
            f"请求错误: {error}",
            status_code=status,
            response_body=getattr(error, "body", None),
        )
    if isinstance(error, openai.InternalServerError):
        return APIError(
            f"服务器错误: {error}",
            status_code=getattr(error, "status_code", 500),
        )
    # 通用 API 错误
    return APIError(
        f"API 错误: {error}",
        status_code=getattr(error, "status_code", None),
    )


class KimiClient:
    """
    Kimi API 客户端（OpenAI 兼容）。

    提供与 Kimi k2.6 模型交互的异步接口，支持：
    - 流式和非流式聊天
    - 工具调用（最多 128 个函数）
    - Thinking 模式控制
    - Token 计数和成本追踪
    - 完善的错误处理和重试机制

    Attributes:
        api_key: API 密钥
        base_url: API 基础 URL
        model: 使用的模型名称
        thinking: 是否启用 thinking 模式
        cost_tracker: 成本追踪器实例
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kimi.com/coding/v1",
        model: str = "kimi-for-coding",
        thinking: bool = True,
        cost_tracker: CostTracker | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """
        初始化 Kimi 客户端。

        Args:
            api_key: Kimi API 密钥（sk-kimi- 前缀）
            base_url: API 基础 URL，默认 Kimi Coding 平台
            model: 模型名称，默认 kimi-for-coding
            thinking: 是否启用 thinking 模式
            cost_tracker: 成本追踪器，None 则创建新实例
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._thinking = thinking
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_config = RetryConfig(max_retries=max_retries)
        self._cost_tracker = cost_tracker or CostTracker()

        # 初始化 OpenAI 兼容客户端（需要 KimiCLI User-Agent 头）
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,  # 我们自己管理重试
            default_headers={"User-Agent": "KimiCLI/1.3"},
        )

        # 初始化 Token 编码器（使用 cl100k_base）
        try:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"tiktoken 编码器初始化失败: {e}，将使用估算计数")
            self._encoder = None

        logger.info(
            f"KimiClient 初始化完成: model={model}, thinking={thinking}, "
            f"base_url={base_url}"
        )

    # ------------------------------------------------------------------
    # 核心聊天 API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        stream: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """
        发起聊天请求（流式响应）。

        核心聊天接口，产生流式 ChatEvent 事件，包括 thinking、
        content、tool_call、usage、done 等事件类型。

        Args:
            messages: 消息列表
            tools: 工具定义列表（OpenAI 函数调用格式）
            stream: 是否使用流式响应
            temperature: 采样温度 (0-2)
            max_tokens: 最大生成 Token 数
            top_p: 核采样参数 (0-1)

        Yields:
            ChatEvent: 流式聊天事件
        """
        config = ChatCompletionConfig(
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=stream,
            tools=tools,
            thinking=ThinkingConfig(
                type="enabled" if self._thinking else "disabled"
            ),
        )

        try:
            async for event in self._chat_with_retry(messages, config):
                yield event
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"chat 未预期错误: {e}", exc_info=True)
            yield ChatEvent(
                type=ChatEventType.ERROR,
                data=f"未预期错误: {e}",
            )

    async def chat_with_thinking(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, str]:
        """
        发起聊天请求，返回分离的 thinking 和 content。

        非流式接口，聚合所有响应后返回 thinking 过程和最终内容。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            temperature: 采样温度
            max_tokens: 最大生成 Token 数

        Returns:
            (reasoning_content, content) 元组
        """
        aggregator = StreamingEventAggregator()

        async for event in self.chat(
            messages=messages,
            tools=tools,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            aggregator.consume(event)

        # 记录 usage
        if aggregator.usage:
            self._cost_tracker.record_usage_object(aggregator.usage)

        return aggregator.thinking, aggregator.content

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """
        发起聊天请求，返回完整响应对象。

        非流式接口，适合需要完整响应信息的场景。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            temperature: 采样温度
            max_tokens: 最大生成 Token 数

        Returns:
            ChatResponse 完整响应对象
        """
        aggregator = StreamingEventAggregator()

        async for event in self.chat(
            messages=messages,
            tools=tools,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            aggregator.consume(event)

        # 记录 usage
        if aggregator.usage:
            self._cost_tracker.record_usage_object(aggregator.usage)

        return ChatResponse(
            content=aggregator.content,
            reasoning=aggregator.thinking,
            tool_calls=aggregator.tool_calls,
            usage=aggregator.usage,
            finish_reason=aggregator.finish_reason,
            model=self._model,
        )

    # ------------------------------------------------------------------
    # 工具调用 API
    # ------------------------------------------------------------------

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
        execute_fn: Any | None = None,
        max_tool_rounds: int = 10,
    ) -> AsyncIterator[ChatEvent]:
        """
        支持工具调用的聊天，自动处理工具调用循环。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            execute_fn: 工具执行函数，接收 ToolCall 返回 ToolResult
            max_tool_rounds: 最大工具调用轮数

        Yields:
            ChatEvent: 流式事件（包含 content 和 tool_call 事件）
        """
        current_messages = list(messages)
        rounds = 0

        while rounds < max_tool_rounds:
            rounds += 1
            aggregator = StreamingEventAggregator()

            # 发起请求
            async for event in self.chat(
                messages=current_messages,
                tools=tools,
                stream=True,
            ):
                yield event
                aggregator.consume(event)

            # 记录 usage
            if aggregator.usage:
                self._cost_tracker.record_usage_object(aggregator.usage)

            # 检查是否有工具调用
            if not aggregator.is_tool_call():
                break

            # 执行工具调用
            tool_results: list[ToolResult] = []
            if execute_fn is not None:
                for tc in aggregator.tool_calls:
                    try:
                        result = await execute_fn(tc)
                        tool_results.append(result)
                    except Exception as e:
                        tool_results.append(
                            ToolResult(
                                tool_call_id=tc.id,
                                content=f"工具执行错误: {e}",
                                is_error=True,
                            )
                        )
            else:
                # 无执行函数，标记为未执行
                for tc in aggregator.tool_calls:
                    tool_results.append(
                        ToolResult(
                            tool_call_id=tc.id,
                            content="工具未执行：未提供执行函数",
                            is_error=True,
                        )
                    )

            # 添加 assistant 消息
            assistant_message = Message.assistant(
                content=aggregator.content or None,
                tool_calls=aggregator.tool_calls,
            )
            current_messages.append(assistant_message)

            # 添加工具结果消息
            for tr in tool_results:
                tool_message = Message.tool(
                    tool_call_id=tr.tool_call_id,
                    content=tr.content,
                    is_error=tr.is_error,
                )
                current_messages.append(tool_message)

        else:
            logger.warning(f"达到最大工具调用轮数限制: {max_tool_rounds}")

    # ------------------------------------------------------------------
    # Token 计数
    # ------------------------------------------------------------------

    def count_tokens(self, text: str) -> int:
        """
        计算文本的 Token 数量。

        使用 tiktoken cl100k_base 编码器。

        Args:
            text: 输入文本

        Returns:
            Token 数量
        """
        if self._encoder is None:
            # 回退：粗略估算（每 4 字符约 1 token）
            return len(text) // 4 + 1
        return len(self._encoder.encode(text))

    def count_message_tokens(self, messages: list[Message]) -> int:
        """
        计算消息列表的 Token 数量。

        包含消息格式开销的估算。

        Args:
            messages: 消息列表

        Returns:
            总 Token 数量（估算值）
        """
        total = 0
        for msg in messages:
            # 角色开销（约 4 tokens）
            total += 4
            # 内容 Token
            if msg.content:
                total += self.count_tokens(msg.content)
            # 工具调用 Token
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count_tokens(tc.function.name)
                    total += self.count_tokens(tc.function.arguments)
                    total += 4  # ID 等开销
        # 对话格式开销
        total += 2
        return total

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit_rate: float = 0.8,
    ) -> float:
        """
        估算 API 调用成本。

        Args:
            input_tokens: 输入 Token 数量
            output_tokens: 输出 Token 数量
            cache_hit_rate: 缓存命中率

        Returns:
            估算成本（人民币）
        """
        from .cost_tracker import Pricing
        cache_hit = int(input_tokens * cache_hit_rate)
        cache_miss = input_tokens - cache_hit

        input_cost = (
            cache_hit * Pricing.INPUT_CACHE_HIT / 1_000_000
            + cache_miss * Pricing.INPUT_CACHE_MISS / 1_000_000
        )
        output_cost = output_tokens * Pricing.OUTPUT / 1_000_000

        return input_cost + output_cost

    # ------------------------------------------------------------------
    # 属性访问
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """获取当前模型名称"""
        return self._model

    @property
    def cost_tracker(self) -> CostTracker:
        """获取成本追踪器"""
        return self._cost_tracker

    @property
    def thinking_enabled(self) -> bool:
        """是否启用 thinking 模式"""
        return self._thinking

    def set_thinking(self, enabled: bool) -> None:
        """
        设置 thinking 模式。

        Args:
            enabled: 是否启用
        """
        self._thinking = enabled
        logger.info(f"Thinking 模式已{'启用' if enabled else '禁用'}")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _chat_with_retry(
        self,
        messages: list[Message],
        config: ChatCompletionConfig,
    ) -> AsyncIterator[ChatEvent]:
        """
        带重试的聊天请求。

        实现指数退避重试策略，处理限流、网络等可重试错误。

        Args:
            messages: 消息列表
            config: 聊天配置

        Yields:
            ChatEvent: 流式聊天事件
        """
        last_error: Exception | None = None

        for attempt in range(1, self._retry_config.max_retries + 1):
            try:
                if config.stream:
                    async for event in self._chat_stream(messages, config):
                        yield event
                    return
                else:
                    result = await self._chat_non_stream(messages, config)
                    # 非流式转换为事件
                    if result.reasoning:
                        yield ChatEvent(type=ChatEventType.THINKING, data=result.reasoning)
                    if result.content:
                        yield ChatEvent(type=ChatEventType.CONTENT, data=result.content)
                    for tc in result.tool_calls:
                        yield ChatEvent(type=ChatEventType.TOOL_CALL, data=tc)
                    if result.usage:
                        yield ChatEvent(type=ChatEventType.USAGE, data=result.usage)
                    yield ChatEvent(type=ChatEventType.DONE, data={})
                    return

            except LLMError as e:
                last_error = e
                if not _is_retryable_error(e) or attempt >= self._retry_config.max_retries:
                    raise

                delay = _calculate_retry_delay(attempt, self._retry_config)
                logger.warning(
                    f"请求失败（第 {attempt}/{self._retry_config.max_retries} 次尝试）: "
                    f"{e}, {delay:.1f} 秒后重试..."
                )
                await asyncio.sleep(delay)

        # 所有重试都失败
        if last_error:
            raise last_error

    async def _chat_stream(
        self,
        messages: list[Message],
        config: ChatCompletionConfig,
    ) -> AsyncIterator[ChatEvent]:
        """
        流式聊天请求（SSE）。

        Args:
            messages: 消息列表
            config: 聊天配置

        Yields:
            ChatEvent: 流式聊天事件
        """
        api_messages = [msg.to_openai_dict() if hasattr(msg, "to_openai_dict") else msg for msg in messages]
        params = config.to_api_params()

        logger.debug(f"流式请求: {len(api_messages)} 条消息, model={config.model}")
        start_time = time.monotonic()

        try:
            response = await self._client.chat.completions.create(
                messages=api_messages,
                **params,
            )

            # 直接从 SDK chunk 对象提取事件，避免不必要的序列化/反序列化
            async for chunk in response:
                chunk_dict = chunk.model_dump()
                event = SSEEventParser._process_delta(chunk_dict)
                if event is not None:
                    yield event

            elapsed = time.monotonic() - start_time
            logger.debug(f"流式请求完成，耗时: {elapsed:.2f}s")

        except openai.OpenAIError as e:
            raise _translate_openai_error(e)

    async def _chat_non_stream(
        self,
        messages: list[Message],
        config: ChatCompletionConfig,
    ) -> ChatResponse:
        """
        非流式聊天请求。

        Args:
            messages: 消息列表
            config: 聊天配置

        Returns:
            ChatResponse: 完整响应
        """
        api_messages = [msg.to_openai_dict() if hasattr(msg, "to_openai_dict") else msg for msg in messages]
        params = config.to_api_params()
        params["stream"] = False

        logger.debug(f"非流式请求: {len(api_messages)} 条消息, model={config.model}")
        start_time = time.monotonic()

        try:
            response = await self._client.chat.completions.create(
                messages=api_messages,
                **params,
            )

            elapsed = time.monotonic() - start_time
            logger.debug(f"非流式请求完成，耗时: {elapsed:.2f}s")

            # 解析响应
            choice = response.choices[0] if response.choices else None
            message = choice.message if choice else None

            tool_calls = []
            if message and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id or "",
                            type="function",
                            function=ToolCallFunction(
                                name=tc.function.name,
                                arguments=tc.function.arguments,
                            ),
                        )
                    )

            # 提取 usage
            usage = None
            if response.usage:
                usage = Usage(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    cached_tokens=response.usage.prompt_tokens_details.cached_tokens
                    if response.usage.prompt_tokens_details
                    else None,
                )
                self._cost_tracker.record_usage_object(usage)

            finish_reason = None
            if choice and choice.finish_reason:
                try:
                    finish_reason = FinishReason(choice.finish_reason)
                except ValueError:
                    finish_reason = FinishReason.NULL

            return ChatResponse(
                content=message.content if message else None,
                reasoning=message.reasoning_content if message and hasattr(message, "reasoning_content") else None,
                tool_calls=tool_calls,
                usage=usage,
                finish_reason=finish_reason,
                model=response.model or config.model,
            )

        except openai.OpenAIError as e:
            raise _translate_openai_error(e)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """关闭客户端，释放资源"""
        await self._client.close()
        logger.info("KimiClient 已关闭")

    async def __aenter__(self) -> KimiClient:
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()
