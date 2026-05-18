"""
四层长期记忆系统 (L0-L3 Memory Hierarchy)

基于 TencentDB Agent Memory 架构，实现：
- L0: 原始对话 (Conversation) — 完整保留原始对话
- L1: 原子事实 (Atom) — 关键信息提取、事实抽取/去重
- L2: 场景聚类 (Scenario) — 结构化总结、场景体/阶段结论
- L3: 用户画像 (Persona) — 稳定偏好/SOP、长期记忆核心

配合符号化短期记忆，实现跨会话持续理解。
Token 压缩率最高可达 61%。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class L0Conversation:
    """L0: 原始对话记录"""
    conv_id: str
    timestamp: str
    role: str  # user / assistant / system
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class L1Atom:
    """L1: 原子事实 — 提取的实体、事实、关系"""
    atom_id: str
    timestamp: str
    source_conv_id: str  # 关联的 L0 对话 ID
    entity_type: str  # person / project / tech / preference / fact / error
    entity_name: str
    relation: str  # uses / prefers / knows / fixed / created
    target: str  # 关系对象
    confidence: float = 1.0  # 置信度 0-1
    count: int = 1  # 重复次数


@dataclass
class L2Scenario:
    """L2: 场景聚类 — 结构化总结"""
    scenario_id: str
    timestamp: str
    category: str  # coding / debugging / planning / review / deployment
    summary: str  # 场景摘要
    key_actions: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    related_atoms: list[str] = field(default_factory=list)  # 关联的 L1 atom_id
    pattern_score: float = 0.0  # 模式成熟度


@dataclass
class L3Persona:
    """L3: 用户画像/Agent画像 — 稳定偏好和 SOP"""
    persona_id: str
    updated_at: str
    user_preferences: dict[str, Any] = field(default_factory=dict)  # 用户偏好
    agent_sop: dict[str, Any] = field(default_factory=dict)  # Agent 标准操作程序
    tech_stack: list[str] = field(default_factory=list)  # 技术栈
    communication_style: dict[str, Any] = field(default_factory=dict)  # 沟通风格
    project_context: dict[str, Any] = field(default_factory=dict)  # 项目上下文


class HierarchicalMemory:
    """四层分层记忆系统

    召回策略：
    - 召回时只带需要的记忆
    - L1 进用户消息（具体事实）
    - L2/L3 进系统上下文（场景知识 + 画像）
    - 必要时回溯 L0 原文

    配合符号化短期记忆，实现跨会话持续理解。
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else Path.home() / ".kimix" / "memory"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 各层存储
        self.l0_conversations: list[L0Conversation] = []
        self.l1_atoms: list[L1Atom] = []
        self.l2_scenarios: list[L2Scenario] = []
        self.l3_persona: L3Persona | None = None

        # 索引
        self._atom_entity_index: dict[str, list[int]] = {}  # entity_name -> atom indices
        self._scenario_category_index: dict[str, list[int]] = {}  # category -> scenario indices

        self._load_all()

    # ── L0: 原始对话 ──

    def record_conversation(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
        """记录原始对话，返回 conv_id"""
        conv_id = self._hash(f"{role}:{content}:{datetime.now(timezone.utc).isoformat()}")
        conv = L0Conversation(
            conv_id=conv_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.l0_conversations.append(conv)
        self._save_l0()
        return conv_id

    def get_conversation(self, conv_id: str) -> L0Conversation | None:
        """获取原始对话"""
        for conv in self.l0_conversations:
            if conv.conv_id == conv_id:
                return conv
        return None

    # ── L1: 原子事实（自动/手动提取）──

    def extract_atoms(self, conv_id: str, content: str) -> list[L1Atom]:
        """从对话内容自动提取原子事实（基于规则+启发式）"""
        atoms: list[L1Atom] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        # 技术栈检测
        tech_patterns = [
            (r"使用\s+(\w+)", "uses", "tech"),
            (r"用\s+(\w+)", "uses", "tech"),
            (r"基于\s+(\w+)", "based_on", "tech"),
            (r"框架[:：]\s*(\w+)", "uses", "tech"),
            (r"语言[:：]\s*(\w+)", "uses", "lang"),
        ]
        for pattern, relation, entity_type in tech_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                entity = match.group(1)
                atoms.append(L1Atom(
                    atom_id=self._hash(f"{conv_id}:{entity}:{relation}"),
                    timestamp=timestamp,
                    source_conv_id=conv_id,
                    entity_type=entity_type,
                    entity_name=entity,
                    relation=relation,
                    target="project",
                ))

        # 偏好检测
        pref_patterns = [
            (r"喜欢\s*(.+?)[。，]", "prefers", "preference"),
            (r"偏好\s*(.+?)[。，]", "prefers", "preference"),
            (r"习惯\s*(.+?)[。，]", "habit", "preference"),
            (r"讨厌\s*(.+?)[。，]", "dislikes", "preference"),
        ]
        for pattern, relation, entity_type in pref_patterns:
            for match in re.finditer(pattern, content):
                entity = match.group(1).strip()
                if len(entity) > 1:
                    atoms.append(L1Atom(
                        atom_id=self._hash(f"{conv_id}:{entity}:{relation}"),
                        timestamp=timestamp,
                        source_conv_id=conv_id,
                        entity_type=entity_type,
                        entity_name=entity,
                        relation=relation,
                        target="user",
                    ))

        # 错误/修复检测
        if "错误" in content or "error" in content.lower() or "bug" in content.lower():
            atoms.append(L1Atom(
                atom_id=self._hash(f"{conv_id}:error:encountered"),
                timestamp=timestamp,
                source_conv_id=conv_id,
                entity_type="error",
                entity_name="error_occurred",
                relation="encountered",
                target="session",
            ))

        # 去重并保存
        for atom in atoms:
            self._add_atom(atom)

        self._save_l1()
        return atoms

    def add_atom(self, entity_type: str, entity_name: str, relation: str, target: str,
                 confidence: float = 1.0, source_conv_id: str = "") -> str:
        """手动添加原子事实"""
        atom = L1Atom(
            atom_id=self._hash(f"{source_conv_id}:{entity_name}:{relation}:{target}"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_conv_id=source_conv_id,
            entity_type=entity_type,
            entity_name=entity_name,
            relation=relation,
            target=target,
            confidence=confidence,
        )
        self._add_atom(atom)
        self._save_l1()
        return atom.atom_id

    def query_atoms(self, entity_name: str | None = None, entity_type: str | None = None,
                    relation: str | None = None, limit: int = 10) -> list[L1Atom]:
        """查询原子事实"""
        results = self.l1_atoms[:]
        if entity_name:
            results = [a for a in results if a.entity_name == entity_name]
        if entity_type:
            results = [a for a in results if a.entity_type == entity_type]
        if relation:
            results = [a for a in results if a.relation == relation]
        return results[:limit]

    def get_knowledge_graph(self) -> dict[str, list[dict]]:
        """获取知识图谱（实体-关系-实体）"""
        nodes: set[str] = set()
        edges: list[dict] = []
        for atom in self.l1_atoms:
            nodes.add(atom.entity_name)
            nodes.add(atom.target)
            edges.append({
                "source": atom.entity_name,
                "relation": atom.relation,
                "target": atom.target,
                "type": atom.entity_type,
                "confidence": atom.confidence,
            })
        return {
            "nodes": [{"id": n, "label": n} for n in nodes],
            "edges": edges,
        }

    # ── L2: 场景聚类 ──

    def record_scenario(self, category: str, summary: str, key_actions: list[str],
                        outcomes: list[str], related_atoms: list[str] | None = None) -> str:
        """记录场景"""
        scenario_id = self._hash(f"{category}:{summary}:{datetime.now(timezone.utc).isoformat()}")
        scenario = L2Scenario(
            scenario_id=scenario_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            summary=summary,
            key_actions=key_actions,
            outcomes=outcomes,
            related_atoms=related_atoms or [],
        )
        self.l2_scenarios.append(scenario)
        self._scenario_category_index.setdefault(category, []).append(len(self.l2_scenarios) - 1)
        self._save_l2()
        return scenario_id

    def get_scenarios(self, category: str | None = None, limit: int = 5) -> list[L2Scenario]:
        """获取场景"""
        if category:
            indices = self._scenario_category_index.get(category, [])
            return [self.l2_scenarios[i] for i in indices[-limit:]]
        return self.l2_scenarios[-limit:]

    # ── L3: 用户画像 ──

    def update_persona(self, **kwargs: Any) -> None:
        """更新用户画像"""
        if self.l3_persona is None:
            self.l3_persona = L3Persona(
                persona_id=self._hash("persona"),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

        for key, value in kwargs.items():
            if hasattr(self.l3_persona, key):
                current = getattr(self.l3_persona, key)
                if isinstance(current, dict) and isinstance(value, dict):
                    current.update(value)
                elif isinstance(current, list) and isinstance(value, list):
                    # 去重追加
                    for item in value:
                        if item not in current:
                            current.append(item)
                else:
                    setattr(self.l3_persona, key, value)

        self.l3_persona.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_l3()

    def get_persona(self) -> dict[str, Any] | None:
        """获取用户画像"""
        if self.l3_persona is None:
            return None
        return {
            "user_preferences": self.l3_persona.user_preferences,
            "agent_sop": self.l3_persona.agent_sop,
            "tech_stack": self.l3_persona.tech_stack,
            "communication_style": self.l3_persona.communication_style,
            "project_context": self.l3_persona.project_context,
            "updated_at": self.l3_persona.updated_at,
        }

    # ── 召回策略 ──

    def recall_for_context(self, query: str, max_tokens: int = 2000) -> dict[str, Any]:
        """智能召回记忆用于上下文

        策略：
        - L1 原子事实 → 用户消息（具体事实）
        - L2 场景 → 系统上下文（工作流知识）
        - L3 画像 → 系统上下文（稳定偏好）
        - L0 仅在需要时回溯
        """
        query_words = set(query.lower().split())

        # 召回相关的 L1 原子事实
        relevant_atoms: list[L1Atom] = []
        for atom in self.l1_atoms:
            atom_words = set(f"{atom.entity_name} {atom.relation} {atom.target}".lower().split())
            overlap = len(query_words & atom_words) / max(len(query_words | atom_words), 1)
            if overlap > 0.3:
                relevant_atoms.append(atom)

        # 召回相关的 L2 场景
        relevant_scenarios: list[L2Scenario] = []
        for scenario in self.l2_scenarios:
            scenario_words = set(scenario.summary.lower().split())
            overlap = len(query_words & scenario_words) / max(len(query_words | scenario_words), 1)
            if overlap > 0.3:
                relevant_scenarios.append(scenario)

        # 构建召回结果
        context = {
            "facts": [f"{a.entity_name} {a.relation} {a.target}" for a in relevant_atoms[:10]],
            "scenarios": [s.summary for s in relevant_scenarios[:3]],
            "persona": self.get_persona(),
        }

        return context

    # ── 内部 ──

    def _add_atom(self, atom: L1Atom) -> None:
        """添加原子事实（自动去重）"""
        for existing in self.l1_atoms:
            if existing.atom_id == atom.atom_id:
                existing.count += 1
                existing.confidence = max(existing.confidence, atom.confidence)
                existing.timestamp = atom.timestamp
                return
        self.l1_atoms.append(atom)
        self._atom_entity_index.setdefault(atom.entity_name, []).append(len(self.l1_atoms) - 1)

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # ── 持久化 ──

    def _l0_path(self) -> Path:
        return self.storage_dir / "l0_conversations.jsonl"

    def _l1_path(self) -> Path:
        return self.storage_dir / "l1_atoms.jsonl"

    def _l2_path(self) -> Path:
        return self.storage_dir / "l2_scenarios.jsonl"

    def _l3_path(self) -> Path:
        return self.storage_dir / "l3_persona.json"

    def _save_l0(self) -> None:
        with open(self._l0_path(), "w", encoding="utf-8") as f:
            for conv in self.l0_conversations:
                f.write(json.dumps(asdict(conv), ensure_ascii=False) + "\n")

    def _save_l1(self) -> None:
        with open(self._l1_path(), "w", encoding="utf-8") as f:
            for atom in self.l1_atoms:
                f.write(json.dumps(asdict(atom), ensure_ascii=False) + "\n")

    def _save_l2(self) -> None:
        with open(self._l2_path(), "w", encoding="utf-8") as f:
            for scenario in self.l2_scenarios:
                f.write(json.dumps(asdict(scenario), ensure_ascii=False) + "\n")

    def _save_l3(self) -> None:
        if self.l3_persona:
            with open(self._l3_path(), "w", encoding="utf-8") as f:
                json.dump(asdict(self.l3_persona), f, ensure_ascii=False, indent=2)

    def _load_all(self) -> None:
        if self._l0_path().exists():
            with open(self._l0_path(), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.l0_conversations.append(L0Conversation(**json.loads(line)))

        if self._l1_path().exists():
            with open(self._l1_path(), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.l1_atoms.append(L1Atom(**json.loads(line)))
            for i, atom in enumerate(self.l1_atoms):
                self._atom_entity_index.setdefault(atom.entity_name, []).append(i)

        if self._l2_path().exists():
            with open(self._l2_path(), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.l2_scenarios.append(L2Scenario(**json.loads(line)))
            for i, scenario in enumerate(self.l2_scenarios):
                self._scenario_category_index.setdefault(scenario.category, []).append(i)

        if self._l3_path().exists():
            with open(self._l3_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                self.l3_persona = L3Persona(**data)

    def get_stats(self) -> dict[str, Any]:
        """记忆系统统计"""
        return {
            "l0_conversations": len(self.l0_conversations),
            "l1_atoms": len(self.l1_atoms),
            "l2_scenarios": len(self.l2_scenarios),
            "l3_persona": self.l3_persona is not None,
            "compression_ratio": self._estimate_compression(),
        }

    def _estimate_compression(self) -> float:
        """估算压缩率"""
        if not self.l0_conversations or not self.l1_atoms:
            return 0.0
        l0_tokens = sum(len(c.content) for c in self.l0_conversations)
        l1_tokens = sum(len(a.entity_name) + len(a.relation) + len(a.target) for a in self.l1_atoms)
        if l0_tokens == 0:
            return 0.0
        return round(1 - (l1_tokens / l0_tokens), 3)
