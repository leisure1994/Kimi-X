"""
经验积累系统模块 (Experience Memory)

Agent 的「长期记忆」专用层，专门记录：
- 预判命中记录（哪些问题被提前发现）
- 修复成功/失败经验（什么错误用什么策略最有效）
- 模式切换历史（什么任务类型适合什么模式）
- 性能基线（不同模型/任务的 latency、token 消耗）

经验库可被预判系统、自我修复引擎、模式路由器读取，
实现「越用越聪明」的进化效果。

持久化: JSON 行文件，每行一条经验记录，支持增量追加。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ExperienceRecord:
    """单条经验记录"""
    record_id: str                           # 唯一 ID (hash)
    timestamp: str                           # ISO 格式 UTC 时间
    category: str                          # preflight / healing / routing / performance
    task_signature: str                    # 任务特征摘要（用于相似匹配）
    event_type: str                        # 事件类型：warning / error / success / pattern
    detail: dict[str, Any] = field(default_factory=dict)  # 详情数据
    outcome: str = ""                      # 结果描述
    effectiveness: float = 0.0             # 有效性评分 (0-1)
    count: int = 1                         # 重复次数（相似经验合并）


class ExperienceMemory:
    """经验积累与检索引擎

    提供：
    - 写入经验（自动去重合并）
    - 相似经验检索（基于 task_signature 模糊匹配）
    - 最佳策略推荐（基于历史修复成功率）
    - 性能基线查询（同类任务的历史 latency/token）
    - 持久化（增量追加到 JSONL）
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        auto_save: bool = True,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self.auto_save = auto_save
        self._records: list[ExperienceRecord] = []
        self._signature_index: dict[str, list[int]] = {}  # signature -> record indices
        self._category_index: dict[str, list[int]] = {}      # category -> record indices

        if self.storage_path and self.storage_path.exists():
            self._load()

    # ── 写入 ──

    def record_preflight(
        self,
        task_signature: str,
        issue_category: str,
        was_prevented: bool,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """记录预判命中/未命中"""
        self._add(ExperienceRecord(
            record_id=self._hash(f"{task_signature}:{issue_category}"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category="preflight",
            task_signature=task_signature,
            event_type="prevented" if was_prevented else "missed",
            detail=detail or {},
            outcome="预判成功" if was_prevented else "预判未命中",
            effectiveness=1.0 if was_prevented else 0.0,
        ))

    def record_fix(
        self,
        error_signature: str,
        strategy: str,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> None:
        """记录修复经验"""
        self._add(ExperienceRecord(
            record_id=self._hash(f"{error_signature}:{strategy}"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category="healing",
            task_signature=error_signature,
            event_type="healed" if success else "failed",
            detail={"strategy": strategy, **(context or {})},
            outcome="修复成功" if success else "修复失败",
            effectiveness=1.0 if success else 0.0,
        ))

    def record_routing(
        self,
        task_signature: str,
        chosen_mode: str,
        satisfaction: float,  # 用户反馈或自我评估
        detail: dict[str, Any] | None = None,
    ) -> None:
        """记录模式路由选择效果"""
        self._add(ExperienceRecord(
            record_id=self._hash(f"{task_signature}:{chosen_mode}"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category="routing",
            task_signature=task_signature,
            event_type="routing_feedback",
            detail={"chosen_mode": chosen_mode, **(detail or {})},
            outcome=f"模式 {chosen_mode}",
            effectiveness=satisfaction,
        ))

    def record_performance(
        self,
        task_signature: str,
        model: str,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """记录性能基线"""
        self._add(ExperienceRecord(
            record_id=self._hash(
                f"{task_signature}:{model}:{datetime.now(timezone.utc).isoformat()}"
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category="performance",
            task_signature=task_signature,
            event_type="performance",
            detail={
                "model": model,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            },
            outcome=f"{latency_ms:.0f}ms, ${cost_usd:.4f}",
            effectiveness=1.0,  # 性能记录默认可信
        ))

    # ── 检索 ──

    def has_similar(self, task_signature: str, threshold: float = 0.7) -> bool:
        """是否存在相似的历史经验"""
        matches = self._search_similar(task_signature, threshold)
        return len(matches) > 0

    def get_similar(
        self,
        task_signature: str,
        category: str | None = None,
        threshold: float = 0.7,
        limit: int = 5,
    ) -> list[ExperienceRecord]:
        """检索相似经验"""
        records = self._search_similar(task_signature, threshold)
        if category:
            records = [r for r in records if r.category == category]
        # 按有效性排序
        records.sort(key=lambda r: r.effectiveness * r.count, reverse=True)
        return records[:limit]

    def get_best_strategy(self, error_signature: str) -> str | None:
        """获取最佳修复策略（基于历史成功率）"""
        records = self._search_similar(error_signature, threshold=0.5)
        healing_records = [r for r in records if r.category == "healing"]
        if not healing_records:
            return None

        # 按策略分组统计成功率
        strategy_stats: dict[str, list[float]] = {}
        for r in healing_records:
            strategy = r.detail.get("strategy", "unknown")
            if strategy not in strategy_stats:
                strategy_stats[strategy] = []
            strategy_stats[strategy].append(r.effectiveness)

        # 加权平均（考虑重复次数）
        best_strategy = None
        best_score = -1.0
        for strategy, scores in strategy_stats.items():
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best_strategy = strategy

        return best_strategy

    def get_performance_baseline(
        self,
        task_signature: str,
        model: str | None = None,
    ) -> dict[str, float] | None:
        """获取性能基线（历史同类任务的平均值）"""
        records = self._search_similar(task_signature, threshold=0.6)
        perf_records = [r for r in records if r.category == "performance"]
        if model:
            perf_records = [r for r in perf_records if r.detail.get("model") == model]

        if not perf_records:
            return None

        return {
            "avg_latency_ms": sum(r.detail["latency_ms"] for r in perf_records) / len(perf_records),
            "avg_input_tokens": sum(r.detail["input_tokens"] for r in perf_records) / len(perf_records),
            "avg_output_tokens": sum(r.detail["output_tokens"] for r in perf_records) / len(perf_records),
            "avg_cost_usd": sum(r.detail["cost_usd"] for r in perf_records) / len(perf_records),
            "sample_count": len(perf_records),
        }

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        """经验库统计"""
        if not self._records:
            return {"total": 0, "categories": {}, "effectiveness": 0.0}

        categories: dict[str, int] = {}
        for r in self._records:
            categories[r.category] = categories.get(r.category, 0) + r.count

        avg_effectiveness = sum(r.effectiveness * r.count for r in self._records) / sum(
            r.count for r in self._records
        )

        return {
            "total": sum(r.count for r in self._records),
            "categories": categories,
            "effectiveness": round(avg_effectiveness, 3),
        }

    # ── 内部 ──

    def _add(self, record: ExperienceRecord) -> None:
        """添加记录（自动合并重复）"""
        # 查找相同 record_id（相同任务+相同策略/模式）
        for i, existing in enumerate(self._records):
            if existing.record_id == record.record_id:
                # 合并：更新有效性为加权平均，增加计数
                total_weight = existing.count + record.count
                existing.effectiveness = (
                    existing.effectiveness * existing.count
                    + record.effectiveness * record.count
                ) / total_weight
                existing.count = total_weight
                existing.timestamp = record.timestamp  # 更新时间
                if record.outcome:
                    existing.outcome = record.outcome
                return

        # 新记录
        idx = len(self._records)
        self._records.append(record)
        self._signature_index.setdefault(record.task_signature, []).append(idx)
        self._category_index.setdefault(record.category, []).append(idx)

        if self.auto_save and self.storage_path:
            self._append_one(record)

    def _search_similar(
        self,
        task_signature: str,
        threshold: float = 0.7,
    ) -> list[ExperienceRecord]:
        """基于签名相似度搜索（简单前缀匹配 + 关键词重叠）"""
        results: list[ExperienceRecord] = []
        query_words = set(task_signature.lower().split())

        for record in self._records:
            # 完全匹配
            if record.task_signature == task_signature:
                results.append(record)
                continue

            # 关键词重叠率
            record_words = set(record.task_signature.lower().split())
            if not query_words or not record_words:
                continue

            overlap = len(query_words & record_words) / len(query_words | record_words)
            if overlap >= threshold:
                results.append(record)

        return results

    def _hash(self, content: str) -> str:
        """生成内容哈希"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # ── 持久化 ──

    def _load(self) -> None:
        """从 JSONL 加载"""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        record = ExperienceRecord(**data)
                        self._records.append(record)
                    except (json.JSONDecodeError, TypeError):
                        continue
            # 重建索引
            for i, r in enumerate(self._records):
                self._signature_index.setdefault(r.task_signature, []).append(i)
                self._category_index.setdefault(r.category, []).append(i)
        except OSError:
            pass

    def _append_one(self, record: ExperienceRecord) -> None:
        """追加单条记录到文件"""
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def save(self) -> None:
        """全量保存（覆盖写入，用于重建）"""
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                for record in self._records:
                    f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def clear(self) -> None:
        """清空经验库"""
        self._records.clear()
        self._signature_index.clear()
        self._category_index.clear()
        if self.storage_path and self.storage_path.exists():
            self.storage_path.unlink()
