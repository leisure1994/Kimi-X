"""
Hindsight 知识图谱引擎

自动从每轮 user/assistant 对话中提取：
- 实体（Entity）：人名、项目名、技术栈、公司名等
- 事实（Fact）：做了什么、用了什么、结果如何
- 关系（Relation）：实体之间的关联
- 时间戳（Timestamp）：事件发生时间

建立知识图谱，在每次 LLM 调用前把相关记忆注入 system prompt，
实现真正的跨会话长期记忆。
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
class KnowledgeEntity:
    """知识图谱实体"""
    entity_id: str
    name: str
    entity_type: str  # person / project / tech / company / concept / file
    aliases: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    mention_count: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeRelation:
    """知识图谱关系"""
    relation_id: str
    source: str  # entity_id
    target: str  # entity_id
    relation_type: str  # uses / created_by / part_of / depends_on / related_to
    timestamp: str = ""
    evidence: list[str] = field(default_factory=list)  # 证据对话ID
    confidence: float = 1.0


@dataclass
class KnowledgeFact:
    """知识事实"""
    fact_id: str
    subject: str  # entity_id
    predicate: str  # 做了什么
    object_: str  # 结果/对象
    timestamp: str = ""
    source_conv_id: str = ""
    confidence: float = 1.0


class HindsightEngine:
    """Hindsight 知识图谱引擎

    自动提取对话中的实体、关系、事实，构建可查询的知识图谱。
    支持：
    - 增量更新（每轮对话自动提取）
    - 实体消歧（别名合并）
    - 关系演化（时间序列关系）
    - 上下文注入（召回相关记忆）
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else Path.home() / ".kimix" / "hindsight"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.entities: dict[str, KnowledgeEntity] = {}
        self.relations: list[KnowledgeRelation] = []
        self.facts: list[KnowledgeFact] = []

        self._load_all()

    # ── 核心：从对话提取 ──

    def extract_from_message(self, role: str, content: str, conv_id: str = "") -> dict[str, Any]:
        """从单条消息中提取实体、关系、事实

        Returns:
            dict with keys: entities, relations, facts
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        extracted = {"entities": [], "relations": [], "facts": []}

        # 1. 实体提取（基于规则 + 启发式）
        entities = self._extract_entities(content)
        for ent_name, ent_type in entities:
            entity = self._get_or_create_entity(ent_name, ent_type, timestamp)
            entity.last_seen = timestamp
            entity.mention_count += 1
            if conv_id:
                entity.attributes.setdefault("mentioned_in", []).append(conv_id)
            extracted["entities"].append(entity.entity_id)

        # 2. 关系提取
        relations = self._extract_relations(content, entities)
        for src, rel_type, tgt in relations:
            src_id = self._get_or_create_entity(src, "unknown", timestamp).entity_id
            tgt_id = self._get_or_create_entity(tgt, "unknown", timestamp).entity_id
            relation = KnowledgeRelation(
                relation_id=self._hash(f"{src_id}:{rel_type}:{tgt_id}:{conv_id}"),
                source=src_id,
                target=tgt_id,
                relation_type=rel_type,
                timestamp=timestamp,
                evidence=[conv_id] if conv_id else [],
            )
            self.relations.append(relation)
            extracted["relations"].append(relation.relation_id)

        # 3. 事实提取
        facts = self._extract_facts(content, entities, conv_id)
        for fact in facts:
            self.facts.append(fact)
            extracted["facts"].append(fact.fact_id)

        self._save_all()
        return extracted

    # ── 查询接口 ──

    def query_entity(self, name: str) -> KnowledgeEntity | None:
        """查询实体"""
        for entity in self.entities.values():
            if entity.name.lower() == name.lower() or name.lower() in [a.lower() for a in entity.aliases]:
                return entity
        return None

    def query_relations(self, entity_name: str) -> list[KnowledgeRelation]:
        """查询与某实体相关的关系"""
        entity = self.query_entity(entity_name)
        if not entity:
            return []
        return [r for r in self.relations if r.source == entity.entity_id or r.target == entity.entity_id]

    def query_facts(self, entity_name: str) -> list[KnowledgeFact]:
        """查询与某实体相关的事实"""
        entity = self.query_entity(entity_name)
        if not entity:
            return []
        return [f for f in self.facts if f.subject == entity.entity_id]

    def get_relevant_context(self, query: str, max_items: int = 10) -> dict[str, Any]:
        """获取与查询相关的知识上下文（用于注入 system prompt）"""
        query_words = set(query.lower().split())

        # 召回相关实体
        relevant_entities: list[KnowledgeEntity] = []
        for entity in self.entities.values():
            entity_words = set(entity.name.lower().split()) | set(a.lower() for a in entity.aliases)
            overlap = len(query_words & entity_words) / max(len(query_words | entity_words), 1)
            if overlap > 0.2 or any(w in query.lower() for w in entity_words):
                relevant_entities.append(entity)

        # 召回相关关系
        entity_ids = {e.entity_id for e in relevant_entities}
        relevant_relations = [r for r in self.relations if r.source in entity_ids or r.target in entity_ids]

        # 召回相关事实
        relevant_facts = [f for f in self.facts if f.subject in entity_ids]

        return {
            "entities": [
                {
                    "name": e.name,
                    "type": e.entity_type,
                    "mentions": e.mention_count,
                    "attributes": e.attributes,
                }
                for e in relevant_entities[:max_items]
            ],
            "relations": [
                {
                    "source": self.entities.get(r.source, KnowledgeEntity(entity_id=r.source, name=r.source, entity_type="unknown")).name,
                    "type": r.relation_type,
                    "target": self.entities.get(r.target, KnowledgeEntity(entity_id=r.target, name=r.target, entity_type="unknown")).name,
                }
                for r in relevant_relations[:max_items]
            ],
            "facts": [
                {
                    "subject": self.entities.get(f.subject, KnowledgeEntity(entity_id=f.subject, name=f.subject, entity_type="unknown")).name,
                    "predicate": f.predicate,
                    "object": f.object_,
                }
                for f in relevant_facts[:max_items]
            ],
        }

    # ── 内部提取逻辑 ──

    def _extract_entities(self, content: str) -> list[tuple[str, str]]:
        """提取实体（规则+启发式）"""
        entities: list[tuple[str, str]] = []

        # 技术栈检测
        tech_keywords = [
            "python", "javascript", "typescript", "rust", "go", "java", "c++", "c#",
            "react", "vue", "angular", "flutter", "django", "flask", "fastapi",
            "docker", "kubernetes", "terraform", "ansible", "nginx", "redis",
            "postgresql", "mysql", "mongodb", "elasticsearch", "kafka",
            "aws", "gcp", "azure", "aliyun", "tencent cloud",
            "git", "github", "gitlab", "jenkins", "ci/cd",
            "llm", "gpt", "claude", "kimi", "deepseek", "qwen",
            "api", "rest", "graphql", "grpc", "websocket",
        ]
        for tech in tech_keywords:
            if re.search(rf"\b{re.escape(tech)}\b", content, re.IGNORECASE):
                entities.append((tech, "tech"))

        # 文件名检测
        file_pattern = r"[\w\-]+\.(py|js|ts|rs|go|java|cpp|h|yaml|yml|json|md|txt|sh|dockerfile)"
        for match in re.finditer(file_pattern, content, re.IGNORECASE):
            entities.append((match.group(0), "file"))

        # URL/域名检测
        url_pattern = r"https?://([^/\s]+)"
        for match in re.finditer(url_pattern, content):
            entities.append((match.group(1), "domain"))

        # 版本号检测
        version_pattern = r"v?\d+\.\d+(?:\.\d+)?"
        for match in re.finditer(version_pattern, content):
            entities.append((match.group(0), "version"))

        return entities

    def _extract_relations(self, content: str, entities: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
        """提取关系"""
        relations: list[tuple[str, str, str]] = []

        # 使用关系
        use_patterns = [
            r"使用\s+([\w\-]+)",
            r"用\s+([\w\-]+)",
            r"基于\s+([\w\-]+)",
            r"built\s+(?:on|with)\s+([\w\-]+)",
            r"using\s+([\w\-]+)",
        ]
        for pattern in use_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                target = match.group(1)
                if any(e[0] == target for e in entities):
                    relations.append(("user", "uses", target))

        # 创建关系
        create_patterns = [
            r"创建\s+([\w\-]+)",
            r"创建\s+了\s+([\w\-]+)",
            r"created\s+([\w\-]+)",
            r"写了\s+([\w\-]+)",
            r"实现\s+([\w\-]+)",
        ]
        for pattern in create_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                target = match.group(1)
                relations.append(("user", "created", target))

        # 修复关系
        fix_patterns = [
            r"修复\s+([\w\-]+)",
            r"修\s+([\w\-]+)",
            r"fixed\s+([\w\-]+)",
            r"解决\s+([\w\-]+)",
        ]
        for pattern in fix_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                target = match.group(1)
                relations.append(("user", "fixed", target))

        return relations

    def _extract_facts(self, content: str, entities: list[tuple[str, str]], conv_id: str) -> list[KnowledgeFact]:
        """提取事实"""
        facts: list[KnowledgeFact] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        # 偏好事实
        pref_patterns = [
            (r"喜欢\s*(.+?)[。，]", "prefers"),
            (r"偏好\s*(.+?)[。，]", "prefers"),
            (r"习惯\s*(.+?)[。，]", "habit"),
            (r"讨厌\s*(.+?)[。，]", "dislikes"),
        ]
        for pattern, predicate in pref_patterns:
            for match in re.finditer(pattern, content):
                object_ = match.group(1).strip()
                facts.append(KnowledgeFact(
                    fact_id=self._hash(f"{conv_id}:user:{predicate}:{object_}"),
                    subject="user",
                    predicate=predicate,
                    object_=object_,
                    timestamp=timestamp,
                    source_conv_id=conv_id,
                ))

        # 错误事实
        if "错误" in content or "error" in content.lower() or "bug" in content.lower():
            facts.append(KnowledgeFact(
                fact_id=self._hash(f"{conv_id}:encountered:error"),
                subject="session",
                predicate="encountered",
                object_="error",
                timestamp=timestamp,
                source_conv_id=conv_id,
            ))

        # 成功事实
        success_patterns = [
            (r"(?:成功|完成)\s*(.+?)[。，]", "completed"),
            (r"done\s*(.+?)[.，]", "completed"),
        ]
        for pattern, predicate in success_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                object_ = match.group(1).strip() if match.lastindex else "task"
                facts.append(KnowledgeFact(
                    fact_id=self._hash(f"{conv_id}:user:{predicate}:{object_}"),
                    subject="user",
                    predicate=predicate,
                    object_=object_,
                    timestamp=timestamp,
                    source_conv_id=conv_id,
                ))

        return facts

    def _get_or_create_entity(self, name: str, entity_type: str, timestamp: str) -> KnowledgeEntity:
        """获取或创建实体"""
        entity_id = self._hash(f"{name}:{entity_type}")
        if entity_id in self.entities:
            return self.entities[entity_id]

        entity = KnowledgeEntity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            first_seen=timestamp,
            last_seen=timestamp,
            mention_count=1,
        )
        self.entities[entity_id] = entity
        return entity

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # ── 持久化 ──

    def _entity_path(self) -> Path:
        return self.storage_path / "entities.json"

    def _relation_path(self) -> Path:
        return self.storage_path / "relations.jsonl"

    def _fact_path(self) -> Path:
        return self.storage_path / "facts.jsonl"

    def _save_all(self) -> None:
        with open(self._entity_path(), "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in self.entities.items()}, f, ensure_ascii=False, indent=2)

        with open(self._relation_path(), "w", encoding="utf-8") as f:
            for r in self.relations:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

        with open(self._fact_path(), "w", encoding="utf-8") as f:
            for fa in self.facts:
                f.write(json.dumps(asdict(fa), ensure_ascii=False) + "\n")

    def _load_all(self) -> None:
        if self._entity_path().exists():
            with open(self._entity_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                self.entities = {k: KnowledgeEntity(**v) for k, v in data.items()}

        if self._relation_path().exists():
            with open(self._relation_path(), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.relations.append(KnowledgeRelation(**json.loads(line)))

        if self._fact_path().exists():
            with open(self._fact_path(), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.facts.append(KnowledgeFact(**json.loads(line)))

    def get_stats(self) -> dict[str, Any]:
        return {
            "entities": len(self.entities),
            "relations": len(self.relations),
            "facts": len(self.facts),
        }
