"""
Kimi-Agent 记忆系统

提供多维记忆管理能力，包括：
- WorkingMemory: 工作记忆（短期缓存，LRU 文件缓存 + 变量空间）
- EpisodicMemory: 情景记忆（事件历史，SQLite + FTS5 全文搜索）
- SemanticMemory: 语义记忆（知识图谱，代码模式 + 关键词相似度搜索）
- MemoryManager: 记忆管理器（统一入口，分层检索 + 记忆整合）

使用示例:
    >>> from kimix.memory import MemoryManager
    >>> from pathlib import Path
    >>> manager = MemoryManager(
    ...     project_path=Path("."),
    ...     db_path=Path.home() / ".kimix" / "memory.db",
    ... )
    >>> results = await manager.recall("数据库连接")
"""

from __future__ import annotations

from kimix.memory.episodic import EpisodicMemory
from kimix.memory.experience import ExperienceMemory, ExperienceRecord
from kimix.memory.manager import MemoryManager
from kimix.memory.semantic import SemanticMemory
from kimix.memory.working import WorkingMemory

__all__ = [
    "MemoryManager",
    "WorkingMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "ExperienceMemory",
    "ExperienceRecord",
]
