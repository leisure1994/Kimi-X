"""
回合管理模块

定义 Turn（回合）和 TurnResult（回合结果）数据模型。
一个回合代表用户一次输入到 Agent 完成响应的完整周期。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """回合模型，代表一次完整的交互周期
    
    一个回合从用户输入开始，经过 Agent 处理（可能包含多轮工具调用），
    到最终响应结束。
    
    Attributes:
        id: 回合唯一标识符（UUID）
        user_input: 用户的原始输入文本
        messages: 本回合累积的消息列表（包含工具调用和结果）
        mode: 本回合使用的工作模式
        created_at: 回合创建时间（ISO 格式）
        status: 回合状态：pending / running / completed / error
    
    Examples:
        >>> turn = Turn(
        ...     id="turn-001",
        ...     user_input="帮我读取 README.md",
        ...     messages=[{"role": "user", "content": "帮我读取 README.md"}],
        ...     mode="agent",
        ... )
    """
    id: str = Field(description="回合唯一标识符")
    user_input: str = Field(description="用户原始输入")
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="本回合累积的消息列表",
    )
    mode: str = Field(
        default="agent",
        description="本回合使用的工作模式",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="回合创建时间",
    )
    status: Literal["pending", "running", "completed", "error"] = Field(
        default="pending",
        description="回合当前状态",
    )

    def add_message(self, role: str, content: str | dict[str, Any], **kwargs: Any) -> None:
        """添加消息到回合消息列表
        
        Args:
            role: 消息角色 (system / user / assistant / tool)
            content: 消息内容
            **kwargs: 额外字段（如 tool_call_id, name 等）
        
        Examples:
            >>> turn = Turn(id="t1", user_input="hi")
            >>> turn.add_message("assistant", "Hello!")
            >>> len(turn.messages)
            1
        """
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)

    def add_tool_call_result(
        self,
        tool_call_id: str,
        name: str,
        result: Any,
        error: str | None = None,
    ) -> None:
        """添加工具调用结果消息
        
        将工具执行结果格式化为标准的 tool 角色消息，
        符合 OpenAI 工具调用规范。
        
        Args:
            tool_call_id: 工具调用 ID
            name: 工具名称
            result: 工具执行结果（会被序列化为字符串）
            error: 错误信息（如有）
        """
        if error:
            content = f"错误: {error}"
        else:
            if isinstance(result, str):
                content = result
            else:
                try:
                    import json
                    content = json.dumps(result, ensure_ascii=False, default=str)
                except Exception:
                    content = str(result)

        self.add_message(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            name=name,
        )

    def set_status(
        self,
        status: Literal["pending", "running", "completed", "error"],
    ) -> None:
        """更新回合状态"""
        self.status = status


class TurnResult(BaseModel):
    """回合结果模型
    
    包含一个回合的最终结果：响应文本、工具调用记录和使用统计。
    
    Attributes:
        turn_id: 对应回合的 ID
        response: Agent 的最终响应文本
        tool_calls: 本回合执行的所有工具调用记录
        usage: Token 使用统计
        duration_ms: 回合执行耗时（毫秒）
        mode: 本回合使用的工作模式
        completed_at: 完成时间（ISO 格式）
    
    Examples:
        >>> result = TurnResult(
        ...     turn_id="turn-001",
        ...     response="已为你读取 README.md，内容是...",
        ...     tool_calls=[{"name": "file_read", "params": {"path": "README.md"}}],
        ...     usage={"input_tokens": 150, "output_tokens": 200},
        ... )
    """
    turn_id: str = Field(description="回合 ID")
    response: str = Field(
        default="",
        description="Agent 最终响应文本",
    )
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="执行的工具调用记录",
    )
    usage: dict[str, Any] = Field(
        default_factory=dict,
        description="Token 使用统计",
    )
    duration_ms: int = Field(
        default=0,
        description="执行耗时（毫秒）",
    )
    mode: str = Field(
        default="agent",
        description="工作模式",
    )
    completed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="完成时间",
    )

    @property
    def total_tokens(self) -> int:
        """获取总 Token 数"""
        return (
            self.usage.get("input_tokens", 0)
            + self.usage.get("output_tokens", 0)
        )

    @property
    def cost_estimate(self) -> float:
        """估算成本（USD），基于 Kimi K2.6 定价
        
        定价参考：
        - 输入：$0.50 / 1M tokens（缓存命中 $0.50）
        - 输出：$2.00 / 1M tokens
        """
        input_tokens = self.usage.get("input_tokens", 0)
        output_tokens = self.usage.get("output_tokens", 0)
        return (input_tokens * 0.50 + output_tokens * 2.00) / 1_000_000
