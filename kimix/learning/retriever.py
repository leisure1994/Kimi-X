"""经验检索器.

基于 Jaccard 相似度从历史经验中检索相关经验，
生成注入到 context 中的经验指导文本。零 LLM 调用，纯启发式。
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ExperienceRecord, SkillPattern, StrategyPlaybook, TaskOutcome

logger = logging.getLogger(__name__)


class Retriever:
    """经验检索器.

    基于任务上下文标签的 Jaccard 相似度检索相关历史经验，
    并格式化为简洁的指导文本注入到 LLM prompt 中。
    """

    def __init__(self, similarity_threshold: float = 0.3, max_injected_tokens: int = 500) -> None:
        """初始化检索器.

        Args:
            similarity_threshold: Jaccard 相似度阈值
            max_injected_tokens: 注入文本的最大 token 估算量
        """
        self._threshold = similarity_threshold
        self._max_tokens = max_injected_tokens

    def retrieve_guidance(
        self,
        task_tags: list[str],
        task_type: str,
        experiences: list[ExperienceRecord],
        strategies: list[StrategyPlaybook],
        skill_patterns: list[SkillPattern],
    ) -> str:
        """检索并生成经验指导文本.

        Args:
            task_tags: 当前任务的上下文标签
            task_type: 当前任务类型
            experiences: 历史经验记录
            strategies: 策略 Playbook
            skill_patterns: 技能模式

        Returns:
            格式化的经验指导文本（空字符串表示无相关经验）
        """
        guidance_parts: list[str] = []

        # 1. 检索匹配的策略
        strategy = self._find_strategy(task_type, strategies)
        if strategy:
            guidance_parts.append(self._format_strategy(strategy))

        # 2. 检索相关经验
        relevant_exps = self._find_relevant_experiences(task_tags, experiences)
        if relevant_exps:
            guidance_parts.append(self._format_experiences(relevant_exps))

        # 3. 检索匹配的技能模式
        matching_skills = self._find_matching_skills(task_tags, skill_patterns)
        if matching_skills:
            guidance_parts.append(self._format_skills(matching_skills))

        if not guidance_parts:
            return ""

        full_text = "\n".join(guidance_parts)

        # 截断到 token 限制（粗略估算 1 char ≈ 0.7 token for 中文）
        max_chars = int(self._max_tokens / 0.7)
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "..."

        return full_text

    def _find_strategy(
        self, task_type: str, strategies: list[StrategyPlaybook]
    ) -> StrategyPlaybook | None:
        """查找匹配的策略 Playbook."""
        for s in strategies:
            if s.task_type == task_type and s.sample_count >= 3:
                return s
        return None

    def _find_relevant_experiences(
        self, task_tags: list[str], experiences: list[ExperienceRecord]
    ) -> list[ExperienceRecord]:
        """通过 Jaccard 相似度查找相关经验."""
        if not task_tags:
            return []

        task_tag_set = set(task_tags)
        scored: list[tuple[float, ExperienceRecord]] = []

        for exp in experiences:
            exp_tag_set = set(exp.context_tags)
            similarity = self._jaccard_similarity(task_tag_set, exp_tag_set)
            if similarity >= self._threshold:
                scored.append((similarity, exp))

        # 按相似度降序，取 top 3
        scored.sort(key=lambda x: (-x[0], -x[1].score))
        return [exp for _, exp in scored[:3]]

    def _find_matching_skills(
        self, task_tags: list[str], patterns: list[SkillPattern]
    ) -> list[SkillPattern]:
        """查找匹配的技能模式."""
        if not task_tags:
            return []

        task_tag_set = set(task_tags)
        matched: list[SkillPattern] = []

        for pattern in patterns:
            trigger_set = set(pattern.trigger_tags)
            similarity = self._jaccard_similarity(task_tag_set, trigger_set)
            if similarity >= self._threshold and pattern.success_rate >= 0.6:
                matched.append(pattern)

        return matched[:2]

    @staticmethod
    def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
        """计算 Jaccard 相似度."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _format_strategy(self, strategy: StrategyPlaybook) -> str:
        """格式化策略为指导文本."""
        lines = [f"[策略] {strategy.task_type} (成功率:{strategy.success_rate:.0%})"]
        if strategy.strategy_text:
            lines.append(f"  方法: {strategy.strategy_text[:100]}")
        if strategy.preferred_tools:
            lines.append(f"  推荐工具: {', '.join(strategy.preferred_tools[:4])}")
        if strategy.anti_patterns:
            lines.append(f"  避免: {'; '.join(strategy.anti_patterns[:2])}")
        return "\n".join(lines)

    def _format_experiences(self, experiences: list[ExperienceRecord]) -> str:
        """格式化经验为指导文本."""
        lines = ["[历史经验]"]
        for exp in experiences:
            icon = "+" if exp.outcome == TaskOutcome.SUCCESS else "-"
            lines.append(f"  {icon} {exp.lesson[:80]}")
        return "\n".join(lines)

    def _format_skills(self, skills: list[SkillPattern]) -> str:
        """格式化技能模式为指导文本."""
        lines = ["[可用技能]"]
        for skill in skills:
            lines.append(
                f"  * {skill.name}: {skill.description[:60]} "
                f"(工具序列: {' -> '.join(skill.tool_sequence[:4])})"
            )
        return "\n".join(lines)
