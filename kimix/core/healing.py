"""
自我修复系统模块 (Self-Healing)

Agent 执行过程中遇到错误时，自动尝试替代方案并恢复执行。
修复策略基于错误类型匹配，从经验库中寻找最佳修复方案。

核心能力:
- 错误分类与根因分析
- 自动降级策略 (流式→非流式、大模型→小模型、工具→手动)
- 重试与指数退避
- 修复成功/失败记录到经验库
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """错误分类"""
    NETWORK = "network"           # 网络超时、连接失败、DNS
    API = "api"                   # API 限流、无效响应、认证失败
    TOKEN = "token"               # Token 超限、上下文溢出
    TOOL = "tool"                 # 工具执行失败、沙箱拦截
    PARSE = "parse"               # 响应解析失败、JSON 错误
    PERMISSION = "permission"     # 文件权限、沙箱拒绝
    RESOURCE = "resource"         # 内存不足、磁盘满
    UNKNOWN = "unknown"           # 未知错误


class HealingStrategy(str, Enum):
    """修复策略"""
    RETRY = "retry"               # 简单重试
    BACKOFF_RETRY = "backoff"     # 指数退避重试
    FALLBACK_MODEL = "fallback_model"  # 切换到备选模型
    NON_STREAM = "non_stream"     # 流式→非流式
    REDUCE_CONTEXT = "reduce_ctx" # 缩减上下文
    SKIP_TOOL = "skip_tool"       # 跳过故障工具
    MANUAL = "manual"             # 需要人工介入


@dataclass
class HealingAttempt:
    """修复尝试记录"""
    error_category: ErrorCategory
    original_error: str
    strategy: HealingStrategy
    success: bool
    result: str = ""
    latency_ms: int = 0
    timestamp: str = ""


@dataclass
class HealingRule:
    """修复规则"""
    category: ErrorCategory
    pattern_keywords: list[str]           # 错误消息匹配关键词
    strategy: HealingStrategy
    max_attempts: int = 3
    fallback_strategies: list[HealingStrategy] = field(default_factory=list)


class SelfHealingEngine:
    """自我修复引擎

    遇到错误时自动选择修复策略，执行修复，记录结果。
    """

    # 内置修复规则 (基于 OpenClaw 实际故障诊断经验)
    DEFAULT_RULES: list[HealingRule] = [
        # 网络超时 → 指数退避重试
        HealingRule(
            category=ErrorCategory.NETWORK,
            pattern_keywords=["timeout", "timed out", "connection", "refused", "dns", "unreachable"],
            strategy=HealingStrategy.BACKOFF_RETRY,
            max_attempts=3,
            fallback_strategies=[HealingStrategy.NON_STREAM],
        ),
        # API 限流 → 指数退避重试 (更长)
        HealingRule(
            category=ErrorCategory.API,
            pattern_keywords=["rate limit", "429", "too many requests", "quota exceeded"],
            strategy=HealingStrategy.BACKOFF_RETRY,
            max_attempts=5,
            fallback_strategies=[],
        ),
        # API Key 无效 → 无法自动修复
        HealingRule(
            category=ErrorCategory.API,
            pattern_keywords=["authentication", "unauthorized", "401", "invalid key", "api key"],
            strategy=HealingStrategy.MANUAL,
            max_attempts=0,
        ),
        # Token 超限 → 缩减上下文
        HealingRule(
            category=ErrorCategory.TOKEN,
            pattern_keywords=["token", "context length", "maximum", "exceed", "too long"],
            strategy=HealingStrategy.REDUCE_CONTEXT,
            max_attempts=2,
            fallback_strategies=[HealingStrategy.FALLBACK_MODEL],
        ),
        # 响应解析失败 → 重试 + 切换到非流式
        HealingRule(
            category=ErrorCategory.PARSE,
            pattern_keywords=["json", "parse", "decode", "invalid", "unexpected", "schema"],
            strategy=HealingStrategy.RETRY,
            max_attempts=2,
            fallback_strategies=[HealingStrategy.NON_STREAM, HealingStrategy.MANUAL],
        ),
        # 工具执行失败 → 跳过该工具
        HealingRule(
            category=ErrorCategory.TOOL,
            pattern_keywords=["tool", "execution", "sandbox", "blocked", "permission denied"],
            strategy=HealingStrategy.SKIP_TOOL,
            max_attempts=1,
            fallback_strategies=[HealingStrategy.MANUAL],
        ),
        # 沙箱权限拒绝 → 跳过
        HealingRule(
            category=ErrorCategory.PERMISSION,
            pattern_keywords=["permission", "access denied", "not allowed", "forbidden", "403"],
            strategy=HealingStrategy.SKIP_TOOL,
            max_attempts=1,
        ),
    ]

    def __init__(
        self,
        experience_memory: Any | None = None,
        custom_rules: list[HealingRule] | None = None,
    ) -> None:
        self.experience_memory = experience_memory
        self.rules = list(self.DEFAULT_RULES)
        if custom_rules:
            self.rules.extend(custom_rules)
        self.attempt_history: list[HealingAttempt] = []

    def classify_error(self, error: Exception) -> ErrorCategory:
        """对错误进行分类"""
        error_msg = str(error).lower()
        error_type = type(error).__name__.lower()

        for rule in self.rules:
            if any(kw in error_msg for kw in rule.pattern_keywords):
                return rule.category

        # 基于异常类型兜底
        if "timeout" in error_type or "connection" in error_type:
            return ErrorCategory.NETWORK
        if "token" in error_type or "context" in error_type:
            return ErrorCategory.TOKEN
        if "json" in error_type or "parse" in error_type:
            return ErrorCategory.PARSE
        if "permission" in error_type or "access" in error_type:
            return ErrorCategory.PERMISSION

        return ErrorCategory.UNKNOWN

    async def heal(
        self,
        error: Exception,
        original_task: Callable[..., Coroutine[Any, Any, Any]],
        task_args: tuple[Any, ...] = (),
        task_kwargs: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, Any]:
        """执行自我修复

        Args:
            error: 捕获的异常
            original_task: 原始任务的协程函数
            task_args: 任务位置参数
            task_kwargs: 任务关键字参数
            context: 执行上下文

        Returns:
            (success, result): 修复是否成功，以及结果（成功时）或 None
        """
        category = self.classify_error(error)
        error_msg = str(error)

        # 查找匹配规则
        rule = self._find_rule(category, error_msg)
        if not rule:
            logger.warning(f"[SelfHealing] 未知错误类型，无法自动修复: {error_msg}")
            return False, None

        if rule.strategy == HealingStrategy.MANUAL:
            logger.warning(f"[SelfHealing] 错误需要人工介入: {error_msg}")
            return False, None

        strategies = [rule.strategy] + list(rule.fallback_strategies)
        last_error = error

        for attempt_idx, strategy in enumerate(strategies):
            if attempt_idx >= rule.max_attempts and strategy == rule.strategy:
                break

            try:
                logger.info(f"[SelfHealing] 尝试修复 #{attempt_idx+1}: {strategy.value} for {category.value}")
                result = await self._apply_strategy(
                    strategy,
                    original_task,
                    task_args,
                    task_kwargs or {},
                    context or {},
                    last_error,
                )

                # 记录成功
                self._record_attempt(category, error_msg, strategy, True)
                logger.info(f"[SelfHealing] 修复成功: {strategy.value}")

                # 保存到经验库
                if self.experience_memory:
                    self.experience_memory.record_fix(
                        error_signature=f"{category.value}:{error_msg[:80]}",
                        strategy=strategy.value,
                        success=True,
                        context=context,
                    )

                return True, result

            except Exception as e:
                last_error = e
                self._record_attempt(category, error_msg, strategy, False)
                logger.warning(f"[SelfHealing] 修复失败: {strategy.value} - {e}")
                continue

        # 所有策略都失败
        logger.error(f"[SelfHealing] 所有修复策略均失败: {error_msg}")
        return False, None

    def _find_rule(self, category: ErrorCategory, error_msg: str) -> HealingRule | None:
        """查找匹配的修复规则"""
        for rule in self.rules:
            if rule.category == category:
                if any(kw in error_msg.lower() for kw in rule.pattern_keywords):
                    return rule
        # 兜底：返回该类别的第一个规则
        for rule in self.rules:
            if rule.category == category:
                return rule
        return None

    async def _apply_strategy(
        self,
        strategy: HealingStrategy,
        task: Callable[..., Coroutine[Any, Any, Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        context: dict[str, Any],
        last_error: Exception,
    ) -> Any:
        """应用修复策略"""
        if strategy == HealingStrategy.RETRY:
            return await task(*args, **kwargs)

        elif strategy == HealingStrategy.BACKOFF_RETRY:
            # 指数退避
            attempt = context.get("healing_attempt", 0)
            delay = min(2 ** attempt, 30)  # 最大 30 秒
            await asyncio.sleep(delay)
            kwargs["healing_attempt"] = attempt + 1
            return await task(*args, **kwargs)

        elif strategy == HealingStrategy.NON_STREAM:
            # 流式→非流式
            kwargs["stream"] = False
            return await task(*args, **kwargs)

        elif strategy == HealingStrategy.REDUCE_CONTEXT:
            # 缩减上下文 (移除最旧的消息)
            messages = kwargs.get("messages", [])
            if len(messages) > 2:
                kwargs["messages"] = messages[-2:]  # 只保留 system + 最后一条
            return await task(*args, **kwargs)

        elif strategy == HealingStrategy.FALLBACK_MODEL:
            # 切换到备选模型 (如果配置中有)
            fallback = context.get("fallback_model")
            if fallback:
                kwargs["model"] = fallback
            return await task(*args, **kwargs)

        elif strategy == HealingStrategy.SKIP_TOOL:
            # 跳过工具调用
            kwargs["tools"] = None
            kwargs["tool_choice"] = None
            return await task(*args, **kwargs)

        else:
            raise ValueError(f"未知修复策略: {strategy}")

    def _record_attempt(
        self,
        category: ErrorCategory,
        error: str,
        strategy: HealingStrategy,
        success: bool,
    ) -> None:
        """记录修复尝试"""
        from datetime import datetime, timezone
        self.attempt_history.append(HealingAttempt(
            error_category=category,
            original_error=error[:200],
            strategy=strategy,
            success=success,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        # 同时写入经验库（成功和失败都有价值）
        if self.experience_memory:
            try:
                self.experience_memory.record_fix(
                    error_signature=f"{category.value}:{error[:80]}",
                    strategy=strategy.value,
                    success=success,
                )
            except Exception:
                pass

    def get_success_rate(self, category: ErrorCategory | None = None) -> float:
        """获取修复成功率"""
        attempts = self.attempt_history
        if category:
            attempts = [a for a in attempts if a.error_category == category]
        if not attempts:
            return 0.0
        return sum(1 for a in attempts if a.success) / len(attempts)

    def get_recommended_strategy(self, error_msg: str) -> HealingStrategy | None:
        """基于历史经验推荐修复策略"""
        if not self.experience_memory:
            return None
        return self.experience_memory.get_best_strategy(error_msg)
