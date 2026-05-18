"""自学习系统数据模型.

定义经验记录、策略、技能模式、Prompt 版本等核心数据结构。
所有模型基于 Pydantic v2，支持序列化/反序列化到 SQLite。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskOutcome(str, Enum):
    """任务执行结果."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    TIMEOUT = "timeout"


class ExperienceRecord(BaseModel):
    """单条经验记录.

    记录一次完整的任务执行经验，包括上下文、行动、结果和反射。
    """

    model_config = ConfigDict(frozen=False)

    id: str = Field(default="", description="唯一标识符")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="创建时间",
    )
    task_type: str = Field(default="", description="任务类型标签")
    task_description: str = Field(default="", description="任务描述摘要")
    context_tags: list[str] = Field(default_factory=list, description="上下文标签集合")
    tools_used: list[str] = Field(default_factory=list, description="使用的工具列表")
    steps_count: int = Field(default=0, description="执行步骤数")
    outcome: TaskOutcome = Field(default=TaskOutcome.SUCCESS, description="执行结果")
    error_type: str = Field(default="", description="错误类型（失败时）")
    lesson: str = Field(default="", description="经验教训/反射总结")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="综合评分")
    duration_seconds: float = Field(default=0.0, description="执行耗时（秒）")
    token_cost: int = Field(default=0, description="Token 消耗量")


class StrategyPlaybook(BaseModel):
    """策略 Playbook.

    针对特定任务类型的最佳实践策略，通过 EMA 持续优化。
    """

    model_config = ConfigDict(frozen=False)

    task_type: str = Field(description="适用的任务类型")
    strategy_text: str = Field(default="", description="策略描述文本")
    success_rate: float = Field(default=0.5, ge=0.0, le=1.0, description="历史成功率 (EMA)")
    avg_steps: float = Field(default=0.0, description="平均步骤数 (EMA)")
    avg_duration: float = Field(default=0.0, description="平均耗时秒 (EMA)")
    preferred_tools: list[str] = Field(default_factory=list, description="偏好工具排序")
    anti_patterns: list[str] = Field(default_factory=list, description="反模式/避免事项")
    sample_count: int = Field(default=0, description="累计样本数")
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="最后更新时间",
    )


class SkillPattern(BaseModel):
    """技能模式.

    通过 Jaccard 相似度聚类发现的可复用技能模式。
    """

    model_config = ConfigDict(frozen=False)

    id: str = Field(default="", description="唯一标识符")
    name: str = Field(default="", description="技能名称")
    description: str = Field(default="", description="技能描述")
    trigger_tags: list[str] = Field(default_factory=list, description="触发标签集合")
    tool_sequence: list[str] = Field(default_factory=list, description="工具调用序列")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="成功率")
    usage_count: int = Field(default=0, description="使用次数")


class PromptVersion(BaseModel):
    """Prompt 版本记录.

    带版本号和性能指标的 Prompt，支持自动演化和回滚。
    """

    model_config = ConfigDict(frozen=False)

    version: int = Field(default=1, description="版本号")
    prompt_text: str = Field(default="", description="Prompt 文本")
    avg_score: float = Field(default=0.0, ge=0.0, le=1.0, description="平均评分")
    sample_count: int = Field(default=0, description="评估样本数")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="创建时间",
    )
    is_active: bool = Field(default=True, description="是否为当前活跃版本")
