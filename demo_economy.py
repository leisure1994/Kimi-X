#!/usr/bin/env python3
"""
Agent 经济系统 — 端到端真实可用性模拟

模拟场景:
1. Agent Alpha (赏金方) 发布任务: "实现一个安全的文件加密工具"
2. Agent Beta (兼职方) 注册到云端，扫描可用任务
3. 智能匹配: 云端将任务推荐给 Agent Beta
4. 握手协商: Agent Alpha 发起握手，Agent Beta 接受
5. Agent Beta 接单并开发代码
6. 沙盒验证 + 代码质量评估
7. Agent Alpha 验收并通过 ClawTip 支付赏金
8. 验证支付成功，双方统计更新

运行: cd /tmp/kimix-agent-complete && python3 demo_economy.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kimix.core.agent_economy import (
    AgentCloudPlatform, BountyEngine, FreelanceEngine,
    SandboxValidator, CodeQualityAssessor,
    create_cloud_platform, create_bounty_mode, create_freelance_mode,
)
from kimix.tools.clawtip import ClawTipPayment

# 使用临时目录隔离演示数据
DEMO_DIR = Path(tempfile.mkdtemp(prefix="kimix_demo_"))
import kimix.core.agent_economy as econ_module
import kimix.tools.clawtip as clawtip_module
econ_module.CLOUD_DIR = DEMO_DIR
clawtip_module.CLOUD_DIR = DEMO_DIR  # 如果clawtip也使用


def print_header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_step(step: int, desc: str) -> None:
    print(f"\n▶ Step {step}: {desc}")
    print("-" * 50)


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run_demo():
    print_header("Agent 经济系统 — 端到端真实可用性模拟")
    print(f"演示目录: {DEMO_DIR}")
    print("场景: Agent Alpha (赏金方) ↔ 云端平台 ↔ Agent Beta (兼职方)")
    print("任务: 实现一个安全的文件加密工具 (赏金 50元)")

    # ── 初始化 ──
    print_step(0, "初始化支付系统")

    # 使用沙箱模式进行演示（不涉及真实资金）
    clawtip = ClawTipPayment(sandbox=True)
    print(f"  ✅ ClawTip 初始化完成 (sandbox={clawtip.sandbox})")
    print(f"  ✅ pay_to 来源: {'配置文件' if clawtip.pay_to else '未配置(演示模式)'}")

    # 创建云端平台
    platform = AgentCloudPlatform(clawtip)
    print(f"  ✅ 云端平台初始化完成")

    # ── Step 1: Agent Beta 注册到云端 ──
    print_step(1, "Agent Beta (兼职方) 注册到云端")

    beta_result = platform.register_freelance_agent(
        agent_id="agent_beta_crypto_expert",
        capabilities=["python", "cryptography", "security", "testing"],
        hourly_rate=800,  # 8元/小时
        token_budget=500000,
    )
    print(f"  ✅ Agent Beta 注册成功")
    print_json(beta_result)

    # 配置更多参数
    beta_engine = platform.freelance_agents["agent_beta_crypto_expert"]
    beta_engine.configure(
        capabilities=["python", "cryptography", "security", "testing", "documentation"],
        hourly_rate=800,
        token_budget=500000,
        max_complexity="high",
    )
    print(f"  ✅ Agent Beta 配置更新: 时薪{beta_engine.profile.hourly_rate}分, 能力{beta_engine.profile.capabilities}")

    # ── Step 2: Agent Alpha 发布赏金任务 ──
    print_step(2, "Agent Alpha (赏金方) 发布赏金任务")

    task = platform.publish_bounty(
        title="实现安全的文件加密工具",
        description="需要实现一个基于AES-256-GCM的文件加密工具，支持密码派生、随机盐值、认证加密",
        total_bounty=5000,  # 50元
        owner_agent="agent_alpha_security_team",
        stages=[
            {
                "title": "设计加密架构",
                "description": "设计密钥派生、盐值管理、认证加密流程，输出设计文档",
                "bounty": 1000,
            },
            {
                "title": "实现核心加密模块",
                "description": "实现encrypt_file和decrypt_file函数，使用AES-256-GCM，PBKDF2密钥派生",
                "bounty": 2000,
            },
            {
                "title": "编写安全测试",
                "description": "编写单元测试覆盖正常/异常场景，包括错误密码、篡改密文检测",
                "bounty": 1000,
            },
            {
                "title": "集成测试与文档",
                "description": "端到端测试、使用文档、安全注意事项",
                "bounty": 1000,
            },
        ],
        complexity="high",
        tags=["python", "cryptography", "security", "file-encryption"],
        deadline_hours=48,
        priority="high",
    )
    print(f"  ✅ 赏金任务发布成功")
    print(f"     任务ID: {task.task_id}")
    print(f"     总赏金: {task.bounty_total}分 ({task.bounty_total/100}元)")
    print(f"     阶段数: {len(task.stages)}")
    print(f"     复杂度: {task.complexity}")
    print(f"     标签: {task.tags}")

    # ── Step 3: 智能匹配 ──
    print_step(3, "云端智能匹配引擎 — 为任务匹配最佳 Freelance Agent")

    matches = platform.match_task(task.task_id, top_n=5)
    print(f"  ✅ 匹配完成，找到 {len(matches)} 个候选 Agent")
    for i, m in enumerate(matches, 1):
        print(f"     #{i} {m['agent_id']} (score={m['total_score']})")
        print(f"        能力匹配={m['breakdown']['capability']:.1f} | "
              f"声誉={m['breakdown']['reputation']:.1f} | "
              f"负载={m['breakdown']['load']:.1f} | "
              f"价格={m['breakdown']['price']:.1f} | "
              f"历史={m['breakdown']['history']:.1f}")

    best_match = matches[0]
    print(f"\n  🎯 最优匹配: {best_match['agent_id']} (总分 {best_match['total_score']})")

    # ── Step 4: 握手协议 ──
    print_step(4, "Agent 之间建立安全握手")

    stage_id = task.stages[1]["stage_id"]  # 选择核心实现阶段

    # Step 4.1: Alpha 发起握手
    hs = platform.initiate_handshake(
        bounty_agent="agent_alpha_security_team",
        freelance_agent=best_match["agent_id"],
        task_id=task.task_id,
        stage_id=stage_id,
        proposed_rate=beta_engine.profile.hourly_rate,
    )
    print(f"  ✅ Step 1: Alpha 发起握手")
    print(f"     握手ID: {hs.handshake_id}")
    print(f"     提议费率: {hs.negotiated_rate}分/小时")

    # Step 4.2: Beta 接受握手
    hs2 = platform.respond_handshake(hs.handshake_id, accept=True)
    print(f"  ✅ Step 2: Beta 接受握手")
    print(f"     状态: {hs2.status}")
    print(f"     建立时间: {time.strftime('%H:%M:%S', time.localtime(hs2.established_at))}")
    print(f"     过期时间: {time.strftime('%H:%M:%S', time.localtime(hs2.expires_at))}")

    # Step 4.3: 验证握手有效
    verify = platform.verify_handshake(hs.handshake_id)
    print(f"  ✅ Step 3: 握手验证")
    print(f"     有效: {verify['valid']}")

    # ── Step 5: Beta 接单 ──
    print_step(5, "Agent Beta 接受任务阶段")

    accept = beta_engine.accept_task(stage_id, platform.bounty_engine)
    print(f"  ✅ 接单结果:")
    print_json(accept)

    # ── Step 6: Beta 开发并提交代码 ──
    print_step(6, "Agent Beta 开发并提交代码")

    # 模拟 Agent Beta 编写的代码
    deliverable_code = '''
"""
安全的文件加密工具 — AES-256-GCM

基于密码的 authenticated encryption，使用 PBKDF2 密钥派生
和随机盐值，确保每次加密结果不同。
"""

import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class SecureFileCipher:
    """安全的文件加密器。"""

    SALT_SIZE = 32          # 256-bit salt
    NONCE_SIZE = 12         # 96-bit nonce for GCM
    KEY_SIZE = 32           # 256-bit key
    ITERATIONS = 100_000    # PBKDF2 迭代次数

    def __init__(self, password: str):
        """用密码初始化加密器。"""
        self.password = password.encode("utf-8")

    def _derive_key(self, salt: bytes) -> bytes:
        """用 PBKDF2 从密码和盐值派生密钥。"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(self.password)

    def encrypt_file(self, plaintext_path: str, ciphertext_path: str) -> None:
        """加密文件。"""
        # 生成随机盐值和 nonce
        salt = secrets.token_bytes(self.SALT_SIZE)
        nonce = secrets.token_bytes(self.NONCE_SIZE)

        # 派生密钥
        key = self._derive_key(salt)

        # 读取明文
        with open(plaintext_path, "rb") as f:
            plaintext = f.read()

        # 加密
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # 写入: salt + nonce + ciphertext
        with open(ciphertext_path, "wb") as f:
            f.write(salt + nonce + ciphertext)

    def decrypt_file(self, ciphertext_path: str, plaintext_path: str) -> None:
        """解密文件。"""
        with open(ciphertext_path, "rb") as f:
            data = f.read()

        # 解析: salt(32) + nonce(12) + ciphertext
        salt = data[: self.SALT_SIZE]
        nonce = data[self.SALT_SIZE : self.SALT_SIZE + self.NONCE_SIZE]
        ciphertext = data[self.SALT_SIZE + self.NONCE_SIZE :]

        # 派生密钥
        key = self._derive_key(salt)

        # 解密
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        with open(plaintext_path, "wb") as f:
            f.write(plaintext)


def encrypt_file(password: str, input_path: str, output_path: str) -> None:
    """便捷函数: 加密文件。"""
    cipher = SecureFileCipher(password)
    cipher.encrypt_file(input_path, output_path)


def decrypt_file(password: str, input_path: str, output_path: str) -> None:
    """便捷函数: 解密文件。"""
    cipher = SecureFileCipher(password)
    cipher.decrypt_file(input_path, output_path)


# ── 测试 ──
if __name__ == "__main__":
    import tempfile

    # 创建测试文件
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Hello, this is a secret message!")
        test_file = f.name

    encrypted_file = test_file + ".enc"
    decrypted_file = test_file + ".dec"

    # 加密
    encrypt_file("my_strong_password_123", test_file, encrypted_file)
    print(f"Encrypted: {test_file} -> {encrypted_file}")

    # 解密
    decrypt_file("my_strong_password_123", encrypted_file, decrypted_file)
    print(f"Decrypted: {encrypted_file} -> {decrypted_file}")

    # 验证
    with open(test_file, "rb") as f:
        original = f.read()
    with open(decrypted_file, "rb") as f:
        restored = f.read()
    assert original == restored, "Decryption failed!"
    print("✅ 加密解密验证通过")

    # 清理
    os.unlink(test_file)
    os.unlink(encrypted_file)
    os.unlink(decrypted_file)
'''

    print(f"  📝 Agent Beta 提交了 {len(deliverable_code)} 字符的代码")

    # 提交到平台
    submit = beta_engine.submit_work(stage_id, deliverable_code, platform.bounty_engine)
    print(f"  ✅ 提交结果:")
    print_json({
        "status": submit["status"],
        "quality_score": submit.get("quality", {}).get("total_score"),
        "sandbox_safe": submit.get("sandbox", {}).get("safe"),
        "lines": submit.get("quality", {}).get("lines"),
        "functions": submit.get("quality", {}).get("functions"),
        "classes": submit.get("quality", {}).get("classes"),
    })

    # ── Step 7: 沙盒验证 + 质量评估 ──
    print_step(7, "沙盒验证与代码质量评估")

    # 沙盒验证
    sandbox = SandboxValidator.run_in_sandbox(deliverable_code, timeout=30)
    print(f"  ✅ 沙盒验证:")
    print_json({
        "executed": sandbox["executed"],
        "runtime_safe": sandbox["runtime_safe"],
        "output_preview": sandbox["output"][:200] if sandbox["output"] else "(无输出)",
        "error": sandbox["error"][:200] if sandbox["error"] else "(无错误)",
    })

    # 代码质量评估
    quality = CodeQualityAssessor.assess(deliverable_code)
    print(f"\n  ✅ 代码质量评估:")
    print_json({
        "total_score": quality["total_score"],
        "quality_level": quality["quality_level"],
        "breakdown": quality["scores"],
        "lines": quality["lines"],
        "functions": quality["functions"],
        "classes": quality["classes"],
        "comment_lines": quality["comment_lines"],
    })

    # ── Step 8: 客观评分 ──
    print_step(8, "云端客观评分系统")

    review = platform.review_stage(stage_id, reviewer_id="platform")
    print(f"  ✅ 评分完成:")
    print_json({
        "review_id": review.review_id,
        "total_score": review.total_score,
        "verdict": review.verdict,
        "scores": review.scores,
    })

    # ── Step 9: 验收并支付 ──
    print_step(9, "Agent Alpha 验收并通过 ClawTip 支付赏金")

    # 赏金方验收
    pay_result = platform.bounty_engine.approve_and_pay(stage_id, reviewer_id="agent_alpha")
    print(f"  ✅ 支付结果:")
    print_json({
        "stage_id": pay_result["stage_id"],
        "status": pay_result["status"],
        "amount": pay_result["amount"],
        "quality_bonus": pay_result["quality_bonus"],
        "bounty_remaining": pay_result["bounty_remaining"],
        "payment_simulated": pay_result["payment"].get("simulated"),
    })

    # ── Step 10: 验证支付 ──
    print_step(10, "验证支付状态")

    # 检查订单
    order_file = DEMO_DIR / "orders"  # clawtip 保存订单的位置
    # 查找订单
    orders_found = []
    if order_file.exists():
        for indicator_dir in order_file.iterdir():
            if indicator_dir.is_dir():
                for f in indicator_dir.glob("*.json"):
                    orders_found.append(f)

    print(f"  ✅ 支付凭证:")
    print(f"     订单文件数: {len(orders_found)}")
    for o in orders_found[:3]:
        with open(o, "r") as f:
            order_data = json.load(f)
        print(f"     - {order_data.get('order_no')}: {order_data.get('status')} "
              f"({order_data.get('amount', 0)}分)")

    # ── Step 11: 双方统计 ──
    print_step(11, "双方统计更新")

    # Agent Beta 收入报告
    beta_report = beta_engine.get_earnings_report()
    print(f"  💰 Agent Beta (兼职方) 收入报告:")
    print_json(beta_report)

    # Agent Alpha 任务报告
    alpha_report = platform.bounty_engine.get_task_report(task.task_id)
    print(f"\n  📊 Agent Alpha (赏金方) 任务报告:")
    print_json(alpha_report)

    # ── Step 12: 平台全景 ──
    print_step(12, "云端平台全景统计")

    stats = platform.get_platform_stats()
    print(f"  🌐 平台统计:")
    print_json(stats)

    # ── 总结 ──
    print_header("模拟完成 — 总结")

    success = (
        submit["status"] == "reviewed"
        and review.verdict == "approved"
        and pay_result["status"] == "paid"
        and sandbox["runtime_safe"] is True
    )

    if success:
        print("✅ 端到端流程验证通过!")
        print(f"   • Agent Beta 成功接单并完成开发")
        print(f"   • 代码通过沙盒安全验证")
        print(f"   • 质量评分: {quality['total_score']}/100 ({quality['quality_level']})")
        print(f"   • 赏金支付: {pay_result['amount']}分 ({pay_result['amount']/100}元)")
        print(f"   • ClawTip 订单创建成功")
        print(f"   • 双方统计正确更新")
    else:
        print("❌ 流程存在异常，请检查日志")

    print(f"\n演示数据已保存到: {DEMO_DIR}")
    print("清理演示数据: shutil.rmtree(DEMO_DIR)")

    return success


if __name__ == "__main__":
    try:
        success = run_demo()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 模拟失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
