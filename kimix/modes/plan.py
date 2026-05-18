"""
规划模式 (Plan Mode)

只读+计划生成模式，用于任务分析和方案制定。
- 可执行只读操作调研项目现状
- 生成详细的执行计划（但不实际执行）
- Thinking 模式开启，深度分析
- 无需审批（不修改任何文件）

适用场景：
- 复杂任务的方案设计
- 代码重构的规划
- 架构设计的讨论
- 项目迁移的计划制定
"""

from __future__ import annotations

from typing import Any

from kimix.core.events import EngineEvent, create_event, create_content_event, create_thinking_event
from kimix.modes.base import BaseMode, ApprovalLevel


class PlanMode(BaseMode):
    """规划模式 - 只读调研与计划生成
    
    此模式下 Agent 可以调研项目（只读），然后生成详细的执行计划。
    不执行任何写入操作，输出格式化的计划文档。
    
    Attributes:
        name: "plan"
        description: "规划模式 - 只读调研与计划生成"
        approval_level: ApprovalLevel.NONE（不执行写入操作）
        supports_thinking: True（开启深度思考）
    
    Examples:
        >>> mode = PlanMode()
        >>> info = mode.get_mode_info()
        >>> info["name"]
        'plan'
    """

    name: str = "plan"
    description: str = "规划模式 - 只读调研与计划生成"
    approval_level: ApprovalLevel = ApprovalLevel.NONE
    supports_thinking: bool = True

    # 允许使用的只读工具
    ALLOWED_TOOLS: set[str] = {
        "file_read", "file_list", "file_search", "file_stat",
        "git_status", "git_log", "git_diff", "git_show", "git_branch",
        "web_search", "web_fetch",
    }

    # 计划输出模板
    PLAN_TEMPLATE: str = """
## 执行计划

### 1. 目标概述
{objective}

### 2. 现状分析
{current_state}

### 3. 执行步骤
{steps}

### 4. 依赖关系
{dependencies}

### 5. 风险评估
{risks}

### 6. 预估工作量
{effort_estimate}

---
> 本计划由规划模式生成。如需执行，请切换到 Agent/Auto/YOLO 模式。
"""

    async def process(
        self,
        engine: Any,
        user_input: str,
    ) -> Any:
        """处理规划模式下的用户输入
        
        流程：
        1. 分析用户需求
        2. 调研项目现状（只读操作）
        3. 生成详细的执行计划
        4. 输出格式化的计划文档
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        """
        # 发送模式标识
        yield create_thinking_event("[规划模式] 开始分析需求并制定计划...")

        # 认知分析
        analysis = engine.cognitive_analysis(user_input)
        task_type = analysis.get("task_type", "general")
        complexity = analysis.get("complexity", "medium")

        yield create_thinking_event(
            f"任务类型：{task_type}，复杂度：{complexity}"
        )

        # 阶段 1：委托给引擎执行调研（只读工具）
        yield create_event("thinking", {
            "text": "[阶段 1/3] 调研项目现状...",
        })

        # 修改用户输入，引导模型先调研再制定计划
        planning_prompt = self._build_planning_prompt(user_input, analysis)

        # 执行调研和计划生成
        plan_parts: list[str] = []
        async for event in engine.run(planning_prompt):
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            # 拦截非只读工具调用
            if event_type == "tool_call":
                tool_calls = event_data.get("tool_calls", [])
                filtered_calls = self._filter_readonly_tools(tool_calls)
                blocked = [tc.get("function", {}).get("name", "") for tc in tool_calls
                          if tc not in filtered_calls]

                if blocked:
                    yield create_thinking_event(
                        f"[规划模式] 跳过写入工具：{', '.join(blocked)}"
                    )

                if filtered_calls:
                    yield create_event("tool_call", {"tool_calls": filtered_calls})
                    results = await engine.execute_tools(filtered_calls)
                    for result in results:
                        yield create_event("tool_result", result)
                continue

            # 收集响应内容用于生成计划
            if event_type == "content":
                plan_parts.append(event_data.get("text", ""))

            # 透传 thinking 和 content 事件
            if event_type in ("thinking", "content"):
                yield event

        # 阶段 2：格式化计划输出
        yield create_thinking_event("[阶段 2/3] 整理执行计划...")

        # 阶段 3：输出总结
        yield create_thinking_event("[阶段 3/3] 计划生成完成")

        # 输出模式切换提示
        yield create_content_event(
            "\n\n---\n"
            "[规划模式] 计划已生成。如需执行上述计划，请切换到 **Agent 模式** 或 **Auto 模式**。\n"
            "提示：使用 `/mode agent` 或 `/mode auto` 切换模式。"
        )

    def _build_planning_prompt(self, user_input: str, analysis: dict[str, Any]) -> str:
        """构建规划模式的提示词
        
        在用户原始输入基础上，增加规划引导指令。
        
        Args:
            user_input: 用户原始输入
            analysis: 认知分析结果
        
        Returns:
            增强后的提示词
        """
        task_type = analysis.get("task_type", "general")
        complexity = analysis.get("complexity", "medium")

        planning_instructions = f"""请帮我制定一个详细的执行计划。

## 用户需求
{user_input}

## 认知分析
- 任务类型：{task_type}
- 复杂度：{complexity}

## 要求
1. 首先调研项目现状（读取相关文件了解当前状态）
2. 然后按照以下格式输出计划：
   - 目标概述
   - 现状分析
   - 执行步骤（编号、描述、涉及文件）
   - 依赖关系
   - 风险评估
   - 预估工作量
3. 只读取文件，不要修改任何内容
4. 步骤要具体可操作，包含具体的文件路径

请开始调研并制定计划："""

        return planning_instructions

    def _filter_readonly_tools(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """过滤工具调用，只保留只读工具
        
        Args:
            tool_calls: 原始工具调用列表
        
        Returns:
            过滤后的只读工具调用列表
        """
        filtered = []
        for tc in tool_calls:
            tc_name = tc.get("function", {}).get("name", "")
            if tc_name in self.ALLOWED_TOOLS or self.is_readonly_tool(tc_name):
                filtered.append(tc)
        return filtered
