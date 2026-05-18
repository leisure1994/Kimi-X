"""
ClawTip 本地单元测试 — 纯本地，不耗 API token
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from kimix.tools.clawtip import ClawTipPayment

pytestmark = pytest.mark.unit


class TestClawTipLocal:
    """ClawTip 支付本地测试"""

    def test_create_order_sandbox(self) -> None:
        """沙箱模式创建订单"""
        payment = ClawTipPayment(sandbox=True)
        order = payment.create_order(
            amount=100,
            description="测试订单",
            question="测试问题",
        )
        assert order["order_no"].startswith("KT")
        assert order["amount"] == 100
        assert order["status"] == "CREATED"

    def test_process_payment_sandbox(self) -> None:
        """沙箱模式处理支付"""
        payment = ClawTipPayment(sandbox=True)
        order = payment.create_order(
            amount=100,
            description="测试支付",
            question="测试",
        )
        result = payment.process_payment(order["order_no"], order["indicator"])
        assert result["status"] == "SUCCESS"

    def test_verify_payment(self) -> None:
        """验证支付状态"""
        payment = ClawTipPayment(sandbox=True)
        order = payment.create_order(
            amount=100,
            description="验证测试",
            question="测试",
        )
        # 支付前
        assert not payment.verify_payment(order["order_no"], order["indicator"])
        # 支付后
        payment.process_payment(order["order_no"], order["indicator"])
        assert payment.verify_payment(order["order_no"], order["indicator"])
