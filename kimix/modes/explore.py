"""
探索模式 (Explore Mode)

只读模式，用于信息收集和代码库理解。
- 所有工具调用均为只读操作
- Thinking 模式开启，深度分析
- 无需审批，用户可自由探索

适用场景：
- 新项目的代码库结构分析
- 代码阅读和审查
- 查找特定代码片段
- 理解项目依赖关系
"""

from __future__ import annotations

from typing import Any

from kimix.core.events import EngineEvent, create_event, create_content_event
from kimix.modes.base import BaseMode, ApprovalLevel


class ExploreMode(BaseMode):
    """探索模式 - 只读信息收集
    
    此模式下 Agent 只能执行只读操作，不能修改任何文件。
    适合用于理解代码库、审查代码、查找信息等场景。
    
    Attributes:
        name: "explore"
        description: "探索模式 - 只读信息收集与代码理解"
        approval_level: ApprovalLevel.NONE（只读操作全部自动通过）
        supports_thinking: True（开启深度思考）
    
    Examples:
        >>> mode = ExploreMode()
        >>> mode.should_approve("file_read")
        False
        >>> mode.should_approve("file_write")
        True  # 写入操作不允许，返回 True 表示"拒绝执行"
    """

    name: str = "explore"
    description: str = "探索模式 - 只读信息收集与代码理解"
    approval_level: ApprovalLevel = ApprovalLevel.NONE
    supports_thinking: bool = True

    # 允许使用的只读工具
    ALLOWED_TOOLS: set[str] = {
        "file_read", "file_list", "file_search", "file_stat",
        "git_status", "git_log", "git_diff", "git_show", "git_branch",
        "web_search", "web_fetch",
    }

    async def process(
        self,
        engine: Any,
        user_input: str,
    ) -> Any:
        """处理探索模式下的用户输入
        
        在探索模式下，直接委托给引擎的 run 方法执行，
        但会过滤工具调用，只允许只读工具。
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        """
        from kimix.core.events import create_thinking_event

        # 发送模式标识事件
        yield create_event("thinking", {
            "text": "[探索模式] 开始只读分析...",
        })

        # 认知分析
        analysis = engine.cognitive_analysis(user_input)
        yield create_thinking_event(
            f"任务分析：{analysis.get('task_type', 'unknown')}，"
            f"复杂度：{analysis.get('complexity', 'unknown')}"
        )

        # 委托给引擎主循环，但拦截工具调用
        async for event in engine.run(user_input):
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            # 拦截非只读工具调用
            if event_type == "tool_call":
                tool_calls = event_data.get("tool_calls", [])
                filtered_calls = []
                blocked_calls = []

                for tc in tool_calls:
                    tc_name = tc.function.name
                    if tc_name in self.ALLOWED_TOOLS or self.is_readonly_tool(tc_name):
                        filtered_calls.append(tc)
                    else:
                        blocked_calls.append(tc_name)

                if blocked_calls:
                    yield create_event("thinking", {
                        "text": f"[探索模式] 已阻止写入操作：{', '.join(blocked_calls)} "
                                f"（探索模式仅允许只读操作）",
                    })

                if filtered_calls:
                    # 只执行允许的只读工具
                    yield create_event("tool_call", {"tool_calls": filtered_calls})
                    results = await engine.execute_tools(filtered_calls)
                    for result in results:
                        yield create_event("tool_result", result)

                    # 工具结果需要回传给模型继续处理
                    # 这里我们不继续循环，而是让调用者处理
                continue

            # 透传其他所有事件
            yield event

        yield create_event("content", {
            "text": "\n\n[探索模式分析完成] 如需修改文件，请切换到 Agent/Auto/YOLO 模式。",
        })

    def should_approve(self, tool_name: str, tool_params: dict[str, Any] | None = None) -> bool:
        """探索模式下，只读工具无需审批，写入工具直接拒绝
        
        Returns:
            False - 只读工具直接执行
            True - 非只读工具需要"审批"（实际是拒绝执行）
        """
        if tool_name in self.ALLOWED_TOOLS or self.is_readonly_tool(tool_name):
            return False  # 无需审批，直接执行

        # 非只读工具：返回 True 表示需要"审批"，实际是拒绝
        return True
