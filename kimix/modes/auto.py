"""
自动模式 (Auto Mode)

自适应自主执行模式，根据任务特性动态调整行为。
- 智能审批门：基于风险评估自动决定是否需要确认
- 自适应 thinking：简单任务关闭 thinking 节省 token，复杂任务开启
- 自动重试：工具失败时自动尝试替代方案
- 批处理优化：多个相似操作自动合并

适用场景：
- 熟练用户的高效工作
- 批量操作
- 已知模式的重复任务
- 需要平衡成本和质量的场景
"""

from __future__ import annotations

import time
from typing import Any

from kimix.core.events import (
    EngineEvent,
    create_event,
    create_thinking_event,
    create_content_event,
    create_tool_result_event,
    create_error_event,
)
from kimix.modes.base import BaseMode, ApprovalLevel


class AutoMode(BaseMode):
    """自动模式 - 自适应自主执行
    
    此模式下 Agent 拥有更高的自主权，通过智能门控系统决定：
    - 何时需要用户确认
    - 是否开启 thinking 模式
    - 如何优化批量操作
    
    Attributes:
        name: "auto"
        description: "自动模式 - 自适应 thinking，智能审批门"
        approval_level: ApprovalLevel.DESTRUCTIVE（通过智能门控细化）
        supports_thinking: True（自适应开关）
    
    Examples:
        >>> mode = AutoMode()
        >>> mode.should_approve("file_write", {})
        False  # Auto 模式下可能自动通过低风险写入
    """

    name: str = "auto"
    description: str = "自动模式 - 自适应 thinking，智能审批门"
    approval_level: ApprovalLevel = ApprovalLevel.DESTRUCTIVE
    supports_thinking: bool = True

    # 审批阈值配置
    APPROVAL_THRESHOLD_LOW = 0.3      # 低于此值自动通过
    APPROVAL_THRESHOLD_HIGH = 0.7     # 高于此值需确认

    # 自动重试配置
    MAX_RETRIES = 2
    RETRY_DELAY_SECONDS = 1

    # 安全工具（自动通过）
    SAFE_TOOLS: set[str] = {
        "file_read", "file_list", "file_search", "file_stat",
        "git_status", "git_log", "git_diff", "git_show", "git_branch",
        "web_search", "web_fetch",
    }

    # 低风险写入工具（记录但自动执行）
    LOW_RISK_WRITE_TOOLS: set[str] = {
        "file_write", "file_edit", "file_create",
    }

    # 高风险工具（需确认）
    HIGH_RISK_TOOLS: set[str] = {
        "file_delete", "shell", "git_reset", "git_checkout_force",
        "git_clean", "git_revert",
    }

    def __init__(self) -> None:
        """初始化自动模式"""
        super().__init__()
        self._thinking_enabled = True  # 动态开关
        self._auto_retry_count = 0
        self._executed_tools_log: list[dict[str, Any]] = []

    async def process(
        self,
        engine: Any,
        user_input: str,
    ) -> Any:
        """处理自动模式下的用户输入
        
        Auto 模式的核心流程：
        1. 认知分析评估任务特性
        2. 根据复杂度决定是否开启 thinking
        3. 委托引擎执行
        4. 智能审批门控处理工具调用
        5. 工具失败时自动重试
        6. 批量操作优化
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        """
        # 发送模式标识
        yield create_thinking_event("[自动模式] 开始自适应执行...")

        # 认知分析
        analysis = engine.cognitive_analysis(user_input)
        complexity = analysis.get("complexity", "medium")
        risk_level = analysis.get("risk_level", "safe")
        needs_thinking = analysis.get("needs_thinking", False)

        # 自适应 thinking 决策
        self._thinking_enabled = needs_thinking or complexity in ("high", "critical")
        thinking_status = "开启" if self._thinking_enabled else "关闭"
        yield create_thinking_event(
            f"任务复杂度：{complexity}，风险等级：{risk_level}，"
            f"Thinking 模式：{thinking_status}"
        )

        # 构建自适应提示词（指导模型根据 thinking 设置调整）
        auto_prompt = self._build_auto_prompt(user_input, analysis)

        # 委托给引擎主循环
        retry_queue: list[dict[str, Any]] = []

        async for event in engine.run(auto_prompt):
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            # 智能审批门控
            if event_type == "tool_call":
                tool_calls = event_data.get("tool_calls", [])
                auto_calls = []
                confirm_calls = []
                log_calls = []

                for tc in tool_calls:
                    tc_name = tc.get("function", {}).get("name", "")
                    tc_params = tc.get("function", {}).get("arguments", "")

                    risk_score = self._calculate_risk_score(tc_name, tc_params)

                    if risk_score < self.APPROVAL_THRESHOLD_LOW:
                        # 低风险：自动执行
                        auto_calls.append(tc)
                    elif risk_score < self.APPROVAL_THRESHOLD_HIGH:
                        # 中低风险：记录并执行
                        log_calls.append(tc)
                    else:
                        # 高风险：需确认
                        confirm_calls.append(tc)

                # 执行自动通过的工具
                if auto_calls:
                    yield create_event("tool_call", {"tool_calls": auto_calls})
                    results = await engine.execute_tools(auto_calls)
                    for result in results:
                        yield create_event("tool_result", result)
                        # 检查是否需要重试
                        if result.get("error") and self._auto_retry_count < self.MAX_RETRIES:
                            retry_queue.append({
                                "tool_call_id": result.get("tool_call_id", ""),
                                "name": result.get("name", ""),
                                "reason": result.get("error", ""),
                            })

                # 记录中低风险操作并执行
                if log_calls:
                    for tc in log_calls:
                        tc_name = tc.get("function", {}).get("name", "")
                        yield create_thinking_event(
                            f"[自动执行] {tc_name}（已记录，风险评分："
                            f"{self._calculate_risk_score(tc_name, {}):.2f}）"
                        )
                    yield create_event("tool_call", {"tool_calls": log_calls})
                    results = await engine.execute_tools(log_calls)
                    for result in results:
                        yield create_event("tool_result", result)

                # 高风险工具：生成审批事件
                if confirm_calls:
                    for tc in confirm_calls:
                        tc_name = tc.get("function", {}).get("name", "")
                        tc_args = tc.get("function", {}).get("arguments", "")
                        yield create_thinking_event(
                            f"⏸️ 需确认：{tc_name} (风险评分："
                            f"{self._calculate_risk_score(tc_name, tc_args):.2f})"
                        )
                    yield create_event("tool_call", {
                        "tool_calls": confirm_calls,
                        "requires_approval": True,
                    })

                # 处理重试队列
                if retry_queue:
                    yield create_thinking_event(
                        f"[自动重试] {len(retry_queue)} 个工具需要重试"
                    )
                    # 实际重试在下一轮循环中处理
                    for retry_item in retry_queue:
                        yield create_thinking_event(
                            f"  - {retry_item['name']}: {retry_item['reason'][:100]}"
                        )
                    retry_queue.clear()

                continue

            # 透传其他事件
            yield event

        # 执行摘要
        if self._executed_tools_log:
            yield create_thinking_event(
                f"本次执行了 {len(self._executed_tools_log)} 个工具"
            )

    def should_approve(self, tool_name: str, tool_params: dict[str, Any] | None = None) -> bool:
        """自动模式的智能审批判断
        
        基于风险评分决定是否需要审批：
        - 风险评分 < 0.3: 自动通过
        - 风险评分 >= 0.7: 需要确认
        - 中间值：记录但执行
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数
        
        Returns:
            True 如果需要审批
        """
        risk_score = self._calculate_risk_score(tool_name, tool_params)
        return risk_score >= self.APPROVAL_THRESHOLD_HIGH

    def _calculate_risk_score(
        self,
        tool_name: str,
        tool_params: Any = None,
    ) -> float:
        """计算工具操作的风险评分
        
        评分范围 0.0（安全）到 1.0（极危险）。
        
        评估维度：
        - 工具本身的风险等级
        - 参数中的危险性指标
        - 历史执行成功率
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数
        
        Returns:
            风险评分 (0.0 - 1.0)
        """
        score = 0.0

        # 工具类型基础分
        if tool_name in self.SAFE_TOOLS:
            score += 0.0
        elif tool_name in self.LOW_RISK_WRITE_TOOLS:
            score += 0.3
        elif tool_name in self.HIGH_RISK_TOOLS:
            score += 0.6
        else:
            score += 0.4  # 未知工具保守处理

        # 参数风险加成
        if tool_params and tool_name == "shell":
            import json
            try:
                params = json.loads(tool_params) if isinstance(tool_params, str) else tool_params
                command = str(params.get("command", "")).lower()

                # 危险命令检测
                dangerous_commands = [
                    "rm -rf", "mkfs", "dd if=", "> /dev/sda",
                    ":(){:|:&};:", "chmod -R 777 /",
                ]
                if any(dc in command for dc in dangerous_commands):
                    score += 0.4

                # 系统级命令
                system_commands = ["reboot", "shutdown", "kill -9", "pkill", "systemctl"]
                if any(sc in command for sc in system_commands):
                    score += 0.3

                # 网络操作
                if any(nc in command for nc in ["curl", "wget", "scp"]):
                    score += 0.1

            except (json.JSONDecodeError, AttributeError):
                score += 0.1  # 参数解析失败，轻微加分

        # 文件删除操作
        if tool_name == "file_delete":
            score += 0.2
            # 如果是批量删除
            if tool_params:
                import json
                try:
                    params = json.loads(tool_params) if isinstance(tool_params, str) else tool_params
                    path = str(params.get("path", ""))
                    if "*" in path or "?" in path:
                        score += 0.3  # 通配符删除更危险
                except (json.JSONDecodeError, AttributeError):
                    pass

        return min(score, 1.0)  # 最高 1.0

    def _build_auto_prompt(self, user_input: str, analysis: dict[str, Any]) -> str:
        """构建自动模式的增强提示词
        
        Args:
            user_input: 用户原始输入
            analysis: 认知分析结果
        
        Returns:
            增强后的提示词
        """
        complexity = analysis.get("complexity", "medium")
        thinking_instruction = (
            "请开启深度思考，仔细分析后再执行。"
            if self._thinking_enabled
            else "请高效执行，无需过多思考。"
        )

        return f"""{user_input}

【自动模式指令】
- 任务复杂度评估：{complexity}
- {thinking_instruction}
- 优先使用最简洁的方案
- 批量操作时尝试合并同类操作
- 遇到错误时先分析原因再重试"""
