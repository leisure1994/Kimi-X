"""经验反射器.

在任务完成后进行启发式反射（零 LLM 调用），
自动从执行轨迹中提取经验教训并生成 ExperienceRecord。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .models import ExperienceRecord, TaskOutcome

logger = logging.getLogger(__name__)


class Reflector:
    """经验反射器.

    基于启发式规则从任务执行结果中提取经验，无需额外 LLM 调用。
    评估维度:
    - 任务是否成功完成
    - 步骤效率（与历史平均对比）
    - 工具选择是否合理
    - 是否出现重试/回退模式
    """

    def reflect(
        self,
        task_description: str,
        task_type: str,
        tools_used: list[str],
        steps: list[dict[str, Any]],
        outcome: TaskOutcome,
        error_info: str = "",
        duration_seconds: float = 0.0,
        token_cost: int = 0,
    ) -> ExperienceRecord:
        """对一次任务执行进行反射.

        Args:
            task_description: 任务描述
            task_type: 任务类型标签
            tools_used: 使用的工具列表
            steps: 执行步骤列表（每步含 type, tool, result 等）
            outcome: 最终执行结果
            error_info: 错误信息（失败时）
            duration_seconds: 执行耗时
            token_cost: Token 消耗

        Returns:
            生成的经验记录
        """
        # 计算综合评分
        score = self._calculate_score(outcome, steps, tools_used, duration_seconds)

        # 提取经验教训
        lesson = self._extract_lesson(outcome, steps, tools_used, error_info)

        # 提取上下文标签
        context_tags = self._extract_context_tags(task_description, task_type, tools_used)

        record = ExperienceRecord(
            task_type=task_type,
            task_description=task_description[:200],
            context_tags=context_tags,
            tools_used=list(set(tools_used)),
            steps_count=len(steps),
            outcome=outcome,
            error_type=error_info[:100] if error_info else "",
            lesson=lesson,
            score=score,
            duration_seconds=duration_seconds,
            token_cost=token_cost,
        )

        logger.debug(
            f"反射完成: type={task_type}, outcome={outcome.value}, "
            f"score={score:.2f}, lesson={lesson[:50]}..."
        )
        return record

    def _calculate_score(
        self,
        outcome: TaskOutcome,
        steps: list[dict[str, Any]],
        tools_used: list[str],
        duration: float,
    ) -> float:
        """计算综合评分 (0.0 ~ 1.0).

        评分维度:
        - 结果权重: success=1.0, partial=0.6, failure=0.2, timeout=0.1
        - 效率奖励: 步骤少于 5 步加分
        - 重试惩罚: 检测到重复工具调用扣分
        """
        # 基础分
        base_scores = {
            TaskOutcome.SUCCESS: 0.7,
            TaskOutcome.PARTIAL: 0.4,
            TaskOutcome.FAILURE: 0.15,
            TaskOutcome.TIMEOUT: 0.05,
        }
        score = base_scores.get(outcome, 0.3)

        # 效率奖励（步骤少加分）
        step_count = len(steps)
        if step_count <= 3 and outcome == TaskOutcome.SUCCESS:
            score += 0.15
        elif step_count <= 5 and outcome == TaskOutcome.SUCCESS:
            score += 0.1
        elif step_count > 15:
            score -= 0.1

        # 重试惩罚（检测连续相同工具调用）
        retry_count = self._detect_retries(steps)
        if retry_count > 0:
            score -= min(retry_count * 0.05, 0.15)

        # 工具多样性奖励
        unique_tools = len(set(tools_used))
        if unique_tools >= 3 and outcome == TaskOutcome.SUCCESS:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _detect_retries(self, steps: list[dict[str, Any]]) -> int:
        """检测重试模式（连续相同工具调用）."""
        retries = 0
        prev_tool = ""
        for step in steps:
            tool = step.get("tool", "")
            if tool and tool == prev_tool:
                retries += 1
            prev_tool = tool
        return retries

    def _extract_lesson(
        self,
        outcome: TaskOutcome,
        steps: list[dict[str, Any]],
        tools_used: list[str],
        error_info: str,
    ) -> str:
        """提取经验教训."""
        lessons: list[str] = []

        if outcome == TaskOutcome.SUCCESS:
            step_count = len(steps)
            if step_count <= 3:
                lessons.append("高效完成，步骤精简")
            unique_tools = set(tools_used)
            if len(unique_tools) > 1:
                lessons.append(f"组合使用 {', '.join(sorted(unique_tools)[:3])}")
        elif outcome == TaskOutcome.FAILURE:
            if error_info:
                lessons.append(f"失败原因: {error_info[:80]}")
            retries = self._detect_retries(steps)
            if retries > 2:
                lessons.append("多次重试无效，应换策略")
        elif outcome == TaskOutcome.TIMEOUT:
            lessons.append("执行超时，考虑分解任务或加超时保护")
        elif outcome == TaskOutcome.PARTIAL:
            lessons.append("部分完成，需要进一步拆解子任务")

        # 检测反模式
        if len(steps) > 10 and outcome != TaskOutcome.SUCCESS:
            lessons.append("步骤过多但未成功，应提前终止并反思")

        return "; ".join(lessons) if lessons else "正常完成"

    def _extract_context_tags(
        self, description: str, task_type: str, tools_used: list[str]
    ) -> list[str]:
        """从任务描述中提取上下文标签."""
        tags: list[str] = []

        if task_type:
            tags.append(task_type)

        # 从描述中提取关键词
        keywords = ["文件", "代码", "测试", "修复", "重构", "部署", "搜索", "分析"]
        desc_lower = description.lower()
        for kw in keywords:
            if kw in desc_lower:
                tags.append(kw)

        # 英文关键词
        en_keywords = ["file", "code", "test", "fix", "refactor", "deploy", "search", "debug"]
        for kw in en_keywords:
            if kw in desc_lower:
                tags.append(kw)

        # 工具标签
        for tool in tools_used[:3]:
            tags.append(f"tool:{tool}")

        return list(set(tags))[:10]
