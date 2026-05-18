"""
LLM 客户端数据模型模块。

定义 Kimi API 交互所需的所有数据模型，包括消息、工具调用、
Token 使用统计等核心数据结构。所有模型均使用 Pydantic v2 进行验证。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallFunction(BaseModel):
    """工具调用中的函数信息"""
    name: str = Field(description="函数名称")
    arguments: str = Field(description="函数参数 JSON 字符串")


class ToolCall(BaseModel):
    """工具调用定义，用于 assistant 消息中的 tool_calls"""
    id: str | None = Field(default=None, description="工具调用唯一标识")
    type: Literal["function"] = Field(default="function", description="调用类型")
    function: ToolCallFunction = Field(description="函数调用详情")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（兼容测试接口）"""
        return {
            "id": self.id or "",
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class ToolResult(BaseModel):
    """工具执行结果，用于 tool 消息"""
    tool_call_id: str = Field(description="对应工具调用的 ID")
    content: str = Field(description="工具执行的输出内容")
    is_error: bool = Field(default=False, description="是否执行出错")


class Message(BaseModel):
    """
    聊天消息模型，兼容 OpenAI 消息格式。

    支持系统消息、用户消息、助手消息和工具消息。
    助手消息可包含 tool_calls，工具消息必须提供 tool_call_id。
    """
    role: MessageRole = Field(description="消息角色")
    content: str | None = Field(default=None, description="消息内容文本")
    reasoning_content: str | None = Field(default=None, description="模型的思考过程内容（thinking 模式）")
    tool_calls: list[ToolCall] | None = Field(default=None, description="助手发起的工具调用列表")
    tool_call_id: str | None = Field(default=None, description="工具消息对应的调用 ID")
    name: str | None = Field(default=None, description="工具名称（用于 function 角色）")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None, info: Any) -> str | None:
        """
        验证 content 字段：
        - tool 角色时 content 可以为 None，但建议提供
        - assistant 角色有 tool_calls 时 content 可以为 None
        """
        values = info.data
        role = values.get("role")
        if v is None and role == MessageRole.USER:
            raise ValueError("用户消息必须有 content")
        return v

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（兼容测试接口）"""
        return self.to_openai_dict()

    def to_openai_dict(self) -> dict[str, Any]:
        """
        转换为 OpenAI API 兼容的字典格式。

        Returns:
            OpenAI 兼容的消息字典
        """
        result: dict[str, Any] = {"role": self.role.value}

        if self.content is not None:
            result["content"] = self.content

        if self.reasoning_content is not None:
            result["reasoning_content"] = self.reasoning_content

        if self.tool_calls is not None:
            result["tool_calls"] = [
                {
                    "id": tc.id or "",
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]

        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id

        if self.name is not None:
            result["name"] = self.name

        return result

    @classmethod
    def from_openai_dict(cls, data: dict[str, Any]) -> Message:
        """
        从 OpenAI API 响应字典创建 Message。

        Args:
            data: OpenAI API 返回的消息字典

        Returns:
            Message 实例
        """
        role = MessageRole(data.get("role", "user"))
        content = data.get("content")
        reasoning_content = data.get("reasoning_content")
        tool_call_id = data.get("tool_call_id")
        name = data.get("name")

        tool_calls = None
        if "tool_calls" in data and data["tool_calls"]:
            tool_calls = []
            for tc in data["tool_calls"]:
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id") or "",
                        type=tc.get("type", "function"),
                        function=ToolCallFunction(
                            name=func.get("name", ""),
                            arguments=func.get("arguments", ""),
                        ),
                    )
                )

        return cls(
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )

    @classmethod
    def system(cls, content: str) -> Message:
        """快速创建系统消息"""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        """快速创建用户消息"""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str | None = None, reasoning_content: str | None = None, tool_calls: list[ToolCall] | None = None) -> Message:
        """快速创建助手消息"""
        return cls(role=MessageRole.ASSISTANT, content=content, reasoning_content=reasoning_content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, tool_call_id: str, content: str, is_error: bool = False) -> Message:
        """
        快速创建工具消息。

        Args:
            tool_call_id: 对应的工具调用 ID
            content: 工具执行结果内容
            is_error: 是否执行出错
        """
        return cls(
            role=MessageRole.TOOL,
            tool_call_id=tool_call_id,
            content=content,
        )


class Usage(BaseModel):
    """
    Token 使用统计模型。

    记录每次 API 调用的 Token 消耗情况，用于成本追踪。
    """
    prompt_tokens: int = Field(default=0, ge=0, description="输入 Token 数量")
    completion_tokens: int = Field(default=0, ge=0, description="输出 Token 数量")
    total_tokens: int = Field(default=0, ge=0, description="总 Token 数量")
    cached_tokens: int | None = Field(default=None, ge=0, description="缓存命中 Token 数量")

    def model_post_init(self, __context: Any) -> None:
        """确保 total_tokens 自动计算"""
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


class ChatEventType(str, Enum):
    """聊天事件类型枚举"""
    THINKING = "thinking"       # 模型思考过程
    CONTENT = "content"         # 正常响应内容
    TOOL_CALL = "tool_call"     # 工具调用
    USAGE = "usage"             # Token 使用统计
    DONE = "done"               # 流式响应完成
    ERROR = "error"             # 错误事件


class ChatEvent(BaseModel):
    """
    流式聊天事件模型（Pydantic v2）。

    替代 TypedDict，提供运行时类型验证和空值保护。
    """
    type: ChatEventType = Field(description="事件类型")
    data: Any = Field(default=None, description="事件数据")

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: Any, info: Any) -> Any:
        """根据事件类型验证 data 字段"""
        event_type = info.data.get("type")
        if event_type in (ChatEventType.THINKING, ChatEventType.CONTENT):
            if v is not None and not isinstance(v, (str, dict)):
                raise ValueError(f"{event_type} 事件的 data 必须是 str 或 dict，得到 {type(v).__name__}")
        return v

    def get(self, key: str, default: Any = None) -> Any:
        """兼容 dict-like 访问，用于现有代码过渡"""
        if key == "type":
            return self.type
        if key == "data":
            return self.data
        return default

    def __getitem__(self, key: str) -> Any:
        """支持 event['type'] / event['data'] 语法"""
        if key == "type":
            return self.type
        if key == "data":
            return self.data
        raise KeyError(key)


class ThinkingConfig(BaseModel):
    """
    Thinking 模式配置。

    控制 Kimi k2.6 模型的思考模式行为。
    """
    type: Literal["enabled", "disabled"] = Field(
        default="disabled",
        description="思考模式: enabled 或 disabled",
    )

    def to_extra_body(self) -> dict[str, Any]:
        """转换为 API extra_body 格式"""
        return {"thinking": {"type": self.type}}


class ChatCompletionConfig(BaseModel):
    """
    聊天补全配置。

    聚合所有 API 调用参数，方便统一管理。
    """
    model: str = Field(default="kimi-k2.6", description="模型名称")
    temperature: float | None = Field(default=None, ge=0, le=2, description="采样温度")
    max_tokens: int | None = Field(default=None, ge=1, description="最大生成 Token 数")
    top_p: float | None = Field(default=None, ge=0, le=1, description="核采样参数")
    stream: bool = Field(default=True, description="是否使用流式响应")
    tools: list[dict[str, Any]] | None = Field(default=None, description="可用工具定义")
    tool_choice: str | dict[str, Any] | None = Field(default=None, description="工具选择策略")
    thinking: ThinkingConfig = Field(
        default_factory=ThinkingConfig,
        description="思考模式配置",
    )

    def to_api_params(self) -> dict[str, Any]:
        """
        转换为 OpenAI API 参数字典。

        Returns:
            API 调用参数字典
        """
        params: dict[str, Any] = {
            "model": self.model,
            "stream": self.stream,
            "extra_body": self.thinking.to_extra_body(),
        }

        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.tools is not None:
            params["tools"] = self.tools
        if self.tool_choice is not None:
            params["tool_choice"] = self.tool_choice

        return params


class FinishReason(str, Enum):
    """响应结束原因枚举"""
    STOP = "stop"               # 正常完成
    LENGTH = "length"           # 达到最大长度限制
    TOOL_CALLS = "tool_calls"   # 触发了工具调用
    CONTENT_FILTER = "content_filter"  # 内容过滤
    NULL = "null"               # 流式响应中尚未结束


class ChatResponse(BaseModel):
    """
    完整聊天响应模型（非流式）。

    用于一次性获取完整响应结果的场景。
    """
    content: str | None = Field(default=None, description="响应文本内容")
    reasoning: str | None = Field(default=None, description="思考过程内容")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="工具调用列表")
    usage: Usage | None = Field(default=None, description="Token 使用统计")
    finish_reason: FinishReason | None = Field(default=None, description="结束原因")
    model: str | None = Field(default=None, description="使用的模型")


class LLMError(Exception):
    """LLM 客户端基础异常"""
    pass


class APIError(LLMError):
    """API 调用异常"""
    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None, **kwargs: Any):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        # 存储额外关键字参数（兼容测试接口）
        for key, value in kwargs.items():
            setattr(self, key, value)


class RateLimitError(APIError):
    """限流异常"""
    def __init__(self, message: str, retry_after: int | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class TokenLimitError(APIError):
    """Token 超限异常"""
    def __init__(self, message: str, max_tokens: int | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.max_tokens = max_tokens


class AuthenticationError(APIError):
    """认证异常"""
    pass


class NetworkError(LLMError):
    """网络连接异常"""
    pass


class TimeoutError(LLMError):
    """请求超时异常"""
    pass
