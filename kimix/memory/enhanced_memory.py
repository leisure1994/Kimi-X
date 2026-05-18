"""
增强型记忆系统 — 集成四层记忆 + Hindsight 知识图谱

整合 HierarchicalMemory (L0-L3) 和 HindsightEngine，
提供统一的记忆接口给 Agent 使用。
"""

from __future__ import annotations

from typing import Any

from .experience import ExperienceMemory
from .hierarchical_memory import HierarchicalMemory
from .hindsight import HindsightEngine
from .memory_bank import MemoryBank


class EnhancedMemorySystem:
    """增强型记忆系统

    整合四层记忆 + 经验记忆 + 知识图谱 + 记忆银行，
    为 Agent 提供完整的记忆能力。

    使用方式:
        memory = EnhancedMemorySystem()
        
        # 记录对话
        memory.record_conversation("user", "帮我写一个 Python 爬虫")
        
        # 自动提取知识
        memory.extract_knowledge("user", "帮我写一个 Python 爬虫，要爬取豆瓣电影 Top250")
        
        # 获取上下文
        context = memory.get_context_for("Python 爬虫")
        print(context)
    """

    def __init__(self, storage_dir: str | None = None) -> None:
        """
        Args:
            storage_dir: 存储目录，默认 ~/.kimix/memory
        """
        self.hierarchical = HierarchicalMemory(storage_dir)
        self.hindsight = HindsightEngine(storage_dir)
        self.experience = ExperienceMemory()
        self.memory_bank = MemoryBank()

    # ── 对话记录 ──

    def record_conversation(self, role: str, content: str, 
                           metadata: dict[str, Any] | None = None) -> str:
        """记录对话并自动提取知识"""
        # L0: 记录原始对话
        conv_id = self.hierarchical.record_conversation(role, content, metadata)
        
        # 自动提取知识（Hindsight）
        self.hindsight.extract_from_message(role, content, conv_id)
        
        # L1: 提取原子事实
        self.hierarchical.extract_atoms(conv_id, content)
        
        return conv_id

    # ── 知识提取 ──

    def extract_knowledge(self, role: str, content: str) -> dict[str, Any]:
        """从内容中提取知识"""
        conv_id = self.record_conversation(role, content)
        
        # 获取提取结果
        hindsight_result = self.hindsight.extract_from_message(role, content, conv_id)
        
        return {
            "conv_id": conv_id,
            "entities": hindsight_result.get("entities", []),
            "relations": hindsight_result.get("relations", []),
            "facts": hindsight_result.get("facts", []),
        }

    # ── 场景记录 ──

    def record_scenario(self, category: str, summary: str, 
                       key_actions: list[str], outcomes: list[str]) -> str:
        """记录场景（L2）"""
        return self.hierarchical.record_scenario(
            category=category,
            summary=summary,
            key_actions=key_actions,
            outcomes=outcomes,
        )

    # ── 画像更新 ──

    def update_persona(self, **kwargs: Any) -> None:
        """更新用户画像（L3）"""
        self.hierarchical.update_persona(**kwargs)

    # ── 上下文召回 ──

    def get_context_for(self, query: str, max_tokens: int = 2000) -> dict[str, Any]:
        """获取与查询相关的上下文"""
        # 分层记忆召回
        hierarchical_context = self.hierarchical.recall_for_context(query, max_tokens)
        
        # Hindsight 知识图谱召回
        hindsight_context = self.hindsight.get_relevant_context(query)
        
        # 合并
        return {
            "query": query,
            "facts": hierarchical_context.get("facts", []),
            "scenarios": hierarchical_context.get("scenarios", []),
            "persona": hierarchical_context.get("persona"),
            "entities": hindsight_context.get("entities", []),
            "relations": hindsight_context.get("relations", []),
            "knowledge_facts": hindsight_context.get("facts", []),
        }

    # ── 经验记录 ──

    def record_experience(self, category: str, task_signature: str, 
                         event_type: str, detail: dict[str, Any], 
                         outcome: str, effectiveness: float) -> None:
        """记录经验"""
        self.experience._add(self.experience._create_record(
            category=category,
            task_signature=task_signature,
            event_type=event_type,
            detail=detail,
            outcome=outcome,
            effectiveness=effectiveness,
        ))

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        """记忆系统统计"""
        return {
            "hierarchical": self.hierarchical.get_stats(),
            "hindsight": self.hindsight.get_stats(),
            "experience": self.experience.get_stats(),
            "memory_bank": self.memory_bank.get_stats() if hasattr(self.memory_bank, 'get_stats') else {},
        }

    # ── 知识图谱 ──

    def get_knowledge_graph(self) -> dict[str, Any]:
        """获取知识图谱"""
        return self.hindsight.get_relevant_context("all", max_items=1000)
