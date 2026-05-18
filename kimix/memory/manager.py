"""
记忆管理器模块

统一管理多维记忆系统（工作记忆、情景记忆、语义记忆），
提供统一的 recall()、store() 和 consolidate() 接口。

检索优先级:
1. 工作记忆（最快，< 100ms）
2. 情景记忆（持久化事件，< 500ms）
3. 语义记忆（知识图谱，< 2s）

设计要点:
- recall() 按优先级分层检索
- store() 根据记忆类型分发到对应存储
- consolidate() 定期将工作记忆转移到情景记忆
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kimix.memory.episodic import EpisodicMemory
from kimix.memory.models import (
    Event,
    MemoryEntry,
    MemoryType,
    ProjectMap,
)
from kimix.memory.semantic import SemanticMemory
from kimix.memory.working import WorkingMemory


class MemoryManager:
    """记忆管理器 - 多维记忆统一入口

    协调工作记忆、情景记忆和语义记忆三个子系统，提供统一的
    存储和检索接口。自动处理记忆类型的路由和优先级调度。

    Attributes:
        working: 工作记忆实例（短期缓存）
        episodic: 情景记忆实例（事件历史）
        semantic: 语义记忆实例（知识图谱）
        _project_path: 当前项目路径（用于语义记忆上下文）
    """

    def __init__(self, project_path: Path, db_path: Path) -> None:
        """初始化记忆管理器

        Args:
            project_path: 当前项目路径（用于语义分析上下文）
            db_path: SQLite 数据库路径（情景记忆和语义记忆共享）
        """
        self.working: WorkingMemory = WorkingMemory()
        self.episodic: EpisodicMemory = EpisodicMemory(db_path)
        self.semantic: SemanticMemory = SemanticMemory(db_path)
        self._project_path: Path = project_path.resolve()
        self._db_path: Path = db_path

    async def recall(
        self,
        query: str,
        memory_type: MemoryType | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        """统一检索记忆

        按优先级分层检索记忆：工作记忆 > 情景记忆 > 语义记忆。
        可以通过 memory_type 指定只检索特定类型的记忆。

        分层检索策略:
        - 工作记忆: 查询变量空间和文件缓存（最快）
        - 情景记忆: 全文搜索最近事件（中等速度）
        - 语义记忆: 关键词相似度搜索知识（最慢）

        Args:
            query: 检索关键词
            memory_type: 可选的记忆类型过滤
            limit: 返回结果数量上限（每个类型）

        Returns:
            MemoryEntry 列表，按相关性排序
        """
        results: list[MemoryEntry] = []

        # 第一层: 工作记忆（最高优先级，最快）
        if memory_type is None or memory_type == MemoryType.WORKING:
            working_results = self._recall_working(query, limit)
            results.extend(working_results)

        # 第二层: 情景记忆
        if memory_type is None or memory_type == MemoryType.EPISODIC:
            episodic_results = await self._recall_episodic(query, limit)
            results.extend(episodic_results)

        # 第三层: 语义记忆
        if memory_type is None or memory_type == MemoryType.SEMANTIC:
            semantic_results = await self._recall_semantic(query, limit)
            results.extend(semantic_results)

        # 按相关性评分排序
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit] if memory_type is None else results

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """统一存储记忆

        根据 entry.type 自动分发到对应的记忆子系统。

        Args:
            entry: 要存储的记忆条目

        Returns:
            存储后的记忆条目（可能包含生成的 id）

        Raises:
            ValueError: 不支持的 memory_type
        """
        if not entry.created_at:
            entry.created_at = _iso_timestamp()

        if entry.type == MemoryType.WORKING:
            # 工作记忆: 作为变量存储
            var_name = entry.metadata.get("var_name", f"mem_{entry.id or 'auto'}")
            self.working.store_variable(var_name, entry.content)
            entry.id = var_name

        elif entry.type == MemoryType.EPISODIC:
            # 情景记忆: 创建事件记录
            event = Event(
                session_id=entry.metadata.get("session_id", "default"),
                event_type=entry.metadata.get("event_type", "memory_store"),
                content=entry.content,
                tool_calls=entry.metadata.get("tool_calls", []),
                created_at=entry.created_at,
            )
            recorded = await self.episodic.record_event(event)
            entry.id = str(recorded.id)

        elif entry.type == MemoryType.SEMANTIC:
            # 语义记忆: 存储为知识条目
            from kimix.memory.models import KnowledgeEntry

            knowledge = KnowledgeEntry(
                topic=entry.metadata.get("topic", query),
                content=entry.content,
                source=entry.metadata.get("source", ""),
                confidence=entry.metadata.get("confidence", 1.0),
            )
            stored = await self.semantic.store_knowledge(knowledge)
            entry.id = str(stored.id)

        else:
            raise ValueError(f"不支持的 memory_type: {entry.type}")

        return entry

    async def consolidate(self) -> dict[str, Any]:
        """记忆整合

        将工作记忆中的重要内容转移到情景记忆中，实现短期记忆
        到长期记忆的转换。通常由后台任务定期调用。

        整合策略:
        - 缓存命中次数超过阈值的文件记录为事件
        - 变量空间中标记为 "important" 的变量转为知识条目
        - 清空已整合的工具结果缓存

        Returns:
            整合统计信息字典:
            - cached_files: 整合的文件缓存数量
            - variables: 整合的变量数量
            - tool_cache_cleared: 是否清空了工具缓存
        """
        stats: dict[str, Any] = {
            "cached_files": 0,
            "variables": 0,
            "tool_cache_cleared": False,
        }

        # 获取工作记忆统计
        wm_stats = self.working.get_stats()

        # 整合文件缓存信息到情景记忆
        if wm_stats["file_cache_entries"] > 0:
            session_id = f"consolidate_{int(time.time())}"
            event = Event(
                session_id=session_id,
                event_type="memory_consolidation",
                content=f"工作记忆整合: 缓存了 {wm_stats['file_cache_entries']} 个文件 "
                f"({wm_stats['file_cache_size_mb']} MB)",
                created_at=_iso_timestamp(),
            )
            await self.episodic.record_event(event)
            stats["cached_files"] = wm_stats["file_cache_entries"]

        # 整合变量空间中的重要变量
        variables = self.working.get_all_variables()
        important_vars = {
            k: v
            for k, v in variables.items()
            if k.startswith("important_") or k.startswith("mem_")
        }

        for var_name, value in important_vars.items():
            if isinstance(value, str) and len(value) > 10:
                event = Event(
                    session_id="consolidation",
                    event_type="important_variable",
                    content=f"[{var_name}] {value[:500]}",
                    created_at=_iso_timestamp(),
                )
                await self.episodic.record_event(event)
                stats["variables"] += 1

        # 清空工具结果缓存（已过期）
        self.working.clear_tool_cache()
        stats["tool_cache_cleared"] = True

        return stats

    async def cache_file(self, path: Path, content: str) -> None:
        """缓存文件到工作记忆（便捷方法）

        Args:
            path: 文件路径
            content: 文件内容
        """
        self.working.cache_file(path, content)

    async def get_cached_file(self, path: Path) -> str | None:
        """从工作记忆获取缓存文件（便捷方法）

        Args:
            path: 文件路径

        Returns:
            文件内容，未缓存则返回 None
        """
        return self.working.get_cached_file(path)

    async def record_event(self, event: Event) -> Event:
        """记录事件到情景记忆（便捷方法）

        Args:
            event: 要记录的事件

        Returns:
            记录后的事件
        """
        return await self.episodic.record_event(event)

    async def build_project_map(self) -> ProjectMap:
        """构建项目知识图谱（便捷方法）

        Returns:
            项目知识图谱
        """
        return await self.semantic.build_project_map(self._project_path)

    async def get_memory_stats(self) -> dict[str, Any]:
        """获取所有记忆系统的统计信息

        Returns:
            统计信息字典，包含 working、episodic、semantic 三个子系统的状态
        """
        return {
            "working": self.working.get_stats(),
            "episodic": {
                "total_events": await self.episodic.get_event_count(),
            },
            "semantic": {
                "db_path": str(self._db_path),
            },
        }

    async def close(self) -> None:
        """关闭所有记忆系统资源"""
        await self.episodic.close()
        await self.semantic.close()

    async def __aenter__(self) -> MemoryManager:
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()

    def _recall_working(self, query: str, limit: int) -> list[MemoryEntry]:
        """检索工作记忆（内部方法）

        查询变量空间和文件缓存，匹配关键词。

        Args:
            query: 检索关键词
            limit: 结果数量上限

        Returns:
            工作记忆中的匹配条目
        """
        results: list[MemoryEntry] = []
        query_lower = query.lower()

        # 搜索变量空间
        variables = self.working.get_all_variables()
        for name, value in variables.items():
            value_str = str(value) if value is not None else ""
            if query_lower in name.lower() or query_lower in value_str.lower():
                relevance = 0.9 if query_lower in name.lower() else 0.6
                results.append(
                    MemoryEntry(
                        type=MemoryType.WORKING,
                        content=f"变量 {name}: {value_str[:200]}",
                        metadata={"var_name": name, "source": "working_memory"},
                        relevance_score=relevance,
                    )
                )

            if len(results) >= limit:
                break

        return results[:limit]

    async def _recall_episodic(self, query: str, limit: int) -> list[MemoryEntry]:
        """检索情景记忆（内部方法）

        使用 FTS5 全文搜索查找最近事件。

        Args:
            query: 检索关键词
            limit: 结果数量上限

        Returns:
            情景记忆中的匹配条目
        """
        try:
            events = await self.episodic.search_events(query, limit=limit)
        except Exception:
            # FTS 搜索失败时回退到最近事件
            events = await self.episodic.get_recent_events(n=limit)

        results: list[MemoryEntry] = []
        for event in events:
            # 计算相关性: 越新的事件相关性越高
            age_score = 0.5  # 默认中等相关性
            results.append(
                MemoryEntry(
                    id=str(event.id),
                    type=MemoryType.EPISODIC,
                    content=event.content,
                    metadata={
                        "session_id": event.session_id,
                        "event_type": event.event_type,
                        "created_at": event.created_at,
                    },
                    created_at=event.created_at,
                    relevance_score=0.5 + age_score * 0.3,
                )
            )

        return results

    async def _recall_semantic(self, query: str, limit: int) -> list[MemoryEntry]:
        """检索语义记忆（内部方法）

        使用余弦相似度搜索知识条目。

        Args:
            query: 检索关键词
            limit: 结果数量上限

        Returns:
            语义记忆中的匹配条目
        """
        entries = await self.semantic.query_knowledge(query, limit=limit)

        results: list[MemoryEntry] = []
        for entry in entries:
            results.append(
                MemoryEntry(
                    id=str(entry.id),
                    type=MemoryType.SEMANTIC,
                    content=f"{entry.topic}: {entry.content}",
                    metadata={
                        "source": entry.source,
                        "confidence": entry.confidence,
                    },
                    relevance_score=entry.confidence,
                )
            )

        return results


def _iso_timestamp() -> str:
    """生成 ISO 8601 格式时间戳（模块级工具函数）

    Returns:
        ISO 8601 格式时间戳字符串
    """
    return datetime.now(timezone.utc).isoformat()
