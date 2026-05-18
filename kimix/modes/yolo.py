"""
YOLO 模式 (YOLO Mode)

全自主执行模式，最大化效率。
- 所有操作自动审批，无需确认
- Thinking 模式关闭，节省 token
- 批量操作时原子性执行
- 自动错误恢复

适用场景：
- 充分信任 Agent 的熟练用户
- 紧急修复
- 大批量重构
- 已充分测试的自动化工作流

⚠️ 警告：此模式不询问确认，请确保你了解潜在风险。
"""

from __future__ import annotations

from typing import Any

from kimix.core.events import (
    EngineEvent,
    create_event,
    create_thinking_event,
    create_content_event,
)
from kimix.modes.base import BaseMode, ApprovalLevel


class YoloMode(BaseMode):
    """YOLO 模式 - 全自主执行
    
    此模式下 Agent 拥有完全自主权，所有操作自动执行。
    Thinking 模式关闭以节省 token，追求最高执行效率。
    
    ⚠️ 安全说明：
    - 仍遵循最小权限原则
    - 操作失败时自动重试或调整
    - 批量操作保持原子性
    - 危险命令仍然会被拦截（底层安全保护）
    
    Attributes:
        name: "yolo"
        description: "YOLO 模式 - 全自主，自动审批"
        approval_level: ApprovalLevel.NONE（所有操作自动通过）
        supports_thinking: False（关闭 thinking 节省 token）
    
    Examples:
        >>> mode = YoloMode()
        >>> mode.should_approve("file_delete")
        False  # YOLO 模式下所有操作自动通过
    """

    name: str = "yolo"
    description: str = "YOLO 模式 - 全自主，自动审批"
    approval_level: ApprovalLevel = ApprovalLevel.NONE
    supports_thinking: bool = False

    # 即使 YOLO 模式下也要拦截的极度危险命令
    BLOCKED_COMMANDS: list[str] = [
        "rm -rf /",
        "rm -rf /*",
        ":(){:|:&};:",  # Fork bomb
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sda",
        "> /dev/sda",
        "mv / /dev/null",
    ]

    async def process(
        self,
        engine: Any,
        user_input: str,
    ) -> Any:
        """处理 YOLO 模式下的用户输入
        
        YOLO 模式直接委托给引擎，所有工具自动执行。
        仅对极度危险命令进行底层拦截。
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        """
        # 发送模式标识
        yield create_thinking_event("[YOLO 模式] 全自主执行，自动审批所有操作...")

        # 认知分析
        analysis = engine.cognitive_analysis(user_input)
        complexity = analysis.get("complexity", "medium")
        task_type = analysis.get("task_type", "general")

        yield create_thinking_event(
            f"任务：{task_type}，复杂度：{complexity}，"
            f"Thinking：关闭（节省 token）"
        )

        # 构建 YOLO 模式提示词
        yolo_prompt = self._build_yolo_prompt(user_input, analysis)

        # 委托给引擎，拦截极度危险命令
        async for event in engine.run(yolo_prompt):
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            # 底层安全拦截：检查极度危险命令
            if event_type == "tool_call":
                tool_calls = event_data.get("tool_calls", [])
                safe_calls = []
                blocked_calls = []

                for tc in tool_calls:
                    tc_name = tc.function.name
                    tc_args = tc.function.arguments

                    if self._is_extremely_dangerous(tc_name, tc_args):
                        blocked_calls.append(tc)
                    else:
                        safe_calls.append(tc)

                # 拦截极度危险命令
                if blocked_calls:
                    for tc in blocked_calls:
                        tc_name = tc.function.name
                        yield create_thinking_event(
                            f"🛡️ 安全拦截：阻止执行极度危险操作 '{tc_name}'"
                        )
                        yield create_event("tool_result", {
                            "tool_call_id": tc.id,
                            "name": tc_name,
                            "result": None,
                            "error": "安全拦截：此操作被系统安全策略阻止",
                        })

                # 执行安全工具
                if safe_calls:
                    yield create_event("tool_call", {"tool_calls": safe_calls})
                    results = await engine.execute_tools(safe_calls)
                    for result in results:
                        yield create_event("tool_result", result)

                continue

            # 透传其他事件
            yield event

    def should_approve(self, tool_name: str, tool_params: dict[str, Any] | None = None) -> bool:
        """YOLO 模式下几乎所有操作都无需审批
        
        底层安全拦截在 process 方法中处理。
        
        Returns:
            False - 几乎所有操作自动通过
        """
        return False

    def _is_extremely_dangerous(self, tool_name: str, tool_args: Any) -> bool:
        """检查是否为极度危险的操作
        
        YOLO 模式的最后防线，阻止明确的破坏性命令。
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
        
        Returns:
            True 如果是极度危险操作
        """
        if tool_name != "shell":
            # 非 shell 工具目前不拦截
            return False

        if not tool_args:
            return False

        import json
        try:
            args = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
            command = str(args.get("command", "")).lower().strip()

            # 检查是否在阻断列表中
            for blocked in self.BLOCKED_COMMANDS:
                if blocked.lower() in command:
                    return True

            # 检查 rm -rf 后跟根目录
            if command.startswith("rm -rf") or command.startswith("rm -fr"):
                parts = command.split()
                for part in parts[2:]:
                    if part in ("/", "/*", "/.", "/.."):
                        return True

            # 检查管道中的危险命令
            if "|" in command:
                segments = [s.strip() for s in command.split("|")]
                for seg in segments:
                    for blocked in self.BLOCKED_COMMANDS:
                        if blocked.lower() in seg:
                            return True

        except (json.JSONDecodeError, AttributeError):
            pass

        return False

    def _build_yolo_prompt(self, user_input: str, analysis: dict[str, Any]) -> str:
        """构建 YOLO 模式的增强提示词
        
        Args:
            user_input: 用户原始输入
            analysis: 认知分析结果
        
        Returns:
            增强后的提示词
        """
        return f"""{user_input}

【YOLO 模式指令】
- 全自主执行，无需用户确认
- 追求最高效率，简洁响应
- 批量操作尽量合并
- 失败时自动重试或调整策略
- 操作完成后给出简洁的总结"""
