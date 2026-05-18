"""
子 Agent 工作进程模块

提供 SubAgentWorker 类，实现单个任务的异步执行。每个 Worker
拥有独立的上下文和工具子集，支持取消操作和进度事件流。

执行模型:
1. Worker 接收任务描述和上下文
2. 在独立 asyncio.Task 中执行
3. 通过 Queue 发送进度事件
4. 返回结构化结果
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from kimix.subagents.models import (
    AgentRole,
    SubAgentEvent,
    SubAgentResult,
    SubAgentTask,
)


class SubAgentWorker:
    """子 Agent 工作进程

    执行单个任务的异步工作单元，拥有独立上下文和工具子集，
    支持进度事件流和取消操作。

    Attributes:
        _task: 任务描述
        _context: 执行上下文
        _role: Agent 角色
        _cancelled: 取消标志
        _event_queue: 进度事件队列
        _execution_log: 执行日志列表
        _start_time: 任务开始时间
    """

    # 各角色对应的工具子集映射
    ROLE_TOOLSETS: dict[AgentRole, list[str]] = {
        AgentRole.EXPLORER: ["file_read", "file_list", "shell"],
        AgentRole.PLANNER: ["file_read", "web_search"],
        AgentRole.CODER: ["file_read", "file_write", "file_edit", "shell"],
        AgentRole.REVIEWER: ["file_read", "git_diff"],
        AgentRole.TESTER: ["file_read", "file_write", "shell"],
        AgentRole.DEBUGGER: ["file_read", "shell", "web_search"],
        AgentRole.RESEARCHER: ["web_search", "web_fetch", "file_read"],
        AgentRole.DOCUMENTER: ["file_read", "file_write"],
    }

    # 各角色的系统提示词模板
    ROLE_PROMPTS: dict[AgentRole, str] = {
        AgentRole.EXPLORER: "你是一个代码库探索专家。分析文件结构，理解代码组织方式，提供清晰的概览。",
        AgentRole.PLANNER: "你是一个架构设计专家。制定详细的实施计划，考虑依赖关系和最佳实践。",
        AgentRole.CODER: "你是一个高效的程序员。编写清晰、可维护、经过测试的代码。",
        AgentRole.REVIEWER: "你是一个严格的代码审查者。检查代码质量、安全性和性能问题。",
        AgentRole.TESTER: "你是一个测试专家。编写全面的测试用例，确保代码正确性。",
        AgentRole.DEBUGGER: "你是一个调试专家。系统性诊断问题根因，提供精确的修复方案。",
        AgentRole.RESEARCHER: "你是一个技术调研专家。搜索并分析技术文档，提供有深度的调研报告。",
        AgentRole.DOCUMENTER: "你是一个技术文档专家。编写清晰、准确的技术文档和注释。",
    }

    def __init__(
        self,
        task: SubAgentTask,
        llm_client: Any | None = None,
    ) -> None:
        """初始化工作进程

        Args:
            task: 子 Agent 任务描述
            llm_client: 可选的 LLM 客户端实例（用于实际 LLM 调用）
        """
        self._task: SubAgentTask = task
        self._llm_client: Any | None = llm_client
        self._role: AgentRole = task.role
        self._cancelled: bool = False
        self._event_queue: asyncio.Queue[SubAgentEvent] = asyncio.Queue()
        self._execution_log: list[str] = []
        self._start_time: float = 0.0

    @property
    def worker_id(self) -> str:
        """工作进程唯一标识符

        Returns:
            Worker ID 字符串
        """
        return f"worker_{self._task.id}_{uuid.uuid4().hex[:8]}"

    @property
    def available_tools(self) -> list[str]:
        """获取当前角色可用的工具列表

        Returns:
            工具名称列表
        """
        return self.ROLE_TOOLSETS.get(self._role, ["file_read"])

    @property
    def system_prompt(self) -> str:
        """获取当前角色的系统提示词

        Returns:
            系统提示词文本
        """
        base_prompt = self.ROLE_PROMPTS.get(
            self._role, "你是一个有帮助的 AI 助手。"
        )
        tools_info = f"\n可用工具: {', '.join(self.available_tools)}"
        task_info = f"\n任务: {self._task.task_description}"
        return f"{base_prompt}{tools_info}{task_info}"

    async def run(self) -> SubAgentResult:
        """执行任务并返回结果

        在 Worker 中执行分配的任务，支持进度事件报告和取消检查。
        如果配置了 llm_client，则使用 LLM 进行智能执行；
        否则使用模拟执行模式（用于测试和演示）。

        Returns:
            SubAgentResult 执行结果

        Raises:
            asyncio.CancelledError: 当任务被取消时
        """
        self._start_time = time.monotonic()
        self._log(f"Worker {self.worker_id} 开始执行任务: {self._task.id}")
        self._log(f"角色: {self._role.value}, 优先级: {self._task.priority.name}")

        # 发送开始事件
        await self._emit_event("progress", {"percent": 0, "message": "任务启动"})

        try:
            if self._llm_client is not None:
                result = await self._execute_with_llm()
            else:
                result = await self._execute_simulated()

            elapsed = time.monotonic() - self._start_time
            self._log(f"任务完成，耗时 {elapsed:.2f} 秒")

            await self._emit_event(
                "completed", {"elapsed": elapsed, "status": "success"}
            )
            return result

        except asyncio.CancelledError:
            self._log("任务被取消")
            await self._emit_event("error", {"message": "任务被取消"})
            raise

        except Exception as e:
            self._log(f"任务执行出错: {type(e).__name__}: {e}")
            await self._emit_event(
                "error", {"message": str(e), "type": type(e).__name__}
            )
            return self._build_result(
                status="failed",
                summary=f"执行失败: {e}",
            )

    async def _execute_with_llm(self) -> SubAgentResult:
        """使用 LLM 客户端执行任务（内部方法）

        实际调用 LLM 进行智能任务执行。需要配置 llm_client。

        Returns:
            执行结果
        """
        # 进度阶段 1: 分析任务
        await self._emit_event("progress", {"percent": 10, "message": "分析任务需求"})
        await self._check_cancelled()

        # 进度阶段 2: 准备上下文
        await self._emit_event("progress", {"percent": 20, "message": "准备执行上下文"})
        context_summary = self._build_context_summary()
        await self._check_cancelled()

        # 进度阶段 3: 执行核心逻辑（使用 LLM）
        await self._emit_event("progress", {"percent": 30, "message": "执行核心任务"})

        # 构建消息
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": f"任务: {self._task.task_description}\n\n上下文: {context_summary}",
            },
        ]

        # 调用 LLM（流式）
        full_response = ""
        try:
            # 注意: 这里假设 llm_client 有 async chat 方法
            if hasattr(self._llm_client, "chat"):
                async for chunk in self._llm_client.chat(
                    messages=messages, stream=True
                ):
                    if hasattr(chunk, "content"):
                        full_response += chunk.content
                    await self._check_cancelled()
            else:
                full_response = f"[模拟 LLM 响应] 执行任务: {self._task.task_description}"
        except Exception as e:
            self._log(f"LLM 调用出错: {e}")
            full_response = f"LLM 调用失败: {e}"

        await self._emit_event("progress", {"percent": 80, "message": "处理执行结果"})

        # 进度阶段 4: 生成结果
        await self._emit_event("progress", {"percent": 95, "message": "生成最终结果"})

        evidence = self._extract_evidence(full_response)

        return self._build_result(
            status="completed",
            summary=full_response,
            evidence=evidence,
        )

    async def _execute_simulated(self) -> SubAgentResult:
        """模拟执行任务（内部方法，用于测试）

        模拟真实执行流程，包含多个进度阶段和延迟。

        Returns:
            模拟的执行结果
        """
        # 阶段 1: 初始化 (10%)
        await self._emit_event("progress", {"percent": 10, "message": "初始化任务环境"})
        await asyncio.sleep(0.1)
        await self._check_cancelled()

        # 阶段 2: 分析 (30%)
        await self._emit_event("progress", {"percent": 30, "message": f"分析任务: {self._task.task_description[:50]}..."})
        await asyncio.sleep(0.1)
        await self._check_cancelled()

        # 阶段 3: 执行核心逻辑 (70%)
        await self._emit_event("progress", {"percent": 70, "message": "执行核心逻辑"})

        # 模拟工具调用日志
        for tool in self.available_tools[:3]:
            self._log(f"调用工具: {tool}")
            await asyncio.sleep(0.05)
            await self._check_cancelled()

        # 阶段 4: 完成 (100%)
        await self._emit_event("progress", {"percent": 100, "message": "任务完成"})

        summary = (
            f"[{self._role.value}] 任务 '{self._task.task_description[:50]}' "
            f"已完成。使用了工具: {', '.join(self.available_tools[:3])}"
        )

        evidence = [
            {"type": "context", "data": self._build_context_summary()},
            {"type": "tools_used", "data": self.available_tools[:3]},
            {"type": "role", "data": self._role.value},
        ]

        return self._build_result(
            status="completed",
            summary=summary,
            evidence=evidence,
        )

    def cancel(self) -> None:
        """取消任务执行

        设置取消标志，Worker 会在下一个检查点停止执行。
        """
        self._cancelled = True
        self._log("收到取消信号")

    async def event_stream(self) -> AsyncIterator[SubAgentEvent]:
        """获取进度事件流

        异步迭代器，实时获取 Worker 执行过程中的事件。

        Yields:
            SubAgentEvent 事件字典
        """
        while True:
            try:
                # 使用 timeout 避免永久阻塞
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=0.5
                )
                yield event
                if event["type"] in ("completed", "error"):
                    break
            except asyncio.TimeoutError:
                # 超时检查 Worker 是否还在运行
                continue

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """发送进度事件（内部方法）

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        event: SubAgentEvent = {"type": event_type, "data": data}
        await self._event_queue.put(event)

    async def _check_cancelled(self) -> None:
        """检查是否被取消（内部方法）

        Raises:
            asyncio.CancelledError: 如果任务已被取消
        """
        if self._cancelled:
            raise asyncio.CancelledError(f"Worker {self.worker_id} 已取消")
        # 让出控制权，允许取消信号处理
        await asyncio.sleep(0)

    def _log(self, message: str) -> None:
        """记录执行日志（内部方法）

        Args:
            message: 日志消息
        """
        timestamp = _iso_timestamp()
        log_entry = f"[{timestamp}] [{self.worker_id}] {message}"
        self._execution_log.append(log_entry)

    def _build_context_summary(self) -> str:
        """构建上下文摘要（内部方法）

        Returns:
            上下文摘要文本
        """
        parts: list[str] = []
        ctx = self._task.context

        if "files" in ctx:
            parts.append(f"相关文件: {', '.join(ctx['files'][:5])}")
        if "code" in ctx:
            code = ctx["code"]
            parts.append(f"代码片段: {code[:200]}..." if len(code) > 200 else f"代码片段: {code}")
        if "project_path" in ctx:
            parts.append(f"项目路径: {ctx['project_path']}")

        return "\n".join(parts) if parts else "无额外上下文"

    def _extract_evidence(self, response: str) -> list[dict[str, Any]]:
        """从响应中提取证据材料（内部方法）

        Args:
            response: LLM 响应文本

        Returns:
            证据材料列表
        """
        evidence: list[dict[str, Any]] = [
            {"type": "response", "data": response[:1000]},
            {"type": "role", "data": self._role.value},
            {"type": "tools_available", "data": self.available_tools},
        ]

        # 提取代码块
        import re
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", response, re.DOTALL)
        for i, (lang, code) in enumerate(code_blocks[:3]):
            evidence.append(
                {
                    "type": "code",
                    "language": lang or "unknown",
                    "data": code[:500],
                }
            )

        return evidence

    def _build_result(
        self,
        status: str,
        summary: str,
        evidence: list[dict[str, Any]] | None = None,
    ) -> SubAgentResult:
        """构建执行结果（内部方法）

        Args:
            status: 结果状态
            summary: 结果摘要
            evidence: 证据材料

        Returns:
            SubAgentResult 实例
        """
        elapsed = time.monotonic() - self._start_time

        return SubAgentResult(
            task_id=self._task.id,
            status=status,
            summary=summary,
            evidence=evidence or [],
            execution_log=self._execution_log,
            usage={
                "input_tokens": len(self.system_prompt) + len(self._task.task_description),
                "output_tokens": len(summary),
                "elapsed_ms": int(elapsed * 1000),
            },
        )


def _iso_timestamp() -> str:
    """生成 ISO 8601 格式时间戳（模块级工具函数）

    Returns:
        ISO 8601 格式时间戳字符串
    """
    return datetime.now(timezone.utc).isoformat()
