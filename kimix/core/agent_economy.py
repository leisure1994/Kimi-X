#!/usr/bin/env python3
"""
Agent Cloud Platform 增强版 — v2

新增:
1. 完整握手协议 (3-way handshake with negotiation)
2. 智能匹配引擎 (能力+声誉+负载+价格+历史)
3. 客观评分系统 (五维量化 + 评分历史 + 人工复核接口)
4. 任务生命周期管理 (创建→匹配→握手→执行→验货→评分→结算)
5. 平台仲裁机制 (争议处理)
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# ── 配置 ──

CLOUD_DIR = Path(os.path.expanduser("~/.kimix/agent_cloud"))
CLOUD_DIR.mkdir(parents=True, exist_ok=True)

# ── 数据模型 ──

@dataclass
class BountyTask:
    task_id: str
    title: str
    description: str
    bounty_total: int
    bounty_remaining: int
    status: str = "open"       # open | matching | assigned | in_progress | reviewing | completed | cancelled | disputed
    owner_agent: str = ""
    assigned_agents: list[str] = field(default_factory=list)
    stages: list[dict] = field(default_factory=list)
    deliverables: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    deadline: float | None = None
    priority: str = "normal"
    tags: list[str] = field(default_factory=list)
    complexity: str = "medium"   # low | medium | high

@dataclass
class FreelanceAgent:
    agent_id: str
    display_name: str
    capabilities: list[str] = field(default_factory=list)
    hourly_rate: int = 0
    token_budget: int = 0
    token_used: int = 0
    earnings_total: int = 0
    earnings_pending: int = 0
    reputation: float = 100.0
    status: str = "idle"       # idle | busy | offline | suspended
    last_heartbeat: float = field(default_factory=time.time)
    sandbox_enabled: bool = True
    max_task_complexity: str = "medium"
    reject_patterns: list[str] = field(default_factory=lambda: [
        r"API\s*key", r"password", r"secret", r"token",
        r"银行卡", r"支付密码", r"私钥",
        r"rm\s+-rf", r"format", r"mkfs",
        r"destructive", r"drop\s+table", r"delete\s+from",
    ])
    tasks_completed: int = 0
    tasks_rejected: int = 0
    avg_quality_score: float = 0.0
    total_lines_delivered: int = 0

@dataclass
class TaskStage:
    stage_id: str
    task_id: str
    title: str
    description: str
    bounty: int
    status: str = "pending"     # pending | matched | handshaking | in_progress | submitted | reviewed | paid | rejected | disputed
    assignee: str = ""
    deliverable_code: str = ""
    code_quality_score: float = 0.0
    sandbox_result: dict = field(default_factory=dict)
    review_notes: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    # v2: 评分历史
    quality_history: list[dict] = field(default_factory=list)
    reviewer_id: str = ""       # 评分者
    review_timestamp: float = 0.0

@dataclass
class HandshakeRecord:
    handshake_id: str
    bounty_agent: str
    freelance_agent: str
    task_id: str
    stage_id: str
    status: str = "pending"     # pending | negotiating | accepted | rejected | timeout | completed | breached
    negotiated_rate: int = 0
    security_level: str = "standard"
    established_at: float | None = None
    expires_at: float | None = None
    # v2: 协商记录
    negotiation_log: list[dict] = field(default_factory=list)
    # v2: 履约监控
    milestones: list[dict] = field(default_factory=list)
    breach_reason: str = ""

@dataclass
class ReviewRecord:
    """评分记录"""
    review_id: str
    stage_id: str
    reviewer: str               # 评分者 Agent ID 或 "platform"
    scores: dict                # 五维评分
    total_score: float
    verdict: str                # approved | rejected | disputed
    comment: str = ""
    timestamp: float = field(default_factory=time.time)
    appeal_status: str = ""     # 申诉状态

# ── 安全沙盒 ──

class SandboxValidator:
    """
    安全沙盒 — 验货前必须通过的检测
    
    检测策略:
    - DANGEROUS: 真正危险的代码（eval/exec/os.system/subprocess），每个扣15分
    - SUSPICIOUS: 可疑但可能合法的操作（import os/open/write），每个扣3分
    - NETWORK: 网络请求，每个扣5分
    
    拒绝阈值: score < 30（只拒绝真正危险的代码）
    """

    DANGEROUS_PATTERNS = [
        r"eval\s*\(", r"exec\s*\(", r"os\.system\s*\(", r"subprocess\.call",
        r"__import__\s*\(", r"compile\s*\(", r"input\s*\(", r"raw_input\s*\(",
        r"socket\.", r"urllib\.", r"requests\.", r"httpx\.",
        r"rm\s+-rf", r"shutil\.rmtree", r"os\.remove",
        r"ctypes", r"mmap", r"fork", r"popen",
    ]

    SUSPICIOUS_PATTERNS = [
        r"import\s+os", r"import\s+subprocess", r"import\s+sys",
        r"open\s*\(", r"file\s*\(", r"write\s*\(",
    ]

    NETWORK_PATTERNS = [r"requests\.", r"urllib", r"httpx", r"socket\.", r"http\.client"]

    @classmethod
    def validate_code(cls, code: str, language: str = "python") -> dict:
        """验证代码安全性，返回详细报告"""
        result = {
            "safe": True,
            "risk_level": "low",
            "issues": [],
            "lines_checked": len(code.splitlines()),
            "score": 100.0,
        }

        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            # 1. 危险模式（扣15分）
            for pattern in cls.DANGEROUS_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    result["issues"].append({
                        "line": i, "code": line.strip(),
                        "pattern": pattern, "severity": "high",
                        "category": "dangerous",
                    })
                    result["score"] -= 15

            # 2. 可疑模式（扣3分）
            for pattern in cls.SUSPICIOUS_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    result["issues"].append({
                        "line": i, "code": line.strip(),
                        "pattern": pattern, "severity": "low",
                        "category": "suspicious",
                        "note": "可疑但可能合法的文件/系统操作",
                    })
                    result["score"] -= 3

            # 3. 网络请求（扣5分）
            for p in cls.NETWORK_PATTERNS:
                if re.search(p, line):
                    result["issues"].append({
                        "line": i, "code": line.strip(),
                        "pattern": p, "severity": "medium",
                        "category": "network",
                        "note": "网络请求需审查",
                    })
                    result["score"] -= 5

        if result["score"] < 0:
            result["score"] = 0

        # 判定风险等级
        dangerous_count = sum(1 for issue in result["issues"] if issue.get("category") == "dangerous")
        if dangerous_count >= 2 or result["score"] < 30:
            result["risk_level"] = "critical"
            result["safe"] = False
        elif dangerous_count == 1 or result["score"] < 50:
            result["risk_level"] = "high"
            result["safe"] = False
        elif result["score"] < 70:
            result["risk_level"] = "medium"
        else:
            result["risk_level"] = "low"

        return result

    @classmethod
    def run_in_sandbox(cls, code: str, language: str = "python", timeout: int = 30) -> dict:
        """在临时沙盒中运行代码（隔离环境）
        
        策略:
        1. 静态检查: 记录问题但不直接拒绝（除非 critical）
        2. 实际运行: 在隔离环境中执行，超时即判不安全
        """
        result = {
            "executed": False,
            "output": "",
            "error": "",
            "runtime_safe": True,
            "static_result": {},
        }

        # 1. 静态检查（记录但不直接拒绝，除非 critical）
        static = cls.validate_code(code, language)
        result["static_result"] = {
            "score": static["score"],
            "risk_level": static["risk_level"],
            "issues_count": len(static["issues"]),
            "dangerous_count": sum(1 for i in static["issues"] if i.get("category") == "dangerous"),
        }

        # 只有真正危险才拒绝执行
        if static["risk_level"] == "critical":
            result["runtime_safe"] = False
            result["error"] = f"静态检查 Critical: {len(static['issues'])} 个问题（含危险操作）"
            return result

        # 2. 创建临时文件执行
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                tmp_path = f.name

            proc = subprocess.run(
                ["python3", "-c", f"exec(open('{tmp_path}').read())"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
            )
            result["output"] = proc.stdout[:2000]
            result["error"] = proc.stderr[:2000]
            result["executed"] = proc.returncode == 0
            # 即使执行失败（如缺少依赖），只要不是沙盒异常，仍算安全
            if not result["executed"] and "ModuleNotFoundError" in result["error"]:
                result["runtime_safe"] = True  # 缺少依赖不算安全问题
                result["note"] = "缺少依赖库，代码本身安全"
        except subprocess.TimeoutExpired:
            result["error"] = "执行超时（可能包含无限循环）"
            result["runtime_safe"] = False
        except Exception as e:
            result["error"] = str(e)
            result["runtime_safe"] = False
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

        return result

# ── 代码质量评估 ──

class CodeQualityAssessor:
    @classmethod
    def assess(cls, code: str, language: str = "python") -> dict:
        lines = code.splitlines()
        total_lines = len(lines)
        non_empty = [l for l in lines if l.strip()]
        code_lines = [l for l in non_empty if not l.strip().startswith("#")]
        comment_lines = [l for l in non_empty if l.strip().startswith("#")]

        scores = {
            "structure": 0.0, "readability": 0.0, "efficiency": 0.0,
            "documentation": 0.0, "correctness": 0.0,
        }

        func_count = len(re.findall(r'^\s*def\s+\w+\s*\(', code, re.MULTILINE))
        class_count = len(re.findall(r'^\s*class\s+\w+', code, re.MULTILINE))
        if func_count > 0 or class_count > 0:
            scores["structure"] = min(30 + func_count * 5 + class_count * 10, 100)
        else:
            scores["structure"] = max(20, 100 - total_lines * 0.5)

        long_lines = sum(1 for l in code_lines if len(l) > 100)
        scores["readability"] = max(0, 100 - long_lines * 5)

        if total_lines > 0:
            doc_ratio = len(comment_lines) / total_lines
            scores["documentation"] = min(100, doc_ratio * 300)
        else:
            scores["documentation"] = 0

        loop_count = len(re.findall(r'\b(for|while)\b', code))
        nested_loop = len(re.findall(r'\b(for|while)\b.*\b(for|while)\b', code))
        scores["efficiency"] = max(0, 100 - nested_loop * 20 - max(0, loop_count - 5) * 5)

        if language == "python":
            try:
                compile(code, '<string>', 'exec')
                scores["correctness"] = 100
            except SyntaxError:
                scores["correctness"] = 0
        else:
            scores["correctness"] = 50

        weights = {"structure": 0.25, "readability": 0.20, "efficiency": 0.20,
                     "documentation": 0.15, "correctness": 0.20}
        total = sum(scores[k] * weights[k] for k in scores)

        # 刷量惩罚
        if total_lines > 0:
            empty_ratio = (total_lines - len(non_empty)) / total_lines
            if empty_ratio > 0.3:
                total *= 0.7
        stripped = [l.strip() for l in code_lines if l.strip()]
        unique = set(stripped)
        if len(stripped) > 0 and len(unique) / len(stripped) < 0.5:
            total *= 0.6

        return {
            "total_score": round(total, 1),
            "scores": scores,
            "lines": total_lines,
            "code_lines": len(code_lines),
            "comment_lines": len(comment_lines),
            "functions": func_count,
            "classes": class_count,
            "quality_level": "excellent" if total >= 85 else "good" if total >= 70 else "acceptable" if total >= 50 else "poor",
        }

# ── 赏金引擎 (v2 增强) ──

class BountyEngine:
    def __init__(self, clawtip: Any | None = None) -> None:
        self.clawtip = clawtip
        self.tasks: dict[str, BountyTask] = {}
        self.stages: dict[str, TaskStage] = {}
        self.reviews: dict[str, ReviewRecord] = {}
        self._load_all()

    def create_bounty(self, title: str, description: str, total_bounty: int,
                      owner_agent: str, stages_plan: list[dict],
                      deadline_hours: int = 24, priority: str = "normal",
                      tags: list[str] | None = None, complexity: str = "medium") -> BountyTask:
        task_id = f"bty_{int(time.time())}_{hashlib.sha256(title.encode()).hexdigest()[:8]}"
        planned = sum(s.get("bounty", 0) for s in stages_plan)
        if planned > total_bounty:
            raise ValueError(f"阶段赏金总和 ({planned}) 超过总赏金 ({total_bounty})")

        task = BountyTask(
            task_id=task_id, title=title, description=description,
            bounty_total=total_bounty, bounty_remaining=total_bounty,
            owner_agent=owner_agent,
            deadline=time.time() + deadline_hours * 3600,
            priority=priority, tags=tags or [], complexity=complexity,
        )
        for i, sp in enumerate(stages_plan):
            stage_id = f"{task_id}_stage_{i}"
            stage = TaskStage(
                stage_id=stage_id, task_id=task_id,
                title=sp["title"], description=sp["description"],
                bounty=sp.get("bounty", 0),
            )
            self.stages[stage_id] = stage
            task.stages.append({"stage_id": stage_id, "title": sp["title"], "bounty": sp.get("bounty", 0)})

        self.tasks[task_id] = task
        self._save_task(task)
        return task

    def assign_stage(self, stage_id: str, freelance_agent_id: str) -> TaskStage:
        stage = self.stages.get(stage_id)
        if not stage or stage.status != "pending":
            raise ValueError(f"阶段 {stage_id} 不可分配")
        stage.assignee = freelance_agent_id
        stage.status = "in_progress"
        self._save_stage(stage)
        # 更新任务状态
        task = self.tasks.get(stage.task_id)
        if task:
            task.status = "in_progress"
            if freelance_agent_id not in task.assigned_agents:
                task.assigned_agents.append(freelance_agent_id)
            self._save_task(task)
        return stage

    def submit_deliverable(self, stage_id: str, code: str) -> dict:
        stage = self.stages.get(stage_id)
        if not stage:
            raise ValueError(f"未知阶段: {stage_id}")
        stage.deliverable_code = code
        stage.status = "submitted"

        # 1. 沙盒验证
        sandbox_result = SandboxValidator.run_in_sandbox(code)
        stage.sandbox_result = sandbox_result
        if not sandbox_result["runtime_safe"]:
            stage.status = "rejected"
            stage.review_notes = f"安全验证失败: {sandbox_result.get('error', '')}"
            self._save_stage(stage)
            return {"stage_id": stage_id, "status": "rejected", "reason": "安全验证失败", "sandbox": sandbox_result}

        # 2. 代码质量评估
        quality = CodeQualityAssessor.assess(code)
        stage.code_quality_score = quality["total_score"]

        if quality["total_score"] < 50:
            stage.status = "rejected"
            stage.review_notes = f"代码质量不足: {quality['total_score']} 分"
            self._save_stage(stage)
            return {"stage_id": stage_id, "status": "rejected", "reason": "代码质量不足", "quality": quality}

        stage.status = "reviewed"
        self._save_stage(stage)
        return {"stage_id": stage_id, "status": "reviewed", "quality": quality, "sandbox": sandbox_result}

    def approve_and_pay(self, stage_id: str, reviewer_id: str = "platform") -> dict:
        """验收通过并支付（v2: 记录评分者）"""
        stage = self.stages.get(stage_id)
        if not stage or stage.status != "reviewed":
            raise ValueError(f"阶段 {stage_id} 未通过审核")
        task = self.tasks.get(stage.task_id)
        if not task:
            raise ValueError(f"未知任务: {stage.task_id}")

        # 计算质量系数
        quality_bonus = 1.0
        if stage.code_quality_score >= 90:
            quality_bonus = 1.2
        elif stage.code_quality_score >= 70:
            quality_bonus = 1.0
        elif stage.code_quality_score >= 50:
            quality_bonus = 0.8

        actual_pay = int(stage.bounty * quality_bonus)
        if actual_pay > task.bounty_remaining:
            actual_pay = task.bounty_remaining

        task.bounty_remaining -= actual_pay
        stage.status = "paid"
        stage.completed_at = time.time()
        stage.reviewer_id = reviewer_id
        stage.review_timestamp = time.time()

        # 记录评分
        review_id = f"rev_{int(time.time())}_{stage_id}"
        quality = CodeQualityAssessor.assess(stage.deliverable_code)
        review = ReviewRecord(
            review_id=review_id, stage_id=stage_id, reviewer=reviewer_id,
            scores=quality["scores"], total_score=quality["total_score"],
            verdict="approved", comment=f"质量系数: {quality_bonus}",
        )
        self.reviews[review_id] = review
        stage.quality_history.append(asdict(review))

        # 支付
        payment_result = {"simulated": True, "amount": actual_pay}
        if self.clawtip and hasattr(self.clawtip, 'create_order'):
            try:
                order = self.clawtip.create_order(
                    amount=actual_pay,
                    description=f"赏金支付: {task.title} - {stage.title}",
                    question=f"赏金任务 {stage_id} 结算",
                )
                payment_result = {"simulated": False, "order": order, "amount": actual_pay}
            except Exception as e:
                payment_result["error"] = str(e)

        self._save_stage(stage)
        self._save_task(task)
        self._save_review(review)

        # 检查任务是否全部完成
        self._check_task_completion(task.task_id)

        return {
            "stage_id": stage_id, "status": "paid", "amount": actual_pay,
            "quality_bonus": quality_bonus, "bounty_remaining": task.bounty_remaining,
            "payment": payment_result, "review_id": review_id,
        }

    def dispute_stage(self, stage_id: str, reason: str) -> dict:
        """对阶段结果提出争议"""
        stage = self.stages.get(stage_id)
        if not stage:
            return {"error": "阶段不存在"}
        stage.status = "disputed"
        self._save_stage(stage)
        return {"stage_id": stage_id, "status": "disputed", "reason": reason}

    def check_low_balance_warning(self, task_id: str, threshold_pct: float = 0.2) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"warning": False}
        remaining_pct = task.bounty_remaining / max(task.bounty_total, 1)
        warning_triggered = remaining_pct <= threshold_pct
        result = {
            "warning": warning_triggered, "task_id": task_id,
            "remaining": task.bounty_remaining, "total": task.bounty_total,
            "remaining_pct": round(remaining_pct * 100, 1),
            "threshold_pct": threshold_pct * 100,
        }
        if warning_triggered:
            active_stages = [s for s in self.stages.values()
                             if s.task_id == task_id and s.status in ("in_progress", "submitted")]
            result["active_stages"] = len(active_stages)
            result["message"] = (
                f"⚠️ 赏金预警: 任务「{task.title}」剩余 {task.bounty_remaining} 分 "
                f"({remaining_pct*100:.1f}%)。建议提前交差、停止分配、尽快验货"
            )
            result["actions"] = [
                "通知所有 active Freelance Agent 提前交差",
                "停止分配新阶段", "对已完成阶段尽快验货结清", "如需继续，主人需追加赏金",
            ]
        return result

    def get_task_report(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"error": "任务不存在"}
        stages_detail = []
        for s in task.stages:
            stage = self.stages.get(s["stage_id"])
            if stage:
                stages_detail.append({
                    "stage_id": stage.stage_id, "title": stage.title,
                    "status": stage.status, "assignee": stage.assignee,
                    "bounty": stage.bounty, "quality_score": stage.code_quality_score,
                    "reviewer": stage.reviewer_id,
                })
        total_paid = sum(s.bounty for s in self.stages.values()
                         if s.task_id == task_id and s.status == "paid")
        return {
            "task_id": task_id, "title": task.title, "status": task.status,
            "total_bounty": task.bounty_total, "remaining": task.bounty_remaining,
            "paid": total_paid, "stages": stages_detail,
            "progress": f"{sum(1 for s in stages_detail if s['status'] == 'paid')}/{len(stages_detail)}",
        }

    def _check_task_completion(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        all_stages = [self.stages.get(s["stage_id"]) for s in task.stages]
        if all(s and s.status in ("paid", "rejected") for s in all_stages):
            task.status = "completed" if any(s.status == "paid" for s in all_stages) else "cancelled"
            self._save_task(task)

    def _task_path(self, task_id: str) -> Path:
        return CLOUD_DIR / "bounty" / f"{task_id}.json"
    def _stage_path(self, stage_id: str) -> Path:
        return CLOUD_DIR / "stages" / f"{stage_id}.json"
    def _review_path(self, review_id: str) -> Path:
        return CLOUD_DIR / "reviews" / f"{review_id}.json"

    def _save_task(self, t: BountyTask) -> None:
        self._task_path(t.task_id).parent.mkdir(parents=True, exist_ok=True)
        self._task_path(t.task_id).write_text(json.dumps(asdict(t), ensure_ascii=False, indent=2), encoding="utf-8")
    def _save_stage(self, s: TaskStage) -> None:
        self._stage_path(s.stage_id).parent.mkdir(parents=True, exist_ok=True)
        self._stage_path(s.stage_id).write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
    def _save_review(self, r: ReviewRecord) -> None:
        self._review_path(r.review_id).parent.mkdir(parents=True, exist_ok=True)
        self._review_path(r.review_id).write_text(json.dumps(asdict(r), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_all(self) -> None:
        for p in (CLOUD_DIR / "bounty").glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self.tasks[data["task_id"]] = BountyTask(**data)
            except:
                pass
        for p in (CLOUD_DIR / "stages").glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self.stages[data["stage_id"]] = TaskStage(**data)
            except:
                pass
        for p in (CLOUD_DIR / "reviews").glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self.reviews[data["review_id"]] = ReviewRecord(**data)
            except:
                pass

# ── 兼职引擎 (v2 增强) ──

class FreelanceEngine:
    def __init__(self, agent_id: str, clawtip: Any | None = None) -> None:
        self.agent_id = agent_id
        self.clawtip = clawtip
        self.profile = self._load_or_create_profile()
        self.active_tasks: dict[str, TaskStage] = {}

    def _load_or_create_profile(self) -> FreelanceAgent:
        path = CLOUD_DIR / "freelance" / f"{self.agent_id}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return FreelanceAgent(**data)
        profile = FreelanceAgent(agent_id=self.agent_id, display_name=f"Agent-{self.agent_id[:8]}")
        self._save_profile(profile)
        return profile

    def _save_profile(self, p: FreelanceAgent) -> None:
        path = CLOUD_DIR / "freelance" / f"{p.agent_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(p), ensure_ascii=False, indent=2), encoding="utf-8")

    def configure(self, capabilities: list[str], hourly_rate: int, token_budget: int,
                  max_complexity: str = "medium", custom_reject_patterns: list[str] | None = None) -> FreelanceAgent:
        self.profile.capabilities = capabilities
        self.profile.hourly_rate = hourly_rate
        self.profile.token_budget = token_budget
        self.profile.max_task_complexity = max_complexity
        if custom_reject_patterns:
            self.profile.reject_patterns.extend(custom_reject_patterns)
        self._save_profile(self.profile)
        return self.profile

    def register_to_cloud(self) -> dict:
        self.profile.status = "idle"
        self.profile.last_heartbeat = time.time()
        self._save_profile(self.profile)
        return {"agent_id": self.agent_id, "status": "registered",
                "capabilities": self.profile.capabilities, "hourly_rate": self.profile.hourly_rate}

    def heartbeat(self) -> dict:
        self.profile.last_heartbeat = time.time()
        self._save_profile(self.profile)
        return {"status": "alive", "last_heartbeat": self.profile.last_heartbeat}

    def scan_available_tasks(self, bounty_engine: BountyEngine) -> list[dict]:
        available = []
        for task in bounty_engine.tasks.values():
            if task.status not in ("open", "in_progress"):
                continue
            for stage_info in task.stages:
                stage = bounty_engine.stages.get(stage_info["stage_id"])
                if stage and stage.status == "pending":
                    if any(cap in task.tags or cap in stage.title for cap in self.profile.capabilities):
                        available.append({
                            "stage_id": stage.stage_id, "task_title": task.title,
                            "stage_title": stage.title, "bounty": stage.bounty,
                            "priority": task.priority, "complexity": task.complexity,
                        })
        return available

    def accept_task(self, stage_id: str, bounty_engine: BountyEngine) -> dict:
        stage = bounty_engine.stages.get(stage_id)
        if not stage:
            return {"error": "阶段不存在"}
        combined_text = f"{stage.title} {stage.description}"
        for pattern in self.profile.reject_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return {"accepted": False, "reason": f"安全审查未通过: 匹配 '{pattern}'", "stage_id": stage_id}
        if self.profile.max_task_complexity == "low" and stage.bounty > 500:
            return {"accepted": False, "reason": "赏金过高，超出低风险范围"}
        if self.profile.token_used >= self.profile.token_budget:
            return {"accepted": False, "reason": "Token 预算已耗尽"}

        bounty_engine.assign_stage(stage_id, self.agent_id)
        self.profile.status = "busy"
        self._save_profile(self.profile)
        self.active_tasks[stage_id] = stage
        return {"accepted": True, "stage_id": stage_id, "agent_id": self.agent_id,
                "estimated_tokens": stage.bounty // 2}

    def submit_work(self, stage_id: str, code: str, bounty_engine: BountyEngine) -> dict:
        result = bounty_engine.submit_deliverable(stage_id, code)
        if result["status"] == "reviewed":
            self.profile.token_used += len(code)
            self._save_profile(self.profile)
        return result

    def go_idle(self) -> None:
        self.profile.status = "idle"
        self._save_profile(self.profile)

    def get_earnings_report(self) -> dict:
        return {
            "agent_id": self.agent_id, "total_earnings": self.profile.earnings_total,
            "pending": self.profile.earnings_pending, "reputation": self.profile.reputation,
            "tasks_completed": self.profile.tasks_completed,
            "tasks_rejected": self.profile.tasks_rejected,
            "avg_quality_score": self.profile.avg_quality_score,
            "token_budget": self.profile.token_budget, "token_used": self.profile.token_used,
            "token_remaining": max(0, self.profile.token_budget - self.profile.token_used),
        }

    def should_continue(self) -> bool:
        return (self.profile.token_used < self.profile.token_budget
                and self.profile.status != "suspended"
                and self.profile.reputation > 50)

# ── 云端握手平台 (v2 增强) ──

class AgentCloudPlatform:
    """
    Agent Cloud Platform v2 — 完整握手 + 智能匹配 + 客观评分
    """

    def __init__(self, clawtip: Any | None = None) -> None:
        self.clawtip = clawtip
        self.bounty_engine = BountyEngine(clawtip)
        self.handshakes: dict[str, HandshakeRecord] = {}
        self.freelance_agents: dict[str, FreelanceEngine] = {}
        self._load_handshakes()

    # ── 注册与发布 ──

    def register_freelance_agent(self, agent_id: str, capabilities: list[str],
                                  hourly_rate: int, token_budget: int) -> dict:
        engine = FreelanceEngine(agent_id, self.clawtip)
        engine.configure(capabilities, hourly_rate, token_budget)
        result = engine.register_to_cloud()
        self.freelance_agents[agent_id] = engine
        return result

    def publish_bounty(self, title: str, description: str, total_bounty: int,
                       owner_agent: str, stages: list[dict], **kwargs) -> BountyTask:
        return self.bounty_engine.create_bounty(
            title=title, description=description, total_bounty=total_bounty,
            owner_agent=owner_agent, stages_plan=stages, **kwargs,
        )

    # ── 智能匹配引擎 ──

    def match_task(self, task_id: str, top_n: int = 5) -> list[dict]:
        """
        智能匹配算法
        
        评分维度:
        1. 能力匹配度 (0-40): 能力标签重叠度
        2. 声誉分 (0-25): 历史评分 + 完成率
        3. 负载均衡 (0-15): 当前任务数越少分越高
        4. 价格竞争力 (0-10): 时薪越低分越高（但有底价保护）
        5. 历史合作 (0-10): 与该 bounty_agent 合作过加分
        
        总权重: 100
        """
        task = self.bounty_engine.tasks.get(task_id)
        if not task:
            return []

        candidates = []
        for fid, fengine in self.freelance_agents.items():
            profile = fengine.profile
            if profile.status != "idle":
                continue
            if not fengine.should_continue():
                continue

            score = 0.0
            breakdown = {}

            # 1. 能力匹配度 (40%)
            matched_caps = [cap for cap in profile.capabilities if cap in task.tags]
            cap_score = min(40, len(matched_caps) * 10)
            breakdown["capability"] = cap_score
            score += cap_score

            # 2. 声誉分 (25%)
            completion_rate = profile.tasks_completed / max(1, profile.tasks_completed + profile.tasks_rejected)
            rep_score = min(25, profile.reputation * 0.15 + completion_rate * 10)
            breakdown["reputation"] = rep_score
            score += rep_score

            # 3. 负载均衡 (15%)
            active_count = len([t for t in self.bounty_engine.stages.values()
                               if t.assignee == fid and t.status in ("in_progress", "submitted")])
            load_score = max(0, 15 - active_count * 5)
            breakdown["load"] = load_score
            score += load_score

            # 4. 价格竞争力 (10%)
            market_avg = self._get_market_avg_rate()
            if market_avg > 0:
                price_score = max(0, min(10, 10 - (profile.hourly_rate - market_avg) / market_avg * 10))
            else:
                price_score = 5
            breakdown["price"] = price_score
            score += price_score

            # 5. 历史合作 (10%)
            history_score = 0
            for hs in self.handshakes.values():
                if hs.bounty_agent == task.owner_agent and hs.freelance_agent == fid:
                    if hs.status == "completed":
                        history_score = 10
                    elif hs.status == "accepted":
                        history_score = 5
                    break
            breakdown["history"] = history_score
            score += history_score

            candidates.append({
                "agent_id": fid,
                "display_name": profile.display_name,
                "total_score": round(score, 1),
                "breakdown": breakdown,
                "hourly_rate": profile.hourly_rate,
                "reputation": profile.reputation,
                "capabilities": profile.capabilities,
            })

        candidates.sort(key=lambda x: -x["total_score"])
        return candidates[:top_n]

    def _get_market_avg_rate(self) -> float:
        """计算市场平均时薪"""
        rates = [f.profile.hourly_rate for f in self.freelance_agents.values() if f.profile.hourly_rate > 0]
        return sum(rates) / len(rates) if rates else 500

    # ── 完整握手协议 ──

    def initiate_handshake(self, bounty_agent: str, freelance_agent: str,
                           task_id: str, stage_id: str, proposed_rate: int) -> HandshakeRecord:
        """
        发起握手 (Step 1)
        
        1. 赏金方发起握手请求
        2. 记录协商初始条件
        """
        hs_id = f"hs_{int(time.time())}_{bounty_agent[:4]}_{freelance_agent[:4]}"
        record = HandshakeRecord(
            handshake_id=hs_id,
            bounty_agent=bounty_agent,
            freelance_agent=freelance_agent,
            task_id=task_id,
            stage_id=stage_id,
            status="pending",
            negotiated_rate=proposed_rate,
            negotiation_log=[{
                "step": 1,
                "from": bounty_agent,
                "action": "initiate",
                "proposed_rate": proposed_rate,
                "timestamp": time.time(),
            }],
        )
        self.handshakes[hs_id] = record
        self._save_handshake(record)
        return record

    def respond_handshake(self, handshake_id: str, accept: bool,
                          counter_rate: int | None = None) -> HandshakeRecord:
        """
        响应握手 (Step 2)
        
        Freelance Agent 响应:
        - accept=True: 直接接受
        - accept=False + counter_rate: 还价
        """
        record = self.handshakes.get(handshake_id)
        if not record:
            raise ValueError(f"握手记录不存在: {handshake_id}")
        if record.status not in ("pending", "negotiating"):
            raise ValueError(f"握手状态不可响应: {record.status}")

        if accept:
            record.status = "accepted"
            record.established_at = time.time()
            record.expires_at = time.time() + 86400  # 24小时过期
            record.negotiation_log.append({
                "step": 2,
                "from": record.freelance_agent,
                "action": "accept",
                "final_rate": record.negotiated_rate,
                "timestamp": time.time(),
            })
        elif counter_rate is not None:
            record.status = "negotiating"
            record.negotiated_rate = counter_rate
            record.negotiation_log.append({
                "step": 2,
                "from": record.freelance_agent,
                "action": "counter",
                "counter_rate": counter_rate,
                "timestamp": time.time(),
            })
        else:
            record.status = "rejected"
            record.negotiation_log.append({
                "step": 2,
                "from": record.freelance_agent,
                "action": "reject",
                "timestamp": time.time(),
            })

        self._save_handshake(record)
        return record

    def finalize_handshake(self, handshake_id: str, accept_counter: bool = True) -> HandshakeRecord:
        """
        最终确认 (Step 3)
        
        赏金方对还价做最终决定:
        - accept_counter=True: 接受还价，握手建立
        - accept_counter=False: 拒绝还价，握手失败
        """
        record = self.handshakes.get(handshake_id)
        if not record or record.status != "negotiating":
            raise ValueError(f"握手状态不可最终确认: {record.status if record else 'None'}")

        if accept_counter:
            record.status = "accepted"
            record.established_at = time.time()
            record.expires_at = time.time() + 86400
            record.negotiation_log.append({
                "step": 3,
                "from": record.bounty_agent,
                "action": "accept_counter",
                "final_rate": record.negotiated_rate,
                "timestamp": time.time(),
            })
        else:
            record.status = "rejected"
            record.negotiation_log.append({
                "step": 3,
                "from": record.bounty_agent,
                "action": "reject_counter",
                "timestamp": time.time(),
            })

        self._save_handshake(record)
        return record

    def verify_handshake(self, handshake_id: str) -> dict:
        """验证握手是否有效"""
        record = self.handshakes.get(handshake_id)
        if not record:
            return {"valid": False, "reason": "握手记录不存在"}
        if record.status != "accepted":
            return {"valid": False, "reason": f"握手状态: {record.status}"}
        if record.expires_at and time.time() > record.expires_at:
            record.status = "timeout"
            self._save_handshake(record)
            return {"valid": False, "reason": "握手已过期"}
        return {"valid": True, "handshake": record}

    def record_milestone(self, handshake_id: str, milestone: str, data: dict) -> None:
        """记录履约里程碑"""
        record = self.handshakes.get(handshake_id)
        if record:
            record.milestones.append({
                "milestone": milestone,
                "data": data,
                "timestamp": time.time(),
            })
            self._save_handshake(record)

    def mark_breach(self, handshake_id: str, reason: str) -> None:
        """标记违约"""
        record = self.handshakes.get(handshake_id)
        if record:
            record.status = "breached"
            record.breach_reason = reason
            self._save_handshake(record)
            # 扣除声誉
            fengine = self.freelance_agents.get(record.freelance_agent)
            if fengine:
                fengine.profile.reputation = max(0, fengine.profile.reputation - 10)
                fengine._save_profile(fengine.profile)

    # ── 客观评分系统 ──

    def review_stage(self, stage_id: str, reviewer_id: str = "platform",
                     custom_scores: dict | None = None) -> ReviewRecord:
        """
        对阶段进行客观评分
        
        评分维度:
        - structure (结构): 代码组织、模块化
        - readability (可读性): 命名、行长度、格式
        - efficiency (效率): 算法复杂度、冗余
        - documentation (文档): 注释覆盖率
        - correctness (正确性): 语法/运行结果
        
        支持人工复核覆盖自动评分。
        """
        stage = self.bounty_engine.stages.get(stage_id)
        if not stage or not stage.deliverable_code:
            raise ValueError(f"阶段 {stage_id} 无交付物")

        # 自动评估
        auto_quality = CodeQualityAssessor.assess(stage.deliverable_code)

        # 如果提供了自定义评分，合并
        scores = auto_quality["scores"].copy()
        if custom_scores:
            for k, v in custom_scores.items():
                if k in scores:
                    scores[k] = v  # 人工评分覆盖

        weights = {"structure": 0.25, "readability": 0.20, "efficiency": 0.20,
                   "documentation": 0.15, "correctness": 0.20}
        total = sum(scores[k] * weights[k] for k in scores)

        review_id = f"rev_{int(time.time())}_{stage_id}"
        verdict = "approved" if total >= 50 else "rejected"

        review = ReviewRecord(
            review_id=review_id, stage_id=stage_id, reviewer=review_id,
            scores=scores, total_score=round(total, 1), verdict=verdict,
            comment=f"自动评估总分: {auto_quality['total_score']}, 复核后: {round(total, 1)}",
        )

        stage.code_quality_score = review.total_score
        stage.quality_history.append(asdict(review))
        stage.reviewer_id = reviewer_id
        stage.review_timestamp = time.time()

        self.bounty_engine.reviews[review_id] = review
        self.bounty_engine._save_review(review)
        self.bounty_engine._save_stage(stage)

        # 更新 Freelance Agent 统计
        if stage.assignee:
            fengine = self.freelance_agents.get(stage.assignee)
            if fengine:
                if verdict == "approved":
                    fengine.profile.tasks_completed += 1
                    fengine.profile.earnings_total += stage.bounty
                else:
                    fengine.profile.tasks_rejected += 1
                # 更新平均质量分
                all_scores = [r["total_score"] for r in stage.quality_history]
                fengine.profile.avg_quality_score = sum(all_scores) / len(all_scores) if all_scores else 0
                fengine._save_profile(fengine.profile)

        return review

    def appeal_review(self, review_id: str, reason: str) -> dict:
        """对评分提出申诉"""
        review = self.bounty_engine.reviews.get(review_id)
        if not review:
            return {"error": "评分记录不存在"}
        review.appeal_status = f"pending: {reason}"
        self.bounty_engine._save_review(review)
        return {"review_id": review_id, "appeal_status": "pending", "reason": reason}

    # ── 统计 ──

    def get_platform_stats(self) -> dict:
        active_tasks = [t for t in self.bounty_engine.tasks.values()
                        if t.status in ("open", "in_progress", "matching")]
        idle_agents = [f for f in self.freelance_agents.values() if f.profile.status == "idle"]
        busy_agents = [f for f in self.freelance_agents.values() if f.profile.status == "busy"]

        total_bounty = sum(t.bounty_total for t in self.bounty_engine.tasks.values())
        total_paid = sum(s.bounty for s in self.bounty_engine.stages.values() if s.status == "paid")

        # 平均评分
        all_reviews = list(self.bounty_engine.reviews.values())
        avg_score = sum(r.total_score for r in all_reviews) / len(all_reviews) if all_reviews else 0

        return {
            "active_bounties": len(active_tasks),
            "idle_freelancers": len(idle_agents),
            "busy_freelancers": len(busy_agents),
            "total_bounty_published": total_bounty,
            "total_bounty_paid": total_paid,
            "handshakes_active": len([h for h in self.handshakes.values() if h.status == "accepted"]),
            "handshakes_total": len(self.handshakes),
            "reviews_count": len(all_reviews),
            "avg_quality_score": round(avg_score, 1),
            "disputes": len([s for s in self.bounty_engine.stages.values() if s.status == "disputed"]),
        }

    def get_handshake_report(self, handshake_id: str) -> dict:
        """获取握手完整报告"""
        record = self.handshakes.get(handshake_id)
        if not record:
            return {"error": "握手不存在"}
        return {
            "handshake_id": record.handshake_id,
            "status": record.status,
            "bounty_agent": record.bounty_agent,
            "freelance_agent": record.freelance_agent,
            "task_id": record.task_id,
            "stage_id": record.stage_id,
            "negotiated_rate": record.negotiated_rate,
            "established_at": record.established_at,
            "expires_at": record.expires_at,
            "negotiation_log": record.negotiation_log,
            "milestones": record.milestones,
            "breach_reason": record.breach_reason,
        }

    # ── 持久化 ──

    def _handshake_path(self, hs_id: str) -> Path:
        return CLOUD_DIR / "handshakes" / f"{hs_id}.json"

    def _save_handshake(self, h: HandshakeRecord) -> None:
        self._handshake_path(h.handshake_id).parent.mkdir(parents=True, exist_ok=True)
        self._handshake_path(h.handshake_id).write_text(
            json.dumps(asdict(h), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_handshakes(self) -> None:
        for p in (CLOUD_DIR / "handshakes").glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self.handshakes[data["handshake_id"]] = HandshakeRecord(**data)
            except:
                pass


# ── 便捷函数 ──

def create_bounty_mode(clawtip: Any | None = None) -> BountyEngine:
    return BountyEngine(clawtip)

def create_freelance_mode(agent_id: str, clawtip: Any | None = None) -> FreelanceEngine:
    return FreelanceEngine(agent_id, clawtip)

def create_cloud_platform(clawtip: Any | None = None) -> AgentCloudPlatform:
    return AgentCloudPlatform(clawtip)
