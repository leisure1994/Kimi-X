"""
Agent 核心引擎模块

实现 Kimi-Agent 的主循环，包括：
- 认知分析（任务复杂度和风险评估）
- 模式决策和切换
- LLM 流式调用
- 工具调用循环
- 记忆存储与检索
- 事件流生成（SSE 兼容）

引擎是 Agent 系统的核心协调者，串联所有子系统。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from kimix.core.events import (
    EngineEvent,
    create_event,
    create_content_event,
    create_thinking_event,
    create_tool_call_event,
    create_tool_result_event,
    create_tool_start_event,
    create_tool_end_event,
    create_error_event,
    create_done_event,
    create_cost_update_event,
)
from kimix.core.turn import Turn, TurnResult
from kimix.core.context import ContextManager
from kimix.core.session import Session, SessionManager
from kimix.core.observability import Observability


# ---- ToolCall 兼容性辅助函数 ----
def _tc_to_dict(tc: Any) -> dict[str, Any]:
    """将 ToolCall（dict 或 pydantic Model）统一转为 dict"""
    if isinstance(tc, dict):
        return tc
    if hasattr(tc, 'to_dict'):
        return tc.to_dict()
    if hasattr(tc, 'id') and hasattr(tc, 'function'):
        return {
            "id": tc.id,
            "type": getattr(tc, 'type', 'function'),
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
        }
    return {}


def _tc_name(tc: Any) -> str:
    """获取 ToolCall 的工具名称"""
    d = _tc_to_dict(tc)
    func = d.get("function") or {}
    return func.get("name", "") or ""


def _tc_params(tc: Any) -> str:
    """获取 ToolCall 的参数 JSON 字符串"""
    d = _tc_to_dict(tc)
    func = d.get("function") or {}
    return func.get("arguments", "") or "{}"


class AgentMode(Enum):
    """Agent 工作模式枚举
    
    定义 5 种工作模式，从保守到激进：
    
    - EXPLORE: 探索模式 - 只读，thinking on
    - PLAN: 规划模式 - 只读+计划生成，thinking on
    - AGENT: Agent 模式 - 交互执行（默认），智能审批
    - AUTO: 自动模式 - 自适应 thinking，智能审批门
    - YOLO: YOLO 模式 - 全自主，自动审批
    
    Examples:
        >>> AgentMode.AGENT
        <AgentMode.AGENT: 'agent'>
        >>> AgentMode.AGENT.value
        'agent'
    """
    EXPLORE = "explore"
    PLAN = "plan"
    AGENT = "agent"
    AUTO = "auto"
    YOLO = "yolo"


# 协议类（用于类型提示，避免循环导入）

@runtime_checkable
class LLMClientLike(Protocol):
    """LLM 客户端协议"""
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]: ...

    async def chat_with_thinking(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
    ) -> tuple[str, str]: ...


@runtime_checkable
class ToolRegistryLike(Protocol):
    """工具注册表协议"""
    def get(self, tool_name: str) -> Any: ...
    def list_tools(self) -> list[Any]: ...
    def to_openai_schema(self) -> list[dict]: ...


@runtime_checkable
class MemoryManagerLike(Protocol):
    """记忆管理器协议"""
    async def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...
    async def store(self, entry: dict[str, Any]) -> None: ...


@runtime_checkable
class SubAgentOrchestratorLike(Protocol):
    """子 Agent 编排器协议"""
    async def spawn(
        self,
        role: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> Any: ...

    async def spawn_batch(self, tasks: list[dict[str, Any]]) -> list[Any]: ...


@runtime_checkable
class ModeRouterLike(Protocol):
    """模式路由器协议"""
    def analyze_task(self, user_input: str) -> dict[str, Any]: ...
    def suggest_mode(self, analysis: dict[str, Any]) -> AgentMode: ...
    def auto_route(self, analysis: dict[str, Any]) -> AgentMode: ...


# 认知分析结果类型
class CognitiveAnalysis(dict):
    """认知分析结果类 - 支持属性访问和字典访问
    
    同时兼容 dict['key'] 和 dict.key 两种访问方式。
    """
    
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
    
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' 对象没有属性 '{name}'") from None
    
    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class AgentEngine:
    """Agent 核心引擎
    
    管理整个 Agent 生命周期，是系统的核心协调者。
    通过 AsyncIterator 产生事件流，支持 SSE 流式输出。
    
    Attributes:
        llm_client: LLM 客户端
        tool_registry: 工具注册表
        memory: 记忆管理器
        subagent_orchestrator: 子 Agent 编排器
        mode: 当前工作模式
        context: 上下文管理器
        session: 当前会话
        mode_router: 模式路由器
    
    Examples:
        >>> # 伪代码示例
        >>> engine = AgentEngine(llm_client, tools, memory)
        >>> async for event in engine.run("帮我分析这个项目"):
        ...     print(event["type"], event["data"])
    """

    def __init__(
        self,
        llm_client: LLMClientLike,
        tool_registry: ToolRegistryLike,
        memory: MemoryManagerLike | None = None,
        subagent_orchestrator: SubAgentOrchestratorLike | None = None,
        mode: AgentMode = AgentMode.AGENT,
        mode_router: ModeRouterLike | None = None,
        session_manager: SessionManager | None = None,
        learning_system: Any | None = None,
        preflight_checker: Any | None = None,
        healing_engine: Any | None = None,
        experience_memory: Any | None = None,
    ) -> None:
        """初始化 Agent 引擎
        
        Args:
            llm_client: LLM 客户端实例
            tool_registry: 工具注册表实例
            memory: 记忆管理器（可选）
            subagent_orchestrator: 子 Agent 编排器（可选）
            mode: 初始工作模式，默认 AGENT
            mode_router: 模式路由器（可选，AUTO 模式需要）
            session_manager: 会话管理器（可选）
            learning_system: 自学习系统（可选）
            preflight_checker: 预判检查器（可选）
            healing_engine: 自我修复引擎（可选）
            experience_memory: 经验积累系统（可选）
        """
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.memory = memory
        self.subagent_orchestrator = subagent_orchestrator
        self._mode = mode
        self.mode_router = mode_router
        self.session_manager = session_manager
        self.learning_system = learning_system
        self.preflight_checker = preflight_checker
        self.healing_engine = healing_engine
        self.experience_memory = experience_memory
        self.observability: Any | None = None  # 由 initialize 时注入

        # 运行时状态
        self._session: Session | None = None
        self._context: ContextManager | None = None
        self._running = False
        self._current_turn: Turn | None = None

        # 累计成本统计
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0

    @property
    def mode(self) -> AgentMode:
        """当前工作模式"""
        return self._mode

    @property
    def session(self) -> Session | None:
        """当前会话"""
        return self._session

    @property
    def context(self) -> ContextManager | None:
        """当前上下文管理器"""
        return self._context

    async def initialize(
        self,
        session: Session | None = None,
        project_path: str = ".",
    ) -> None:
        """初始化引擎运行环境
        
        Args:
            session: 复用的会话（可选）
            project_path: 项目路径（新建会话时使用）
        """
        # 初始化会话
        if session:
            self._session = session
        elif self.session_manager:
            self._session = await self.session_manager.create(
                project_path=project_path,
            )
        else:
            self._session = Session(project_path=project_path)

        # 初始化上下文管理器
        self._context = ContextManager(
            session_id=self._session.id,
            project_path=project_path,
            mode=self._mode.value,
        )

        self._running = True

    async def run(self, user_input: str) -> AsyncIterator[EngineEvent]:
        """主运行循环，产生流式事件
        
        核心执行流程：
        1. 认知分析 - 分析任务复杂度和风险
        2. 模式决策 - 根据分析和当前模式确定执行模式
        3. 记忆检索 - 获取相关上下文记忆
        4. 构建消息 - 组装 LLM 输入
        5. 调用 LLM（流式）- 产生 thinking/content/tool_call 事件
        6. 工具执行 - 如需要，执行工具并回传结果
        7. 存储记忆 - 保存交互到记忆系统
        8. 完成 - 产生 done 事件
        
        Args:
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        
        Examples:
            >>> async for event in engine.run("帮我读取 README.md"):
            ...     if event["type"] == "content":
            ...         print(event["data"]["text"], end="")
            ...     elif event["type"] == "tool_call":
            ...         print(f"调用工具: {event['data']['tool_calls']}")
        """
        if not self._running or self._context is None:
            yield create_error_event(
                message="引擎未初始化，请先调用 initialize()",
                code="ENGINE_NOT_INITIALIZED",
                recoverable=False,
            )
            return

        start_time = time.monotonic()
        turn_id = f"turn-{uuid.uuid4().hex[:8]}"

        # 可观测性追踪
        if self.observability is not None:
            self.observability.event("turn_start", {"turn_id": turn_id, "mode": self._mode.value, "input_length": len(user_input)})

        # 创建回合
        turn = Turn(
            id=turn_id,
            user_input=user_input,
            mode=self._mode.value,
        )
        turn.set_status("running")
        self._current_turn = turn

        try:
            # ========== 0. 预判检查 ==========
            if self.preflight_checker is not None:
                preflight_ctx = {
                    "api_key": getattr(self.llm_client, "api_key", None),
                    "budget_tokens": getattr(self.llm_client, "_budget_limit", 1_000_000),
                    "workspace_dir": self._context.project_path if self._context else ".",
                    "active_subagents": getattr(self.subagent_orchestrator, "active_count", 0) if self.subagent_orchestrator else 0,
                    "max_concurrent": 32,
                    "experience_memory": self.experience_memory,
                    "task_signature": user_input[:200],
                }
                preflight_result = await self.preflight_checker.check(preflight_ctx)
                
                # 输出预判警告
                for warning in preflight_result.warnings:
                    yield create_event(
                        type="warning",
                        data={
                            "category": warning.category,
                            "message": warning.message,
                            "suggestion": warning.suggestion,
                        },
                    )
                
                # 输出自动修复结果
                for fixed in preflight_result.auto_fixed:
                    yield create_event(
                        type="notice",
                        data={
                            "message": f"已自动修复: {fixed}",
                        },
                    )
                
                # 严重问题阻断执行
                if not preflight_result.passed:
                    for issue in preflight_result.issues:
                        if issue.risk_level.value == "critical":
                            yield create_error_event(
                                message=f"预判发现严重问题 [{issue.category}]: {issue.message}。建议: {issue.suggestion}",
                                code="PREFLIGHT_CRITICAL",
                                recoverable=False,
                            )
                            turn.set_status("error")
                            return
                    # HIGH 级别问题不阻断，但发出强烈警告
                    for issue in preflight_result.issues:
                        yield create_event(
                            type="preflight_alert",
                            data={
                                "risk_level": issue.risk_level.value,
                                "category": issue.category,
                                "message": issue.message,
                                "suggestion": issue.suggestion,
                            },
                        )

            # ========== 1. 认知分析 ==========
            if self.observability is not None:
                self.observability.event("preflight_done", {"passed": preflight_result.passed, "issues": len(preflight_result.issues), "warnings": len(preflight_result.warnings)})
            analysis = self.cognitive_analysis(user_input)
            yield create_event("thinking", {
                "text": f"认知分析：复杂度={analysis.get('complexity', 'unknown')}, "
                        f"风险={analysis.get('risk_level', 'unknown')}, "
                        f"类型={analysis.get('task_type', 'unknown')}",
            })

            # ========== 2. 模式决策 ==========
            effective_mode = self._mode
            if self._mode == AgentMode.AUTO and self.mode_router is not None:
                effective_mode = self.mode_router.auto_route(analysis)
                if effective_mode != self._mode:
                    yield create_event("mode_switch", {
                        "from": self._mode.value,
                        "to": effective_mode.value,
                        "reason": f"AUTO 模式路由决策：{analysis.get('task_type', 'unknown')}",
                    })

            # ========== 3. 记忆检索 ==========
            relevant_memories: list[dict[str, Any]] = []
            if self.memory is not None:
                try:
                    relevant_memories = await self.memory.recall(user_input, limit=5)
                    if relevant_memories:
                        yield create_event("thinking", {
                            "text": f"检索到 {len(relevant_memories)} 条相关记忆",
                        })
                except Exception as e:
                    yield create_event("thinking", {
                        "text": f"记忆检索失败（非关键）: {e}",
                    })

            # ========== 3.5 自学习经验检索 ==========
            experience_guidance = ""
            if self.learning_system is not None:
                try:
                    task_type = analysis.get("task_type", "general")
                    context_tags = [task_type, self._mode.value]
                    experience_guidance = await self.learning_system.retrieve_guidance(
                        task_description=user_input[:200],
                        task_type=task_type,
                        context_tags=context_tags,
                    )
                    if experience_guidance:
                        yield create_event("thinking", {
                            "text": f"注入历史经验指导（{len(experience_guidance)} chars）",
                        })
                except Exception:
                    pass

            # ========== 4. 构建消息 ==========
            messages = self._context.build_messages(
                user_input, relevant_memories, experience_guidance=experience_guidance
            )

            # 获取工具定义
            tools = self.tool_registry.to_openai_schema()

            # ========== 5. 流式调用 LLM ==========
            max_iterations = 10  # 防止无限循环
            iteration = 0
            assistant_response = ""
            accumulated_tool_calls: list[dict[str, Any]] = []

            while iteration < max_iterations:
                iteration += 1
                current_tool_calls: list[dict[str, Any]] = []
                current_content = ""
                current_thinking = ""
                tool_call_accumulator: dict[str, Any] = {}

                try:
                    async for event in self.llm_client.chat(messages, tools=tools):
                        event_type = event.get("type", "")
                        event_data = event.get("data", {})

                        if event_type == "thinking":
                            # 思考内容 - event_data 可能是字符串或字典
                            thinking_text = event_data if isinstance(event_data, str) else event_data.get("text", "")
                            current_thinking += thinking_text
                            yield create_thinking_event(thinking_text)

                        elif event_type == "content":
                            # 响应内容 - event_data 可能是字符串或字典
                            text = event_data if isinstance(event_data, str) else event_data.get("text", "")
                            current_content += text
                            yield create_content_event(text)

                        elif event_type == "tool_call":
                            # 工具调用（增量或完整）
                            # event_data 可能是 ToolCall Model（来自 streaming）或 dict
                            if hasattr(event_data, 'to_dict'):
                                tc = event_data.to_dict()
                            elif hasattr(event_data, 'get'):
                                tc = event_data.get("tool_call", {})
                            elif isinstance(event_data, dict):
                                tc = event_data
                            else:
                                tc = {}
                            if tc:
                                current_tool_calls.append(tc)

                        elif event_type == "usage":
                            # Token 使用统计
                            if isinstance(event_data, dict):
                                input_tokens = event_data.get("input_tokens", 0) or 0
                                output_tokens = event_data.get("output_tokens", 0) or 0
                            else:
                                input_tokens = getattr(event_data, "prompt_tokens", 0) or 0
                                output_tokens = getattr(event_data, "completion_tokens", 0) or 0
                            self._total_input_tokens += input_tokens
                            self._total_output_tokens += output_tokens

                            # 使用 cost_tracker 的定价计算成本
                            from kimix.llm.cost_tracker import Pricing
                            pricing = Pricing()
                            cost = (
                                input_tokens * pricing.input_per_1m
                                + output_tokens * pricing.output_per_1m
                            ) / 1_000_000
                            self._total_cost_usd += cost
                            yield create_cost_update_event(
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cost_usd=cost,
                            )

                except Exception as e:
                    # ========== 自我修复尝试 ==========
                    if self.healing_engine is not None:
                        yield create_event(
                            type="healing_start",
                            data={
                                "error": str(e),
                                "message": f"检测到错误，尝试自动修复: {type(e).__name__}",
                            },
                        )
                        healed, heal_result = await self.healing_engine.heal(
                            error=e,
                            original_task=self.llm_client.chat,
                            task_args=(messages,),
                            task_kwargs={"tools": tools, "stream": True},
                            context={
                                "api_key": getattr(self.llm_client, "api_key", None),
                                "fallback_model": "kimi-for-coding-lite",
                                "healing_attempt": iteration - 1,
                            },
                        )
                        if healed:
                            yield create_event(
                                type="healing_success",
                                data={
                                    "message": "自动修复成功，继续执行",
                                    "result_preview": str(heal_result)[:100] if heal_result else "",
                                },
                            )
                            # 修复成功，可以继续（这里简化为重新进入下一轮迭代）
                            continue
                        else:
                            yield create_event(
                                type="healing_failed",
                                data={
                                    "message": "自动修复失败，需要人工介入",
                                    "original_error": str(e),
                                },
                            )

                    yield create_error_event(
                        message=f"LLM 调用失败: {e}",
                        code="LLM_ERROR",
                        recoverable=False,
                    )
                    turn.set_status("error")
                    return

                # 保存助手回复到上下文
                if current_content or current_tool_calls:
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": current_content,
                    }
                    if current_tool_calls:
                        assistant_msg["tool_calls"] = current_tool_calls
                    messages.append(assistant_msg)
                    self._context.add_assistant_message(
                        current_content, current_tool_calls
                    )

                assistant_response += current_content
                accumulated_tool_calls.extend(current_tool_calls)

                # ========== 6. 工具执行 ==========
                if current_tool_calls:
                    yield create_tool_call_event(current_tool_calls)

                    # 执行工具
                    results = await self.execute_tools(current_tool_calls)

                    for result in results:
                        if isinstance(result, dict):
                            tc_id = result.get("tool_call_id", "")
                            tc_name = result.get("name", "")
                            tc_result = result.get("result")
                            tc_error = result.get("error")
                        else:
                            tc_id = getattr(result, "tool_call_id", "")
                            tc_name = getattr(result, "name", "")
                            tc_result = getattr(result, "result", None)
                            tc_error = getattr(result, "error", None)

                        # 发送结果事件
                        yield create_tool_result_event(
                            tool_call_id=tc_id,
                            name=tc_name,
                            result=tc_result,
                            error=tc_error,
                        )

                        # 添加工具结果到消息
                        content = tc_result if tc_result else f"错误: {tc_error}"
                        if not isinstance(content, str):
                            import json
                            content = json.dumps(content, ensure_ascii=False, default=str)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tc_name,
                            "content": content,
                        })
                        self._context.add_tool_message(tc_id, tc_name, content)

                    # 工具结果回传后，继续循环让 LLM 处理
                    continue

                # 没有工具调用，完成本轮
                break

            # ========== 7. 存储记忆 ==========
            if self.memory is not None:
                try:
                    await self.memory.store({
                        "type": "conversation",
                        "query": user_input,
                        "response": assistant_response,
                        "turn_id": turn_id,
                        "mode": self._mode.value,
                        "tool_calls": [
                            {"name": _tc_name(tc), "params": _tc_params(tc)}
                            for tc in accumulated_tool_calls
                        ],
                    })
                except Exception as e:
                    yield create_event("thinking", {
                        "text": f"记忆存储失败（非关键）: {e}",
                    })

            # 完成
            duration_ms = int((time.monotonic() - start_time) * 1000)
            duration_seconds = duration_ms / 1000.0
            turn.set_status("completed")

            # ========== 7.5 经验积累 ==========
            if self.experience_memory is not None:
                try:
                    task_type = analysis.get("task_type", "general")
                    # 记录性能基线
                    self.experience_memory.record_performance(
                        task_signature=f"{task_type}:{user_input[:100]}",
                        model=getattr(self.llm_client, "model", "unknown"),
                        latency_ms=duration_ms,
                        input_tokens=self._total_input_tokens,
                        output_tokens=self._total_output_tokens,
                        cost_usd=self._total_cost_usd,
                    )
                    # 记录路由效果（如果模式发生了切换）
                    if self._mode == AgentMode.AUTO and self.mode_router is not None:
                        effective_mode = self._get_effective_mode(analysis)
                        self.experience_memory.record_routing(
                            task_signature=f"{task_type}:{user_input[:100]}",
                            chosen_mode=effective_mode.value,
                            satisfaction=0.85,  # 简化评估，实际可根据完成质量动态打分
                        )
                except Exception:
                    pass  # 经验积累失败不应阻断主流程

            # ========== 8. 后台自学习 ==========
            if self.learning_system is not None:
                try:
                    from kimix.learning.models import TaskOutcome
                    task_type = analysis.get("task_type", "general")
                    tools_names = [
                        (tc.get("function") or {}).get("name", "") if isinstance(tc, dict)
                        else getattr(getattr(tc, "function", None), "name", "")
                        for tc in accumulated_tool_calls
                    ]
                    outcome = TaskOutcome.SUCCESS if assistant_response else TaskOutcome.PARTIAL
                    await self.learning_system.learn_from_execution(
                        task_description=user_input[:200],
                        task_type=task_type,
                        tools_used=tools_names,
                        steps=[{"tool": t} for t in tools_names],
                        outcome=outcome,
                        duration_seconds=duration_seconds,
                        token_cost=self._total_input_tokens + self._total_output_tokens,
                    )
                except Exception:
                    pass

            # 可观测性收尾
            duration_ms = int((time.monotonic() - start_time) * 1000)
            if self.observability is not None:
                self.observability.finish_turn(
                    turn_id=turn_id,
                    latency_ms=duration_ms,
                    input_tokens=self._total_input_tokens,
                    output_tokens=self._total_output_tokens,
                    cost_usd=self._total_cost_usd,
                    model=getattr(self.llm_client, "model", "unknown"),
                    mode=self._mode.value,
                    tool_calls=len(accumulated_tool_calls),
                    errors=0,
                    healing_attempts=0,
                    preflight_issues=len(preflight_result.issues) if 'preflight_result' in dir() else 0,
                )

            yield create_done_event(
                turn_id=turn_id,
                usage={
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                    "total_tokens": self._total_input_tokens + self._total_output_tokens,
                },
            )

        except Exception as e:
            turn.set_status("error")
            yield create_error_event(
                message=f"引擎运行错误: {e}",
                code="ENGINE_RUNTIME_ERROR",
                recoverable=False,
            )

    async def process_turn(self, turn: Turn) -> TurnResult:
        """处理单个回合
        
        非流式接口，适合不需要实时事件反馈的场景。
        
        Args:
            turn: 要处理的 Turn 对象
        
        Returns:
            TurnResult 回合结果
        """
        start_time = time.monotonic()
        response_parts: list[str] = []
        tool_calls_log: list[dict[str, Any]] = []

        async for event in self.run(turn.user_input):
            event_type = event["type"]
            event_data = event["data"]

            if event_type == "content":
                response_parts.append(event_data if isinstance(event_data, str) else event_data.get("text", ""))
            elif event_type == "tool_result":
                if isinstance(event_data, dict):
                    tool_calls_log.append({
                        "name": event_data.get("name", ""),
                        "result": event_data.get("result"),
                        "error": event_data.get("error"),
                    })
                else:
                    tool_calls_log.append({
                        "name": getattr(event_data, "name", "") or "",
                        "result": getattr(event_data, "result", None),
                        "error": getattr(event_data, "error", None),
                    })

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return TurnResult(
            turn_id=turn.id,
            response="".join(response_parts),
            tool_calls=tool_calls_log,
            usage={
                "input_tokens": self._total_input_tokens,
                "output_tokens": self._total_output_tokens,
            },
            duration_ms=duration_ms,
            mode=self._mode.value,
        )

    async def execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """执行工具调用列表
        
        并发执行所有工具调用，收集结果。
        
        Args:
            tool_calls: 工具调用列表，每项包含 id, function(name, arguments)
        
        Returns:
            工具结果列表，每项包含 tool_call_id, name, result, error
        """
        results: list[dict[str, Any]] = []

        # 创建并发执行任务
        async def execute_single(tool_call: Any) -> dict[str, Any]:
            tc_dict = _tc_to_dict(tool_call)
            tc_id = tc_dict.get("id", "")
            function_data = tc_dict.get("function") or {}
            tool_name = function_data.get("name", "") or ""
            arguments_str = function_data.get("arguments", "") or "{}"

            start_time = time.monotonic()

            try:
                # 解析参数
                import json
                try:
                    params = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                except json.JSONDecodeError:
                    params = {"raw": arguments_str}

                # 查找工具
                try:
                    tool = self.tool_registry.get(tool_name)
                except Exception as e:
                    return {
                        "tool_call_id": tc_id,
                        "name": tool_name,
                        "result": None,
                        "error": f"工具 '{tool_name}' 未找到: {e}",
                        "duration_ms": int((time.monotonic() - start_time) * 1000),
                    }

                # 执行工具
                result = await tool.execute(params, {})

                return {
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "result": result,
                    "error": None,
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                }

            except Exception as e:
                return {
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "result": None,
                    "error": str(e),
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                }

        # 并发执行所有工具
        tasks = [execute_single(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常结果
        final_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tc = tool_calls[i] if i < len(tool_calls) else {}
                tc_id = tc.get("id", "") if isinstance(tc, dict) else ""
                fn_data = tc.get("function", {}) if isinstance(tc, dict) else {}
                tool_name = fn_data.get("name", "") if isinstance(fn_data, dict) else ""
                final_results.append({
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "result": None,
                    "error": f"工具执行异常: {result}",
                    "duration_ms": 0,
                })
            else:
                final_results.append(result)

        return final_results

    def switch_mode(self, mode: AgentMode) -> None:
        """切换工作模式
        
        切换模式会更新引擎状态和上下文管理器的系统提示词。
        
        Args:
            mode: 目标工作模式
        
        Raises:
            ValueError: 如果 mode 不是有效的 AgentMode
        
        Examples:
            >>> engine.switch_mode(AgentMode.EXPLORE)
            >>> engine.mode
            <AgentMode.EXPLORE: 'explore'>
        """
        if not isinstance(mode, AgentMode):
            raise ValueError(f"无效的工作模式: {mode}")

        old_mode = self._mode
        self._mode = mode

        # 更新上下文管理器的模式
        if self._context is not None:
            self._context.update_mode(mode.value)

    def cognitive_analysis(self, user_input: str) -> CognitiveAnalysis:
        """认知分析 - 分析任务复杂度和风险
        
        基于启发式规则分析用户输入，识别：
        - 任务类型：简单问答、文件操作、代码重构、架构设计等
        - 复杂度：low / medium / high / critical
        - 风险等级：safe / low / medium / high
        - 是否需要文件操作
        - 是否涉及破坏性操作
        
        此分析用于模式决策和审批控制。
        
        Args:
            user_input: 用户输入文本
        
        Returns:
            认知分析结果字典
        
        Examples:
            >>> analysis = engine.cognitive_analysis("帮我读取 README.md")
            >>> analysis["complexity"]
            'low'
            >>> analysis["task_type"]
            'file_read'
        """
        import re

        result = CognitiveAnalysis(
            task_type="general",
            complexity="low",
            risk_level="safe",
            needs_file_ops=False,
            destructive=False,
            needs_thinking=False,
            suggested_tools=[],
            reasoning="",
        )

        text = user_input.lower()

        # ===== 任务类型识别 =====

        # 简单问答模式
        simple_qa_patterns = [
            r"^(什么|怎么|为什么|如何|请问|什么是)",
            r"(解释|说明|介绍|什么是|什么是)$",
            r"^(hi|hello|hey|你好|您好|在吗)",
            r"(谢谢|感谢|再见|拜拜)",
        ]
        if any(re.search(p, text) for p in simple_qa_patterns):
            result["task_type"] = "simple_qa"
            result["complexity"] = "low"
            result["risk_level"] = "safe"
            result["needs_file_ops"] = False
            result["needs_thinking"] = False
            result["suggested_tools"] = []
            result["reasoning"] = "简单问答，无需文件操作"
            return result

        # 文件读取模式
        read_patterns = [
            r"(读取|查看|打开|显示|读一下|读一下|cat|read|show|display)\s+\S+\.(md|txt|py|json|yaml|yml|js|ts|html|css|go|rs|java|c|cpp|h)",
            r"(看看|看下|看一下)\s+\S+",
            r"README",
            r"\.py\b",
            r"\.json\b",
            r"\.yaml\b",
            r"\.md\b",
        ]
        if any(re.search(p, text) for p in read_patterns):
            result["task_type"] = "file_read"
            result["complexity"] = "low"
            result["risk_level"] = "safe"
            result["needs_file_ops"] = True
            result["destructive"] = False
            result["needs_thinking"] = False
            result["suggested_tools"] = ["file_read"]
            result["reasoning"] = "文件读取操作，只读无风险"

        # 文件写入/修改模式
        write_patterns = [
            r"(创建|写入|修改|编辑|更新|保存|write|create|edit|modify|update)\s+\S+\.",
            r"(写个|写一个|新建|添加)\s+(文件|脚本|函数|类|模块)",
            r"(生成|gen)\s+(代码|文件|脚本)",
            r"(fix|修复|fix\s+bug|debug|调试)",
            r"(refactor|重构|重写|rewrite)",
        ]
        if any(re.search(p, text) for p in write_patterns):
            result["task_type"] = "file_write"
            result["needs_file_ops"] = True
            result["destructive"] = True  # 写入可能覆盖
            if "重构" in user_input or "refactor" in text:
                result["task_type"] = "code_refactor"
                result["complexity"] = "high"
                result["needs_thinking"] = True
                result["reasoning"] = "代码重构任务，需要分析和规划"
            elif "fix" in text or "修复" in user_input or "debug" in text or "调试" in user_input:
                result["task_type"] = "debug"
                result["complexity"] = "medium"
                result["needs_thinking"] = True
                result["reasoning"] = "调试任务，需要分析错误原因"
            else:
                result["complexity"] = "medium"
                result["reasoning"] = "文件写入操作，需谨慎处理"
            result["risk_level"] = "medium"
            result["suggested_tools"] = ["file_read", "file_write", "file_edit"]

        # Shell 命令模式
        shell_patterns = [
            r"(运行|执行|调用|run|execute|exec)\s+(命令|cmd|shell|script|\w+)",
            r"(pip|npm|yarn|cargo|go\s+mod|docker|kubectl|git\s+(clone|pull|push|commit|checkout|merge|rebase))",
            r"^(cd|ls|pwd|cat|grep|find|mkdir|touch|rm|cp|mv|chmod|chown|curl|wget)\b",
        ]
        if any(re.search(p, text) for p in shell_patterns):
            result["task_type"] = "shell_exec"
            result["needs_file_ops"] = True
            result["destructive"] = "rm" in text or "删除" in user_input or "drop" in text
            result["complexity"] = "medium"
            result["risk_level"] = "medium" if not result["destructive"] else "high"
            result["suggested_tools"] = ["shell"]
            result["reasoning"] = f"Shell 命令执行，风险等级: {result['risk_level']}"

        # 架构设计模式
        arch_patterns = [
            r"(架构|设计|架构设计|系统设计|system\s+design|architecture)",
            r"(设计模式|pattern|DDD|TDD|微服务|microservice|分布式|distributed)",
            r"(数据库设计|db\s+design|schema\s+design|ER\s*图)",
            r"(API\s+设计|接口设计|openapi|swagger|graphql)",
        ]
        if any(re.search(p, text) for p in arch_patterns):
            result["task_type"] = "architecture_design"
            result["complexity"] = "high"
            result["risk_level"] = "low"  # 设计本身不修改文件
            result["needs_file_ops"] = False
            result["destructive"] = False
            result["needs_thinking"] = True
            result["suggested_tools"] = ["file_read"]
            result["reasoning"] = "架构设计任务，需要深度思考"

        # 代码审查模式
        review_patterns = [
            r"(审查|review|code\s+review|cr|检查|check)\s+(代码|code|文件|file|PR|pull\s*request|mr)",
            r"(看看|review)\s+(这个|这段|这个文件|this)",
            r"(优化建议|improvement|优化|optimize|better\s+way)",
        ]
        if any(re.search(p, text) for p in review_patterns):
            result["task_type"] = "code_review"
            result["complexity"] = "medium"
            result["risk_level"] = "safe"
            result["needs_file_ops"] = True
            result["destructive"] = False
            result["needs_thinking"] = True
            result["suggested_tools"] = ["file_read"]
            result["reasoning"] = "代码审查任务，只读分析"

        # 批量/复杂操作检测
        batch_patterns = [
            r"(所有|全部|every|all\s+files|批量|batch|bulk)",
            r"(多个|几个|多\s*个|many|several)",
            r"(项目|整个项目|project|codebase|仓库|repo)\s+(重构|修改|分析|审查|迁移)",
        ]
        if any(re.search(p, text) for p in batch_patterns):
            result["complexity"] = "high"
            result["needs_thinking"] = True
            result["reasoning"] += "；批量操作，复杂度提升"

        # Git 操作
        git_patterns = [
            r"(git\s+(commit|push|pull|merge|rebase|checkout|branch|reset|revert|stash|tag))",
            r"(提交|推送|拉取|合并|分支|回滚|撤销)",
        ]
        if any(re.search(p, text) for p in git_patterns):
            result["task_type"] = "git_operation"
            result["needs_file_ops"] = True
            result["destructive"] = any(
                kw in text for kw in ["reset", "revert", "回滚", "撤销", "--hard"]
            )
            result["risk_level"] = "medium" if not result["destructive"] else "high"
            result["suggested_tools"] = ["git"]
            result["reasoning"] = f"Git 操作，风险等级: {result['risk_level']}"

        # 安全性检查
        dangerous_patterns = [
            r"rm\s+-rf\s+/",
            r":\(\)\{\s*:\|:&\s*\};:",
            r"dd\s+if=.*of=/dev/",
            r">\s*/dev/\w+",
            r"mkfs\.",
            r"chmod\s+-R\s+777\s+/",
        ]
        if any(re.search(p, text) for p in dangerous_patterns):
            result["risk_level"] = "critical"
            result["destructive"] = True
            result["reasoning"] += "；⚠️ 检测到危险命令模式！"

        # 最终复杂度综合评估
        if result["complexity"] == "high" or result["needs_thinking"]:
            result["needs_thinking"] = True

        return result

    async def shutdown(self) -> None:
        """关闭引擎，释放资源"""
        self._running = False
        self._current_turn = None

        # 保存当前会话
        if self._session and self.session_manager:
            try:
                await self.session_manager.save(self._session)
            except Exception:
                pass  # 关闭时不阻断

    def get_stats(self) -> dict[str, Any]:
        """获取引擎运行统计
        
        Returns:
            包含 token 使用、成本、模式等统计信息的字典
        """
        return {
            "mode": self._mode.value,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "session_id": self._session.id if self._session else None,
            "is_running": self._running,
        }
