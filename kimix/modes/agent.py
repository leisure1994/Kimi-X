"""
Agent 模式 (Agent Mode)

默认的交互执行模式，平衡自主性和安全性。
- 可读写文件、执行 Shell 命令
- 智能审批：只读自动通过，写入需确认
- 交互式确认关键决策
- Thinking 模式根据任务自动调整

适用场景：
- 日常开发任务
- 代码编写和修改
- 调试和修复
- 文件操作
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


class AgentMode(BaseMode):
    """Agent 模式 - 交互执行（默认模式）
    
    此模式下 Agent 可以执行读写操作，但破坏性操作需要用户确认。
    是日常开发的主要工作模式，平衡了效率和安全性。
    
    Attributes:
        name: "agent"
        description: "Agent 模式 - 交互执行，智能审批（默认）"
        approval_level: ApprovalLevel.DESTRUCTIVE（破坏性操作需审批）
        supports_thinking: True（根据任务自动调整）
    
    Examples:
        >>> mode = AgentMode()
        >>> mode.should_approve("file_read")
        False  # 只读无需审批
        >>> mode.should_approve("file_write")
        True   # 写入需审批
    """

    name: str = "agent"
    description: str = "Agent 模式 - 交互执行，智能审批（默认）"
    approval_level: ApprovalLevel = ApprovalLevel.DESTRUCTIVE
    supports_thinking: bool = True

    # 无需审批的工具（只读+安全操作）
    AUTO_APPROVE_TOOLS: set[str] = {
        "file_read", "file_list", "file_search", "file_stat",
        "git_status", "git_log", "git_diff", "git_show", "git_branch",
        "web_search", "web_fetch",
        # 安全的 git 操作
        "git_add", "git_commit",
    }

    # 总是需要确认的工具（破坏性操作）
    ALWAYS_CONFIRM_TOOLS: set[str] = {
        "file_delete",
        "shell",
        "git_reset", "git_checkout_force", "git_clean", "git_revert",
    }

    async def process(
        self,
        engine: Any,
        user_input: str,
    ) -> Any:
        """处理 Agent 模式下的用户输入
        
        Agent 模式直接委托给引擎主循环，但在工具调用时进行审批检查。
        
        流程：
        1. 认知分析
        2. 委托引擎执行
        3. 拦截工具调用，根据审批规则处理
        4. 需要审批的工具：生成审批请求事件
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        """
        # 发送模式标识
        yield create_thinking_event("[Agent 模式] 开始交互执行...")

        # 认知分析
        analysis = engine.cognitive_analysis(user_input)
        task_type = analysis.get("task_type", "general")
        risk_level = analysis.get("risk_level", "safe")

        yield create_thinking_event(
            f"任务类型：{task_type}，风险等级：{risk_level}"
        )

        # 如果风险较高，提示用户
        if risk_level in ("high", "critical"):
            yield create_event("thinking", {
                "text": f"⚠️ 检测到高风险操作（{risk_level}），将要求逐项确认",
            })

        # 委托给引擎主循环，但拦截并处理工具调用的审批
        pending_tool_calls: list[dict[str, Any]] = []
        pending_results: list[dict[str, Any]] = []

        async for event in engine.run(user_input):
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            # 拦截工具调用事件，进行审批检查
            if event_type == "tool_call":
                tool_calls = event_data.get("tool_calls", [])
                approved_calls = []
                needs_approval = []

                for tc in tool_calls:
                    tc_name = tc.get("function", {}).get("name", "")
                    tc_params = tc.get("function", {}).get("arguments", {})

                    if self._is_auto_approved(tc_name, tc_params):
                        approved_calls.append(tc)
                    else:
                        needs_approval.append(tc)

                # 执行自动通过的工具
                if approved_calls:
                    yield create_event("tool_call", {"tool_calls": approved_calls})
                    results = await engine.execute_tools(approved_calls)
                    for result in results:
                        yield create_event("tool_result", result)

                # 对需审批的工具生成审批事件
                if needs_approval:
                    for tc in needs_approval:
                        tc_name = tc.get("function", {}).get("name", "")
                        tc_args = tc.get("function", {}).get("arguments", "")
                        tc_id = tc.get("id", "")

                        yield create_event("thinking", {
                            "text": f"⏸️ 等待审批：工具 '{tc_name}' (参数: {tc_args})",
                            "tool_call_id": tc_id,
                            "tool_name": tc_name,
                            "tool_params": tc_args,
                            "requires_approval": True,
                        })

                    # 在 Agent 模式下，这里应该暂停等待用户确认
                    # 实际实现中，UI 层会处理审批交互
                    # 引擎层面将待审批的工具保留，等待后续处理
                    pending_tool_calls.extend(needs_approval)

                continue

            # 透传其他所有事件
            yield event

        # 如有待审批工具，在结束时提示
        if pending_tool_calls:
            tool_names = [tc.get("function", {}).get("name", "") for tc in pending_tool_calls]
            yield create_content_event(
                f"\n\n[待审批操作] 以下工具调用需要您的确认：\n"
                + "\n".join(f"  - {name}" for name in tool_names)
                + "\n请确认是否执行以上操作。"
            )

    def _is_auto_approved(self, tool_name: str, tool_params: Any = None) -> bool:
        """判断工具是否自动通过审批
        
        Agent 模式的审批逻辑：
        - 只读工具：自动通过
        - 白名单工具：自动通过
        - 黑名单工具：总是需要确认
        - 写入工具：需要确认
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数
        
        Returns:
            True 如果自动通过
        """
        # 黑名单工具总是需确认
        if tool_name in self.ALWAYS_CONFIRM_TOOLS:
            # 但 shell 命令需要检查具体内容
            if tool_name == "shell" and tool_params:
                import json
                try:
                    params = json.loads(tool_params) if isinstance(tool_params, str) else tool_params
                    command = str(params.get("command", "")).lower()
                    # 安全的命令可自动通过
                    safe_commands = ["ls", "pwd", "cat", "grep", "find", "echo", "head", "tail", "wc", "sort", "uniq"]
                    if any(command.strip().startswith(sc) for sc in safe_commands):
                        return True
                except (json.JSONDecodeError, AttributeError):
                    pass
            return False

        # 白名单工具自动通过
        if tool_name in self.AUTO_APPROVE_TOOLS:
            return True

        # 只读工具自动通过
        if self.is_readonly_tool(tool_name):
            return True

        # 其他工具（主要是写入类）需要确认
        return False
