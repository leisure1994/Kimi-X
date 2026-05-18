#!/usr/bin/env python3
"""
自动经济模式提示系统 (Auto Economy Prompter)

功能:
1. 空闲检测: Agent 闲置3小时后，自动提示用户开启闲时兼职模式
2. 复杂度检测: 任务复杂度超过日常3倍时，询问是否开启赏金模式
3. 智能防打扰: 同一模式24小时内最多提示一次
4. ClawTip 状态检查: 未开通时自动引导开通流程
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

PROMPT_STATE_DIR = Path(os.path.expanduser("~/.kimix/auto_prompt"))
PROMPT_STATE_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class PromptRecord:
    """提示记录"""
    mode: str              # "freelance" | "bounty"
    prompted_at: float
    user_response: str = ""   # "accepted" | "declined" | "pending"
    clawtip_ready: bool = False
    

class IdleDetector:
    """
    空闲检测器
    
    检测 Agent 是否处于闲置状态。
    空闲定义: 无用户输入、无进行中的任务、无活跃对话。
    """

    def __init__(self, idle_threshold_seconds: float = 10800) -> None:  # 3小时
        self.idle_threshold = idle_threshold_seconds
        self.last_activity: float = time.time()
        self.state_path = PROMPT_STATE_DIR / "idle_state.json"
        self._load()

    def record_activity(self, activity_type: str = "user_input") -> None:
        """记录任何活动，重置空闲计时器"""
        self.last_activity = time.time()
        self._save()

    def get_idle_seconds(self) -> float:
        """获取当前已空闲秒数"""
        return time.time() - self.last_activity

    def is_idle_long_enough(self) -> bool:
        """是否已达到提示阈值"""
        return self.get_idle_seconds() >= self.idle_threshold

    def get_idle_human_readable(self) -> str:
        """人类可读的空闲时长"""
        secs = self.get_idle_seconds()
        hours = int(secs // 3600)
        mins = int((secs % 3600) // 60)
        if hours > 0:
            return f"{hours}小时{mins}分钟"
        return f"{mins}分钟"

    def _save(self) -> None:
        data = {"last_activity": self.last_activity, "threshold": self.idle_threshold}
        self.state_path.write_text(json.dumps(data), encoding="utf-8")

    def _load(self) -> None:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.last_activity = data.get("last_activity", time.time())
            except:
                pass


class TaskComplexityEstimator:
    """
    任务复杂度评估器
    
    多维度评估任务复杂度:
    - 输入长度（字数/代码行数）
    - 涉及文件数量
    - 需要的工具调用数
    - 预估步骤数
    - 历史同类型任务平均复杂度
    
    复杂度评分: 0-100
    """

    def __init__(self, baseline_window: int = 20) -> None:
        """
        Args:
            baseline_window: 用于计算日常基线的最近任务数
        """
        self.baseline_window = baseline_window
        self.history_path = PROMPT_STATE_DIR / "complexity_history.jsonl"
        self._history: list[dict] = []
        self._load_history()

    def estimate(self, user_input: str, 
                 estimated_files: int = 0,
                 estimated_tools: int = 0,
                 estimated_steps: int = 0) -> dict[str, Any]:
        """
        评估任务复杂度
        
        返回包含 score (0-100) 和 breakdown 的字典。
        """
        # 1. 文本长度分 (0-30)
        text_len = len(user_input)
        code_lines = user_input.count('\n')
        length_score = min(30, text_len / 50 + code_lines / 5)

        # 2. 文件操作分 (0-20)
        file_indicators = [
            '文件', '目录', 'folder', 'file', '路径', 'path',
            '批量', '批量处理', '批量修改', '多个文件',
            '项目', '仓库', 'repo', 'repository',
        ]
        file_score = min(20, estimated_files * 4 + sum(1 for w in file_indicators if w in user_input))

        # 3. 工具调用分 (0-20)
        tool_indicators = [
            '搜索', '查询', '调用', 'API', '接口',
            '数据库', '爬取', '抓取', '自动化',
            '测试', '部署', '构建', '编译',
        ]
        tool_score = min(20, estimated_tools * 5 + sum(1 for w in tool_indicators if w in user_input) * 2)

        # 4. 步骤预估分 (0-20)
        step_indicators = [
            '步骤', '流程', '先', '然后', '接着', '最后',
            '第一步', '第二步', '阶段', 'phase', 'stage',
            '设计', '实现', '测试', '部署', '优化', '重构',
        ]
        step_score = min(20, estimated_steps * 3 + sum(1 for w in step_indicators if w in user_input))

        # 5. 语义复杂度分 (0-10)
        complex_indicators = [
            '架构', '系统设计', 'microservice', '分布式',
            '并发', '异步', '缓存', '队列', '数据库',
            '安全', '加密', '认证', '授权',
            '集成', '迁移', '升级', '兼容',
        ]
        semantic_score = min(10, sum(1 for w in complex_indicators if w in user_input) * 2)

        total_score = length_score + file_score + tool_score + step_score + semantic_score
        total_score = min(100, total_score)

        result = {
            "score": round(total_score, 1),
            "breakdown": {
                "length": round(length_score, 1),
                "files": round(file_score, 1),
                "tools": round(tool_score, 1),
                "steps": round(step_score, 1),
                "semantic": round(semantic_score, 1),
            },
            "is_complex": False,
            "baseline": 0.0,
            "ratio": 1.0,
        }

        # 与基线比较
        if len(self._history) >= 3:
            baseline = self._get_baseline()
            result["baseline"] = round(baseline, 1)
            if baseline > 0:
                result["ratio"] = round(total_score / baseline, 2)
                result["is_complex"] = result["ratio"] >= 3.0

        # 记录到历史
        self._record(user_input, result)
        return result

    def _get_baseline(self) -> float:
        """计算日常基线（最近N个任务的平均复杂度）"""
        if not self._history:
            return 0.0
        recent = self._history[-self.baseline_window:]
        return sum(h["score"] for h in recent) / len(recent)

    def _record(self, user_input: str, result: dict) -> None:
        """记录任务复杂度"""
        record = {
            "timestamp": time.time(),
            "input_preview": user_input[:100],
            "score": result["score"],
        }
        self._history.append(record)
        # 限制历史长度
        if len(self._history) > 100:
            self._history = self._history[-50:]
        self._save_history()

    def _save_history(self) -> None:
        with open(self.history_path, "w", encoding="utf-8") as f:
            for h in self._history:
                f.write(json.dumps(h, ensure_ascii=False) + "\n")

    def _load_history(self) -> None:
        if not self.history_path.exists():
            return
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self._history.append(json.loads(line))
        except:
            pass


class AutoEconomyPrompter:
    """
    自动经济模式提示器
    
    负责:
    1. 检测空闲并提示兼职模式
    2. 检测复杂任务并提示赏金模式
    3. 检查 ClawTip 开通状态
    4. 引导用户开通流程
    5. 防打扰（同一模式24小时内最多提示一次）
    """

    COOLDOWN_SECONDS = 86400  # 24小时冷却

    def __init__(self, clawtip: Any | None = None) -> None:
        self.clawtip = clawtip
        self.idle_detector = IdleDetector()
        self.complexity_estimator = TaskComplexityEstimator()
        self.records: dict[str, PromptRecord] = {}
        self.state_path = PROMPT_STATE_DIR / "prompt_records.json"
        self._load_records()

    # ── 核心触发接口 ──

    def check_idle_and_prompt(self) -> str | None:
        """
        检查空闲状态，如果需要提示则返回提示消息，否则返回 None。
        应在 Agent 主循环的每次心跳或闲置检测时调用。
        """
        if not self.idle_detector.is_idle_long_enough():
            return None

        if self._is_in_cooldown("freelance"):
            return None

        clawtip_ready = self._check_clawtip_ready()

        if not clawtip_ready:
            return self._build_freelance_prompt(clawtip_ready=False)

        return self._build_freelance_prompt(clawtip_ready=True)

    def check_complexity_and_prompt(self, user_input: str, 
                                    estimated_files: int = 0,
                                    estimated_tools: int = 0,
                                    estimated_steps: int = 0) -> str | None:
        """
        评估任务复杂度，如果超过基线3倍则返回提示消息。
        应在收到用户输入后立即调用。
        """
        complexity = self.complexity_estimator.estimate(
            user_input, estimated_files, estimated_tools, estimated_steps
        )

        if not complexity["is_complex"]:
            return None

        if self._is_in_cooldown("bounty"):
            return None

        clawtip_ready = self._check_clawtip_ready()

        if not clawtip_ready:
            return self._build_bounty_prompt(
                complexity=complexity,
                clawtip_ready=False
            )

        return self._build_bounty_prompt(
            complexity=complexity,
            clawtip_ready=True
        )

    # ── 提示消息构建 ──

    def _build_freelance_prompt(self, clawtip_ready: bool) -> str:
        """构建闲时兼职模式提示消息"""
        idle_time = self.idle_detector.get_idle_human_readable()

        if clawtip_ready:
            return f"""💤 检测到您已空闲 {idle_time}

我发现您的 Agent 已经闲置一段时间了。要不要开启 **闲时兼职模式**，让它在后台帮您赚钱？

**闲时兼职模式简介：**
• 您的 Agent 会进入云端任务市场，接单帮助其他 Agent 完成工作
• 所有任务都在安全沙盒中运行，不会影响您的设备
• 自动拒绝任何涉及您隐私、API密钥或敏感信息的任务
• 收入通过京东 ClawTip 自动结算到您的账户
• 您可以设置每日 Token 用量上限，完全可控

开启后，Agent 会在您不使用电脑时自动接单赚钱，积累经验让自己变得更聪明。

> 回复 **"开启兼职"** 即可启动，或回复 **"不用了"** 忽略此提示（24小时内不再提醒）。
"""
        else:
            return f"""💤 检测到您已空闲 {idle_time}

我发现您的 Agent 已经闲置一段时间了。要不要让它在后台帮您赚钱？

不过，需要先开通 **京东 ClawTip 收付款功能**，这样兼职收入才能结算到您的账户。

**开通步骤（约2分钟）：**
1. 访问 https://clawtip.jd.com 注册开发者账号
2. 创建收款服务，获取 `pay_to`（收款服务ID）
3. 获取 SM4 密钥（通过邮件发放）
4. 配置到 Agent：
   ```bash
   export CLAWTIP_PAY_TO="您的收款服务ID"
   export CLAWTIP_SM4_KEY="您的SM4密钥"
   ```
   或写入配置文件 `~/.openclaw/skills/clawtip/payment_keys.json`

开通后，您的 Agent 就可以：
• 在后台安全地帮助其他 Agent 完成任务
• 自动赚取赏金收入
• 在安全沙盒中运行，零风险

> 回复 **"教我开通"** 获取详细图文教程，或回复 **"不用了"** 忽略。
"""

    def _build_bounty_prompt(self, complexity: dict, clawtip_ready: bool) -> str:
        """构建赏金模式提示消息"""
        score = complexity["score"]
        ratio = complexity["ratio"]
        breakdown = complexity["breakdown"]

        if clawtip_ready:
            return f"""⚡ 检测到复杂任务（复杂度评分: {score}/100，是日常任务的 {ratio} 倍）

这个任务看起来比平时的 workload 大不少，需要处理的环节比较多：
• 文本规模: {breakdown['length']}/30
• 文件操作: {breakdown['files']}/20  
• 工具调用: {breakdown['tools']}/20
• 预估步骤: {breakdown['steps']}/20
• 技术深度: {breakdown['semantic']}/10

要不要开启 **赏金模式**，让多个 Agent 协同帮您加速完成？

**赏金模式简介：**
• 您预设一笔赏金（比如 10-50 元）
• Agent 自动将任务拆解为多个小阶段
• 每个阶段分配给不同的 Freelance Agent 并行处理
• 完成一个阶段，验收通过后立即结算
• 代码质量检测 + 安全沙盒验货，确保交付物可靠
• 赏金用完即自动停止，完全可控

开启后，原本需要 2 小时的任务可能 30 分钟就搞定。

> 回复 **"开启赏金"** 并告诉我预算金额，或回复 **"自己来"** 忽略（24小时内不再提醒）。
"""
        else:
            return f"""⚡ 检测到复杂任务（复杂度评分: {score}/100，是日常任务的 {ratio} 倍）

这个任务工作量不小，要不要开启 **赏金模式** 让多个 Agent 协同加速？

不过，需要先开通 **京东 ClawTip 收付款功能**，这样才能给协助的 Agent 发放赏金。

**开通步骤（约2分钟）：**
1. 访问 https://clawtip.jd.com 注册开发者账号
2. 创建收款服务，获取 `pay_to`（收款服务ID）
3. 获取 SM4 密钥（通过邮件发放）
4. 配置到 Agent：
   ```bash
   export CLAWTIP_PAY_TO="您的收款服务ID"
   export CLAWTIP_SM4_KEY="您的SM4密钥"
   ```
   或写入配置文件 `~/.openclaw/skills/clawtip/payment_keys.json`

**赏金模式开通后：**
• 您预设赏金金额（比如 10-50 元）
• 任务自动拆解为多阶段，分配给 Freelance Agent 并行处理
• 每阶段验收通过即结算，质量检测 + 安全沙盒双重保障
• 赏金用完自动停止，零超支风险

> 回复 **"教我开通"** 获取详细图文教程，或回复 **"自己来"** 忽略此提示。
"""

    # ── 用户响应处理 ──

    def handle_user_response(self, mode: str, response: str) -> str:
        """
        处理用户对提示的响应。

        Args:
            mode: "freelance" 或 "bounty"
            response: 用户回复文本

        Returns:
            处理结果消息
        """
        response_lower = response.lower().strip()

        # 接受
        accept_keywords = ["开启", "同意", "好的", "可以", "行", "接受", "accept", "yes", "y", "ok", "开", "启动"]
        if any(k in response_lower for k in accept_keywords):
            self._record_response(mode, "accepted")

            if mode == "freelance":
                return self._get_freelance_guide()
            else:
                return self._get_bounty_guide()

        # 拒绝
        decline_keywords = ["不用", "不了", "拒绝", "decline", "no", "n", "否", "关闭", "cancel", "ignore", "忽略"]
        if any(k in response_lower for k in decline_keywords):
            self._record_response(mode, "declined")
            return f"已记录您的选择，24小时内不再提示{self._mode_name(mode)}。"

        # 教开通
        setup_keywords = ["开通", "教我", "怎么", "如何", "setup", "配置", "clawtip", "支付"]
        if any(k in response_lower for k in setup_keywords):
            return self._get_clawtip_setup_guide()

        return f"我没有理解您的回复。请回复 **开启{self._mode_name(mode)}**、**不用了** 或 **教我开通**"

    def _get_freelance_guide(self) -> str:
        """闲时兼职模式详细说明"""
        return """✅ 闲时兼职模式已准备就绪！

**模式说明：**
您的 Agent 会在您不使用电脑时（检测到空闲3小时以上），自动进入云端任务市场接单赚钱。

**安全机制：**
✓ 所有任务在隔离沙盒中运行，不影响您的主系统
✓ 自动拒绝涉及您隐私、API密钥、密码的任务
✓ 拒绝 rm -rf、format 等危险操作
✓ 每日 Token 用量上限由您设定，不超支

**收益方式：**
• 按完成的任务阶段结算赏金
• 收入通过京东 ClawTip 实时到账
• 代码质量越高，收入越高（质量为主，数量为辅）

**开启命令：**
```python
agent.start_freelance_mode(
    capabilities=["python", "testing", "writing"],  # 您的 Agent 擅长的技能
    hourly_rate=500,      # 时薪（分）= 5元/小时
    token_budget=100000,  # 每日 Token 上限
)
```

**随时停止：**
发送 "停止兼职" 即可立即退出，已接单的任务会正常完成后不再接新单。

> 要现在开启吗？回复 **"现在开启"** + 你的时薪和技能标签。
"""

    def _get_bounty_guide(self) -> str:
        """赏金模式详细说明"""
        return """✅ 赏金模式已准备就绪！

**模式说明：**
您预设一笔赏金，Agent 自动将复杂任务拆解为多阶段，分配给多个 Freelance Agent 并行处理，大幅加速完成。

**工作流程：**
1. 您设定总赏金金额和任务描述
2. Agent 自动拆解为 3-8 个阶段，每阶段分配赏金
3. Freelance Agent 接单并在沙盒中完成
4. 代码质量检测 + 安全验货
5. 验收通过立即结算该阶段赏金
6. 全部完成，任务交付

**费用控制：**
• 赏金总额由您预设，用完即停
• 每阶段独立结算，质量不合格可拒付
• 智能预警：剩余 ≤20% 时通知提前交差
• 代码质量系数：优秀+20%，及格只付80%

**使用示例：**
```python
agent.start_bounty_mode(
    title="重构用户认证模块",
    description="将现有认证系统改造为JWT+RBAC架构...",
    total_bounty=5000,  # 总赏金50元
    stages=[
        {"title": "设计JWT认证流程", "description": "...", "bounty": 1000},
        {"title": "实现RBAC权限模型", "description": "...", "bounty": 2000},
        {"title": "编写单元测试", "description": "...", "bounty": 1000},
        {"title": "集成测试与验收", "description": "...", "bounty": 1000},
    ]
)
```

**进度查看：**
```python
agent.get_economy_stats()
```

> 要现在开启吗？回复 **"现在开启"** + 任务描述和预算金额。
"""

    def _get_clawtip_setup_guide(self) -> str:
        """ClawTip 开通详细教程"""
        return """📖 ClawTip 开通教程

**为什么需要 ClawTip？**
赏金模式和闲时兼职模式都需要收付款功能。ClawTip 是京东提供的安全支付服务，支持国密 SM4 加密。

**Step 1: 注册开发者账号**
1. 访问 https://clawtip.jd.com
2. 点击 "注册开发者"，填写邮箱/手机
3. 完成实名认证（个人/企业）

**Step 2: 创建收款服务**
1. 登录控制台 → 收款服务 → 新建
2. 填写服务名称（如 "Kimi-Agent-收款"）
3. 选择结算方式：实时到账 / 日结 / 周结
4. 提交审核（通常5分钟内通过）

**Step 3: 获取密钥**
1. 进入服务详情页 → 安全设置
2. 点击 "生成 SM4 密钥"
3. 密钥会通过邮件发送到您的注册邮箱
4. **妥善保管，不要泄露**

**Step 4: 配置到 Agent**

方式 A - 环境变量（推荐）:
```bash
export CLAWTIP_PAY_TO="您的收款服务ID"
export CLAWTIP_SM4_KEY="您的SM4密钥"
export CLAWTIP_SANDBOX="false"  # 生产环境
```

方式 B - 配置文件:
```json
// ~/.openclaw/skills/clawtip/payment_keys.json
{
    "pay_to": "您的收款服务ID",
    "sm4_key": "您的SM4密钥",
    "sandbox": false
}
```

**Step 5: 验证**
```python
from kimix.tools.clawtip import ClawTipPayment
payment = ClawTipPayment()
order = payment.create_order(amount=1, description="测试", question="测试")
print(order)  # 成功则配置正确
```

**需要帮助？**
• 技术支持: org.clawtip1@jd.com
• 文档: https://clawtip.jd.com/docs
• 测试模式: 设置 `"sandbox": true` 可用测试金额验证流程

> 配置完成后回复 **"已开通"**，我继续为您开启经济模式。
"""

    # ── 辅助方法 ──

    def _check_clawtip_ready(self) -> bool:
        """检查 ClawTip 是否已配置可用"""
        if self.clawtip is None:
            return False
        try:
            # 尝试检查配置
            return hasattr(self.clawtip, 'pay_to') and self.clawtip.pay_to is not None
        except:
            return False

    def _is_in_cooldown(self, mode: str) -> bool:
        """检查是否处于冷却期"""
        record = self.records.get(mode)
        if not record:
            return False
        elapsed = time.time() - record.prompted_at
        return elapsed < self.COOLDOWN_SECONDS and record.user_response in ("declined", "accepted")

    def _record_response(self, mode: str, response: str) -> None:
        """记录用户响应"""
        self.records[mode] = PromptRecord(
            mode=mode,
            prompted_at=time.time(),
            user_response=response,
            clawtip_ready=self._check_clawtip_ready(),
        )
        self._save_records()

    def _mode_name(self, mode: str) -> str:
        return "闲时兼职模式" if mode == "freelance" else "赏金模式"

    def _save_records(self) -> None:
        data = {k: asdict(v) for k, v in self.records.items()}
        self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_records(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            for k, v in data.items():
                self.records[k] = PromptRecord(**v)
        except:
            pass

    def get_stats(self) -> dict:
        """获取提示器统计"""
        return {
            "idle_seconds": round(self.idle_detector.get_idle_seconds(), 0),
            "idle_long_enough": self.idle_detector.is_idle_long_enough(),
            "history_count": len(self.complexity_estimator._history),
            "baseline": round(self.complexity_estimator._get_baseline(), 1),
            "records": {k: {"mode": v.mode, "response": v.user_response, 
                          "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(v.prompted_at))}
                       for k, v in self.records.items()},
            "cooldown_hours_remaining": {
                k: round((self.COOLDOWN_SECONDS - (time.time() - v.prompted_at)) / 3600, 1)
                for k, v in self.records.items()
                if self._is_in_cooldown(k)
            },
        }
