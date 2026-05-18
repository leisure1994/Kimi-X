"""
子 Agent 系统数据模型

定义子 Agent 编排器使用的所有数据模型，包括 Agent 角色、
任务优先级、任务描述、工作进程句柄和结果等核心数据结构。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(str, Enum):
    """Agent 角色枚举

    定义子 Agent 的专业角色，每种角色对应不同的职责范围、
    模型配置和工具权限。

    - EXPLORER: 代码库探索、文件分析
    - PLANNER: 任务规划、架构设计
    - CODER: 代码编写、重构
    - REVIEWER: 代码审查、质量检查
    - TESTER: 测试编写、测试执行
    - DEBUGGER: 错误诊断、修复
    - RESEARCHER: 技术调研、文档查询
    - DOCUMENTER: 文档生成、注释编写
    """

    EXPLORER = "explorer"
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DEBUGGER = "debugger"
    RESEARCHER = "researcher"
    DOCUMENTER = "documenter"


class TaskPriority(int, Enum):
    """任务优先级枚举

    用于子 Agent 任务队列的优先级排序。
    数值越大优先级越高，URGENT 任务将被优先调度。

    - LOW: 低优先级（后台任务）
    - NORMAL: 正常优先级（默认）
    - HIGH: 高优先级（重要任务）
    - URGENT: 紧急优先级（阻塞性任务）
    """

    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class SubAgentTask(BaseModel):
    """子 Agent 任务描述

    定义需要分配给子 Agent 执行的任务单元，包含角色分配、
    任务描述、执行上下文和优先级。

    Attributes:
        id: 任务唯一标识符（由编排器生成）
        role: Agent 角色，决定执行策略和工具集
        task_description: 任务描述文本（自然语言）
        context: 执行上下文数据（文件路径、代码片段等）
        priority: 任务优先级，影响调度顺序
    """

    id: str = Field(default="", description="任务唯一标识符")
    role: AgentRole = Field(..., description="Agent 角色")
    task_description: str = Field(..., description="任务描述文本")
    context: dict[str, Any] = Field(
        default_factory=dict, description="执行上下文数据"
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL, description="任务优先级"
    )

    model_config = ConfigDict(frozen=False)


class SubAgentHandle(BaseModel):
    """子 Agent 工作进程句柄

    子 Agent 任务的生命周期标识符，用于跟踪任务状态、
    查询进度和取消执行。

    Attributes:
        task_id: 关联的任务标识符
        worker_id: 工作进程唯一标识符（UUID）
        status: 当前状态（pending/running/completed/failed/cancelled）
        start_time: 任务启动时间戳（ISO 8601 格式）
        retry_count: 重试次数
    """

    task_id: str = Field(..., description="关联的任务标识符")
    worker_id: str = Field(..., description="工作进程唯一标识符")
    status: str = Field(default="pending", description="当前状态")
    start_time: str = Field(default="", description="启动时间戳 (ISO 8601)")
    retry_count: int = Field(default=0, description="重试次数")

    model_config = ConfigDict(frozen=False)


class SubAgentResult(BaseModel):
    """子 Agent 执行结果

    子 Agent 任务完成后的输出数据，包含执行摘要、
    证据材料、执行日志和 Token 使用量。

    Attributes:
        task_id: 关联的任务标识符
        status: 最终状态（completed/failed/cancelled）
        summary: 执行结果摘要文本
        evidence: 证据材料列表（文件路径、代码片段等）
        execution_log: 详细执行日志
        usage: Token 使用统计
    """

    task_id: str = Field(..., description="关联的任务标识符")
    status: str = Field(default="pending", description="最终状态")
    summary: str = Field(default="", description="执行结果摘要")
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="证据材料列表"
    )
    execution_log: list[str] = Field(
        default_factory=list, description="详细执行日志"
    )
    usage: dict[str, int] = Field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0},
        description="Token 使用统计",
    )

    @property
    def input_tokens(self) -> int:
        """输入 Token 数量"""
        return self.usage.get("input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        """输出 Token 数量"""
        return self.usage.get("output_tokens", 0)

    model_config = ConfigDict(frozen=False)


class SubAgentEvent(TypedDict):
    """子 Agent 事件（TypedDict）

    用于子 Agent 工作进程向编排器发送的实时事件消息，
    支持进度更新、中间结果通知和完成通知。

    Attributes:
        type: 事件类型（progress/result/completed/error）
        data: 事件载荷数据（根据类型变化）

    Examples:
        >>> event: SubAgentEvent = {
        ...     "type": "progress",
        ...     "data": {"percent": 50, "message": "正在分析文件..."},
        ... }
    """

    type: str  # "progress" | "result" | "completed" | "error"
    data: dict[str, Any]
