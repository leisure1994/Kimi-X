"""Prompt 演化器.

实现 Prompt 的版本化管理、自动演化和性能回滚。
基于历史经验的统计表现决定是否演化或回滚 Prompt。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .models import ExperienceRecord, PromptVersion, TaskOutcome
from .store import LearningStore

logger = logging.getLogger(__name__)

# 默认系统 Prompt 模板
_BASE_SYSTEM_PROMPT = """你是 Kimi-Agent，一个高效的终端 AI 助手。
基于历史经验，你已学会以下策略：
{experience_guidance}

执行原则：
- 优先使用已验证有效的工具组合
- 遇到失败时及时切换策略，避免重复尝试
- 控制步骤数，追求高效完成"""


class Evolver:
    """Prompt 演化器.

    管理 Prompt 版本，基于性能指标自动演化或回滚。
    演化策略:
    - 累计 N 个样本后评估当前版本性能
    - 如果表现低于阈值，生成新版本
    - 如果新版本表现不如旧版本，回滚
    """

    def __init__(
        self,
        store: LearningStore,
        min_samples: int = 10,
        improvement_threshold: float = 0.05,
    ) -> None:
        """初始化演化器.

        Args:
            store: 存储层
            min_samples: 评估所需的最少样本数
            improvement_threshold: 判定改进的最小阈值
        """
        self._store = store
        self._min_samples = min_samples
        self._improvement_threshold = improvement_threshold

    async def get_current_prompt(self, experience_guidance: str = "") -> str:
        """获取当前活跃的系统 Prompt.

        Args:
            experience_guidance: 经验指导文本（由 Retriever 生成）

        Returns:
            格式化后的系统 Prompt
        """
        active = await self._store.get_active_prompt()
        if active:
            template = active.prompt_text
        else:
            template = _BASE_SYSTEM_PROMPT

        return template.format(experience_guidance=experience_guidance or "暂无历史经验")

    async def record_performance(self, score: float) -> None:
        """记录当前 Prompt 版本的执行表现.

        Args:
            score: 本次执行的评分 (0.0 ~ 1.0)
        """
        active = await self._store.get_active_prompt()
        if not active:
            # 初始化第一个版本
            active = PromptVersion(
                version=1,
                prompt_text=_BASE_SYSTEM_PROMPT,
                avg_score=score,
                sample_count=1,
                is_active=True,
            )
            await self._store.save_prompt_version(active)
            return

        # 更新平均分（增量平均）
        n = active.sample_count + 1
        active.avg_score = active.avg_score + (score - active.avg_score) / n
        active.sample_count = n
        await self._store.save_prompt_version(active)

    async def maybe_evolve(self, recent_experiences: list[ExperienceRecord]) -> bool:
        """评估是否需要演化 Prompt.

        条件: 累计样本 >= min_samples 且性能有下降趋势。

        Args:
            recent_experiences: 近期经验记录

        Returns:
            是否执行了演化
        """
        active = await self._store.get_active_prompt()
        if not active or active.sample_count < self._min_samples:
            return False

        # 计算近期表现
        if len(recent_experiences) < 5:
            return False

        recent_scores = [e.score for e in recent_experiences[:10]]
        recent_avg = sum(recent_scores) / len(recent_scores)

        # 如果近期表现明显好于历史平均，无需演化
        if recent_avg >= active.avg_score:
            return False

        # 性能下降超过阈值，触发演化
        if active.avg_score - recent_avg < self._improvement_threshold:
            return False

        logger.info(
            f"触发 Prompt 演化: 历史平均={active.avg_score:.3f}, "
            f"近期平均={recent_avg:.3f}"
        )

        # 生成新版本
        new_prompt = self._evolve_prompt(active.prompt_text, recent_experiences)
        new_version = await self._store.get_latest_prompt_version() + 1

        # 停用旧版本
        await self._store.deactivate_all_prompts()

        # 保存新版本
        new_pv = PromptVersion(
            version=new_version,
            prompt_text=new_prompt,
            avg_score=0.0,
            sample_count=0,
            is_active=True,
        )
        await self._store.save_prompt_version(new_pv)

        return True

    async def maybe_rollback(self) -> bool:
        """检查是否需要回滚到上一个版本.

        条件: 新版本累计样本 >= min_samples 且表现不如上一版本。

        Returns:
            是否执行了回滚
        """
        active = await self._store.get_active_prompt()
        if not active or active.version <= 1 or active.sample_count < self._min_samples:
            return False

        # 获取上一个版本
        prev_version = active.version - 1
        # 简化: 通过数据库查询
        assert self._store._db is not None
        cursor = await self._store._db.execute(
            "SELECT * FROM prompt_versions WHERE version = ?", (prev_version,)
        )
        row = await cursor.fetchone()
        if not row:
            return False

        prev_pv = self._store._row_to_prompt_version(row)

        # 如果新版本表现不如旧版本
        if active.avg_score < prev_pv.avg_score - self._improvement_threshold:
            logger.warning(
                f"Prompt 回滚: v{active.version}({active.avg_score:.3f}) < "
                f"v{prev_pv.version}({prev_pv.avg_score:.3f})"
            )
            await self._store.deactivate_all_prompts()
            prev_pv.is_active = True
            await self._store.save_prompt_version(prev_pv)
            return True

        return False

    def _evolve_prompt(
        self, current_prompt: str, recent_experiences: list[ExperienceRecord]
    ) -> str:
        """基于近期经验生成演化后的 Prompt.

        纯启发式: 从失败经验中提取反模式，从成功经验中提取最佳实践。
        """
        # 收集失败教训
        failures = [e for e in recent_experiences if e.outcome == TaskOutcome.FAILURE]
        successes = [e for e in recent_experiences if e.outcome == TaskOutcome.SUCCESS]

        extra_rules: list[str] = []

        # 从失败中提取规则
        for fail in failures[:3]:
            if fail.lesson and "失败" not in current_prompt:
                extra_rules.append(f"- 避免: {fail.lesson[:60]}")

        # 从成功中提取规则
        for succ in successes[:3]:
            if succ.lesson and succ.score >= 0.8:
                extra_rules.append(f"- 推荐: {succ.lesson[:60]}")

        if not extra_rules:
            return current_prompt

        # 在执行原则后追加新规则
        evolved = current_prompt.rstrip()
        evolved += "\n\n学习到的新规则：\n" + "\n".join(extra_rules)
        return evolved
