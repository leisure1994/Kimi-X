"""策略优化器.

通过 EMA (Exponential Moving Average) 持续优化任务策略 Playbook。
从经验记录中提取模式，更新成功率、平均步骤、偏好工具等指标。
零 LLM 调用，纯统计驱动。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .models import ExperienceRecord, SkillPattern, StrategyPlaybook, TaskOutcome
from .store import LearningStore

logger = logging.getLogger(__name__)


class Optimizer:
    """策略优化器.

    基于 EMA 滑动平均更新策略 Playbook 的各项指标，
    并通过 Jaccard 聚类发现可复用的技能模式。
    """

    def __init__(self, ema_alpha: float = 0.3, store: LearningStore | None = None) -> None:
        """初始化优化器.

        Args:
            ema_alpha: EMA 平滑系数 (0~1)，越大越重视新数据
            store: 存储层引用
        """
        self._alpha = ema_alpha
        self._store = store

    async def update_strategy(
        self, experience: ExperienceRecord, current_strategy: StrategyPlaybook | None = None
    ) -> StrategyPlaybook:
        """根据新经验更新策略 Playbook.

        Args:
            experience: 新的经验记录
            current_strategy: 当前策略（None 则创建新策略）

        Returns:
            更新后的策略
        """
        if current_strategy is None:
            current_strategy = StrategyPlaybook(
                task_type=experience.task_type,
                strategy_text="",
                success_rate=0.5,
                avg_steps=float(experience.steps_count),
                avg_duration=experience.duration_seconds,
                preferred_tools=experience.tools_used[:5],
                anti_patterns=[],
                sample_count=0,
            )

        # EMA 更新成功率
        is_success = 1.0 if experience.outcome == TaskOutcome.SUCCESS else 0.0
        current_strategy.success_rate = self._ema(
            current_strategy.success_rate, is_success
        )

        # EMA 更新平均步骤
        current_strategy.avg_steps = self._ema(
            current_strategy.avg_steps, float(experience.steps_count)
        )

        # EMA 更新平均耗时
        current_strategy.avg_duration = self._ema(
            current_strategy.avg_duration, experience.duration_seconds
        )

        # 更新偏好工具（使用频率排序）
        current_strategy.preferred_tools = self._update_preferred_tools(
            current_strategy.preferred_tools, experience.tools_used
        )

        # 更新反模式
        if experience.outcome == TaskOutcome.FAILURE and experience.lesson:
            current_strategy.anti_patterns = self._update_anti_patterns(
                current_strategy.anti_patterns, experience.lesson
            )

        # 更新策略文本
        current_strategy.strategy_text = self._generate_strategy_text(current_strategy)

        current_strategy.sample_count += 1
        current_strategy.last_updated = datetime.now(timezone.utc).isoformat()

        # 持久化
        if self._store:
            await self._store.save_strategy(current_strategy)

        return current_strategy

    async def discover_skill_patterns(
        self, experiences: list[ExperienceRecord]
    ) -> list[SkillPattern]:
        """通过 Jaccard 聚类发现技能模式.

        从成功经验中发现可复用的工具组合模式。

        Args:
            experiences: 经验记录列表

        Returns:
            发现的技能模式列表
        """
        # 只分析成功的经验
        success_exps = [e for e in experiences if e.outcome == TaskOutcome.SUCCESS]
        if len(success_exps) < 3:
            return []

        # 按工具组合聚类
        tool_clusters: dict[str, list[ExperienceRecord]] = {}
        for exp in success_exps:
            # 用排序后的工具集合作为 key
            tool_key = "|".join(sorted(set(exp.tools_used)))
            if tool_key not in tool_clusters:
                tool_clusters[tool_key] = []
            tool_clusters[tool_key].append(exp)

        # 从频繁出现的聚类中提取技能模式
        patterns: list[SkillPattern] = []
        for tool_key, cluster_exps in tool_clusters.items():
            if len(cluster_exps) < 2:
                continue

            tools = tool_key.split("|")
            # 合并所有触发标签
            all_tags: list[str] = []
            for exp in cluster_exps:
                all_tags.extend(exp.context_tags)

            # 取频率 top tags
            tag_counter = Counter(all_tags)
            common_tags = [tag for tag, count in tag_counter.most_common(5) if count >= 2]

            if not common_tags:
                continue

            avg_score = sum(e.score for e in cluster_exps) / len(cluster_exps)

            pattern = SkillPattern(
                name=f"{'_'.join(tools[:2])}_pattern",
                description=f"组合使用 {', '.join(tools)} 的典型模式",
                trigger_tags=common_tags,
                tool_sequence=tools,
                success_rate=avg_score,
                usage_count=len(cluster_exps),
            )
            patterns.append(pattern)

        # 持久化
        if self._store:
            for pattern in patterns:
                await self._store.save_skill_pattern(pattern)

        logger.debug(f"发现 {len(patterns)} 个技能模式")
        return patterns

    def _ema(self, old_value: float, new_value: float) -> float:
        """指数移动平均."""
        return self._alpha * new_value + (1 - self._alpha) * old_value

    def _update_preferred_tools(
        self, current_tools: list[str], new_tools: list[str]
    ) -> list[str]:
        """更新偏好工具列表（按频率排序）."""
        # 简化实现：合并后去重，新工具放前面
        combined = list(dict.fromkeys(new_tools + current_tools))
        return combined[:6]

    def _update_anti_patterns(
        self, current_patterns: list[str], lesson: str
    ) -> list[str]:
        """更新反模式列表（最多保留 5 条）."""
        # 避免重复
        if lesson in current_patterns:
            return current_patterns
        updated = current_patterns + [lesson[:100]]
        return updated[-5:]

    def _generate_strategy_text(self, strategy: StrategyPlaybook) -> str:
        """根据统计数据生成策略描述文本."""
        parts: list[str] = []

        if strategy.success_rate >= 0.8:
            parts.append("高成功率任务类型")
        elif strategy.success_rate < 0.5:
            parts.append("需要谨慎处理的任务类型")

        if strategy.avg_steps <= 3:
            parts.append("通常可快速完成")
        elif strategy.avg_steps >= 10:
            parts.append("较复杂，建议分步执行")

        if strategy.preferred_tools:
            parts.append(f"推荐工具: {', '.join(strategy.preferred_tools[:3])}")

        return "; ".join(parts) if parts else ""
