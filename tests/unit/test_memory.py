"""
记忆系统单元测试

测试 WorkingMemory（工作记忆）、EpisodicMemory（情景记忆）、
SemanticMemory（语义记忆）和 MemoryManager（记忆管理器）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kimix.memory.episodic import EpisodicMemory, Event
from kimix.memory.manager import MemoryManager
from kimix.memory.models import (
    CodePattern,
    KnowledgeEntry,
    MemoryEntry,
    MemoryType,
)
from kimix.memory.semantic import SemanticMemory
from kimix.memory.working import WorkingMemory



pytestmark = pytest.mark.unit
class TestWorkingMemory:
    """WorkingMemory 工作记忆测试"""

    def test_init(self) -> None:
        """测试初始化"""
        wm = WorkingMemory()
        assert wm.get_stats()["file_cache_entries"] == 0
        assert wm.get_stats()["variable_count"] == 0

    def test_cache_and_get_file(self, temp_dir: Path) -> None:
        """测试缓存和获取文件"""
        wm = WorkingMemory()
        path = temp_dir / "test.txt"
        path.write_text("Hello")
        wm.cache_file(path, "Hello")
        assert wm.get_cached_file(path) == "Hello"
        assert wm.get_stats()["file_cache_entries"] == 1

    def test_get_nonexistent_cached_file(self, temp_dir: Path) -> None:
        """测试获取未缓存的文件"""
        wm = WorkingMemory()
        path = temp_dir / "not_cached.txt"
        assert wm.get_cached_file(path) is None

    def test_store_and_get_variable(self) -> None:
        """测试存储和获取变量"""
        wm = WorkingMemory()
        wm.store_variable("key", "value")
        assert wm.get_variable("key") == "value"
        assert wm.get_stats()["variable_count"] == 1

    def test_get_nonexistent_variable(self) -> None:
        """测试获取不存在的变量"""
        wm = WorkingMemory()
        assert wm.get_variable("nonexistent") is None

    def test_get_all_variables(self) -> None:
        """测试获取所有变量"""
        wm = WorkingMemory()
        wm.store_variable("a", 1)
        wm.store_variable("b", 2)
        vars_dict = wm.get_all_variables()
        assert vars_dict == {"a": 1, "b": 2}

    def test_cache_tool_result(self) -> None:
        """测试缓存工具结果"""
        wm = WorkingMemory()
        wm.cache_tool_result("test_tool", {"param": "value"}, "result")
        assert wm.get_cached_tool_result("test_tool", {"param": "value"}) == "result"

    def test_get_nonexistent_tool_result(self) -> None:
        """测试获取未缓存的工具结果"""
        wm = WorkingMemory()
        assert wm.get_cached_tool_result("none", {}) is None

    def test_clear_file_cache(self, temp_dir: Path) -> None:
        """测试清空文件缓存"""
        wm = WorkingMemory()
        path = temp_dir / "clear.txt"
        path.write_text("data")
        wm.cache_file(path, "data")
        assert wm.get_stats()["file_cache_entries"] == 1
        wm.clear_file_cache()
        assert wm.get_stats()["file_cache_entries"] == 0

    def test_clear_variables(self) -> None:
        """测试清空变量"""
        wm = WorkingMemory()
        wm.store_variable("x", 1)
        wm.clear_variables()
        assert wm.get_stats()["variable_count"] == 0

    def test_get_stats(self, temp_dir: Path) -> None:
        """测试获取统计信息"""
        wm = WorkingMemory()
        path = temp_dir / "stat.txt"
        path.write_text("content")
        wm.cache_file(path, "content")
        wm.store_variable("v", "val")
        stats = wm.get_stats()
        assert stats["file_cache_entries"] == 1
        assert stats["variable_count"] == 1


class TestEpisodicMemory:
    """EpisodicMemory 情景记忆测试"""

    @pytest.mark.asyncio
    async def test_record_event(self, temp_dir: Path) -> None:
        """测试记录事件"""
        db_path = temp_dir / "memory.db"
        em = EpisodicMemory(db_path)
        event = Event(session_id="test-sess", event_type="test", content="test content")
        recorded = await em.record_event(event)
        assert recorded.id is not None
        await em.close()

    @pytest.mark.asyncio
    async def test_get_recent_events(self, temp_dir: Path) -> None:
        """测试获取最近事件"""
        db_path = temp_dir / "memory.db"
        em = EpisodicMemory(db_path)
        event = Event(session_id="test-sess", event_type="test", content="recent")
        await em.record_event(event)
        events = await em.get_recent_events(n=10, session_id="test-sess")
        assert len(events) >= 1
        await em.close()

    @pytest.mark.asyncio
    async def test_get_event_count(self, temp_dir: Path) -> None:
        """测试获取事件总数"""
        db_path = temp_dir / "memory.db"
        em = EpisodicMemory(db_path)
        count_before = await em.get_event_count()
        event = Event(session_id="test-sess", event_type="test", content="count")
        await em.record_event(event)
        count_after = await em.get_event_count()
        assert count_after == count_before + 1
        await em.close()

    @pytest.mark.asyncio
    async def test_delete_old_events(self, temp_dir: Path) -> None:
        """测试删除旧事件"""
        db_path = temp_dir / "memory.db"
        em = EpisodicMemory(db_path)
        event = Event(session_id="test-sess", event_type="test", content="old")
        await em.record_event(event)
        deleted = await em.delete_old_events("2099-01-01T00:00:00+00:00")
        assert deleted >= 1
        await em.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_dir: Path) -> None:
        """测试上下文管理器"""
        db_path = temp_dir / "memory.db"
        async with EpisodicMemory(db_path) as em:
            event = Event(session_id="test", event_type="test", content="ctx")
            await em.record_event(event)


class TestSemanticMemory:
    """SemanticMemory 语义记忆测试"""

    @pytest.mark.asyncio
    async def test_store_knowledge(self, temp_dir: Path) -> None:
        """测试存储知识"""
        db_path = temp_dir / "semantic.db"
        sm = SemanticMemory(db_path)
        entry = KnowledgeEntry(topic="Python", content="Python is a language")
        stored = await sm.store_knowledge(entry)
        assert stored.id is not None
        await sm.close()

    @pytest.mark.asyncio
    async def test_query_knowledge(self, temp_dir: Path) -> None:
        """测试查询知识"""
        db_path = temp_dir / "semantic.db"
        sm = SemanticMemory(db_path)
        entry = KnowledgeEntry(topic="Python", content="Python programming language")
        await sm.store_knowledge(entry)
        results = await sm.query_knowledge("Python", limit=5)
        assert len(results) >= 1
        await sm.close()

    @pytest.mark.asyncio
    async def test_learn_code_pattern(self, temp_dir: Path) -> None:
        """测试学习代码模式"""
        db_path = temp_dir / "semantic.db"
        sm = SemanticMemory(db_path)
        pattern = CodePattern(pattern="def hello():", language="python")
        learned = await sm.learn_code_pattern(pattern)
        assert learned.id is not None
        await sm.close()

    @pytest.mark.asyncio
    async def test_get_code_patterns(self, temp_dir: Path) -> None:
        """测试获取代码模式"""
        db_path = temp_dir / "semantic.db"
        sm = SemanticMemory(db_path)
        pattern = CodePattern(pattern="class Test:", language="python")
        await sm.learn_code_pattern(pattern)
        patterns = await sm.get_code_patterns(language="python", limit=10)
        assert len(patterns) >= 1
        await sm.close()

    @pytest.mark.asyncio
    async def test_build_project_map(self, temp_dir: Path) -> None:
        """测试构建项目知识图谱"""
        (temp_dir / "main.py").write_text("print('hello')")
        (temp_dir / "README.md").write_text("# Project")
        db_path = temp_dir / "semantic.db"
        sm = SemanticMemory(db_path)
        pmap = await sm.build_project_map(temp_dir)
        assert pmap.project_path == str(temp_dir.resolve())
        await sm.close()


class TestMemoryManager:
    """MemoryManager 记忆管理器测试"""

    @pytest.mark.asyncio
    async def test_recall_working(self, temp_dir: Path) -> None:
        """测试检索工作记忆"""
        db_path = temp_dir / "memory.db"
        mm = MemoryManager(project_path=temp_dir, db_path=db_path)
        mm.working.store_variable("test_var", "test working memory")
        results = await mm.recall("test", memory_type=MemoryType.WORKING)
        assert len(results) >= 1
        await mm.close()

    @pytest.mark.asyncio
    async def test_store_working(self, temp_dir: Path) -> None:
        """测试存储工作记忆"""
        db_path = temp_dir / "memory.db"
        mm = MemoryManager(project_path=temp_dir, db_path=db_path)
        entry = MemoryEntry(type=MemoryType.WORKING, content="working content")
        stored = await mm.store(entry)
        assert stored.id is not None
        await mm.close()

    @pytest.mark.asyncio
    async def test_consolidate(self, temp_dir: Path) -> None:
        """测试记忆整合"""
        db_path = temp_dir / "memory.db"
        mm = MemoryManager(project_path=temp_dir, db_path=db_path)
        stats = await mm.consolidate()
        assert "cached_files" in stats
        assert "variables" in stats
        assert "tool_cache_cleared" in stats
        await mm.close()

    @pytest.mark.asyncio
    async def test_get_memory_stats(self, temp_dir: Path) -> None:
        """测试获取记忆统计"""
        db_path = temp_dir / "memory.db"
        mm = MemoryManager(project_path=temp_dir, db_path=db_path)
        stats = await mm.get_memory_stats()
        assert "working" in stats
        assert "episodic" in stats
        assert "semantic" in stats
        await mm.close()

    @pytest.mark.asyncio
    async def test_cache_file(self, temp_dir: Path) -> None:
        """测试缓存文件"""
        db_path = temp_dir / "memory.db"
        mm = MemoryManager(project_path=temp_dir, db_path=db_path)
        path = temp_dir / "cache.txt"
        path.write_text("cached")
        await mm.cache_file(path, "cached")
        content = await mm.get_cached_file(path)
        assert content == "cached"
        await mm.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_dir: Path) -> None:
        """测试上下文管理器"""
        db_path = temp_dir / "memory.db"
        async with MemoryManager(project_path=temp_dir, db_path=db_path) as mm:
            entry = MemoryEntry(type=MemoryType.WORKING, content="ctx test")
            await mm.store(entry)
