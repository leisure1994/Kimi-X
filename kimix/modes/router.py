"""
模式路由器模块

实现认知-决策分离架构中的模式决策逻辑。
基于任务特征分析,自动推荐或决定最适合的工作模式。

核心功能:
- 任务特征分析(复杂度、风险、文件操作需求)
- 模式推荐
- 自动路由(AUTO 模式下)
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from kimix.core.engine import AgentMode


class TaskAnalysis(TypedDict):
    """任务分析结果

    认知分析的结构化输出,用于模式决策。

    Attributes:
        task_type: 任务类型
        complexity: 复杂度 (low / medium / high / critical)
        risk_level: 风险等级 (safe / low / medium / high / critical)
        needs_file_ops: 是否需要文件操作
        destructive: 是否涉及破坏性操作
        needs_thinking: 是否需要深度思考
        suggested_tools: 建议使用的工具列表
        reasoning: 分析推理说明
    """
    task_type: str
    complexity: str
    risk_level: str
    needs_file_ops: bool
    destructive: bool
    needs_thinking: bool
    suggested_tools: list[str]
    reasoning: str


class ModeRouter:
    """模式路由器

    基于任务特征分析,推荐或自动选择最适合的工作模式。
    实现认知-决策分离架构的决策层。

    Attributes:
        default_mode: 默认模式(当无法判断时使用)
        user_preference: 用户偏好(可覆盖自动决策)

    Examples:
        >>> router = ModeRouter()
        >>> analysis = router.analyze_task("帮我读取 README.md")
        >>> suggested = router.suggest_mode(analysis)
        >>> suggested
        <AgentMode.EXPLORE: 'explore'>
    """

    # 模式选择权重矩阵
    # 格式: {任务类型: {模式: 权重}}
    MODE_WEIGHTS: dict[str, dict[str, int]] = {
        "simple_qa": {
            "explore": 3,
            "plan": 1,
            "agent": 2,
            "auto": 2,
            "yolo": 1,
        },
        "file_read": {
            "explore": 5,
            "plan": 2,
            "agent": 3,
            "auto": 3,
            "yolo": 2,
        },
        "file_write": {
            "explore": 0,
            "plan": 3,
            "agent": 5,
            "auto": 4,
            "yolo": 2,
        },
        "code_refactor": {
            "explore": 1,
            "plan": 4,
            "agent": 4,
            "auto": 3,
            "yolo": 2,
        },
        "debug": {
            "explore": 2,
            "plan": 2,
            "agent": 5,
            "auto": 4,
            "yolo": 2,
        },
        "shell_exec": {
            "explore": 0,
            "plan": 1,
            "agent": 3,
            "auto": 4,
            "yolo": 3,
        },
        "architecture_design": {
            "explore": 1,
            "plan": 5,
            "agent": 2,
            "auto": 2,
            "yolo": 0,
        },
        "code_review": {
            "explore": 4,
            "plan": 2,
            "agent": 2,
            "auto": 2,
            "yolo": 1,
        },
        "git_operation": {
            "explore": 0,
            "plan": 1,
            "agent": 4,
            "auto": 4,
            "yolo": 3,
        },
        "general": {
            "explore": 2,
            "plan": 2,
            "agent": 4,
            "auto": 3,
            "yolo": 1,
        },
    }

    # 风险等级对模式的限制
    RISK_MODE_LIMIT: dict[str, list[str]] = {
        "safe": ["explore", "plan", "agent", "auto", "yolo"],
        "low": ["explore", "plan", "agent", "auto", "yolo"],
        "medium": ["explore", "plan", "agent", "auto"],  # YOLO 受限
        "high": ["explore", "plan", "agent"],  # AUTO 和 YOLO 受限
        "critical": ["explore", "plan", "agent"],  # 只允许最保守的模式
    }

    def __init__(
        self,
        default_mode: AgentMode = AgentMode.AGENT,
        feedback_file: str | None = None,
    ) -> None:
        """初始化模式路由器

        Args:
            default_mode: 无法决策时的默认模式
            feedback_file: 用户反馈持久化文件路径（可选）
        """
        self.default_mode = default_mode
        self._user_override: AgentMode | None = None
        self._feedback_history: dict[str, dict[str, int]] = {}
        self._feedback_file = feedback_file
        self._load_feedback()

    def _load_feedback(self) -> None:
        """从文件加载历史反馈"""
        import json
        import os
        
        if self._feedback_file and os.path.exists(self._feedback_file):
            try:
                with open(self._feedback_file, "r", encoding="utf-8") as f:
                    self._feedback_history = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._feedback_history = {}

    def _save_feedback(self) -> None:
        """保存反馈到文件"""
        import json
        
        if self._feedback_file:
            try:
                with open(self._feedback_file, "w", encoding="utf-8") as f:
                    json.dump(self._feedback_history, f, ensure_ascii=False, indent=2)
            except OSError:
                pass

    def record_feedback(
        self,
        task_type: str,
        suggested_mode: AgentMode,
        user_choice: AgentMode,
    ) -> None:
        """记录用户对模式选择的反馈

        用于自适应调整模式权重。当用户频繁覆盖某个任务类型的
        推荐模式时，系统会学习并调整权重。

        Args:
            task_type: 任务类型
            suggested_mode: 系统推荐的模式
            user_choice: 用户实际选择的模式
        """
        if task_type not in self._feedback_history:
            self._feedback_history[task_type] = {}
        
        key = f"{suggested_mode.value}>{user_choice.value}"
        self._feedback_history[task_type][key] = (
            self._feedback_history[task_type].get(key, 0) + 1
        )
        self._save_feedback()

    def _apply_feedback_weights(
        self,
        task_type: str,
        scores: dict[str, float],
    ) -> dict[str, float]:
        """根据历史反馈调整模式权重

        如果用户对某个任务类型频繁选择特定模式，
        提升该模式的得分。

        Args:
            task_type: 任务类型
            scores: 基础模式得分

        Returns:
            调整后的得分
        """
        if task_type not in self._feedback_history:
            return scores
        
        feedback = self._feedback_history[task_type]
        adjusted = dict(scores)
        
        for transition, count in feedback.items():
            if count >= 3:  # 至少3次才认为是稳定偏好
                _, target = transition.split(">")
                if target in adjusted:
                    # 用户偏好的模式获得加成
                    adjusted[target] *= (1 + 0.1 * min(count, 10))
        
        return adjusted

    def analyze_task(self, user_input: str) -> TaskAnalysis:
        """分析任务特征

        基于启发式规则分析用户输入,提取任务特征。
        这是认知层的核心方法。

        分析维度:
        1. 任务类型识别(简单问答、文件操作、重构等)
        2. 复杂度评估(基于关键词和上下文)
        3. 风险评估(基于操作类型和危险性)
        4. 文件操作需求判断

        Args:
            user_input: 用户输入文本

        Returns:
            任务分析结果

        Examples:
            >>> router = ModeRouter()
            >>> analysis = router.analyze_task("帮我读取 README.md")
            >>> analysis["task_type"]
            'file_read'
            >>> analysis["complexity"]
            'low'
        """
        text = user_input.lower()

        # 任务类型识别
        task_type = self._classify_task_type(text)

        # 复杂度评估
        complexity = self._assess_complexity(text, task_type)

        # 风险评估
        risk_level = self._assess_risk(text, task_type)

        # 文件操作需求
        needs_file_ops = self._needs_file_operations(text, task_type)

        # 破坏性操作判断
        destructive = self._is_destructive(text, task_type)

        # Thinking 需求
        needs_thinking = complexity in ("high", "critical") or task_type in (
            "architecture_design", "code_refactor", "debug", "code_review"
        )

        # 建议工具
        suggested_tools = self._suggest_tools(task_type)

        # 推理说明
        reasoning = (
            f"任务类型:{task_type},"
            f"复杂度:{complexity},"
            f"风险:{risk_level},"
            f"需文件操作:{needs_file_ops}"
        )

        return TaskAnalysis(
            task_type=task_type,
            complexity=complexity,
            risk_level=risk_level,
            needs_file_ops=needs_file_ops,
            destructive=destructive,
            needs_thinking=needs_thinking,
            suggested_tools=suggested_tools,
            reasoning=reasoning,
        )

    def suggest_mode(self, analysis: TaskAnalysis | dict[str, Any]) -> AgentMode:
        """根据分析结果推荐工作模式

        基于任务特征,从模式权重矩阵中选择最合适的模式。

        Args:
            analysis: 任务分析结果

        Returns:
            推荐的 AgentMode

        Examples:
            >>> router = ModeRouter()
            >>> analysis = router.analyze_task("分析项目结构")
            >>> mode = router.suggest_mode(analysis)
        """
        # 统一处理 dict 和 TaskAnalysis
        if isinstance(analysis, dict):
            task_type = analysis.get("task_type", "general")
            complexity = analysis.get("complexity", "medium")
            risk_level = analysis.get("risk_level", "safe")
        else:
            task_type = analysis["task_type"]
            complexity = analysis["complexity"]
            risk_level = analysis["risk_level"]

        # 获取该任务类型的模式权重
        weights = self.MODE_WEIGHTS.get(task_type, self.MODE_WEIGHTS["general"])

        # 根据风险等级限制可选模式
        allowed_modes = self.RISK_MODE_LIMIT.get(risk_level, ["agent"])

        # 根据复杂度调整权重
        complexity_multiplier = {
            "low": {"explore": 1.2, "auto": 1.1, "yolo": 1.1},
            "medium": {"agent": 1.2, "auto": 1.1},
            "high": {"plan": 1.3, "agent": 1.2, "explore": 0.8},
            "critical": {"plan": 1.3, "agent": 1.1, "explore": 1.0, "auto": 0.5, "yolo": 0.0},
        }.get(complexity, {})

        # 计算基础得分
        scores: dict[str, float] = {}
        for mode_name, base_weight in weights.items():
            if mode_name not in allowed_modes:
                continue
            multiplier = complexity_multiplier.get(mode_name, 1.0)
            scores[mode_name] = base_weight * multiplier

        if not scores:
            return self.default_mode

        # 应用反馈权重（自适应学习）
        scores = self._apply_feedback_weights(task_type, scores)

        # 选择得分最高的模式
        best_mode_name = max(scores, key=scores.get)  # type: ignore
        mode_map = {
            "explore": AgentMode.EXPLORE,
            "plan": AgentMode.PLAN,
            "agent": AgentMode.AGENT,
            "auto": AgentMode.AUTO,
            "yolo": AgentMode.YOLO,
        }
        return mode_map.get(best_mode_name, self.default_mode)

    def auto_route(self, analysis: TaskAnalysis | dict[str, Any]) -> AgentMode:
        """自动路由到最适合的模式(AUTO 模式使用)

        与 suggest_mode 的区别:
        - auto_route 会考虑用户历史偏好
        - auto_route 在边界情况下更保守
        - auto_route 支持动态调整

        Args:
            analysis: 任务分析结果

        Returns:
            决定的 AgentMode
        """
        # 如果有用户覆盖,优先使用
        if self._user_override is not None:
            return self._user_override

        # 使用 suggest_mode 的基础逻辑
        suggested = self.suggest_mode(analysis)

        # 统一处理 dict 和 TaskAnalysis
        if isinstance(analysis, dict):
            risk_level = analysis.get("risk_level", "safe")
            destructive = analysis.get("destructive", False)
        else:
            risk_level = analysis["risk_level"]
            destructive = analysis["destructive"]

        # AUTO 模式的保守策略
        # 高风险任务不使用 YOLO
        if risk_level == "high" and suggested == AgentMode.YOLO:
            return AgentMode.AUTO

        # 破坏性操作在 AUTO 模式下用 AGENT 处理
        if destructive and suggested == AgentMode.YOLO:
            return AgentMode.AGENT

        # 简单只读任务直接用 EXPLORE
        if isinstance(analysis, dict):
            task_type = analysis.get("task_type", "")
            needs_file_ops = analysis.get("needs_file_ops", False)
        else:
            task_type = analysis["task_type"]
            needs_file_ops = analysis["needs_file_ops"]

        if task_type == "file_read" and not needs_file_ops:
            return AgentMode.EXPLORE

        return suggested

    def set_user_override(self, mode: AgentMode | None) -> None:
        """设置用户模式覆盖

        用户可手动设置偏好模式,覆盖自动路由决策。

        Args:
            mode: 用户偏好的模式,None 取消覆盖
        """
        self._user_override = mode

    def get_mode_explanation(
        self,
        mode: AgentMode,
        analysis: TaskAnalysis | dict[str, Any] | None = None,
    ) -> str:
        """获取模式选择的解释说明

        用于向用户解释为什么选择某个模式。

        Args:
            mode: 选定的模式
            analysis: 任务分析结果(可选)

        Returns:
            解释文本(中文)
        """
        explanations = {
            AgentMode.EXPLORE: "探索模式(只读)- 适合信息收集和代码理解",
            AgentMode.PLAN: "规划模式(只读+计划)- 适合方案设计和任务分析",
            AgentMode.AGENT: "Agent 模式(交互执行)- 日常开发,写入操作需确认",
            AgentMode.AUTO: "自动模式(自适应)- 智能判断,平衡效率和安全",
            AgentMode.YOLO: "YOLO 模式(全自主)- 最高效率,自动审批",
        }
        base = explanations.get(mode, "未知模式")

        if analysis:
            if isinstance(analysis, dict):
                reasoning = analysis.get("reasoning", "")
            else:
                reasoning = analysis["reasoning"]
            return f"{base}\n选择原因:{reasoning}"

        return base

    # ===== 内部分析方法 =====

    def _classify_task_type(self, text: str) -> str:
        """分类任务类型"""
        patterns = {
            "simple_qa": [
                r"^(什么|怎么|为什么|如何|请问|什么是)",
                r"^(hi|hello|hey|你好|您好|在吗|谢谢|再见)",
                r"(解释|说明|介绍|什么是$)",
            ],
            "file_read": [
                r"(读取|查看|打开|显示|读一下|cat|read|show|display)\s+\S+\.\w+",
                r"(看看|看下|看一下)\s+\S+\.\w+",
                r"README",
            ],
            "file_write": [
                r"(创建|写入|修改|编辑|更新|保存|write|create|edit|modify)\s+\S+\.\w+",
                r"(写个|写一个|新建|添加)\s+(文件|脚本|函数|类|模块)",
                r"(生成|gen)\s+(代码|文件|脚本)",
            ],
            "code_refactor": [
                r"(重构|refactor|重写|rewrite|优化|optimize)\s+(代码|函数|类|模块)",
                r"(改进|improve|better)\s+(代码|实现|结构)",
            ],
            "debug": [
                r"(fix|修复|fix\s+bug|debug|调试|排查)",
                r"(报错|错误|exception|error|bug|崩溃|crash)",
            ],
            "shell_exec": [
                r"(运行|执行|调用|run|execute|exec)\s+(命令|cmd|shell|script)",
                r"(pip|npm|yarn|cargo|go\s+mod|docker|kubectl)",
            ],
            "architecture_design": [
                r"(架构|设计|架构设计|system\s+design|architecture)",
                r"(设计模式|pattern|DDD|TDD|微服务|microservice)",
            ],
            "code_review": [
                r"(审查|review|code\s+review|cr|检查)\s+(代码|code|文件|file)",
                r"(看看|review)\s+(这个|这段|这个文件|this)\s+(代码|实现)",
            ],
            "git_operation": [
                r"(git\s+(commit|push|pull|merge|rebase|checkout|branch|reset|revert|stash|tag|clone))",
                r"(提交|推送|拉取|合并|分支|回滚|撤销|克隆)",
            ],
        }

        for task_type, pattern_list in patterns.items():
            if any(re.search(p, text) for p in pattern_list):
                return task_type

        return "general"

    def _assess_complexity(self, text: str, task_type: str) -> str:
        """评估任务复杂度"""
        # 基于关键词评估
        high_complexity_indicators = [
            r"(重构|架构| redesign|restructure|migration)",
            r"(所有|全部|every|all\s+files|批量|batch)",
            r"(项目|整个项目|project|codebase|仓库|repo)\s+(重构|修改|分析|迁移)",
            r"(多个|几个|多\s*个|many|several)\s+(文件|模块|组件)",
        ]

        low_complexity_indicators = [
            r"^(什么|怎么|为什么|如何)",
            r"(查看|看看|读一下|显示)\s+\S+",
            r"^(hi|hello|hey|你好)",
        ]

        if any(re.search(p, text) for p in high_complexity_indicators):
            return "high"

        if any(re.search(p, text) for p in low_complexity_indicators):
            return "low"

        # 基于任务类型的默认复杂度
        defaults = {
            "simple_qa": "low",
            "file_read": "low",
            "file_write": "medium",
            "code_refactor": "high",
            "debug": "medium",
            "shell_exec": "medium",
            "architecture_design": "high",
            "code_review": "medium",
            "git_operation": "medium",
            "general": "medium",
        }
        return defaults.get(task_type, "medium")

    def _assess_risk(self, text: str, task_type: str) -> str:
        """评估风险等级"""
        # 危险命令检测
        dangerous_patterns = [
            r"rm\s+-rf\s+/",
            r":\(\)\{\s*:\|:&\s*\};:",
            r"dd\s+if=.*of=/dev/",
            r"mkfs\.",
            r"chmod\s+-R\s+777\s+/",
        ]

        if any(re.search(p, text) for p in dangerous_patterns):
            return "critical"

        # 高风险操作
        high_risk_patterns = [
            r"(删除|delete|drop|remove)\s+(所有|全部|every)",
            r"(reset\s+--hard|checkout\s+-f)",
            r"(覆盖|overwrite|强制|force)",
        ]

        if any(re.search(p, text) for p in high_risk_patterns):
            return "high"

        # 基于任务类型的默认风险
        defaults = {
            "simple_qa": "safe",
            "file_read": "safe",
            "file_write": "medium",
            "code_refactor": "medium",
            "debug": "low",
            "shell_exec": "medium",
            "architecture_design": "safe",
            "code_review": "safe",
            "git_operation": "medium",
            "general": "low",
        }
        return defaults.get(task_type, "low")

    def _needs_file_operations(self, text: str, task_type: str) -> bool:
        """判断是否需要文件操作"""
        file_related_types = {
            "file_read", "file_write", "code_refactor",
            "debug", "code_review", "git_operation",
        }
        return task_type in file_related_types

    def _is_destructive(self, text: str, task_type: str) -> bool:
        """判断是否涉及破坏性操作"""
        destructive_types = {"file_write", "code_refactor", "shell_exec", "git_operation"}
        destructive_keywords = ["删除", "覆盖", "替换", "delete", "overwrite", "replace"]

        if task_type not in destructive_types:
            return False

        return any(kw in text for kw in destructive_keywords)

    def _suggest_tools(self, task_type: str) -> list[str]:
        """建议使用的工具列表"""
        tool_map = {
            "simple_qa": [],
            "file_read": ["file_read", "file_list"],
            "file_write": ["file_read", "file_write", "file_edit"],
            "code_refactor": ["file_read", "file_edit", "file_write"],
            "debug": ["file_read", "shell"],
            "shell_exec": ["shell"],
            "architecture_design": ["file_read", "file_list"],
            "code_review": ["file_read"],
            "git_operation": ["git"],
            "general": ["file_read", "web_search"],
        }
        return tool_map.get(task_type, [])
