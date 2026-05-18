"""
预判系统模块 (Pre-flight / Predictive Diagnostics)

基于 Claw 的问题诊断经验，在 Agent 执行前检测潜在风险：
- 网络连通性 (API 超时 / DNS / 代理)
- Token 预算超限 (输入+预估输出 > budget)
- 权限/路径问题 (文件不可写、目录不存在)
- 并发过载 (活跃子 Agent 数接近上限)
- 历史故障模式匹配 (相同错误曾发生)

经验来源: OpenClaw 实际运行中的常见问题诊断。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """风险等级"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PreFlightIssue:
    """预判发现的问题"""
    category: str  # network / token / permission / concurrency / history
    risk_level: RiskLevel
    message: str
    suggestion: str
    auto_fixable: bool = False
    fix_action: str | None = None  # 自动修复时要执行的操作描述


@dataclass
class PreFlightResult:
    """预判结果"""
    passed: bool
    issues: list[PreFlightIssue] = field(default_factory=list)
    warnings: list[PreFlightIssue] = field(default_factory=list)
    auto_fixed: list[str] = field(default_factory=list)  # 已自动修复的问题描述


class PreFlightChecker:
    """预判检查器

    在执行前扫描所有已知风险点，基于历史经验库预判故障。
    支持自动修复低风险问题（如创建缺失目录、调整超时等）。
    """

    # 经验库: 常见故障模式 (从 OpenClaw 实际运行中积累)
    KNOWN_FAILURE_PATTERNS: dict[str, dict[str, Any]] = {
        "token_overflow": {
            "description": "输入+预估输出超过预算",
            "check": lambda ctx: ctx.get("estimated_tokens", 0) > ctx.get("budget_tokens", 1_000_000),
            "risk": RiskLevel.HIGH,
            "message": "预估 Token 消耗 ({estimated_tokens}) 超过预算 ({budget_tokens})",
            "suggestion": "拆分任务为多个子任务，或提高 budget_limit",
            "auto_fixable": False,
        },
        "missing_api_key": {
            "description": "API Key 未配置",
            "check": lambda ctx: not ctx.get("api_key"),
            "risk": RiskLevel.CRITICAL,
            "message": "API Key 未配置 (MOONSHOT_API_KEY 为空)",
            "suggestion": "运行 kimix auth 配置 API Key",
            "auto_fixable": False,
        },
        "api_key_suspicious_format": {
            "description": "API Key 格式可疑",
            "check": lambda ctx: bool(ctx.get("api_key")) and not str(ctx.get("api_key")).startswith("sk-"),
            "risk": RiskLevel.HIGH,
            "message": "API Key 格式不正确，应以 'sk-' 开头",
            "suggestion": "检查 API Key 是否复制完整",
            "auto_fixable": False,
        },
        "dir_not_exists": {
            "description": "工作目录不存在",
            "check": lambda ctx: bool(ctx.get("workspace_dir")) and not os.path.exists(ctx.get("workspace_dir", "")),
            "risk": RiskLevel.MEDIUM,
            "message": "工作目录不存在: {workspace_dir}",
            "suggestion": "自动创建工作目录",
            "auto_fixable": True,
            "fix_action": "mkdir_workspace",
        },
        "file_not_writable": {
            "description": "目标文件不可写",
            "check": lambda ctx: _check_not_writable(ctx.get("target_file")),
            "risk": RiskLevel.HIGH,
            "message": "目标文件不可写: {target_file}",
            "suggestion": "检查文件权限或更换输出路径",
            "auto_fixable": False,
        },
        "concurrency_high": {
            "description": "并发子 Agent 接近上限",
            "check": lambda ctx: ctx.get("active_subagents", 0) >= ctx.get("max_concurrent", 32) * 0.8,
            "risk": RiskLevel.MEDIUM,
            "message": "活跃子 Agent ({active_subagents}/{max_concurrent}) 接近上限，新任务可能排队",
            "suggestion": "等待部分任务完成，或提高 max_concurrent",
            "auto_fixable": False,
        },
        "history_similar_failure": {
            "description": "历史相同故障模式",
            "check": lambda ctx: ctx.get("experience_memory", {}).has_similar(ctx.get("task_signature", "")),
            "risk": RiskLevel.MEDIUM,
            "message": "该任务类型曾在 {time} 失败: {reason}",
            "suggestion": "参考历史修复方案: {fix}",
            "auto_fixable": False,
        },
        "network_no_proxy_but_needed": {
            "description": "国内网络可能需要代理",
            "check": lambda ctx: _is_cn_network() and not ctx.get("proxy"),
            "risk": RiskLevel.LOW,
            "message": "检测到国内网络环境，未配置代理可能影响 API 连通性",
            "suggestion": "如 API 超时，可配置 HTTPS_PROXY 环境变量",
            "auto_fixable": False,
        },
    }

    def __init__(self, experience_memory: Any | None = None) -> None:
        self.experience_memory = experience_memory

    async def check(self, context: dict[str, Any]) -> PreFlightResult:
        """执行全量预判检查

        Args:
            context: 执行上下文，包含 api_key, budget_tokens, workspace_dir 等

        Returns:
            PreFlightResult: 预判结果（通过/问题/警告/自动修复）
        """
        issues: list[PreFlightIssue] = []
        warnings: list[PreFlightIssue] = []
        auto_fixed: list[str] = []

        for pattern_name, pattern in self.KNOWN_FAILURE_PATTERNS.items():
            try:
                if pattern["check"](context):
                    msg = pattern["message"].format(**context) if "{" in pattern["message"] else pattern["message"]
                    suggestion = pattern["suggestion"]

                    # 如果有历史经验，补充历史信息
                    if pattern_name == "history_similar_failure" and self.experience_memory:
                        record = self.experience_memory.get_similar(context.get("task_signature", ""))
                        if record:
                            msg = msg.format(time=record.time, reason=record.failure_reason)
                            suggestion = suggestion.format(fix=record.fix_action)

                    issue = PreFlightIssue(
                        category=pattern_name,
                        risk_level=pattern["risk"],
                        message=msg,
                        suggestion=suggestion,
                        auto_fixable=pattern.get("auto_fixable", False),
                        fix_action=pattern.get("fix_action"),
                    )

                    # 尝试自动修复
                    if issue.auto_fixable and issue.fix_action:
                        fixed = await self._try_auto_fix(issue.fix_action, context)
                        if fixed:
                            auto_fixed.append(msg)
                            continue  # 已修复，不加入 issues

                    # 分级
                    if pattern["risk"] in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                        issues.append(issue)
                    else:
                        warnings.append(issue)
            except Exception:
                # 预判检查本身不应阻塞执行
                continue

        # 网络连通性快速测试（非阻塞）
        if not context.get("skip_network_test"):
            network_ok = await self._quick_network_test(context.get("base_url", "https://api.kimi.com"))
            if not network_ok:
                issues.append(PreFlightIssue(
                    category="network",
                    risk_level=RiskLevel.HIGH,
                    message="API 服务器网络连通性测试失败",
                    suggestion="检查网络连接、代理配置或 API 服务状态",
                    auto_fixable=False,
                ))

        passed = len([i for i in issues if i.risk_level == RiskLevel.CRITICAL]) == 0
        return PreFlightResult(
            passed=passed,
            issues=issues,
            warnings=warnings,
            auto_fixed=auto_fixed,
        )

    async def _try_auto_fix(self, action: str, context: dict[str, Any]) -> bool:
        """尝试自动修复"""
        if action == "mkdir_workspace":
            dir_path = context.get("workspace_dir", "")
            if dir_path:
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    return True
                except OSError:
                    return False
        return False

    async def _quick_network_test(self, url: str, timeout: float = 3.0) -> bool:
        """快速网络连通性测试"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url.replace("/v1", "/"),
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    ssl=False,
                ):
                    return True
        except Exception:
            return False


def _check_not_writable(file_path: str | None) -> bool:
    """检查文件是否不可写"""
    if not file_path:
        return False
    if not os.path.exists(file_path):
        # 检查父目录是否可写
        parent = os.path.dirname(file_path) or "."
        return not os.access(parent, os.W_OK)
    return not os.access(file_path, os.W_OK)


def _is_cn_network() -> bool:
    """简单判断是否为国内网络环境"""
    import socket
    try:
        # 如果能直接解析 google.com 很快，可能不在国内
        socket.getaddrinfo("google.com", None, socket.AF_INET)
        return False
    except socket.gaierror:
        return True
