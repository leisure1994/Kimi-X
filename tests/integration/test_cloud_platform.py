#!/usr/bin/env python3
"""
Agent Cloud Platform 集成测试 — 验证握手、匹配、评分全流程

运行: cd /tmp/kimix-agent-complete && python3 tests/integration/test_cloud_platform.py
"""

import pytest
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kimix.core.agent_economy import (
    AgentCloudPlatform, BountyEngine, FreelanceEngine,
    SandboxValidator, CodeQualityAssessor, create_cloud_platform,
)

# 使用临时目录隔离测试数据
TEST_CLOUD_DIR = Path(tempfile.mkdtemp(prefix="kimix_test_cloud_"))

# Monkey-patch 持久化目录
import kimix.core.agent_economy as econ_module
econ_module.CLOUD_DIR = TEST_CLOUD_DIR


def setup_test_env():
    """清理并准备测试环境"""
    if TEST_CLOUD_DIR.exists():
        shutil.rmtree(TEST_CLOUD_DIR)
    TEST_CLOUD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ 测试环境准备完成: {TEST_CLOUD_DIR}")



pytestmark = pytest.mark.integration
def test_sandbox_validator():
    """测试安全沙盒验证"""
    print("\n[测试] 安全沙盒验证")

    # 安全代码
    safe_code = """
def hello():
    return "Hello World"

if __name__ == "__main__":
    print(hello())
"""
    result = SandboxValidator.validate_code(safe_code)
    assert result["safe"] is True, f"安全代码应通过: {result}"
    assert result["score"] >= 80, f"安全代码应高分: {result['score']}"
    print(f"  ✅ 安全代码验证通过 (score={result['score']})")

    # 危险代码
    dangerous_code = """
import os
os.system("rm -rf /")
eval("1+1")
"""
    result = SandboxValidator.validate_code(dangerous_code)
    assert result["safe"] is False, f"危险代码应被拒: {result}"
    assert len(result["issues"]) >= 2, f"应检测多个问题: {len(result['issues'])}"
    print(f"  ✅ 危险代码正确拒绝 (issues={len(result['issues'])}, score={result['score']})")

    # 运行时沙盒
    result = SandboxValidator.run_in_sandbox(safe_code, timeout=5)
    assert result["executed"] is True, f"应成功执行: {result}"
    print(f"  ✅ 沙盒运行成功")

    # 超时检测
    loop_code = """
while True:
    pass
"""
    result = SandboxValidator.run_in_sandbox(loop_code, timeout=2)
    assert result["runtime_safe"] is False, f"无限循环应超时: {result}"
    print(f"  ✅ 超时检测有效")


def test_code_quality_assessment():
    """测试代码质量评估"""
    print("\n[测试] 代码质量评估")

    excellent_code = """
class Calculator:
    '''A simple calculator with operations.'''
    
    def add(self, a: int, b: int) -> int:
        '''Add two numbers.'''
        return a + b
    
    def subtract(self, a: int, b: int) -> int:
        '''Subtract b from a.'''
        return a - b

# Main usage
if __name__ == "__main__":
    calc = Calculator()
    print(calc.add(1, 2))
    print(calc.subtract(5, 3))
"""
    result = CodeQualityAssessor.assess(excellent_code)
    assert result["total_score"] >= 70, f"优秀代码应高分: {result['total_score']}"
    assert result["quality_level"] in ("excellent", "good"), f"应为高等级: {result['quality_level']}"
    assert result["functions"] >= 2, f"应检测函数: {result['functions']}"
    assert result["classes"] >= 1, f"应检测类: {result['classes']}"
    print(f"  ✅ 优秀代码评分: {result['total_score']} ({result['quality_level']})")

    poor_code = """
import os
def bad():
    x=1;y=2;z=x+y
    print(z)
    a=z*2;b=a/0
    return b
"""
    result = CodeQualityAssessor.assess(poor_code)
    assert result["total_score"] < 70, f"劣质代码应低分: {result['total_score']}"
    print(f"  ✅ 劣质代码评分: {result['total_score']} ({result['quality_level']})")

    # 重复代码检测
    repetitive_code = "\n".join(["x = 1"] * 50)
    result = CodeQualityAssessor.assess(repetitive_code)
    assert result["total_score"] < 60, f"重复代码应被惩罚: {result['total_score']}"
    print(f"  ✅ 重复代码惩罚: {result['total_score']} (重复率>50%被惩罚)")


def test_freelance_registration():
    """测试 Freelance Agent 注册"""
    print("\n[测试] Freelance Agent 注册")

    platform = create_cloud_platform()
    result = platform.register_freelance_agent(
        agent_id="test_freelancer_001",
        capabilities=["python", "testing", "documentation"],
        hourly_rate=500,
        token_budget=100000,
    )
    assert result["status"] == "registered"
    assert "test_freelancer_001" in platform.freelance_agents
    print(f"  ✅ Freelance Agent 注册成功: {result['agent_id']}")

    # 心跳
    engine = platform.freelance_agents["test_freelancer_001"]
    hb = engine.heartbeat()
    assert hb["status"] == "alive"
    print(f"  ✅ 心跳正常")

    # 配置
    engine.configure(
        capabilities=["python", "testing", "documentation", "web_search"],
        hourly_rate=600,
        token_budget=150000,
        max_complexity="high",
    )
    assert "web_search" in engine.profile.capabilities
    assert engine.profile.hourly_rate == 600
    print(f"  ✅ 配置更新成功")


def test_bounty_creation():
    """测试赏金任务创建"""
    print("\n[测试] 赏金任务创建")

    platform = create_cloud_platform()
    task = platform.publish_bounty(
        title="重构用户认证模块", description="重构用户认证模块描述",
        total_bounty=5000,
        owner_agent="test_bounty_owner",
        stages=[
            {"title": "设计JWT认证流程", "description": "设计JWT生成和验证流程", "bounty": 1000},
            {"title": "实现RBAC权限模型", "description": "实现角色和权限管理", "bounty": 2000},
            {"title": "编写单元测试", "description": "覆盖核心功能", "bounty": 1000},
            {"title": "集成测试与验收", "description": "端到端验证", "bounty": 1000},
        ],
        complexity="high",
        tags=["python", "security", "authentication"],
    )
    assert task.task_id.startswith("bty_")
    assert task.bounty_total == 5000
    assert task.bounty_remaining == 5000
    assert len(task.stages) == 4
    assert task.complexity == "high"
    print(f"  ✅ 赏金任务创建成功: {task.task_id}")
    print(f"  ✅ 总赏金: {task.bounty_total}分, 阶段数: {len(task.stages)}")


def test_smart_matching():
    """测试智能匹配算法"""
    print("\n[测试] 智能匹配")

    platform = create_cloud_platform()

    # 注册多个 Freelance Agent
    agents = [
        ("freelancer_python", ["python", "testing"], 500, 100000),
        ("freelancer_security", ["python", "security", "authentication"], 800, 200000),
        ("freelancer_cheap", ["python"], 300, 50000),
        ("freelancer_busy", ["python", "testing", "security"], 600, 150000),
    ]
    for aid, caps, rate, budget in agents:
        platform.register_freelance_agent(aid, caps, rate, budget)

    # 创建任务
    task = platform.publish_bounty(
        title="安全认证模块开发", description="安全认证模块开发描述",
        total_bounty=3000,
        owner_agent="test_owner",
        stages=[
            {"title": "JWT实现", "description": "...", "bounty": 1500},
            {"title": "RBAC实现", "description": "...", "bounty": 1500},
        ],
        tags=["python", "security", "authentication"],
        complexity="high",
    )

    # 匹配
    matches = platform.match_task(task.task_id, top_n=5)
    assert len(matches) > 0, "应有匹配结果"

    # 验证排序: security 专家应该排前面（能力匹配度更高）
    top_agent = matches[0]["agent_id"]
    print(f"  ✅ 匹配到 {len(matches)} 个候选 Agent")
    print(f"  ✅ 最优匹配: {top_agent} (score={matches[0]['total_score']})")

    # 验证评分维度
    for m in matches:
        assert "breakdown" in m
        assert all(k in m["breakdown"] for k in ["capability", "reputation", "load", "price", "history"])
    print(f"  ✅ 所有候选都有完整评分维度")


def test_handshake_protocol():
    """测试完整握手协议"""
    print("\n[测试] 完整握手协议 (3-way)")

    platform = create_cloud_platform()
    platform.register_freelance_agent("hs_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="测试握手", description="测试握手描述", total_bounty=1000, owner_agent="hs_owner",
        stages=[{"title": "测试阶段", "description": "测试", "bounty": 1000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    # Step 1: 发起握手
    hs = platform.initiate_handshake(
        bounty_agent="hs_owner",
        freelance_agent="hs_freelancer",
        task_id=task.task_id,
        stage_id=stage_id,
        proposed_rate=500,
    )
    assert hs.status == "pending"
    assert len(hs.negotiation_log) == 1
    assert hs.negotiation_log[0]["step"] == 1
    print(f"  ✅ Step 1 发起握手: {hs.handshake_id}")

    # Step 2: Freelance 接受
    hs2 = platform.respond_handshake(hs.handshake_id, accept=True)
    assert hs2.status == "accepted"
    assert hs2.established_at is not None
    assert hs2.expires_at is not None
    print(f"  ✅ Step 2 接受握手: status={hs2.status}")

    # 验证握手有效
    verify = platform.verify_handshake(hs.handshake_id)
    assert verify["valid"] is True
    print(f"  ✅ 握手验证通过")


def test_handshake_negotiation():
    """测试握手协商（还价）"""
    print("\n[测试] 握手协商")

    platform = create_cloud_platform()
    platform.register_freelance_agent("nego_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="协商测试", description="协商测试描述", total_bounty=2000, owner_agent="nego_owner",
        stages=[{"title": "协商阶段", "description": "...", "bounty": 2000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    # 发起
    hs = platform.initiate_handshake("nego_owner", "nego_freelancer", task.task_id, stage_id, 500)

    # Freelance 还价到 700
    hs2 = platform.respond_handshake(hs.handshake_id, accept=False, counter_rate=700)
    assert hs2.status == "negotiating"
    assert hs2.negotiated_rate == 700
    print(f"  ✅ 还价: 500 → 700")

    # 赏金方接受还价
    hs3 = platform.finalize_handshake(hs.handshake_id, accept_counter=True)
    assert hs3.status == "accepted"
    assert hs3.negotiated_rate == 700
    print(f"  ✅ 接受还价: status={hs3.status}, rate={hs3.negotiated_rate}")

    # 检查协商日志完整
    assert len(hs3.negotiation_log) == 3
    assert hs3.negotiation_log[0]["step"] == 1
    assert hs3.negotiation_log[1]["step"] == 2
    assert hs3.negotiation_log[2]["step"] == 3
    print(f"  ✅ 协商日志完整 (3步)")


def test_handshake_rejection():
    """测试握手拒绝"""
    print("\n[测试] 握手拒绝")

    platform = create_cloud_platform()
    platform.register_freelance_agent("reject_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="拒绝测试", description="拒绝测试描述", total_bounty=1000, owner_agent="reject_owner",
        stages=[{"title": "拒绝阶段", "description": "...", "bounty": 1000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    hs = platform.initiate_handshake("reject_owner", "reject_freelancer", task.task_id, stage_id, 500)
    hs2 = platform.respond_handshake(hs.handshake_id, accept=False)
    assert hs2.status == "rejected"

    verify = platform.verify_handshake(hs.handshake_id)
    assert verify["valid"] is False
    print(f"  ✅ 拒绝握手有效")


def test_handshake_timeout():
    """测试握手过期"""
    print("\n[测试] 握手过期")

    platform = create_cloud_platform()
    platform.register_freelance_agent("timeout_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="过期测试", description="过期测试描述", total_bounty=1000, owner_agent="timeout_owner",
        stages=[{"title": "过期阶段", "description": "...", "bounty": 1000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    hs = platform.initiate_handshake("timeout_owner", "timeout_freelancer", task.task_id, stage_id, 500)
    hs2 = platform.respond_handshake(hs.handshake_id, accept=True)

    # 模拟过期 (将 expires_at 设为过去)
    hs2.expires_at = time.time() - 1
    platform._save_handshake(hs2)

    verify = platform.verify_handshake(hs.handshake_id)
    assert verify["valid"] is False
    assert "过期" in verify["reason"]
    print(f"  ✅ 握手过期检测有效")


def test_full_task_lifecycle():
    """测试完整任务生命周期"""
    print("\n[测试] 完整任务生命周期")

    platform = create_cloud_platform()
    platform.register_freelance_agent("lifecycle_freelancer", ["python", "testing"], 500, 100000)

    task = platform.publish_bounty(
        title="全生命周期测试", description="全生命周期测试描述",
        total_bounty=2000,
        owner_agent="lifecycle_owner",
        stages=[{"title": "实现功能", "description": "写一个加法函数", "bounty": 2000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    # 1. 匹配
    matches = platform.match_task(task.task_id)
    assert len(matches) > 0
    freelancer_id = matches[0]["agent_id"]
    print(f"  ✅ 1. 匹配到 {freelancer_id}")

    # 2. 握手
    hs = platform.initiate_handshake("lifecycle_owner", freelancer_id, task.task_id, stage_id, 500)
    platform.respond_handshake(hs.handshake_id, accept=True)
    print(f"  ✅ 2. 握手建立")

    # 3. 接单
    fengine = platform.freelance_agents[freelancer_id]
    accept = fengine.accept_task(stage_id, platform.bounty_engine)
    assert accept["accepted"] is True
    print(f"  ✅ 3. 接单成功")

    # 4. 提交代码
    code = """
def add(a, b):
    '''Add two numbers safely.'''
    return a + b

class Calculator:
    '''A calculator class.'''
    def sum(self, numbers):
        '''Sum a list of numbers.'''
        return sum(numbers)
"""
    submit = fengine.submit_work(stage_id, code, platform.bounty_engine)
    assert submit["status"] == "reviewed"
    print(f"  ✅ 4. 提交并初评: score={submit['quality']['total_score']}")

    # 5. 客观评分
    review = platform.review_stage(stage_id, reviewer_id="platform")
    assert review.verdict == "approved"
    print(f"  ✅ 5. 客观评分: {review.total_score} ({review.verdict})")

    # 6. 验收支付
    pay = platform.bounty_engine.approve_and_pay(stage_id)
    assert pay["status"] == "paid"
    assert pay["amount"] > 0
    print(f"  ✅ 6. 支付完成: {pay['amount']}分")

    # 7. 检查 Freelance Agent 统计更新
    report = fengine.get_earnings_report()
    assert report["tasks_completed"] >= 1
    assert report["total_earnings"] > 0
    print(f"  ✅ 7. Freelancer 统计: 完成{report['tasks_completed']}任务, 收入{report['total_earnings']}分")

    # 8. 平台统计
    stats = platform.get_platform_stats()
    assert stats["reviews_count"] >= 1
    print(f"  ✅ 8. 平台统计: {stats['reviews_count']}次评分, 平均分{stats['avg_quality_score']}")


def test_dispute_and_appeal():
    """测试争议和申诉"""
    print("\n[测试] 争议和申诉")

    platform = create_cloud_platform()
    platform.register_freelance_agent("dispute_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="争议测试", description="争议测试描述", total_bounty=1000, owner_agent="dispute_owner",
        stages=[{"title": "争议阶段", "description": "...", "bounty": 1000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    # 提交低质量代码
    bad_code = "x=1\n"
    platform.bounty_engine.assign_stage(stage_id, "dispute_freelancer")

    # 提交
    submit = platform.bounty_engine.submit_deliverable(stage_id, bad_code)
    # 手动拒绝
    result = platform.bounty_engine.dispute_stage(stage_id, "代码质量不符合要求")
    assert result["status"] == "disputed"
    print(f"  ✅ 争议发起成功")

    # 申诉
    review_id = f"rev_{int(time.time())}_{stage_id}"
    # 创建一个评分记录用于申诉测试
    from kimix.core.agent_economy import ReviewRecord
    review = ReviewRecord(
        review_id=review_id, stage_id=stage_id, reviewer="platform",
        scores={"structure": 10, "readability": 10, "efficiency": 10, "documentation": 5, "correctness": 20},
        total_score=11, verdict="rejected", comment="质量不足",
    )
    platform.bounty_engine.reviews[review_id] = review
    platform.bounty_engine._save_review(review)

    appeal = platform.appeal_review(review_id, "我认为评分过低")
    assert appeal["appeal_status"] == "pending"
    print(f"  ✅ 申诉提交成功: {appeal['review_id']}")


def test_bounty_balance_warning():
    """测试赏金余额预警"""
    print("\n[测试] 赏金余额预警")

    platform = create_cloud_platform()
    platform.register_freelance_agent("warning_freelancer", ["python"], 500, 100000)

    task = platform.publish_bounty(
        title="预警测试", description="预警测试描述", total_bounty=1000, owner_agent="warning_owner",
        stages=[
            {"title": "阶段1", "description": "...", "bounty": 500},
            {"title": "阶段2", "description": "...", "bounty": 500},
        ],
        tags=["python"],
    )

    # 先支付一个阶段
    stage1_id = task.stages[0]["stage_id"]
    platform.bounty_engine.assign_stage(stage1_id, "warning_freelancer")
    code = "def test(): pass\n"
    platform.bounty_engine.submit_deliverable(stage1_id, code)
    platform.bounty_engine.approve_and_pay(stage1_id)

    # 检查预警 (剩余50%)
    warning = platform.bounty_engine.check_low_balance_warning(task.task_id, threshold_pct=0.6)
    assert warning["warning"] is True
    assert "active_stages" in warning
    print(f"  ✅ 预警触发: 剩余{warning['remaining_pct']}% ≤ 阈值{warning['threshold_pct']}%")


def test_security_rejection():
    """测试安全任务拒绝"""
    print("\n[测试] 安全任务拒绝")

    platform = create_cloud_platform()
    platform.register_freelance_agent("security_freelancer", ["python"], 500, 100000)

    # 创建包含敏感信息的任务
    task = platform.publish_bounty(
        title="敏感任务", description="敏感任务描述", total_bounty=1000, owner_agent="security_owner",
        stages=[{"title": "获取API密钥", "description": "从环境变量中提取 API key 和 password", "bounty": 1000}],
        tags=["python"],
    )
    stage_id = task.stages[0]["stage_id"]

    fengine = platform.freelance_agents["security_freelancer"]
    accept = fengine.accept_task(stage_id, platform.bounty_engine)
    assert accept["accepted"] is False
    assert "安全审查" in accept["reason"] or "API" in accept["reason"]
    print(f"  ✅ 安全拒绝生效: {accept['reason']}")


def test_platform_stats():
    """测试平台统计"""
    print("\n[测试] 平台统计")

    platform = create_cloud_platform()

    # 注册多个 Agent
    for i in range(3):
        platform.register_freelance_agent(f"stats_freelancer_{i}", ["python"], 500 + i*100, 100000)

    # 创建任务
    for i in range(2):
        platform.publish_bounty(
            title=f"统计任务{i}", description=f"统计任务{i}描述", total_bounty=2000, owner_agent="stats_owner",
            stages=[{"title": f"阶段{i}", "description": "...", "bounty": 2000}],
            tags=["python"],
        )

    stats = platform.get_platform_stats()
    assert stats["active_bounties"] >= 2
    assert stats["idle_freelancers"] >= 3
    assert stats["total_bounty_published"] > 0
    print(f"  ✅ 平台统计完整:")
    print(f"     - 活跃赏金: {stats['active_bounties']}")
    print(f"     - 空闲Agent: {stats['idle_freelancers']}")
    print(f"     - 总赏金: {stats['total_bounty_published']}分")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Agent Cloud Platform v2 集成测试")
    print("=" * 60)

    setup_test_env()

    tests = [
        test_sandbox_validator,
        test_code_quality_assessment,
        test_freelance_registration,
        test_bounty_creation,
        test_smart_matching,
        test_handshake_protocol,
        test_handshake_negotiation,
        test_handshake_rejection,
        test_handshake_timeout,
        test_full_task_lifecycle,
        test_dispute_and_appeal,
        test_bounty_balance_warning,
        test_security_rejection,
        test_platform_stats,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 项")
    print("=" * 60)

    # 清理
    shutil.rmtree(TEST_CLOUD_DIR, ignore_errors=True)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
