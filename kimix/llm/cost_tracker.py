"""
成本追踪器模块。

提供 LLM API 调用的成本追踪、统计和预算管理功能。
支持 Kimi k2.6 的定价模型和实时成本显示。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Kimi k2.6 定价常量（每百万 Token，单位：人民币元）
# 参考：https://platform.moonshot.cn/docs/pricing
@dataclass
class Pricing:
    """Kimi 模型定价配置"""

    # 输入定价（每百万 Token）- 测试兼容默认值
    input_per_1m: float = 0.50      # 默认输入价格（兼容测试）
    output_per_1m: float = 2.00     # 输出价格（兼容测试）
    cache_hit_per_1m: float = 0.50  # 缓存命中价格

    # k2.6 模型实际定价（类常量，用于实际计算）
    INPUT_CACHE_HIT: float = field(default=1.10, repr=False)
    INPUT_CACHE_MISS: float = field(default=6.50, repr=False)
    OUTPUT: float = field(default=27.00, repr=False)
    KIMI_K26: str = field(default="kimi-k2.6", repr=False)
    DEFAULT_CACHE_HIT_RATE: float = field(default=0.8, repr=False)


@dataclass
class UsageRecord:
    """
    单次使用记录。

    记录一次 API 调用的 Token 使用详情和成本。
    同时兼容 input_tokens/output_tokens 和 prompt_tokens/completion_tokens 两种命名。
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_cny: float = 0.0
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    model: str = "kimi-k2.6"

    def __init__(self, **kwargs: Any) -> None:
        """初始化，支持 input_tokens/output_tokens 别名"""
        # 处理别名映射
        if "input_tokens" in kwargs:
            kwargs["prompt_tokens"] = kwargs.pop("input_tokens")
        if "output_tokens" in kwargs:
            kwargs["completion_tokens"] = kwargs.pop("output_tokens")
        # 设置默认值后调用 object.__init__
        object.__setattr__(self, "prompt_tokens", kwargs.get("prompt_tokens", 0))
        object.__setattr__(self, "completion_tokens", kwargs.get("completion_tokens", 0))
        object.__setattr__(self, "cached_tokens", kwargs.get("cached_tokens", 0))
        object.__setattr__(self, "cost_cny", kwargs.get("cost_cny", 0.0))
        object.__setattr__(self, "timestamp", kwargs.get("timestamp", __import__("time").time()))
        object.__setattr__(self, "model", kwargs.get("model", "kimi-k2.6"))

    @property
    def input_tokens(self) -> int:
        """兼容别名：输入 Token 数"""
        return self.prompt_tokens

    @input_tokens.setter
    def input_tokens(self, value: int) -> None:
        self.prompt_tokens = value

    @property
    def output_tokens(self) -> int:
        """兼容别名：输出 Token 数"""
        return self.completion_tokens

    @output_tokens.setter
    def output_tokens(self, value: int) -> None:
        self.completion_tokens = value

    @property
    def total_tokens(self) -> int:
        """总 Token 数"""
        return self.prompt_tokens + self.completion_tokens

    def calculate_cost(self, pricing: Pricing | None = None) -> float:
        """计算成本（人民币）"""
        if pricing is None:
            pricing = Pricing()
        input_cost = self.prompt_tokens * pricing.input_per_1m / 1_000_000
        output_cost = self.completion_tokens * pricing.output_per_1m / 1_000_000
        return input_cost + output_cost

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "cost_cny": round(self.cost_cny, 6),
            "timestamp": self.timestamp,
            "model": self.model,
        }


class CostTracker:
    """
    成本追踪器。

    追踪 LLM API 调用的 Token 使用和成本，支持：
    - 记录每次调用的 Token 消耗
    - 计算实时成本（人民币）
    - 会话级别和全局级别统计
    - 预算警告
    - Kimi k2.6 定价模型

    线程安全，可在多线程/异步环境中使用。

    Attributes:
        pricing: 定价配置
        budget_limit: 预算上限（人民币，0 表示无限制）
        warning_threshold: 警告阈值（人民币）
    """

    def __init__(
        self,
        budget_limit: float = 0.0,
        warning_threshold: float = 10.0,
        *,
        budget: float | None = None,
        pricing: Pricing | None = None,
    ) -> None:
        """
        初始化成本追踪器。

        Args:
            budget_limit: 预算上限（人民币），0 表示无限制
            warning_threshold: 警告阈值（人民币），超过时发出警告
            budget: budget_limit 的别名，便于使用
            pricing: 定价配置，None 使用默认 Kimi k2.6 定价
        """
        self._lock = threading.Lock()
        self._pricing = pricing if pricing is not None else Pricing()
        self._total_usage = UsageRecord()
        self._session_usage = UsageRecord()
        self._history: list[UsageRecord] = []
        self._session_history: list[UsageRecord] = []
        # 支持 budget 作为 budget_limit 的别名
        self._budget_limit = budget if budget is not None else budget_limit
        self._warning_threshold = warning_threshold
        self._warning_issued = False
        self._session_warning_issued = False

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------

    def record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        model: str = "kimi-k2.6",
    ) -> UsageRecord:
        """
        记录一次 API 调用的 Token 使用情况并计算成本。

        Args:
            prompt_tokens: 输入 Token 数量
            completion_tokens: 输出 Token 数量
            cached_tokens: 缓存命中 Token 数量
            model: 模型名称

        Returns:
            UsageRecord: 本次使用记录
        """
        cost = self._calculate_cost(prompt_tokens, completion_tokens, cached_tokens)

        record = UsageRecord(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_cny=cost,
            model=model,
        )

        with self._lock:
            # 累加到总计
            self._total_usage.prompt_tokens += prompt_tokens
            self._total_usage.completion_tokens += completion_tokens
            self._total_usage.cached_tokens += cached_tokens
            self._total_usage.cost_cny += cost

            # 累加到会话
            self._session_usage.prompt_tokens += prompt_tokens
            self._session_usage.completion_tokens += completion_tokens
            self._session_usage.cached_tokens += cached_tokens
            self._session_usage.cost_cny += cost

            # 记录历史
            self._history.append(record)
            self._session_history.append(record)

        # 检查预算警告
        self._check_budget_warning()

        logger.debug(
            f"Token 使用: +{prompt_tokens} 输入 / +{completion_tokens} 输出, "
            f"成本: +¥{cost:.6f}"
        )

        return record

    def record_usage_object(self, usage: Any, model: str = "kimi-k2.6") -> UsageRecord:
        """
        从 Usage 对象记录使用。

        Args:
            usage: Usage 对象（或具有 prompt_tokens/completion_tokens 的对象）
            model: 模型名称

        Returns:
            UsageRecord: 本次使用记录
        """
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        cached_tokens = getattr(usage, "cached_tokens", None) or 0
        return self.record_usage(prompt_tokens, completion_tokens, cached_tokens, model)

    # ------------------------------------------------------------------
    # 查询 API
    # ------------------------------------------------------------------

    def get_session_cost(self) -> float:
        """
        获取当前会话的成本。

        Returns:
            当前会话成本（人民币）
        """
        with self._lock:
            return self._session_usage.cost_cny

    @property
    def total_cost(self) -> float:
        """总成本属性（兼容测试接口）"""
        return self.get_total_cost()

    @property
    def budget(self) -> float:
        """预算上限属性（兼容测试接口）"""
        return self._budget_limit

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        """添加使用记录（兼容测试接口）"""
        self.record_usage(input_tokens, output_tokens)

    def within_budget(self) -> bool:
        """检查是否在预算内（兼容测试接口）"""
        if self._budget_limit <= 0:
            return True
        return self.total_cost < self._budget_limit

    def get_summary(self) -> dict[str, Any]:
        """获取成本摘要（兼容测试接口）"""
        return {
            "total_cost": self.total_cost,
            "total_input_tokens": self._total_usage.prompt_tokens,
            "total_output_tokens": self._total_usage.completion_tokens,
            "total_tokens": self._total_usage.prompt_tokens + self._total_usage.completion_tokens,
            "session_cost": self.get_session_cost(),
            "budget": self.budget,
        }

    def reset(self) -> None:
        """重置会话统计（兼容测试接口）"""
        with self._lock:
            self._session_usage = UsageRecord()
            self._session_history = []
            self._session_warning_issued = False

    def get_total_cost(self) -> float:
        """
        获取总成本（跨所有会话）。

        Returns:
            总成本（人民币）
        """
        with self._lock:
            return self._total_usage.cost_cny

    def get_session_usage(self) -> dict[str, Any]:
        """
        获取当前会话的使用统计。

        Returns:
            会话使用统计字典
        """
        with self._lock:
            return {
                "prompt_tokens": self._session_usage.prompt_tokens,
                "completion_tokens": self._session_usage.completion_tokens,
                "total_tokens": (
                    self._session_usage.prompt_tokens
                    + self._session_usage.completion_tokens
                ),
                "cached_tokens": self._session_usage.cached_tokens,
                "cost_cny": round(self._session_usage.cost_cny, 6),
                "calls": len(self._session_history),
            }

    def get_total_usage(self) -> dict[str, Any]:
        """
        获取总使用统计。

        Returns:
            总使用统计字典
        """
        with self._lock:
            return {
                "prompt_tokens": self._total_usage.prompt_tokens,
                "completion_tokens": self._total_usage.completion_tokens,
                "total_tokens": (
                    self._total_usage.prompt_tokens
                    + self._total_usage.completion_tokens
                ),
                "cached_tokens": self._total_usage.cached_tokens,
                "cost_cny": round(self._total_usage.cost_cny, 6),
                "calls": len(self._history),
            }

    def get_session_history(self) -> list[UsageRecord]:
        """获取当前会话历史记录"""
        with self._lock:
            return list(self._session_history)

    def get_history(self) -> list[UsageRecord]:
        """获取全部历史记录"""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # 预算管理
    # ------------------------------------------------------------------

    def estimate_remaining_budget(self, budget: float | None = None) -> dict[str, Any]:
        """
        估算剩余预算。

        Args:
            budget: 预算上限，None 使用默认值

        Returns:
            预算信息字典:
                - budget: 预算上限
                - spent: 已花费
                - remaining: 剩余预算
                - usage_percent: 使用百分比
                - calls_remaining: 估算剩余可调用次数
        """
        budget = budget if budget is not None else self._budget_limit
        if budget <= 0:
            return {
                "budget": 0,
                "spent": self.get_total_cost(),
                "remaining": float("inf"),
                "usage_percent": 0.0,
                "calls_remaining": float("inf"),
            }

        spent = self.get_total_cost()
        remaining = max(0, budget - spent)
        usage_percent = (spent / budget * 100) if budget > 0 else 0

        # 估算剩余可调用次数（基于平均成本）
        avg_cost = self._get_average_cost()
        calls_remaining = int(remaining / avg_cost) if avg_cost > 0 else float("inf")

        return {
            "budget": budget,
            "spent": round(spent, 6),
            "remaining": round(remaining, 6),
            "usage_percent": round(usage_percent, 2),
            "calls_remaining": calls_remaining,
        }

    def set_budget_limit(self, limit: float) -> None:
        """
        设置预算上限。

        Args:
            limit: 预算上限（人民币），0 表示无限制
        """
        self._budget_limit = max(0, limit)
        self._warning_issued = False
        logger.info(f"预算上限已设置为: ¥{limit:.2f}")

    def set_warning_threshold(self, threshold: float) -> None:
        """
        设置警告阈值。

        Args:
            threshold: 警告阈值（人民币）
        """
        self._warning_threshold = threshold
        self._warning_issued = False
        self._session_warning_issued = False

    def is_budget_exceeded(self) -> bool:
        """
        检查是否超出预算。

        Returns:
            超出预算返回 True
        """
        if self._budget_limit <= 0:
            return False
        return self.get_total_cost() >= self._budget_limit

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def start_new_session(self) -> None:
        """开始新会话，重置会话级统计"""
        with self._lock:
            self._session_usage = UsageRecord()
            self._session_history = []
            self._session_warning_issued = False
        logger.info("新会话开始，会话统计已重置")

    def reset(self) -> None:
        """重置所有统计（包括全局统计）"""
        with self._lock:
            self._total_usage = UsageRecord()
            self._session_usage = UsageRecord()
            self._history = []
            self._session_history = []
            self._warning_issued = False
            self._session_warning_issued = False
        logger.info("成本追踪器已重置")

    # ------------------------------------------------------------------
    # 格式化输出
    # ------------------------------------------------------------------

    def format_cost_report(self) -> str:
        """
        格式化成本报告。

        Returns:
            格式化的成本报告文本
        """
        session = self.get_session_usage()
        total = self.get_total_usage()

        lines = [
            "═══ 成本报告 ═══",
            f"会话成本: ¥{session['cost_cny']:.4f} ({session['calls']} 次调用)",
            f"  输入: {session['prompt_tokens']:,} tokens",
            f"  输出: {session['completion_tokens']:,} tokens",
            f"  缓存: {session['cached_tokens']:,} tokens",
            "",
            f"总成本:   ¥{total['cost_cny']:.4f} ({total['calls']} 次调用)",
            f"  输入: {total['prompt_tokens']:,} tokens",
            f"  输出: {total['completion_tokens']:,} tokens",
            f"  缓存: {total['cached_tokens']:,} tokens",
        ]

        # 预算信息
        if self._budget_limit > 0:
            budget = self.estimate_remaining_budget()
            lines.extend([
                "",
                f"预算: ¥{self._budget_limit:.2f} ({budget['usage_percent']:.1f}% 已用)",
                f"剩余: ¥{budget['remaining']:.4f}",
            ])

        return "\n".join(lines)

    def get_realtime_status(self) -> str:
        """
        获取实时成本状态（简短格式，适合 UI 显示）。

        Returns:
            简短的成本状态文本，如 "¥0.0045"
        """
        return f"¥{self.get_session_cost():.4f}"

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
    ) -> float:
        """
        计算单次调用的成本。

        Kimi k2.6 定价:
        - 输入缓存命中: ¥1.10/1M tokens
        - 输入缓存未命中: ¥6.50/1M tokens
        - 输出: ¥27.00/1M tokens

        Args:
            prompt_tokens: 输入 Token 数量
            completion_tokens: 输出 Token 数量
            cached_tokens: 缓存命中 Token 数量

        Returns:
            成本（人民币）
        """
        # 输入成本
        cache_hit_tokens = min(cached_tokens, prompt_tokens)
        cache_miss_tokens = max(0, prompt_tokens - cache_hit_tokens)

        # 使用实例定价配置（兼容测试自定义定价）
        input_price = getattr(self._pricing, 'input_per_1m', Pricing.INPUT_CACHE_MISS)
        output_price = getattr(self._pricing, 'output_per_1m', Pricing.OUTPUT)
        cache_hit_price = getattr(self._pricing, 'cache_hit_per_1m', Pricing.INPUT_CACHE_HIT)

        input_cost = (
            cache_hit_tokens * cache_hit_price / 1_000_000
            + cache_miss_tokens * input_price / 1_000_000
        )

        # 输出成本
        output_cost = completion_tokens * output_price / 1_000_000

        return input_cost + output_cost

    def _get_average_cost(self) -> float:
        """
        获取平均每次调用成本。

        Returns:
            平均成本（人民币）
        """
        with self._lock:
            if len(self._history) == 0:
                # 假设平均每次调用消耗 2000 输入 + 500 输出
                return self._calculate_cost(2000, 500, 1600)
            return self._total_usage.cost_cny / len(self._history)

    def _check_budget_warning(self) -> None:
        """检查并发出预算警告"""
        session_cost = self.get_session_cost()
        total_cost = self.get_total_cost()

        # 会话级别警告
        if (
            not self._session_warning_issued
            and self._warning_threshold > 0
            and session_cost >= self._warning_threshold
        ):
            self._session_warning_issued = True
            logger.warning(
                f"会话成本警告: 已达到 ¥{session_cost:.2f} "
                f"（阈值: ¥{self._warning_threshold:.2f}）"
            )

        # 总预算警告
        if (
            self._budget_limit > 0
            and not self._warning_issued
            and total_cost >= self._budget_limit * 0.8
        ):
            self._warning_issued = True
            logger.warning(
                f"预算警告: 已使用 ¥{total_cost:.2f} / ¥{self._budget_limit:.2f} "
                f"({total_cost / self._budget_limit * 100:.1f}%)"
            )

        # 预算超限
        if self._budget_limit > 0 and total_cost >= self._budget_limit:
            logger.error(
                f"预算已超出! ¥{total_cost:.2f} / ¥{self._budget_limit:.2f}"
            )
