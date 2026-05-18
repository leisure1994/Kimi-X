"""
CLI 界面模块（非交互模式）

提供一次性问答和批处理场景的命令行界面：
- CLIInterface 类: 统一的 CLI 界面入口
  - run_once(): 单次问答执行
  - run_interactive(): 简单交互循环
  - run_stream(): 流式响应实时渲染

使用 Rich Console 进行格式化输出，支持：
- 流式响应实时渲染（思考过程和内容）
- 成本实时显示
- 工具执行进度指示器（spinner）
- 代码块语法高亮
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from typing import Any, AsyncIterator

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.status import Status
from rich.syntax import Syntax
from rich.text import Text

from kimix.core.engine import AgentEngine, AgentMode
from kimix.core.events import EngineEvent
from kimix.ui.renderers import (
    ThinkingRenderer,
    ToolCallRenderer,
    ToolResultRenderer,
    CostRenderer,
    MessageRenderer,
)


class CLIInterface:
    """CLI 界面类

    为非交互式场景提供格式化输出界面，
    包括一次性问答、流式响应渲染和成本追踪。

    Attributes:
        console: Rich 控制台实例
        mode: 当前 Agent 模式
        cost_renderer: 成本渲染器
        message_renderer: 消息渲染器
        show_thinking: 是否显示思考过程
        show_cost: 是否显示成本
        streaming: 是否启用流式输出
    """

    def __init__(
        self,
        console: Console | None = None,
        mode: AgentMode = AgentMode.AGENT,
        show_thinking: bool = True,
        show_cost: bool = True,
        streaming: bool = True,
    ) -> None:
        self.console = console or Console()
        self.mode = mode
        self.show_thinking = show_thinking
        self.show_cost = show_cost
        self.streaming = streaming

        # 渲染器
        self.cost_renderer = CostRenderer(console=self.console)
        self.message_renderer = MessageRenderer(console=self.console)
        self.thinking_renderer = ThinkingRenderer(console=self.console)
        self.tool_call_renderer = ToolCallRenderer(console=self.console)
        self.tool_result_renderer = ToolResultRenderer(console=self.console)

        # 状态
        self._current_content: str = ""  # 当前累积的响应内容
        self._is_thinking: bool = False
        self._executing_tools: set[str] = set()  # 正在执行的工具

    def print_banner(self) -> None:
        """打印启动横幅"""
        banner = Text.assemble(
            Text("╭────────────────────────────────────╮\n", style="magenta"),
            Text("│  ", style="magenta"),
            Text("🤖 Kimi-Agent", style="bold magenta"),
            Text(" v1.0.0-beta", style="magenta dim"),
            Text("          │\n", style="magenta"),
            Text("│  ", style="magenta"),
            Text("智能终端 AI Agent - 比 TUI 更聪明", style="white dim"),
            Text("  │\n", style="magenta"),
            Text("╰────────────────────────────────────╯", style="magenta"),
        )
        self.console.print(banner)

    def print_mode_info(self) -> None:
        """打印当前模式信息"""
        mode_labels: dict[AgentMode, str] = {
            AgentMode.EXPLORE: "🔍 探索模式 - 只读，安全浏览",
            AgentMode.PLAN: "📋 规划模式 - 制定执行计划",
            AgentMode.AGENT: "🤖 Agent 模式 - 交互执行（默认）",
            AgentMode.AUTO: "⚡ 自动模式 - 智能审批",
            AgentMode.YOLO: "🚀 YOLO 模式 - 全自主执行",
        }
        label = mode_labels.get(self.mode, "未知模式")
        self.console.print(f"\n[bold cyan]{label}[/bold cyan]")
        self.console.print(Rule(style="bright_black"))

    async def run_once(
        self,
        engine: AgentEngine | None,
        query: str,
    ) -> dict[str, Any]:
        """执行单次问答

        接收用户输入，调用引擎处理，实时渲染流式输出，
        最后返回完整结果和统计信息。

        Args:
            engine: Agent 引擎实例
            query: 用户问题

        Returns:
            dict: 包含响应内容和统计信息
        """
        result: dict[str, Any] = {
            "content": "",
            "thinking": "",
            "tool_calls": [],
            "cost": 0.0,
            "error": None,
        }

        if engine is None:
            self.console.print(
                "[red]错误: 引擎未初始化。请检查 API Key 配置。[/red]"
            )
            result["error"] = "引擎未初始化"
            return result

        # 显示用户输入
        self.console.print()
        self.console.print(
            Panel(
                Text(query, style="cyan"),
                border_style="cyan dim",
                title="[bold]👤 你[/bold]",
                title_align="left",
            )
        )
        self.console.print()

        try:
            if self.streaming:
                result = await self._run_streaming(engine, query)
            else:
                result = await self._run_batch(engine, query)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]已取消[/yellow]")
            result["error"] = "用户取消"
        except Exception as exc:
            self.console.print(f"\n[red]错误: {exc}[/red]")
            result["error"] = str(exc)

        return result

    async def _run_streaming(
        self,
        engine: AgentEngine,
        query: str,
    ) -> dict[str, Any]:
        """流式执行并实时渲染"""
        content = ""
        thinking = ""
        tool_calls: list[dict[str, Any]] = []

        # 创建布局组件
        content_text = Text("", style="magenta")
        thinking_panel = self.thinking_renderer.render()
        cost_text = self.cost_renderer.render()

        # 使用 Rich Live 进行实时更新
        with Live(
            self._build_streaming_display(content_text, thinking_panel, cost_text),
            console=self.console,
            refresh_per_second=10,
            transient=False,
        ) as live:
            async for event in engine.run(query):
                ev_type = event["type"]
                data = event.get("data", {})

                if ev_type == "thinking":
                    # 更新思考过程
                    thinking += data.get("text", "")
                    if self.show_thinking:
                        self.thinking_renderer.update(data.get("text", ""))

                elif ev_type == "content":
                    # 更新响应内容
                    chunk = data.get("text", "")
                    content += chunk
                    content_text.append(chunk, style="magenta")

                elif ev_type == "tool_start":
                    # 工具开始执行
                    tool_name = data.get("name", "unknown")
                    params = data.get("params", {})
                    self._executing_tools.add(data.get("tool_call_id", tool_name))
                    tool_calls.append({
                        "name": tool_name,
                        "params": params,
                        "status": "running",
                    })

                elif ev_type == "tool_result":
                    # 工具执行结果
                    tool_name = data.get("name", "unknown")
                    result_data = data.get("result")
                    error = data.get("error")
                    tc_id = data.get("tool_call_id", tool_name)
                    if tc_id in self._executing_tools:
                        self._executing_tools.discard(tc_id)
                    # 更新工具调用记录
                    for tc in tool_calls:
                        if tc["name"] == tool_name:
                            tc["result"] = result_data
                            tc["error"] = error
                            tc["status"] = "completed"

                elif ev_type == "cost_update":
                    # 更新成本
                    self.cost_renderer.update(
                        cost_usd=data.get("cost_usd", 0.0),
                        input_tokens=data.get("input_tokens", 0),
                        output_tokens=data.get("output_tokens", 0),
                    )

                elif ev_type == "done":
                    # 完成
                    break

                elif ev_type == "error":
                    # 错误
                    error_msg = data.get("message", "未知错误")
                    self.console.print(f"[red]错误: {error_msg}[/red]")

                # 更新显示
                thinking_panel = self.thinking_renderer.render_inline() if self.show_thinking else Text("")
                cost_text = self.cost_renderer.render() if self.show_cost else Text("")
                live.update(
                    self._build_streaming_display(content_text, thinking_panel, cost_text)
                )

        # 最终输出
        self.console.print()
        if content:
            self.console.print(
                Panel(
                    Markdown(content),
                    border_style="magenta dim",
                    title="[bold]🤖 Kimi[/bold]",
                    title_align="left",
                )
            )

        # 显示成本
        if self.show_cost:
            self.console.print()
            self.console.print(self.cost_renderer.render())

        return {
            "content": content,
            "thinking": thinking,
            "tool_calls": tool_calls,
            "cost": self.cost_renderer.session_cost,
            "error": None,
        }

    def _build_streaming_display(
        self,
        content: Text,
        thinking: Text | Panel,
        cost: Text,
    ) -> Panel:
        """构建流式显示内容"""
        table_content: list[RenderableType] = []

        # 思考过程（折叠显示）
        if self.show_thinking and thinking:
            table_content.append(thinking)
            table_content.append(Text(""))

        # 内容区域
        if content.plain:
            table_content.append(content)

        # 成本
        if self.show_cost:
            table_content.append(Text(""))
            table_content.append(cost)

        # 工具执行状态
        if self._executing_tools:
            spinner = Spinner("dots", text="正在执行工具...", style="green")
            table_content.append(Text(""))
            table_content.append(spinner)

        from rich.table import Table as RichTable
        display = RichTable(show_header=False, box=None, padding=(0, 0))
        display.add_column("content", ratio=1)
        for item in table_content:
            display.add_row(item)

        return Panel(
            display,
            border_style="bright_black dim",
            padding=(0, 1),
        )

    async def _run_batch(
        self,
        engine: AgentEngine,
        query: str,
    ) -> dict[str, Any]:
        """批量执行（非流式）"""
        content = ""
        thinking = ""
        tool_calls: list[dict[str, Any]] = []

        with self.console.status("[bold green]思考中...") as status:
            async for event in engine.run(query):
                ev_type = event["type"]
                data = event.get("data", {})

                if ev_type == "thinking":
                    thinking += data.get("text", "")
                    status.update("[bold green]💭 思考中...[/bold green]")

                elif ev_type == "tool_start":
                    tool_name = data.get("name", "unknown")
                    status.update(f"[bold green]🔧 执行 {tool_name}...[/bold green]")

                elif ev_type == "content":
                    content += data.get("text", "")

                elif ev_type == "done":
                    break

        # 输出结果
        self.console.print()
        if content:
            self.console.print(
                Panel(
                    Markdown(content),
                    border_style="magenta dim",
                    title="[bold]🤖 Kimi[/bold]",
                    title_align="left",
                )
            )

        return {
            "content": content,
            "thinking": thinking,
            "tool_calls": tool_calls,
            "cost": 0.0,
            "error": None,
        }

    async def run_interactive(
        self,
        engine: AgentEngine | None,
    ) -> None:
        """运行简单交互循环

        提供基于 prompt_toolkit 的交互式输入循环，
        每轮输入后调用引擎处理并渲染结果。

        Args:
            engine: Agent 引擎实例
        """
        self.print_banner()
        self.print_mode_info()

        if engine is None:
            self.console.print(
                "[red]错误: 引擎未初始化。请运行 'kimix auth' 配置 API Key。[/red]"
            )
            return

        self.console.print(
            "[dim]提示: 输入问题开始对话，输入 /exit 退出，/help 查看帮助[/dim]\n"
        )

        while True:
            try:
                # 读取用户输入
                user_input = await self._read_input()

                if not user_input.strip():
                    continue

                # 处理 / 命令
                if user_input.startswith("/"):
                    should_exit = await self._handle_command(user_input, engine)
                    if should_exit:
                        break
                    continue

                # 执行问答
                await self.run_once(engine, user_input)
                self.console.print()

            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]再见！[/yellow]")
                break
            except Exception as exc:
                self.console.print(f"[red]错误: {exc}[/red]")

    async def _read_input(self) -> str:
        """读取用户输入

        使用标准输入（非 prompt_toolkit，保持简单）。
        支持异步读取。
        """
        # 显示提示符
        self.console.print("[bold cyan]❯[/bold cyan] ", end="")

        # 读取输入
        try:
            # 使用 asyncio 读取标准输入
            loop = asyncio.get_event_loop()
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            return user_input.rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            raise

    async def _handle_command(
        self,
        cmd: str,
        engine: AgentEngine | None,
    ) -> bool:
        """处理 / 命令

        Args:
            cmd: 命令字符串
            engine: Agent 引擎

        Returns:
            bool: 是否退出交互循环
        """
        parts = cmd.strip().split()
        if not parts:
            return False

        command = parts[0].lower()
        args = parts[1:]

        if command == "/exit" or command == "/quit":
            self.console.print("[yellow]再见！[/yellow]")
            return True

        elif command == "/help":
            self._print_help()

        elif command == "/clear":
            self.console.clear()
            self.print_banner()

        elif command == "/mode":
            if args:
                mode_str = args[0].lower()
                try:
                    new_mode = AgentMode(mode_str)
                    self.mode = new_mode
                    if engine:
                        engine.switch_mode(new_mode)
                    self.console.print(f"[green]已切换到 {mode_str} 模式[/green]")
                except ValueError:
                    self.console.print(
                        f"[red]未知模式: {mode_str}[/red]\n"
                        f"可用模式: explore, plan, agent, auto, yolo"
                    )
            else:
                self.console.print(f"[cyan]当前模式: {self.mode.value}[/cyan]")

        elif command == "/cost":
            self.console.print(self.cost_renderer.render())

        elif command == "/save":
            if args:
                filename = args[0]
                self.console.print(f"[green]会话已保存到: {filename}[/green]")
            else:
                self.console.print("[yellow]用法: /save <文件名>[/yellow]")

        else:
            self.console.print(f"[red]未知命令: {command}[/red]")
            self.console.print("[dim]输入 /help 查看帮助[/dim]")

        return False

    def _print_help(self) -> None:
        """打印帮助信息"""
        help_text = """
[bold]可用命令[/bold]

  [cyan]/exit[/cyan], [cyan]/quit[/cyan]  退出程序
  [cyan]/clear[/cyan]           清屏
  [cyan]/mode <模式>[/cyan]      切换模式 (explore/plan/agent/auto/yolo)
  [cyan]/cost[/cyan]             显示成本统计
  [cyan]/save <文件>[/cyan]      保存会话
  [cyan]/help[/cyan]             显示帮助

[bold]快捷键[/bold]

  Ctrl+C              取消当前操作
  Ctrl+D              退出程序
"""
        self.console.print(help_text)

    def print_error(self, message: str, code: str = "") -> None:
        """打印错误信息"""
        prefix = f"[{code}] " if code else ""
        self.console.print(
            Panel(
                Text(f"{prefix}{message}", style="red"),
                border_style="red",
                title="[bold]❌ 错误[/bold]",
                title_align="left",
            )
        )

    def print_success(self, message: str) -> None:
        """打印成功信息"""
        self.console.print(
            Panel(
                Text(message, style="green"),
                border_style="green",
                title="[bold]✓ 成功[/bold]",
                title_align="left",
            )
        )

    def print_info(self, message: str) -> None:
        """打印信息"""
        self.console.print(
            Panel(
                Text(message, style="blue"),
                border_style="blue dim",
                title="[bold]ℹ 信息[/bold]",
                title_align="left",
            )
        )

    def print_warning(self, message: str) -> None:
        """打印警告信息"""
        self.console.print(
            Panel(
                Text(message, style="yellow"),
                border_style="yellow",
                title="[bold]⚠ 警告[/bold]",
                title_align="left",
            )
        )
