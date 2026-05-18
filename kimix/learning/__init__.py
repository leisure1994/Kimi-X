"""自学习系统.

提供 LearningSystem 作为统一门面，整合:
- Reflector: 经验反射（任务后自动提取教训）
- Retriever: 经验检索（任务前注入历史指导）
- Optimizer: 策略优化（EMA 持续优化 Playbook）
- Evolver: Prompt 演化（版本化管理与自动回滚）
- Store: 持久化存储（SQLite）

设计原则:
- 零额外 LLM 调用（全部启发式/统计驱动）
- 每轮 < 500 tokens 注入开销
- 后台异步执行，不阻塞主流程
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .models import ExperienceRecord, TaskOutcome
from .reflector import Reflector
from .retriever import Retriever
from .optimizer import Optimizer
from .evolver import Evolver
from .store import LearningStore

if TYPE_CHECKING:
    from kimix.config.settings import LearningConfig

logger = logging.getLogger(__name__)


class LearningSystem:
    """自学习系统统一门面.

    管理整个学习循环:
    1. 任务开始前 → retrieve_guidance() 注入经验
    2. 任务完成后 → learn_from_execution() 后台反射和优化
    """

    def __init__(self, db_path: Path, config: Any = None) -> None:
        """初始化学习系统.

        Args:
            db_path: SQLite 数据库路径
            config: LearningConfig 配置对象
        """
        self._store = LearningStore(db_path)
        self._reflector = Reflector()

        # 从 config 中提取参数
        similarity_threshold = 0.3
        max_injected_tokens = 500
        ema_alpha = 0.3
        min_samples = 10
        improvement_threshold = 0.05
        self._max_experiences = 1000

        if config is not None:
            similarity_threshold = getattr(config, "similarity_threshold", 0.3)
            max_injected_tokens = getattr(config, "max_injected_tokens", 500)
            ema_alpha = getattr(config, "ema_alpha", 0.3)
            min_samples = getattr(config, "evolution_min_samples", 10)
            improvement_threshold = getattr(config, "evolution_improvement_threshold", 0.05)
            self._max_experiences = getattr(config, "max_experiences", 1000)

        self._retriever = Retriever(
            similarity_threshold=similarity_threshold,
            max_injected_tokens=max_injected_tokens,
        )
        self._optimizer = Optimizer(ema_alpha=ema_alpha, store=self._store)
        self._evolver = Evolver(
            store=self._store,
            min_samples=min_samples,
            improvement_threshold=improvement_threshold,
        )
        self._initialized = False

    async def initialize(self) -> None:
        """初始化存储层（必须在使用前调用）."""
        if not self._initialized:
            await self._store.initialize()
            self._initialized = True
            logger.debug("自学习系统初始化完成")

    async def close(self) -> None:
        """关闭学习系统."""
        await self._store.close()
        self._initialized = False

    async def retrieve_guidance(
        self, task_description: str, task_type: str, context_tags: list[str]
    ) -> str:
        """在任务开始前检索经验指导.

        Args:
            task_description: 任务描述
            task_type: 任务类型
            context_tags: 上下文标签

        Returns:
            经验指导文本（可直接注入 system prompt）
        """
        if not self._initialized:
            return ""

        try:
            experiences = await self._store.get_recent_experiences(limit=30)
            strategies = await self._store.get_all_strategies()
            skill_patterns = await self._store.get_skill_patterns()

            guidance = self._retriever.retrieve_guidance(
                task_tags=context_tags,
                task_type=task_type,
                experiences=experiences,
                strategies=strategies,
                skill_patterns=skill_patterns,
            )
            return guidance
        except Exception as e:
            logger.warning(f"经验检索失败: {e}")
            return ""

    async def learn_from_execution(
        self,
        task_description: str,
        task_type: str,
        tools_used: list[str],
        steps: list[dict[str, Any]],
        outcome: TaskOutcome,
        error_info: str = "",
        duration_seconds: float = 0.0,
        token_cost: int = 0,
    ) -> None:
        """在任务完成后进行学习（后台执行）.

        流程:
        1. 反射生成经验记录
        2. 持久化经验
        3. 更新策略 Playbook
        4. 评估 Prompt 演化
        5. 修剪旧经验

        Args:
            task_description: 任务描述
            task_type: 任务类型
            tools_used: 使用的工具列表
            steps: 执行步骤
            outcome: 执行结果
            error_info: 错误信息
            duration_seconds: 执行耗时
            token_cost: Token 消耗
        """
        if not self._initialized:
            return

        try:
            # 1. 反射
            experience = self._reflector.reflect(
                task_description=task_description,
                task_type=task_type,
                tools_used=tools_used,
                steps=steps,
                outcome=outcome,
                error_info=error_info,
                duration_seconds=duration_seconds,
                token_cost=token_cost,
            )

            # 2. 持久化
            await self._store.save_experience(experience)

            # 3. 更新策略
            current_strategy = await self._store.get_strategy(task_type)
            await self._optimizer.update_strategy(experience, current_strategy)

            # 4. 记录 Prompt 性能
            await self._evolver.record_performance(experience.score)

            # 5. 评估 Prompt 演化
            recent = await self._store.get_recent_experiences(limit=15)
            await self._evolver.maybe_evolve(recent)
            await self._evolver.maybe_rollback()

            # 6. 修剪旧经验
            await self._store.prune_experiences(self._max_experiences)

            # 7. 定期发现技能模式（每 20 次学习触发一次）
            total = await self._store.count_experiences()
            if total > 0 and total % 20 == 0:
                all_exps = await self._store.get_experiences(limit=100)
                await self._optimizer.discover_skill_patterns(all_exps)

            logger.debug(
                f"学习完成: {task_type}/{outcome.value}, score={experience.score:.2f}"
            )

        except Exception as e:
            logger.warning(f"学习过程失败（不影响主流程）: {e}")

    async def get_system_prompt(self, experience_guidance: str = "") -> str:
        """获取经过演化的系统 Prompt.

        Args:
            experience_guidance: 本次检索到的经验指导文本

        Returns:
            完整的系统 Prompt
        """
        if not self._initialized:
            return ""
        try:
            return await self._evolver.get_current_prompt(experience_guidance)
        except Exception:
            return ""

    async def get_stats(self) -> dict[str, Any]:
        """获取学习系统统计信息."""
        if not self._initialized:
            return {}
        try:
            total_exp = await self._store.count_experiences()
            strategies = await self._store.get_all_strategies()
            skills = await self._store.get_skill_patterns()
            active_prompt = await self._store.get_active_prompt()
            return {
                "total_experiences": total_exp,
                "strategy_count": len(strategies),
                "skill_pattern_count": len(skills),
                "prompt_version": active_prompt.version if active_prompt else 0,
                "prompt_avg_score": active_prompt.avg_score if active_prompt else 0.0,
            }
        except Exception:
            return {}
