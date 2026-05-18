"""
工具系统基类与核心数据模型

定义所有工具的抽象基类、上下文、结果和审批级别枚举。
所有工具必须继承 Tool 基类并实现 execute 方法。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 审批级别枚举
# ---------------------------------------------------------------------------


class ApprovalLevel(str, Enum):
    """工具操作的审批级别

    - NONE: 无需审批，可直接执行
    - READONLY: 只读操作无需审批，写入需审批
    - DESTRUCTIVE: 破坏性操作（删除、覆盖等）需审批
    - ALL: 所有操作都需要审批
    """

    NONE = "none"
    READONLY = "readonly"
    DESTRUCTIVE = "destructive"
    ALL = "all"


# ---------------------------------------------------------------------------
# 工具上下文
# ---------------------------------------------------------------------------


class ToolContext(BaseModel):
    """工具执行上下文

    每次调用工具时传入的上下文信息，包含工作目录、
    环境变量和沙箱配置等。
    """

    work_dir: str = Field(
        default=".",
        description="工作目录路径，所有相对路径操作均以此为基准",
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="额外的环境变量，会覆盖系统环境变量",
    )
    sandbox_enabled: bool = Field(
        default=True,
        description="是否启用沙箱隔离，启用后限制文件和命令访问范围",
    )
    allowed_paths: list[str] = Field(
        default_factory=list,
        description="沙箱允许访问的路径列表（白名单）",
    )
    timeout: int = Field(
        default=60,
        description="工具执行超时时间（秒）",
    )
    session_id: str | None = Field(
        default=None,
        description="当前会话唯一标识",
    )

    model_config = {"frozen": False, "extra": "forbid"}


# ---------------------------------------------------------------------------
# 工具执行结果
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """工具执行结果

    统一封装工具的执行结果，包含成功标志、返回内容和错误信息。
    """

    success: bool = Field(
        ...,
        description="工具是否执行成功",
    )
    content: str = Field(
        default="",
        description="工具返回的文本内容",
    )
    error: str | None = Field(
        default=None,
        description="错误信息，仅在失败时有值",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="额外的元数据（如执行时间、文件路径等）",
    )

    @classmethod
    def ok(cls, content: str = "", **meta: Any) -> "ToolResult":
        """创建成功的结果"""
        return cls(success=True, content=content, metadata=meta)

    @classmethod
    def fail(cls, error: str, content: str = "", **meta: Any) -> "ToolResult":
        """创建失败的结果"""
        return cls(success=False, content=content, error=error, metadata=meta)


# ---------------------------------------------------------------------------
# 工具抽象基类
# ---------------------------------------------------------------------------


@runtime_checkable
class Tool(Protocol):
    """工具协议（Protocol）

    定义工具必须实现的接口。所有工具类都必须符合此协议。
    推荐使用 AbstractTool 基类进行实现。
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    approval_required: ApprovalLevel

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult: ...


class AbstractTool(ABC):
    """工具抽象基类

    所有具体工具的基类，提供标准接口和通用辅助方法。
    子类必须设置类属性 name、description、parameters 和 approval_required。

    Example:
        class MyTool(AbstractTool):
            name = "my_tool"
            description = "我的工具描述"
            parameters = {...}  # JSON Schema
            approval_required = ApprovalLevel.NONE

            async def execute(self, params, context):
                return ToolResult.ok("done")
    """

    # 类属性 —— 子类必须覆盖
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[dict[str, Any]] = {}
    approval_required: ClassVar[ApprovalLevel] = ApprovalLevel.NONE

    # 实例属性
    def __init__(self) -> None:
        # 子类可在 __init__ 中做初始化
        pass

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """执行工具逻辑

        Args:
            params: 经过 JSON Schema 校验后的参数字典
            context: 当前执行上下文

        Returns:
            ToolResult: 执行结果
        """
        ...

    def to_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema 描述（OpenAI function format）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ---------------------------------------------------------------------------
# 工具调用描述（LLM 返回的调用请求）
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """LLM 发起的工具调用请求"""

    id: str = Field(description="工具调用唯一标识")
    name: str = Field(description="要调用的工具名称")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="调用参数",
    )


class ToolCallResult(BaseModel):
    """工具调用结果（回传给 LLM）"""

    tool_call_id: str = Field(description="对应 ToolCall 的 id")
    name: str = Field(description="工具名称")
    result: ToolResult = Field(description="执行结果")

    def to_message_content(self) -> str:
        """转换为适合放入 LLM message 的文本"""
        if self.result.success:
            return self.result.content
        return f"[错误] {self.result.error}"
