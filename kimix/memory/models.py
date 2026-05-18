"""
记忆系统数据模型

定义多维记忆系统使用的所有 Pydantic 模型和枚举类型，
包括记忆条目、事件、代码模式和知识条目等核心数据结构。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    """记忆类型枚举

    标识记忆条目的分类维度:
    - WORKING: 工作记忆（短期缓存，会话级别）
    - EPISODIC: 情景记忆（事件历史，持久化）
    - SEMANTIC: 语义记忆（知识图谱，结构化知识）
    """

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryEntry(BaseModel):
    """统一记忆条目

    作为多维记忆系统的通用数据容器，用于 recall() 和 store() 的
    统一接口。包含记忆内容、类型、元数据和相关性评分。

    Attributes:
        id: 记忆唯一标识符（由存储层生成）
        type: 记忆类型，决定存储和检索策略
        content: 记忆内容文本
        metadata: 扩展元数据字典
        created_at: 创建时间戳（ISO 8601 格式）
        relevance_score: 相关性评分（0.0-1.0，由检索层计算）
    """

    id: str = Field(default="", description="记忆唯一标识符")
    type: MemoryType = Field(..., description="记忆类型")
    content: str = Field(..., description="记忆内容文本")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="扩展元数据字典"
    )
    created_at: str = Field(default="", description="创建时间戳 (ISO 8601)")
    relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="相关性评分"
    )

    model_config = ConfigDict(frozen=False)


class Event(BaseModel):
    """情景记忆事件

    记录 Agent 执行过程中的离散事件，包括对话回合、工具调用、
    错误记录等。存储于 SQLite 的 events 表中，支持全文搜索。

    Attributes:
        id: 事件唯一标识符（数据库自增）
        session_id: 所属会话标识符
        event_type: 事件类型（如 'turn', 'tool_call', 'error'）
        content: 事件内容文本
        tool_calls: 相关工具调用 JSON 列表
        created_at: 创建时间戳（ISO 8601 格式）
    """

    id: int = Field(default=0, description="事件唯一标识符")
    session_id: str = Field(..., description="所属会话标识符")
    event_type: str = Field(..., description="事件类型")
    content: str = Field(..., description="事件内容文本")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="相关工具调用列表"
    )
    created_at: str = Field(default="", description="创建时间戳 (ISO 8601)")

    model_config = ConfigDict(frozen=False)


class CodePattern(BaseModel):
    """代码模式条目

    语义记忆中记录的代码片段和编程模式，用于代码补全建议、
    重构参考和最佳实践推荐。

    Attributes:
        id: 模式唯一标识符（数据库自增）
        pattern: 代码模式文本（正则或模板）
        language: 编程语言标识符
        frequency: 使用频率（出现次数）
        last_used: 最后使用时间戳
    """

    id: int = Field(default=0, description="模式唯一标识符")
    pattern: str = Field(..., description="代码模式文本")
    language: str = Field(default="", description="编程语言")
    frequency: int = Field(default=1, ge=0, description="使用频率")
    last_used: str = Field(default="", description="最后使用时间戳 (ISO 8601)")

    model_config = ConfigDict(frozen=False)


class KnowledgeEntry(BaseModel):
    """知识条目

    语义记忆中的结构化知识单元，记录项目相关的概念、API、
    依赖关系等事实性知识。

    Attributes:
        id: 知识条目唯一标识符（数据库自增）
        topic: 知识主题/标题
        content: 知识内容文本
        source: 知识来源（如文件路径、URL）
        confidence: 置信度评分（0.0-1.0）
    """

    id: int = Field(default=0, description="知识条目唯一标识符")
    topic: str = Field(..., description="知识主题")
    content: str = Field(..., description="知识内容文本")
    source: str = Field(default="", description="知识来源")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="置信度评分"
    )

    model_config = ConfigDict(frozen=False)


class ProjectMap(BaseModel):
    """项目知识图谱

    语义记忆生成的项目结构映射，包含文件关系、模块依赖、
    关键入口点等结构化信息。

    Attributes:
        project_path: 项目根路径
        files: 文件列表及元数据
        modules: 模块列表及依赖关系
        entry_points: 项目入口点
        relationships: 文件/模块间关系列表
    """

    project_path: str = Field(..., description="项目根路径")
    files: list[dict[str, Any]] = Field(
        default_factory=list, description="文件列表及元数据"
    )
    modules: list[dict[str, Any]] = Field(
        default_factory=list, description="模块列表及依赖关系"
    )
    entry_points: list[str] = Field(
        default_factory=list, description="项目入口点"
    )
    relationships: list[dict[str, Any]] = Field(
        default_factory=list, description="文件/模块间关系列表"
    )

    model_config = ConfigDict(frozen=False)
