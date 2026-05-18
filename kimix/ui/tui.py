"""
TUI 界面模块（交互模式）

提供基于 Rich Live 的实时交互式终端界面：
- TUIApp 类: TUI 应用主类
  - run(): 启动 TUI 主循环
  - handle_input(): 处理用户输入和 / 命令
  - render(): 渲染完整界面

特性：
- Rich Live 实时更新，不闪烁
- 状态栏显示当前模式、累计成本、缓存状态
- 消息历史渲染（颜色区分用户/Agent/工具/系统）
- 工具执行可视化（折叠/展开工具调用详情）
- 支持 /mode, /clear, /save, /exit 等命令
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from kimix.core.engine import AgentEngine, AgentMode
from kimix.core.events import EngineEvent
from kimix.ui.components import ChatHistory, StatusBar, InputBox, TUILayout
from kimix.ui.renderers import (
    ThinkingRenderer,
    ToolCallRenderer,
    ToolResultRenderer,
    CostRenderer,
)
from kimix.version import __version__

# / 命令定义
COMMANDS: dict[str, dict[str, str]] = {
    "/help": {"desc": "显示帮助信息", "usage": "/help"},
    "/exit": {"desc": "退出 TUI", "usage": "/exit"},
    "/quit": {"desc": "退出 TUI", "usage": "/quit"},
    "/clear": {"desc": "清空聊天记录", "usage": "/clear"},
    "/mode": {"desc": "切换模式", "usage": "/mode <explore|plan|agent|auto|yolo>"},
    "/cost": {"desc": "显示成本统计", "usage": "/cost"},
    "/save": {"desc": "保存会话到文件", "usage": "/save <文件名>"},
    "/history": {"desc": "显示输入历史", "usage": "/history"},
    "/status": {"desc": "显示当前状态", "usage": "/status"},
}


class TUIApp:
    """TUI 应用主类

    提供交互式终端界面，基于 Rich Live 实现实时更新。
    支持流式响应、工具执行可视化、模式切换和成本追踪。

    Attributes:
        console: Rich 控制台实例
        engine: Agent 引擎实例
        layout: 布局管理器
        chat_history: 聊天历史组件
        status_bar: 状态栏组件
        input_box: 输入框组件
        cost_renderer: 成本渲染器
        thinking_renderer: 思考渲染器
        current_mode: 当前工作模式
        running: TUI 运行状态
    """

    def __init__(
        self,
        console: Console | None = None,
        engine: AgentEngine | None = None,
        mode: AgentMode = AgentMode.AGENT,
    ) -> None:
        self.console = console or Console()
        self.engine = engine
        self.current_mode = mode
        self.running = False

        # 组件
        self.chat_history = ChatHistory(wrap_width=self.console.width - 10)
        self.status_bar = StatusBar(current_mode=mode, version=__version__)
        self.input_box = InputBox(prompt="> ")

        # 渲染器
        self.cost_renderer = CostRenderer(console=self.console)
        self.thinking_renderer = ThinkingRenderer(
            console=self.console,
            collapsed=True,
        )
        self.tool_call_renderer = ToolCallRenderer(console=self.console)
        self.tool_result_renderer = ToolResultRenderer(console=self.console)

        # 布局
        self._layout = Layout()

        # 状态
        self._current_response: str = ""  # 当前流式响应内容
        self._is_streaming: bool = False  # 是否正在流式输出
        self._current_tool: str = ""  # 当前执行的工具
        self._spinner_style: str = "dots"  # 旋转器样式

    def build_layout(self) -> Layout:
        """构建 TUI 布局

        创建以下区域：
        - header: 顶部标题栏
        - chat: 聊天消息区域（可滚动）
        - thinking: 思考过程区域（可折叠）
        - tools: 工具执行区域
        - status: 底部状态栏
        - input: 输入框

        Returns:
            Layout: Rich 布局对象
        """
        self._layout = Layout()

        # 根布局
        self._layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        # 主体区域
        self._layout["body"].split_row(
            Layout(name="chat", ratio=1),
        )

        # 底部区域
        self._layout["footer"].split_column(
            Layout(name="info_bar", size=1),
            Layout(name="input", size=1),
            Layout(name="status_bar", size=1),
        )

        # 初始化各区域内容
        self._update_header()
        self._update_chat()
        self._update_info_bar()
        self._update_input()
        self._update_status_bar()

        return self._layout

    def _update_header(self) -> None:
        """更新顶部标题栏"""
        mode_cfg = {
            AgentMode.EXPLORE: ("🔍 Explore", "blue"),
            AgentMode.PLAN: ("📋 Plan", "yellow"),
            AgentMode.AGENT: ("🤖 Agent", "green"),
            AgentMode.AUTO: ("⚡ Auto", "cyan"),
            AgentMode.YOLO: ("🚀 YOLO", "red"),
        }
        mode_label, mode_color = mode_cfg.get(
            self.current_mode, ("🤖 Agent", "green")
        )

        header_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        header_table.add_column("left", justify="left", ratio=1)
        header_table.add_column("center", justify="center")
        header_table.add_column("right", justify="right")

        title = Text.assemble(
            Text("🤖 ", style="magenta"),
            Text("Kimi-Agent", style="bold magenta"),
            Text(f" v{__version__}", style="magenta dim"),
        )

        mode_text = Text(
            f"[{mode_label}]",
            style=f"bold {mode_color}",
        )

        cost_text = self.cost_renderer.render_bar()

        header_table.add_row(title, mode_text, cost_text)

        self._layout["header"].update(
            Panel(
                header_table,
                border_style="magenta dim",
                padding=(0, 1),
                height=3,
            )
        )

    def _update_chat(self) -> None:
        """更新聊天区域"""
        chat_panel = self.chat_history.render()
        self._layout["chat"].update(chat_panel)

    def _update_info_bar(self) -> None:
        """更新信息栏（显示当前状态提示）"""
        if self._is_streaming:
            if self._current_tool:
                info = Text(
                    f"🔧 正在执行: {self._current_tool}",
                    style="green dim",
                )
            else:
                info = Spinner("dots", text="思考中...", style="bright_black")
        else:
            shortcuts = Text.assemble(
                Text("/help", style="cyan dim"),
                Text(" 帮助 ", style="bright_black dim"),
                Text("/clear", style="cyan dim"),
                Text(" 清屏 ", style="bright_black dim"),
                Text("/mode", style="cyan dim"),
                Text(" 切换模式 ", style="bright_black dim"),
                Text("/exit", style="cyan dim"),
                Text(" 退出", style="bright_black dim"),
            )
            info = shortcuts

        self._layout["info_bar"].update(info)

    def _update_input(self) -> None:
        """更新输入框区域"""
        input_text = self.input_box.render()
        self._layout["input"].update(
            Panel(
                input_text,
                border_style="cyan dim",
                padding=(0, 1),
                height=1,
            )
        )

    def _update_status_bar(self) -> None:
        """更新状态栏"""
        self.status_bar.update(
            mode=self.current_mode,
            cost=self.cost_renderer.session_cost,
        )
        self._layout["status_bar"].update(self.status_bar.render())

    async def run(self) -> int:
        """运行 TUI 主循环

        检测终端环境，Windows CMD 使用简化模式避免抖动。

        Returns:
            int: 退出码，0 表示正常退出
        """
        if self.engine is None:
            self.console.print(
                "[red]错误: 引擎未初始化。请运行 'kimix auth' 配置 API Key。[/red]"
            )
            return 1

        self.running = True

        # Windows CMD 检测：不支持 Rich Live 的终端使用简化模式
        is_windows = sys.platform == "win32"
        is_windows_terminal = os.environ.get("WT_SESSION") is not None
        is_vscode = os.environ.get("TERM_PROGRAM") == "vscode"
        force_simple = os.environ.get("KIMIX_SIMPLE_UI", "").lower() in ("1", "true", "yes")

        if is_windows and not is_windows_terminal and not is_vscode or force_simple:
            return await self._run_simple()

        return await self._run_rich()

    async def _run_simple(self) -> int:
        """简化模式 — Windows CMD 兼容

        不使用 Rich Live，直接打印 + input()，彻底避免抖动。
        """
        print(f"\n🤖 Kimi-Agent {__version__} | 模式: {self.current_mode.value}")
        print("输入 /help 查看帮助，/exit 退出。\n")

        while self.running:
            try:
                # 读取输入（阻塞式，CMD 原生支持）
                user_input = input("> ").strip()

                if not user_input:
                    continue

                # 处理 / 命令
                if user_input.startswith("/"):
                    should_exit = await self._handle_command(user_input)
                    if should_exit:
                        break
                    continue

                # 显示用户消息
                print(f"\n[你] {user_input}")

                # 处理流式响应
                await self._process_streaming_simple(user_input)

            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                self.running = False
            except Exception as exc:
                print(f"\n[错误] {exc}")

        print("\n👋 再见！")
        return 0

    async def _process_streaming_simple(self, query: str) -> None:
        """简化模式的流式处理（直接打印，无 Live）"""
        if self.engine is None:
            print("[错误] 引擎未初始化")
            return

        self._is_streaming = True
        current_agent_content = ""
        current_thinking = ""

        print("[Agent] ", end="", flush=True)

        try:
            async for event in self.engine.run(query):
                ev_type = event["type"]
                data = event.get("data", {})

                if ev_type == "thinking":
                    thinking_text = data.get("text", "")
                    current_thinking += thinking_text

                elif ev_type == "content":
                    chunk = data.get("text", "")
                    current_agent_content += chunk
                    print(chunk, end="", flush=True)

                elif ev_type == "tool_start":
                    tool_name = data.get("name", "unknown")
                    print(f"\n[工具] {tool_name} 执行中...", end=" ", flush=True)

                elif ev_type == "tool_end":
                    duration_ms = data.get("duration_ms", 0)
                    print(f"✓ ({duration_ms}ms)")
                    print("[Agent] ", end="", flush=True)

                elif ev_type == "done":
                    self._is_streaming = False
                    break

                elif ev_type == "error":
                    error_msg = data.get("message", "未知错误")
                    print(f"\n[错误] {error_msg}")

        except Exception as exc:
            print(f"\n[错误] 流式处理异常: {exc}")

        self._is_streaming = False
        print()  # 换行

    async def _run_rich(self) -> int:
        """Rich Live 模式 — 现代终端（Windows Terminal / iTerm2 / GNOME Terminal）"""
        # 欢迎消息
        self.chat_history.add_message(
            "system",
            f"欢迎使用 Kimi-Agent！当前模式: {self.current_mode.value}",
        )
        self.chat_history.add_message(
            "system",
            "输入 /help 查看帮助，/exit 退出。",
        )

        # 启动 Live（刷新率极低，避免抖动）
        layout = self.build_layout()
        refresh_rate = 2  # 2fps，现代终端也保持低刷新率

        with Live(
            layout,
            console=self.console,
            refresh_per_second=refresh_rate,
            screen=True,  # 全屏模式更稳定
            transient=False,
        ) as live:
            self._live = live

            while self.running:
                try:
                    # 更新输入提示
                    self._update_input()

                    # 读取用户输入
                    user_input = await self._read_input_async()

                    if not user_input.strip():
                        continue

                    # 记录输入历史
                    self.input_box.add_history(user_input)

                    # 处理 / 命令
                    if user_input.startswith("/"):
                        should_exit = await self._handle_command(user_input)
                        if should_exit:
                            break
                        continue

                    # 显示用户消息
                    self.chat_history.add_message("user", user_input)
                    self._update_chat()

                    # 清空输入
                    self.input_box.current_input = ""
                    self._update_input()

                    # 处理用户请求（流式）
                    await self._process_streaming(user_input)

                    # 更新界面
                    self._update_header()
                    self._update_chat()
                    self._update_info_bar()
                    self._update_status_bar()

                except (EOFError, KeyboardInterrupt):
                    self.chat_history.add_message("system", "已退出。")
                    self.running = False
                except Exception as exc:
                    self.chat_history.add_message(
                        "error", f"运行时错误: {exc}"
                    )
                    self._update_chat()

        self.console.clear()
        self.console.print("[yellow]👋 再见！[/yellow]")
        return 0


    async def _read_input_async(self) -> str:
        """异步读取用户输入

        使用 asyncio 在非阻塞模式下读取标准输入。
        """
        self._update_input()
        if hasattr(self, "_live"):
            self._live.refresh()

        # 使用 run_in_executor 实现异步 stdin 读取
        loop = asyncio.get_event_loop()
        try:
            # 保存当前终端设置并启用行编辑
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            return user_input.rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            raise

    async def handle_input(self, user_input: str) -> None:
        """处理用户输入

        将用户输入发送到引擎并处理响应。
        此方法是公开 API，可用于外部调用。

        Args:
            user_input: 用户输入文本
        """
        if not user_input.strip():
            return

        # 记录历史
        self.input_box.add_history(user_input)

        # 添加到聊天
        self.chat_history.add_message("user", user_input)

        # 处理流式响应
        await self._process_streaming(user_input)

    async def _process_streaming(self, query: str) -> None:
        """处理流式响应

        调用引擎的流式 API，实时更新界面显示。

        Args:
            query: 用户查询
        """
        if self.engine is None:
            self.chat_history.add_message("error", "引擎未初始化")
            return

        self._is_streaming = True
        self._current_response = ""
        self._current_tool = ""

        # 用于累积当前 Agent 消息的引用
        current_agent_content = ""
        current_thinking = ""

        try:
            async for event in self.engine.run(query):
                ev_type = event["type"]
                data = event.get("data", {})

                if ev_type == "thinking":
                    # 思考过程
                    thinking_text = data.get("text", "")
                    current_thinking += thinking_text
                    # 添加思考消息（去重更新）
                    if thinking_text.strip():
                        self._update_thinking(current_thinking)

                elif ev_type == "content":
                    # 流式内容
                    chunk = data.get("text", "")
                    current_agent_content += chunk
                    self._current_response = current_agent_content
                    self._update_agent_response(current_agent_content)

                elif ev_type == "tool_start":
                    # 工具开始
                    tool_name = data.get("name", "unknown")
                    params = data.get("params", {})
                    self._current_tool = tool_name
                    self.chat_history.add_tool_call(tool_name, params, "running")
                    self._update_chat()
                    self._update_info_bar()

                elif ev_type == "tool_end":
                    # 工具结束
                    tool_name = data.get("name", "unknown")
                    duration_ms = data.get("duration_ms", 0)
                    self._current_tool = ""
                    # 添加工具完成消息
                    self.chat_history.add_message(
                        "system",
                        f"✓ {tool_name} 完成 ({duration_ms}ms)",
                    )
                    self._update_chat()
                    self._update_info_bar()

                elif ev_type == "tool_result":
                    # 工具结果
                    tool_name = data.get("name", "unknown")
                    result = data.get("result")
                    error = data.get("error")
                    self.chat_history.add_tool_result(tool_name, result, error)
                    self._update_chat()

                elif ev_type == "cost_update":
                    # 成本更新
                    self.cost_renderer.update(
                        cost_usd=data.get("cost_usd", 0.0),
                        input_tokens=data.get("input_tokens", 0),
                        output_tokens=data.get("output_tokens", 0),
                        cache_hit=data.get("cache_hit", False),
                    )
                    self.status_bar.update(
                        cost=self.cost_renderer.session_cost,
                        cache_hit=self.cost_renderer._cache_hit,
                    )
                    self._update_header()
                    self._update_status_bar()

                elif ev_type == "mode_switch":
                    # 模式切换
                    from_mode = data.get("from", "")
                    to_mode = data.get("to", "")
                    reason = data.get("reason", "")
                    try:
                        self.current_mode = AgentMode(to_mode)
                        self.status_bar.update(mode=self.current_mode)
                        self.chat_history.add_message(
                            "system",
                            f"模式切换: {from_mode} → {to_mode} ({reason})",
                        )
                        self._update_chat()
                        self._update_header()
                        self._update_status_bar()
                    except ValueError:
                        pass

                elif ev_type == "done":
                    # 完成
                    self._is_streaming = False
                    self._current_tool = ""
                    if current_agent_content:
                        self.chat_history.add_message(
                            "agent", current_agent_content
                        )
                    self._update_chat()
                    self._update_info_bar()
                    break

                elif ev_type == "error":
                    # 错误
                    error_msg = data.get("message", "未知错误")
                    self.chat_history.add_message("error", error_msg)
                    self._is_streaming = False
                    self._current_tool = ""
                    self._update_chat()
                    self._update_info_bar()
                    break

                # 实时刷新界面（仅关键事件，避免频繁抖动）
                if ev_type in ("tool_start", "tool_end", "tool_result", "done", "error", "mode_switch"):
                    if hasattr(self, "_live"):
                        self._live.refresh()

        except Exception as exc:
            self.chat_history.add_message("error", f"流式处理错误: {exc}")
            self._is_streaming = False

        self._is_streaming = False
        self._current_tool = ""

    def _update_thinking(self, thinking: str) -> None:
        """更新思考过程显示

        用最新的思考内容替换最后一条思考消息。
        """
        # 移除旧的思考消息，添加新的
        msgs = self.chat_history.messages
        # 找到最后一条思考消息并替换
        found = False
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "thinking":
                msgs[i]["content"] = thinking
                msgs[i]["timestamp"] = datetime.now()
                found = True
                break
        if not found and thinking.strip():
            self.chat_history.add_thinking(thinking)
        self._update_chat()

    def _update_agent_response(self, content: str) -> None:
        """更新 Agent 响应显示

        用最新内容替换最后一条 Agent 消息。
        """
        msgs = self.chat_history.messages
        found = False
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "agent":
                msgs[i]["content"] = content
                msgs[i]["timestamp"] = datetime.now()
                found = True
                break
        if not found:
            self.chat_history.add_message("agent", content)
        self._update_chat()

    async def _handle_command(self, cmd_line: str) -> bool:
        """处理 / 命令

        Args:
            cmd_line: 完整命令行

        Returns:
            bool: 是否退出 TUI
        """
        parts = cmd_line.strip().split()
        if not parts:
            return False

        command = parts[0].lower()
        args = parts[1:]

        if command in ("/exit", "/quit"):
            self.chat_history.add_message("system", "正在退出...")
            self.running = False
            return True

        elif command == "/help":
            self._show_help()

        elif command == "/clear":
            self.chat_history.clear()
            self.chat_history.add_message("system", "聊天记录已清空。")

        elif command == "/mode":
            if args:
                await self._switch_mode(args[0])
            else:
                self.chat_history.add_message(
                    "system",
                    f"当前模式: {self.current_mode.value}"
                    f"\n用法: /mode <explore|plan|agent|auto|yolo>",
                )

        elif command == "/cost":
            cost_info = (
                f"累计成本: ${self.cost_renderer.session_cost:.3f}\n"
                f"输入 Tokens: {self.cost_renderer._input_tokens}\n"
                f"输出 Tokens: {self.cost_renderer._output_tokens}"
            )
            self.chat_history.add_message("system", cost_info)

        elif command == "/save":
            if args:
                filename = args[0]
                self._save_session(filename)
            else:
                self.chat_history.add_message(
                    "system", "用法: /save <文件名>"
                )

        elif command == "/history":
            history_list = list(self.input_box.history)[-20:]
            if history_list:
                lines = "\n".join(
                    f"  {i+1}. {h[:60]}{'...' if len(h) > 60 else ''}"
                    for i, h in enumerate(history_list)
                )
                self.chat_history.add_message("system", f"输入历史:\n{lines}")
            else:
                self.chat_history.add_message("system", "暂无输入历史。")

        elif command == "/status":
            status_info = (
                f"模式: {self.current_mode.value}\n"
                f"流式输出: {'是' if self._is_streaming else '否'}\n"
                f"累计成本: ${self.cost_renderer.session_cost:.3f}\n"
                f"消息数: {len(self.chat_history.messages)}"
            )
            self.chat_history.add_message("system", status_info)

        else:
            self.chat_history.add_message(
                "error", f"未知命令: {command}\n输入 /help 查看帮助"
            )

        self._update_chat()
        return False

    def _show_help(self) -> None:
        """显示帮助信息"""
        lines: list[str] = []
        lines.append("[bold]可用命令[/bold]")
        lines.append("")
        for cmd, info in COMMANDS.items():
            lines.append(f"  [cyan]{info['usage']}[/cyan]")
            lines.append(f"      {info['desc']}")
        lines.append("")
        lines.append("[bold]快捷键[/bold]")
        lines.append("  Ctrl+C  取消当前操作")
        lines.append("  Ctrl+D  退出")

        self.chat_history.add_message("system", "\n".join(lines))

    async def _switch_mode(self, mode_str: str) -> None:
        """切换工作模式

        Args:
            mode_str: 模式名称字符串
        """
        try:
            new_mode = AgentMode(mode_str.lower())
            old_mode = self.current_mode
            self.current_mode = new_mode

            if self.engine:
                self.engine.switch_mode(new_mode)

            self.status_bar.update(mode=new_mode)
            self._update_header()
            self._update_status_bar()

            self.chat_history.add_message(
                "system",
                f"已切换模式: {old_mode.value} → {new_mode.value}",
            )
        except ValueError:
            self.chat_history.add_message(
                "error",
                f"未知模式: {mode_str}\n"
                f"可用模式: explore, plan, agent, auto, yolo",
            )

    def _save_session(self, filename: str) -> None:
        """保存会话到文件

        Args:
            filename: 保存文件名
        """
        try:
            messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "timestamp": m.get("timestamp", datetime.now()).isoformat(),
                }
                for m in self.chat_history.messages
            ]
            data = {
                "version": __version__,
                "mode": self.current_mode.value,
                "timestamp": datetime.now().isoformat(),
                "cost_usd": self.cost_renderer.session_cost,
                "messages": messages,
            }
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.chat_history.add_message(
                "system", f"✓ 会话已保存到: {filename}"
            )
        except Exception as exc:
            self.chat_history.add_message(
                "error", f"保存失败: {exc}"
            )

    def render(self) -> Layout:
        """渲染完整界面

        Returns:
            Layout: 完整的 TUI 布局
        """
        return self.build_layout()

    def __rich__(self) -> Layout:
        """Rich 协议支持"""
        return self.render()
