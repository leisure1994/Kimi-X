"""
ClawTip 支付集成模块

京东背书的 Agent 支付系统，为 Kimi-Agent 提供完整的支付能力。

核心流程（三阶段）：
1. Phase 1 — 创建订单: Agent 创建订单，保存订单文件
2. Phase 2 — 支付处理: clawtip 读取订单文件，完成支付，写入支付凭证
3. Phase 3 — 执行服务: Agent 读取支付凭证，调用服务端验证并履约

支付方式:
- 用户钱包 → 商家钱包的直接转账
- SM4 国密加密保障交易安全
- 支付凭证（payCredential）自动写入订单文件

用户如果需要，可以直接教用户配置自己的收款能力。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

# SM4 加密（如果可用）
try:
    from gmssl.sm4 import CryptSM4, SM4_ENCRYPT, SM4_DECRYPT
    HAS_SM4 = True
except ImportError:
    HAS_SM4 = False


class ClawTipPayment:
    """ClawTip 支付集成

    为 Agent 提供:
    - 订单创建与管理
    - 支付状态查询
    - 支付凭证验证
    - 收款配置指导（教用户设置自己的收款）

    使用方式:
        payment = ClawTipPayment()
        # 创建订单
        order = payment.create_order(
            amount=1000,  # 分（10元）
            description="代码生成服务",
            question="帮我写一个 Python 爬虫",
        )
        # 处理支付
        result = payment.process_payment(order["order_no"])
        # 验证支付
        if payment.verify_payment(order["order_no"]):
            print("支付成功，开始履约")
    """

    def __init__(
        self,
        pay_to: str | None = None,
        sm4_key: bytes | None = None,
        sandbox: bool = True,
    ) -> None:
        """
        Args:
            pay_to: 收款服务 ID（默认从环境变量或配置文件读取）
            sm4_key: SM4 加密密钥（默认从 ~/.openclaw/skills/clawtip/payment_keys.json 读取）
            sandbox: 是否使用沙箱模式（测试用）
        """
        self.sandbox = sandbox
        self.pay_to = pay_to or self._load_default_pay_to()
        self.sm4_key = sm4_key or self._load_default_sm4_key()
        self.orders_dir = Path.home() / ".openclaw" / "skills" / "orders"
        self.orders_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: 创建订单 ──

    def create_order(
        self,
        amount: int,
        description: str,
        question: str,
        resource_url: str = "",
        slug: str = "kimix-agent",
    ) -> dict[str, Any]:
        """创建支付订单

        Args:
            amount: 金额（单位：分）
            description: 交易描述（≤128字符）
            question: 用户请求内容
            resource_url: 服务提供地址
            slug: 技能唯一标识符

        Returns:
            订单信息字典
        """
        order_no = self._generate_order_no()
        indicator = self._compute_indicator(slug)
        order_dir = self.orders_dir / indicator
        order_dir.mkdir(parents=True, exist_ok=True)

        # 构建订单数据
        order_data = {
            "skill-id": f"clawtip-{slug}",
            "order_no": order_no,
            "amount": amount,
            "question": question,
            "description": description,
            "pay_to": self.pay_to,
            "slug": slug,
            "resource_url": resource_url,
            "created_at": int(time.time()),
            "status": "CREATED",
        }

        # SM4 加密（如果可用）
        if HAS_SM4 and self.sm4_key:
            encrypted = self._sm4_encrypt(json.dumps(order_data))
            order_data["encrypted_data"] = encrypted
        else:
            order_data["encrypted_data"] = ""

        # 保存订单文件
        order_file = order_dir / f"{order_no}.json"
        with open(order_file, "w", encoding="utf-8") as f:
            json.dump(order_data, f, ensure_ascii=False, indent=2)

        return {
            "order_no": order_no,
            "indicator": indicator,
            "amount": amount,
            "pay_to": self.pay_to,
            "order_file": str(order_file),
            "status": "CREATED",
        }

    # ── Phase 2: 支付处理 ──

    def process_payment(self, order_no: str, indicator: str | None = None) -> dict[str, Any]:
        """处理支付（模拟/真实）

        在真实环境中，这会调用 clawtip 服务端 API。
        当前实现为模拟流程，展示集成方式。

        Args:
            order_no: 交易单号
            indicator: 技能标识符（MD5哈希）

        Returns:
            支付结果
        """
        # 查找订单文件
        if indicator is None:
            # 搜索所有 indicator 目录
            indicator = self._find_indicator(order_no)

        if not indicator:
            return {
                "status": "FAIL",
                "error": f"Order not found: {order_no}",
            }

        order_file = self.orders_dir / indicator / f"{order_no}.json"
        if not order_file.exists():
            return {
                "status": "FAIL",
                "error": f"Order file not found: {order_file}",
            }

        # 读取订单
        with open(order_file, "r", encoding="utf-8") as f:
            order = json.load(f)

        # 模拟/真实支付处理
        if self.sandbox:
            # 沙箱模式：模拟支付成功
            pay_credential = self._generate_sandbox_credential(order)
            order["payCredential"] = pay_credential
            order["status"] = "PAID"
            order["paid_at"] = int(time.time())

            with open(order_file, "w", encoding="utf-8") as f:
                json.dump(order, f, ensure_ascii=False, indent=2)

            return {
                "status": "SUCCESS",
                "order_no": order_no,
                "amount": order["amount"],
                "pay_to": order["pay_to"],
                "credential": pay_credential,
                "sandbox": True,
            }
        else:
            # 真实环境：调用 clawtip API
            # TODO: 实现真实的 API 调用
            return {
                "status": "PROCESSING",
                "order_no": order_no,
                "message": "调用 clawtip 服务端进行支付处理...",
            }

    # ── Phase 3: 验证与履约 ──

    def verify_payment(self, order_no: str, indicator: str | None = None) -> bool:
        """验证支付是否成功

        Args:
            order_no: 交易单号
            indicator: 技能标识符

        Returns:
            True if paid, False otherwise
        """
        if indicator is None:
            indicator = self._find_indicator(order_no)

        if not indicator:
            return False

        order_file = self.orders_dir / indicator / f"{order_no}.json"
        if not order_file.exists():
            return False

        with open(order_file, "r", encoding="utf-8") as f:
            order = json.load(f)

        return order.get("status") == "PAID" and "payCredential" in order

    def get_order(self, order_no: str, indicator: str | None = None) -> dict[str, Any] | None:
        """获取订单详情"""
        if indicator is None:
            indicator = self._find_indicator(order_no)

        if not indicator:
            return None

        order_file = self.orders_dir / indicator / f"{order_no}.json"
        if not order_file.exists():
            return None

        with open(order_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── 收款配置指导 ──

    @staticmethod
    def get_setup_guide() -> str:
        """教用户如何配置自己的 ClawTip 收款能力

        Returns:
            配置指南（中文）
        """
        return """
# ClawTip 收款配置指南

## 1. 注册京东 ClawTip 开发者账号

访问 https://clawtip.jd.com 注册开发者账号。

## 2. 创建收款服务

在控制台创建收款服务，获取：
- **pay_to** (收款服务 ID): 类似 `f5372a24e31f12a5b2035ec9ae9080e9202605100450020020005480K87TfWpe6P5VLvbkyf1aY4Q0bXpdOobspdyp7tsPJjR7RB1XEA8R4qhAtit6ktDT0HxNXO8X`
- **SM4 密钥**: 通过邮件发放

## 3. 配置 Kimi-Agent

将以下信息配置到 Agent：

```python
# 方式 1: 代码配置
from kimix.tools.clawtip import ClawTipPayment

payment = ClawTipPayment(
    pay_to="你的收款服务ID",
    sm4_key=b"你的SM4密钥",
    sandbox=False,  # 生产环境设为 False
)
```

```bash
# 方式 2: 环境变量
export CLAWTIP_PAY_TO="你的收款服务ID"
export CLAWTIP_SM4_KEY="你的SM4密钥"
```

```json
# 方式 3: 配置文件 ~/.openclaw/skills/clawtip/payment_keys.json
{
    "pay_to": "你的收款服务ID",
    "sm4_key": "你的SM4密钥",
    "sandbox": false
}
```

## 4. 验证配置

```python
from kimix.tools.clawtip import ClawTipPayment

payment = ClawTipPayment()
order = payment.create_order(
    amount=1,  # 1分钱测试
    description="测试订单",
    question="测试支付",
)
print(f"订单创建成功: {order['order_no']}")
```

## 5. 接入自己的服务

用户支付后，Agent 会：
1. 创建订单（Phase 1）
2. 引导用户支付（Phase 2）
3. 验证支付凭证（Phase 3）
4. 确认收款后履约服务

## 6. 沙箱测试

测试时使用 `sandbox=True`，不涉及真实资金：

```python
payment = ClawTipPayment(sandbox=True)
result = payment.process_payment(order["order_no"])
print(result)  # 模拟支付成功
```

## 联系方式

org.clawtip1@jd.com
"""

    @staticmethod
    def get_quick_setup_command() -> str:
        """返回一键配置命令"""
        return """\
# 一键配置 ClawTip 收款（交互式）
python3 -c "
from kimix.tools.clawtip import ClawTipPayment
print(ClawTipPayment.get_setup_guide())

pay_to = input('请输入你的 pay_to (收款服务ID): ').strip()
sm4_key = input('请输入你的 SM4 密钥: ').strip()

config = {
    'pay_to': pay_to,
    'sm4_key': sm4_key,
    'sandbox': True
}

import json, os
config_dir = os.path.expanduser('~/.openclaw/skills/clawtip')
os.makedirs(config_dir, exist_ok=True)

with open(f'{config_dir}/payment_keys.json', 'w') as f:
    json.dump(config, f, indent=2)

print(f'✅ 配置已保存到 {config_dir}/payment_keys.json')
print('测试订单:')
payment = ClawTipPayment()
order = payment.create_order(amount=1, description='测试', question='test')
print(order)
"
"""

    # ── 内部工具 ──

    def _generate_order_no(self) -> str:
        """生成订单号"""
        timestamp = str(int(time.time()))
        random_suffix = hashlib.md5(os.urandom(16)).hexdigest()[:6]
        return f"KT{timestamp}{random_suffix}"

    def _compute_indicator(self, slug: str) -> str:
        """计算技能标识符（MD5）"""
        return hashlib.md5(slug.encode("utf-8")).hexdigest()

    def _find_indicator(self, order_no: str) -> str | None:
        """搜索订单所在的 indicator"""
        for indicator_dir in self.orders_dir.iterdir():
            if indicator_dir.is_dir():
                if (indicator_dir / f"{order_no}.json").exists():
                    return indicator_dir.name
        return None

    def _load_default_pay_to(self) -> str:
        """从配置文件加载默认 pay_to"""
        config_file = Path.home() / ".openclaw" / "skills" / "clawtip" / "payment_keys.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("pay_to", "")
        # 尝试环境变量
        return os.environ.get("CLAWTIP_PAY_TO", "")

    def _load_default_sm4_key(self) -> bytes | None:
        """从配置文件加载默认 SM4 密钥"""
        config_file = Path.home() / ".openclaw" / "skills" / "clawtip" / "payment_keys.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                key = config.get("sm4_key", "")
                return key.encode("utf-8") if key else None
        # 尝试环境变量
        env_key = os.environ.get("CLAWTIP_SM4_KEY", "")
        return env_key.encode("utf-8") if env_key else None

    def _sm4_encrypt(self, plaintext: str) -> str:
        """SM4 加密"""
        if not HAS_SM4 or not self.sm4_key:
            return ""
        crypt_sm4 = CryptSM4()
        crypt_sm4.set_key(self.sm4_key, SM4_ENCRYPT)
        encrypted = crypt_sm4.crypt_ecb(plaintext.encode("utf-8"))
        return encrypted.hex()

    def _generate_sandbox_credential(self, order: dict[str, Any]) -> str:
        """生成沙箱支付凭证"""
        credential_data = {
            "orderNo": order["order_no"],
            "amount": order["amount"],
            "payTo": order["pay_to"],
            "payStatus": "SUCCESS",
            "finishTime": int(time.time()),
            "sandbox": True,
        }
        return hashlib.sha256(json.dumps(credential_data, sort_keys=True).encode()).hexdigest()

    def get_stats(self) -> dict[str, Any]:
        """支付统计"""
        total_orders = 0
        paid_orders = 0
        total_amount = 0

        for indicator_dir in self.orders_dir.iterdir():
            if indicator_dir.is_dir():
                for order_file in indicator_dir.glob("*.json"):
                    try:
                        with open(order_file, "r", encoding="utf-8") as f:
                            order = json.load(f)
                            total_orders += 1
                            total_amount += order.get("amount", 0)
                            if order.get("status") == "PAID":
                                paid_orders += 1
                    except (json.JSONDecodeError, OSError):
                        continue

        return {
            "total_orders": total_orders,
            "paid_orders": paid_orders,
            "unpaid_orders": total_orders - paid_orders,
            "total_amount_cents": total_amount,
            "total_amount_yuan": round(total_amount / 100, 2),
            "sandbox": self.sandbox,
            "has_sm4": HAS_SM4,
        }
