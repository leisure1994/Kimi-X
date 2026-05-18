"""
UI 组件模块

提供 TUI 使用的基础 UI 组件：
- StatusBar: 状态栏（模式、成本、缓存状态）
- InputBox: 输入框（带历史记录支持）
- ChatHistory: 聊天历史面板
- ModeSelector: 模式选择器

所有组件均为 Rich 可渲染对象，支持中文和主题自适应。
"""

from __future__ import annotations

import textwrap
from collections import deque
from datetime import datetime
from typing import Any, Protocol

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, ConsoleRenderable, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from kimix.core.engine import AgentMode

# 模式显示配置
MODE_DISPLAY: dict[AgentMode, dict[str, str]] = {
    AgentMode.EXPLORE: {
        "label": "Explore",
        "color": "blue",
        "icon": "🔍",
        "desc": "探索模式",
    },
    AgentMode.PLAN: {
        "label": "Plan",
        "color": "yellow",
        "icon": "📋",
        "desc": "规划模式",
    },
    AgentMode.AGENT: {
        "label": "Agent",
        "color": "green",
        "icon": "🤖",
        "desc": "Agent 模式",
    },
    AgentMode.AUTO: {
        "label": "Auto",
        "color": "cyan",
        "icon": "⚡",
        "desc": "自动模式",
    },
    AgentMode.YOLO: {
        "label": "YOLO",
        "color": "red",
        "icon": "🚀",
        "desc": "YOLO 模式",
    },
}


def _mode_cfg(mode: AgentMode) -> dict[str, str]:
    """获取模式显示配置"""
    return MODE_DISPLAY.get(mode, MODE_DISPLAY[AgentMode.AGENT])


class Renderable(Protocol):
    """可渲染对象协议"""

    def __rich__(self) -> ConsoleRenderable: ...


class StatusBar:
    """状态栏组件

    显示当前模式、累计成本、缓存状态和连接信息。
    位于 TUI 底部，实时更新。

    Attributes:
        current_mode: 当前 Agent 模式
        session_cost: 当前会话累计成本
        cache_hit: 缓存命中状态
        connected: API 连接状态
        version: 版本号
    """

    def __init__(
        self,
        current_mode: AgentMode = AgentMode.AGENT,
        session_cost: float = 0.0,
        cache_hit: bool = False,
        connected: bool = True,
        version: str = "1.0.0",
        input_prompt: str = "",
    ) -> None:
        self.current_mode = current_mode
        self.session_cost = session_cost
        self.cache_hit = cache_hit
        self.connected = connected
        self.version = version
        self.input_prompt = input_prompt

    def update(
        self,
        mode: AgentMode | None = None,
        cost: float | None = None,
        cache_hit: bool | None = None,
        connected: bool | None = None,
    ) -> None:
        """更新状态栏数据"""
        if mode is not None:
            self.current_mode = mode
        if cost is not None:
            self.session_cost = cost
        if cache_hit is not None:
            self.cache_hit = cache_hit
        if connected is not None:
            self.connected = connected

    def render(self) -> Table:
        """渲染状态栏

        Returns:
            Table: 包含左右分栏的状态栏表格
        """
        cfg = _mode_cfg(self.current_mode)
        mode_color = cfg["color"]
        mode_label = cfg["label"]
        mode_icon = cfg["icon"]

        # 左侧: 模式指示器
        mode_text = Text(
            f"{mode_icon} {mode_label}",
            style=f"{mode_color} bold on {mode_color} black",
        )
        mode_badge = Text(
            f"[{mode_label}]",
            style=f"{mode_color} bold",
        )

        # 成本显示
        cost_text = Text(
            f"${self.session_cost:.3f}",
            style="yellow dim",
        )

        # 缓存指示
        cache_text = Text(
            "⚡缓存" if self.cache_hit else "",
            style="green dim",
        )

        # 连接指示
        conn_icon = "●" if self.connected else "○"
        conn_color = "green" if self.connected else "red"
        conn_text = Text(conn_icon, style=f"{conn_color}")

        # 输入提示
        input_text = Text(
            f"> {self.input_prompt}_",
            style="white on black",
        ) if self.input_prompt else Text(
            "> _",
            style="dim",
        )

        # 构建状态栏
        left_parts = Text.assemble(
            Text("Kimi-Agent ", style="white bold"),
            Text(f"v{self.version}  ", style="white dim"),
            mode_badge,
            Text("  ", style="default"),
            cost_text,
            Text("  ", style="default"),
            cache_text,
            Text("  ", style="default"),
            conn_text,
        )

        # 模式切换按钮提示
        modes_bar = Text.assemble(
            Text("[", style="bright_black"),
            Text("Agent", style="green bold" if self.current_mode == AgentMode.AGENT else "green dim"),
            Text("] [", style="bright_black"),
            Text("Explore", style="blue bold" if self.current_mode == AgentMode.EXPLORE else "blue dim"),
            Text("] [", style="bright_black"),
            Text("Plan", style="yellow bold" if self.current_mode == AgentMode.PLAN else "yellow dim"),
            Text("] [", style="bright_black"),
            Text("Auto", style="cyan bold" if self.current_mode == AgentMode.AUTO else "cyan dim"),
            Text("] [", style="bright_black"),
            Text("YOLO", style="red bold" if self.current_mode == AgentMode.YOLO else "red dim"),
            Text("]", style="bright_black"),
        )

        table = Table(
            show_header=False,
            box=None,
            padding=(0, 1),
            expand=True,
        )
        table.add_column("left", ratio=1)
        table.add_column("right", justify="right")
        table.add_row(left_parts, modes_bar)

        return table

    def __rich__(self) -> Table:
        """Rich 协议支持"""
        return self.render()


class InputBox:
    """输入框组件

    模拟命令行输入框，带历史记录支持。
    记录最近的输入历史，支持上下键回顾。

    Attributes:
        history: 输入历史记录
        max_history: 最大历史记录数
        current_input: 当前输入内容
    """

    def __init__(
        self,
        max_history: int = 100,
        prompt: str = "> ",
    ) -> None:
        self.history: deque[str] = deque(maxlen=max_history)
        self.max_history = max_history
        self.prompt = prompt
        self.current_input: str = ""
        self._history_index: int = 0  # 0 表示当前输入

    def add_history(self, text: str) -> None:
        """添加输入到历史记录

        Args:
            text: 输入文本
        """
        if text.strip():
            self.history.append(text)
        self._history_index = 0

    def previous(self) -> str | None:
        """获取上一条历史记录

        Returns:
            str | None: 历史文本，无则返回 None
        """
        if not self.history:
            return None
        self._history_index = min(self._history_index + 1, len(self.history))
        idx = len(self.history) - self._history_index
        if 0 <= idx < len(self.history):
            return self.history[idx]
        return None

    def next(self) -> str | None:
        """获取下一条历史记录"""
        if not self.history or self._history_index <= 0:
            self._history_index = 0
            return ""
        self._history_index -= 1
        if self._history_index == 0:
            return ""
        idx = len(self.history) - self._history_index
        if 0 <= idx < len(self.history):
            return self.history[idx]
        return ""

    def render(self) -> Text:
        """渲染输入框

        Returns:
            Text: 带提示符的输入文本
        """
        return Text(
            f"{self.prompt}{self.current_input}_",
            style="bold",
        )

    def __rich__(self) -> Text:
        """Rich 协议支持"""
        return self.render()


class ChatHistory:
    """聊天历史面板组件

    管理并渲染聊天记录，支持不同角色的颜色区分。
    自动滚动到最新消息。

    Attributes:
        messages: 消息列表
        max_messages: 最大显示消息数
    """

    def __init__(
        self,
        max_messages: int = 500,
        wrap_width: int = 80,
    ) -> None:
        self.messages: list[dict[str, Any]] = []
        self.max_messages = max_messages
        self.wrap_width = wrap_width

    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加消息到历史

        Args:
            role: 消息角色 (user/agent/system/tool/error)
            content: 消息内容
            metadata: 附加元数据
        """
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(),
            "metadata": metadata or {},
        }
        self.messages.append(msg)

        # 限制消息数量
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def add_thinking(self, content: str) -> None:
        """添加思考消息"""
        self.add_message("thinking", content)

    def add_tool_call(
        self,
        tool_name: str,
        params: dict[str, Any],
        status: str = "calling",
    ) -> None:
        """添加工具调用消息"""
        self.add_message(
            "tool_call",
            f"{tool_name}({', '.join(f'{k}={v!r}' for k, v in params.items())})",
            {"tool_name": tool_name, "params": params, "status": status},
        )

    def add_tool_result(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
    ) -> None:
        """添加工具结果消息"""
        self.add_message(
            "tool_result",
            str(result) if not error else f"错误: {error}",
            {"tool_name": tool_name, "error": error},
        )

    def clear(self) -> None:
        """清空聊天历史"""
        self.messages.clear()

    def get_messages(self) -> list[dict[str, Any]]:
        """获取所有消息"""
        return list(self.messages)

    def render(self) -> Panel:
        """渲染聊天历史面板

        Returns:
            Panel: 包含所有消息的滚动面板
        """
        if not self.messages:
            empty_text = Text("(暂无消息，开始对话吧！)", style="dim", justify="center")
            return Panel(
                Align.center(empty_text, vertical="middle"),
                border_style="bright_black dim",
                title="[dim]对话历史[/dim]",
                title_align="left",
            )

        # 渲染消息列表
        rendered: list[Text | Panel] = []

        for msg in self.messages:
            role = msg["role"]
            content = msg["content"]
            ts = msg.get("timestamp")

            rendered_msg = self._render_single_message(role, content, ts)
            if rendered_msg:
                rendered.append(rendered_msg)

        # 使用 Table 垂直排列
        table = Table(show_header=False, box=None, padding=(0, 0), expand=True)
        table.add_column("messages", ratio=1)

        for item in rendered:
            table.add_row(item)

        return Panel(
            table,
            border_style="bright_black dim",
            title="[dim]对话[/dim]",
            title_align="left",
            padding=(0, 1),
        )

    def _render_single_message(
        self,
        role: str,
        content: str,
        timestamp: datetime | None = None,
    ) -> Text | Panel | None:
        """渲染单条消息"""
        ts_str = ""
        if timestamp:
            ts_str = f"[{timestamp.strftime('%H:%M:%S')}] "

        # 角色样式配置
        role_styles: dict[str, dict[str, str]] = {
            "user": {"icon": "👤", "label": "你", "color": "cyan"},
            "agent": {"icon": "🤖", "label": "Kimi", "color": "magenta"},
            "system": {"icon": "⚡", "label": "系统", "color": "yellow"},
            "thinking": {"icon": "💭", "label": "思考", "color": "bright_black"},
            "tool_call": {"icon": "🔧", "label": "工具", "color": "green"},
            "tool_result": {"icon": "📤", "label": "结果", "color": "blue"},
            "error": {"icon": "⚠", "label": "错误", "color": "red"},
        }

        style = role_styles.get(role, role_styles["system"])
        icon = style["icon"]
        color = style["color"]

        if role == "user":
            header = Text(f"{ts_str}{icon} ", style=f"{color} bold")
            body = Text(content, style=color)
            return Text.assemble(header, body)

        elif role == "agent":
            header = Text(f"{ts_str}{icon} ", style=f"{color} bold")
            body_lines = content.split("\n")
            formatted_body: list[str | Text] = []
            in_code = False
            for line in body_lines:
                if line.startswith("```"):
                    in_code = not in_code
                    formatted_body.append(Text(line + "\n", style="dim"))
                elif in_code:
                    formatted_body.append(Text(f"  {line}\n", style="bright_black"))
                else:
                    formatted_body.append(Text(line + "\n", style=color))
            if formatted_body:
                body = Text.assemble(*formatted_body)
            else:
                body = Text(content, style=color)
            # 返回 Panel 包装
            inner = Text.assemble(header, Text("\n"), body)
            return Panel(inner, border_style=f"{color} dim", padding=(0, 1))

        elif role == "thinking":
            preview = content.strip()
            if len(preview) > 50:
                preview = preview[:50] + "..."
            return Text(
                f"{ts_str}{icon} {preview}",
                style=f"{color} dim",
            )

        elif role in ("tool_call", "tool_result"):
            if role == "tool_call":
                return Text(
                    f"{ts_str}{icon} {content}",
                    style=f"{color} dim",
                )
            else:
                return Text(
                    f"{ts_str}{icon} {content[:100]}{'...' if len(content) > 100 else ''}",
                    style=color,
                )

        else:  # system, error, etc.
            return Text(
                f"{ts_str}{icon} {content}",
                style=color,
            )

    def __rich__(self) -> Panel:
        """Rich 协议支持"""
        return self.render()


class ModeSelector:
    """模式选择器组件

    以水平按钮组形式展示可用模式，
    高亮当前选中的模式。

    Attributes:
        current_mode: 当前选中的模式
        on_change: 模式切换回调函数（可选）
    """

    def __init__(
        self,
        current_mode: AgentMode = AgentMode.AGENT,
        on_change: Any = None,
    ) -> None:
        self.current_mode = current_mode
        self.on_change = on_change

    def set_mode(self, mode: AgentMode) -> None:
        """设置当前模式"""
        old_mode = self.current_mode
        self.current_mode = mode
        if self.on_change and old_mode != mode:
            self.on_change(mode)

    def render(self) -> Text:
        """渲染模式选择器

        Returns:
            Text: 水平排列的模式按钮组
        """
        parts: list[Text] = []

        for mode, cfg in MODE_DISPLAY.items():
            is_active = mode == self.current_mode
            color = cfg["color"]
            label = cfg["label"]
            icon = cfg["icon"]

            if is_active:
                btn = Text(
                    f" {icon} {label} ",
                    style=f"white on {color} bold",
                )
            else:
                btn = Text(
                    f" {label} ",
                    style=f"{color} dim",
                )

            parts.append(btn)

            # 添加间隔
            if mode != AgentMode.YOLO:
                parts.append(Text(" ", style="default"))

        return Text.assemble(*parts)

    def render_compact(self) -> Text:
        """渲染紧凑模式（仅标签）"""
        parts: list[Text] = []

        for mode, cfg in MODE_DISPLAY.items():
            is_active = mode == self.current_mode
            color = cfg["color"]
            label = cfg["label"]

            if is_active:
                btn = Text(
                    f"[{label}]",
                    style=f"{color} bold",
                )
            else:
                btn = Text(
                    f"[{label}]",
                    style=f"{color} dim",
                )

            parts.append(btn)

        return Text.assemble(*parts)

    def __rich__(self) -> Text:
        """Rich 协议支持"""
        return self.render()


class TUILayout:
    """TUI 布局管理器

    使用 Rich Layout 构建 TUI 的页面结构：
    - 顶部标题栏
    - 中间聊天区域
    - 底部状态栏 + 输入框

    Attributes:
        chat_history: 聊天历史组件
        status_bar: 状态栏组件
        input_box: 输入框组件
    """

    def __init__(
        self,
        chat_history: ChatHistory | None = None,
        status_bar: StatusBar | None = None,
        input_box: InputBox | None = None,
    ) -> None:
        self.chat_history = chat_history or ChatHistory()
        self.status_bar = status_bar or StatusBar()
        self.input_box = input_box or InputBox()
        self._layout = Layout()

    def build(self) -> Layout:
        """构建完整布局

        Returns:
            Layout: Rich 布局对象
        """
        # 根布局分为上下两部分
        self._layout.split_column(
            Layout(name="header", size=1),
            Layout(name="main", ratio=1),
            Layout(name="status", size=1),
            Layout(name="input", size=1),
        )

        # 顶部标题
        title_text = Text(
            "Kimi-Agent 终端",
            style="bold white on black",
            justify="center",
        )
        self._layout["header"].update(title_text)

        # 主聊天区域
        self._layout["main"].update(self.chat_history)

        # 状态栏
        self._layout["status"].update(self.status_bar)

        # 输入框
        self._layout["input"].update(self.input_box)

        return self._layout

    def update_chat(self, messages: list[dict[str, Any]]) -> None:
        """更新聊天区域内容"""
        for msg in messages:
            self.chat_history.add_message(
                msg.get("role", "system"),
                msg.get("content", ""),
                msg.get("metadata"),
            )

    def update_status(
        self,
        mode: AgentMode | None = None,
        cost: float | None = None,
        cache_hit: bool | None = None,
    ) -> None:
        """更新状态栏"""
        self.status_bar.update(mode=mode, cost=cost, cache_hit=cache_hit)

    def __rich__(self) -> Layout:
        """Rich 协议支持"""
        return self.build()
