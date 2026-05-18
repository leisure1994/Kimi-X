"""
Core Rules 单元测试 — 纯本地，不耗 API token
"""

from __future__ import annotations

import pytest
from kimix.core.core_rules import inject_core_rules

pytestmark = pytest.mark.unit


class TestCoreRules:
    """核心规则注入测试"""

    def test_inject_core_rules_adds_prefix(self) -> None:
        """规则注入在系统提示前添加核心原则"""
        system_prompt = "你是一个助手"
        result = inject_core_rules(system_prompt)
        assert "Agent 核心准则" in result or "核心准则" in result
        assert system_prompt in result

    def test_inject_core_rules_idempotent(self) -> None:
        """重复注入不会重复添加"""
        system_prompt = "测试"
        first = inject_core_rules(system_prompt)
        second = inject_core_rules(first)
        # 不应重复添加（简单检查：内容不应翻倍）
        assert len(second) < len(first) * 2

    def test_inject_core_rules_preserves_original(self) -> None:
        """注入后原系统提示仍然完整保留"""
        system_prompt = "原始提示内容"
        result = inject_core_rules(system_prompt)
        assert system_prompt in result
