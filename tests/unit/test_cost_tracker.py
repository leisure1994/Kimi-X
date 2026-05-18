"""
成本追踪单元测试

测试 CostTracker 的 Token 计算、成本估算、预算管理
和报告功能，验证计算精度。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# 绕过 kimix.llm.__init__ 直接导入 cost_tracker（避免加载 tiktoken）
_ct_spec = importlib.util.spec_from_file_location(
    "kimix_llm_cost", Path(__file__).parent.parent.parent / "kimix" / "llm" / "cost_tracker.py"
)
_ct_module = importlib.util.module_from_spec(_ct_spec)
sys.modules["kimix_llm_cost"] = _ct_module
_ct_spec.loader.exec_module(_ct_module)

from kimix_llm_cost import CostTracker, Pricing, UsageRecord



pytestmark = pytest.mark.unit
class TestPricing:
    """Pricing 定价模型测试"""

    def test_default_pricing(self) -> None:
        """测试默认定价"""
        pricing = Pricing()
        assert pricing.input_per_1m == 0.50
        assert pricing.output_per_1m == 2.00
        assert pricing.cache_hit_per_1m == 0.50

    def test_custom_pricing(self) -> None:
        """测试自定义定价"""
        pricing = Pricing(input_per_1m=1.0, output_per_1m=3.0)
        assert pricing.input_per_1m == 1.0
        assert pricing.output_per_1m == 3.0


class TestUsageRecord:
    """UsageRecord 使用记录测试"""

    def test_create_record(self) -> None:
        """测试创建使用记录"""
        record = UsageRecord(input_tokens=1000, output_tokens=500)
        assert record.input_tokens == 1000
        assert record.output_tokens == 500

    def test_total_tokens(self) -> None:
        """测试总 Token 数计算"""
        record = UsageRecord(input_tokens=100, output_tokens=50)
        assert record.total_tokens == 150

    def test_cost_calculation_precision(self) -> None:
        """测试成本计算精度"""
        record = UsageRecord(input_tokens=1_000_000, output_tokens=500_000)
        pricing = Pricing()
        expected_cost = (1_000_000 * 0.50 + 500_000 * 2.00) / 1_000_000
        assert abs(record.calculate_cost(pricing) - expected_cost) < 0.001

    def test_cost_zero_tokens(self) -> None:
        """测试零 Token 成本"""
        record = UsageRecord(input_tokens=0, output_tokens=0)
        pricing = Pricing()
        assert record.calculate_cost(pricing) == 0.0


class TestCostTracker:
    """CostTracker 成本追踪器测试"""

    def test_init(self) -> None:
        """测试初始化"""
        tracker = CostTracker(budget=10.0)
        assert tracker.total_cost == 0.0
        assert tracker.budget == 10.0

    def test_add_usage(self) -> None:
        """测试添加使用记录"""
        tracker = CostTracker()
        tracker.add_usage(1_000_000, 500_000)
        assert tracker.total_cost > 0

    def test_add_usage_precision(self) -> None:
        """测试添加使用记录的精度"""
        tracker = CostTracker()
        tracker.add_usage(1000, 500)
        expected = (1000 * 0.50 + 500 * 2.00) / 1_000_000
        assert abs(tracker.total_cost - expected) < 0.0001

    def test_within_budget(self) -> None:
        """测试预算内"""
        tracker = CostTracker(budget=10.0)
        tracker.add_usage(1000, 500)
        assert tracker.within_budget() is True

    def test_exceed_budget(self) -> None:
        """测试超出预算"""
        tracker = CostTracker(budget=0.001)
        tracker.add_usage(1_000_000, 1_000_000)
        assert tracker.within_budget() is False

    def test_get_summary(self) -> None:
        """测试获取摘要"""
        tracker = CostTracker()
        tracker.add_usage(1000, 500)
        summary = tracker.get_summary()
        assert "total_cost" in summary
        assert "total_input_tokens" in summary
        assert "total_output_tokens" in summary

    def test_reset(self) -> None:
        """测试重置"""
        tracker = CostTracker()
        tracker.add_usage(1000, 500)
        assert tracker.total_cost > 0
        tracker.reset()
        assert tracker.total_cost == 0.0

    def test_multiple_additions(self) -> None:
        """测试多次添加"""
        tracker = CostTracker()
        tracker.add_usage(1000, 500)
        cost1 = tracker.total_cost
        tracker.add_usage(2000, 1000)
        cost2 = tracker.total_cost
        assert cost2 > cost1

    def test_large_token_count(self) -> None:
        """测试大量 Token"""
        tracker = CostTracker()
        tracker.add_usage(100_000_000, 50_000_000)
        assert abs(tracker.total_cost - 150.0) < 0.01
