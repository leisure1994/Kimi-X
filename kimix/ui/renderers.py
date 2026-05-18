"""
渲染器模块

提供各类 Agent 事件的 Rich 格式化渲染：
- ThinkingRenderer: 思考过程渲染（灰色折叠显示）
- ToolCallRenderer: 工具调用渲染（绿色，带参数）
- ToolResultRenderer: 工具结果渲染（蓝色/红色状态区分）
- CostRenderer: 成本渲染（黄色小字）
- MessageRenderer: 消息渲染（带头像和颜色区分）

所有渲染器支持亮色/暗色主题自适应，中文友好。
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.json import JSON
from rich.panel import Panel
from rich.rule import Rule
from rich.status import Status
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

# 主题配色 - 自适应亮/暗色
THEME = {
    "thinking": {
        "color": "bright_black",
        "dim": True,
        "icon": "💭",
        "fallback_icon": "[T]",
    },
    "tool_call": {
        "color": "green",
        "icon": "🔧",
        "fallback_icon": "[>]",
    },
    "tool_result_ok": {
        "color": "blue",
        "icon": "✓",
        "fallback_icon": "[+]",
    },
    "tool_result_error": {
        "color": "red",
        "icon": "✗",
        "fallback_icon": "[-]",
    },
    "cost": {
        "color": "yellow",
        "dim": True,
        "icon": "💰",
        "fallback_icon": "[$]",
    },
    "user": {
        "color": "cyan",
        "icon": "👤",
        "fallback_icon": ">>>",
    },
    "agent": {
        "color": "magenta",
        "icon": "🤖",
        "fallback_icon": "[A]",
    },
    "system": {
        "color": "yellow",
        "icon": "⚡",
        "fallback_icon": "[!]",
    },
    "separator": {
        "color": "bright_black",
        "dim": True,
    },
}


def _icon(key: str) -> str:
    """获取图标，支持 ASCII 回退"""
    cfg = THEME.get(key, {})
    return cfg.get("icon", cfg.get("fallback_icon", ""))


def _color(key: str) -> str:
    """获取主题颜色"""
    return THEME.get(key, {}).get("color", "white")


class ThinkingRenderer:
    """思考过程渲染器

    将模型的推理过程渲染为灰色折叠面板，默认收起状态，
    用户可通过点击或按键展开查看详细思考过程。

    Attributes:
        console: Rich 控制台实例
        collapsed: 是否处于折叠状态
        max_preview_length: 预览文本最大长度
    """

    def __init__(
        self,
        console: Console | None = None,
        collapsed: bool = True,
        max_preview_length: int = 60,
    ) -> None:
        self.console = console or Console()
        self.collapsed = collapsed
        self.max_preview_length = max_preview_length
        self._thinking_text: str = ""

    def update(self, text: str) -> None:
        """追加思考文本"""
        self._thinking_text += text

    def reset(self) -> None:
        """重置思考文本"""
        self._thinking_text = ""

    def render(self) -> Panel | Text:
        """渲染当前思考内容

        Returns:
            Panel: 折叠时显示为紧凑面板
            Text: 展开时显示完整文本
        """
        if not self._thinking_text:
            return Text("")

        preview = self._thinking_text.strip()
        if len(preview) > self.max_preview_length:
            preview = preview[: self.max_preview_length] + "..."

        if self.collapsed:
            label = Text(
                f"{_icon('thinking')} 思考中... ",
                style=f"{_color('thinking')} dim",
            )
            preview_text = Text(preview, style=f"{_color('thinking')} dim")
            content = Text.assemble(label, preview_text)
            return Panel(
                content,
                border_style=f"{_color('thinking')} dim",
                padding=(0, 1),
                height=3,
            )

        # 展开状态 - 显示完整思考过程
        header = Text(
            f"{_icon('thinking')} 思考过程",
            style=f"{_color('thinking')} bold",
        )
        body = Text(
            self._thinking_text,
            style=f"{_color('thinking')}",
        )
        content = Text.assemble(header, Text("\n"), body)
        return Panel(
            content,
            border_style=_color("thinking"),
            title="[dim]思考[/dim]",
            title_align="left",
            padding=(0, 1),
        )

    def render_inline(self) -> Text:
        """渲染单行思考提示（用于流式输出）"""
        if not self._thinking_text:
            return Text(f"{_icon('thinking')} 思考中...", style=f"{_color('thinking')} dim")
        preview = self._thinking_text.strip()
        if len(preview) > self.max_preview_length:
            preview = preview[: self.max_preview_length] + "..."
        return Text(
            f"{_icon('thinking')} {preview}",
            style=f"{_color('thinking')} dim",
        )

    def __rich__(self) -> Panel | Text:
        """Rich 协议支持"""
        return self.render()


class ToolCallRenderer:
    """工具调用渲染器

    渲染工具调用信息，包括工具名称、参数和执行状态。
    支持参数折叠和语法高亮。

    Attributes:
        console: Rich 控制台实例
        show_params: 是否显示参数详情
        max_param_length: 参数预览最大长度
    """

    def __init__(
        self,
        console: Console | None = None,
        show_params: bool = True,
        max_param_length: int = 200,
    ) -> None:
        self.console = console or Console()
        self.show_params = show_params
        self.max_param_length = max_param_length

    def render(
        self,
        tool_name: str,
        params: dict[str, Any],
        status: str = "calling",
    ) -> Panel | Text:
        """渲染工具调用

        Args:
            tool_name: 工具名称
            params: 工具参数
            status: 调用状态 (calling/running/completed)

        Returns:
            Panel 或 Text 的 Rich 可渲染对象
        """
        status_icons = {
            "calling": "▸",
            "running": "⟳",
            "completed": "✓",
        }
        icon = status_icons.get(status, "▸")
        color = _color("tool_call")

        header = Text(
            f"{_icon('tool_call')} {icon} {tool_name}",
            style=f"{color} bold",
        )

        if not self.show_params or not params:
            return Panel(
                header,
                border_style=f"{color} dim" if status != "running" else color,
                padding=(0, 1),
                height=3,
            )

        # 格式化参数
        try:
            param_str = json.dumps(params, ensure_ascii=False, indent=2)
            if len(param_str) > self.max_param_length:
                param_str = param_str[: self.max_param_length] + "..."
            syntax = Syntax(
                param_str,
                "json",
                theme="default",
                line_numbers=False,
                word_wrap=True,
            )
            content: Text | Syntax = syntax
        except (TypeError, ValueError):
            param_text = Text(str(params), style=f"{color} dim")
            content = param_text

        table = Table(show_header=False, box=None, padding=(0, 0))
        table.add_row(header)
        table.add_row(content)

        return Panel(
            table,
            border_style=f"{color} dim" if status != "running" else color,
            padding=(0, 1),
        )

    def render_start(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> Text:
        """渲染工具开始执行的简短提示

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            Text 单行提示
        """
        # 提取关键参数用于预览
        preview = ""
        if params:
            key = next(iter(params))
            val = str(params[key])[:40]
            preview = f"({key}={val}{'...' if len(str(params[key])) > 40 else ''})"

        return Text(
            f"{_icon('tool_call')} {tool_name}{preview}",
            style=f"{_color('tool_call')} dim",
        )

    def __call__(
        self,
        tool_name: str,
        params: dict[str, Any],
        status: str = "calling",
    ) -> Panel | Text:
        """便捷调用方式"""
        return self.render(tool_name, params, status)


class ToolResultRenderer:
    """工具结果渲染器

    渲染工具执行结果，根据成功/失败状态使用不同颜色。
    支持结果截断和代码高亮。

    Attributes:
        console: Rich 控制台实例
        max_result_length: 结果最大显示长度
        highlight_code: 是否对代码结果进行语法高亮
    """

    def __init__(
        self,
        console: Console | None = None,
        max_result_length: int = 500,
        highlight_code: bool = True,
    ) -> None:
        self.console = console or Console()
        self.max_result_length = max_result_length
        self.highlight_code = highlight_code

    def render(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Panel | Text:
        """渲染工具执行结果

        Args:
            tool_name: 工具名称
            result: 执行结果
            error: 错误信息（如有）
            duration_ms: 执行耗时（毫秒）

        Returns:
            Rich 可渲染对象
        """
        if error:
            return self._render_error(tool_name, error, duration_ms)
        return self._render_success(tool_name, result, duration_ms)

    def _render_success(
        self,
        tool_name: str,
        result: Any,
        duration_ms: int | None = None,
    ) -> Panel:
        """渲染成功结果"""
        color = _color("tool_result_ok")
        time_str = f" ({duration_ms}ms)" if duration_ms else ""
        header = Text(
            f"{_icon('tool_result_ok')} {tool_name}{time_str}",
            style=f"{color} bold",
        )

        # 格式化结果
        content = self._format_result(result)

        table = Table(show_header=False, box=None, padding=(0, 0))
        table.add_row(header)
        table.add_row(content)

        return Panel(
            table,
            border_style=f"{color} dim",
            padding=(0, 1),
        )

    def _render_error(
        self,
        tool_name: str,
        error: str,
        duration_ms: int | None = None,
    ) -> Panel:
        """渲染错误结果"""
        color = _color("tool_result_error")
        time_str = f" ({duration_ms}ms)" if duration_ms else ""
        header = Text(
            f"{_icon('tool_result_error')} {tool_name}{time_str}",
            style=f"{color} bold",
        )

        error_text = Text(
            f"错误: {error}",
            style=f"{color}",
        )

        table = Table(show_header=False, box=None, padding=(0, 0))
        table.add_row(header)
        table.add_row(error_text)

        return Panel(
            table,
            border_style=color,
            padding=(0, 1),
        )

    def _format_result(self, result: Any) -> Text | Syntax:
        """格式化结果为 Rich 可渲染对象"""
        if result is None:
            return Text("(无返回值)", style="dim")

        result_str = str(result)
        if len(result_str) > self.max_result_length:
            result_str = result_str[: self.max_result_length] + "\n... (已截断)"

        # 尝试 JSON 格式化
        try:
            if isinstance(result, (dict, list)):
                json_str = json.dumps(result, ensure_ascii=False, indent=2)
                if len(json_str) > self.max_result_length:
                    json_str = json_str[: self.max_result_length] + "\n  ... (已截断)"
                return Syntax(json_str, "json", theme="default", word_wrap=True)
        except (TypeError, ValueError):
            pass

        # 代码高亮检测
        if self.highlight_code and (
            result_str.strip().startswith("def ")
            or result_str.strip().startswith("class ")
            or result_str.strip().startswith("import ")
            or result_str.strip().startswith("from ")
            or "=" in result_str[:20]
            and "\n" in result_str
        ):
            return Syntax(result_str, "python", theme="default", word_wrap=True)

        return Text(result_str, style="default")

    def render_short(
        self,
        tool_name: str,
        success: bool = True,
        duration_ms: int | None = None,
    ) -> Text:
        """渲染简短结果提示（单行）"""
        icon = _icon("tool_result_ok") if success else _icon("tool_result_error")
        color = _color("tool_result_ok") if success else _color("tool_result_error")
        time_str = f" ({duration_ms}ms)" if duration_ms else ""
        return Text(
            f"{icon} {tool_name}{time_str}",
            style=f"{color}",
        )

    def __call__(
        self,
        tool_name: str,
        result: Any,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Panel | Text:
        """便捷调用"""
        return self.render(tool_name, result, error, duration_ms)


class CostRenderer:
    """成本渲染器

    渲染 Token 使用和成本信息，以黄色小字显示。
    支持实时累计成本和缓存状态显示。

    Attributes:
        console: Rich 控制台实例
        precision: 成本显示小数位数
        show_tokens: 是否显示 Token 数
    """

    def __init__(
        self,
        console: Console | None = None,
        precision: int = 3,
        show_tokens: bool = True,
    ) -> None:
        self.console = console or Console()
        self.precision = precision
        self.show_tokens = show_tokens
        self._session_cost: float = 0.0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._cache_hit: bool = False

    def update(
        self,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_hit: bool = False,
    ) -> None:
        """更新成本数据

        Args:
            cost_usd: 本次成本（美元）
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数
            cache_hit: 是否命中缓存
        """
        self._session_cost += cost_usd
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._cache_hit = cache_hit

    @property
    def session_cost(self) -> float:
        """获取当前会话累计成本"""
        return self._session_cost

    def reset(self) -> None:
        """重置成本统计"""
        self._session_cost = 0.0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_hit = False

    def render(self) -> Text:
        """渲染成本信息

        Returns:
            Text: 格式化的成本文本
        """
        cost_str = f"${self._session_cost:.{self.precision}f}"
        parts: list[str | Text] = [
            f"{_icon('cost')} {cost_str}",
        ]

        if self.show_tokens:
            token_info = f" ({self._input_tokens}↓ {self._output_tokens}↑)"
            parts.append(token_info)

        if self._cache_hit:
            parts.append(Text(" ⚡缓存", style="green dim"))

        style = f"{_color('cost')} dim"
        return Text.assemble(
            Text(parts[0], style=style),
            *(
                [Text(p, style=style) if isinstance(p, str) else p for p in parts[1:]]
            ),
        )

    def render_compact(self) -> Text:
        """渲染紧凑成本（仅显示金额）"""
        return Text(
            f"${_icon('cost')} {self._session_cost:.{self.precision}f}",
            style=f"{_color('cost')} dim",
        )

    def render_bar(self) -> Text:
        """渲染状态栏格式的成本信息"""
        cost_str = f"${self._session_cost:.{self.precision}f}"
        cache_indicator = " ⚡缓存" if self._cache_hit else ""
        return Text(
            f"[{cost_str}{cache_indicator}]",
            style=f"{_color('cost')} dim",
        )

    def __rich__(self) -> Text:
        """Rich 协议支持"""
        return self.render()

    def __repr__(self) -> str:
        return f"CostRenderer(cost=${self._session_cost:.3f})"


class MessageRenderer:
    """消息渲染器

    渲染聊天记录中的各类消息，支持用户、Agent、工具、系统消息的颜色区分。
    包含时间戳、头像和格式化内容。

    Attributes:
        console: Rich 控制台实例
        show_timestamp: 是否显示时间戳
        wrap_width: 文本自动换行宽度
    """

    MESSAGE_STYLES: dict[str, dict[str, str]] = {
        "user": {
            "color": "cyan",
            "icon": "👤",
            "label": "你",
        },
        "agent": {
            "color": "magenta",
            "icon": "🤖",
            "label": "Kimi",
        },
        "system": {
            "color": "yellow",
            "icon": "⚡",
            "label": "系统",
        },
        "tool": {
            "color": "green",
            "icon": "🔧",
            "label": "工具",
        },
        "error": {
            "color": "red",
            "icon": "⚠",
            "label": "错误",
        },
        "info": {
            "color": "blue",
            "icon": "ℹ",
            "label": "信息",
        },
    }

    def __init__(
        self,
        console: Console | None = None,
        show_timestamp: bool = True,
        wrap_width: int = 80,
    ) -> None:
        self.console = console or Console()
        self.show_timestamp = show_timestamp
        self.wrap_width = wrap_width

    def render(
        self,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Panel | Text:
        """渲染单条消息

        Args:
            role: 消息角色 (user/agent/system/tool/error/info)
            content: 消息内容
            timestamp: 消息时间戳
            metadata: 附加元数据

        Returns:
            Rich 可渲染对象
        """
        style_cfg = self.MESSAGE_STYLES.get(role, self.MESSAGE_STYLES["info"])
        color = style_cfg["color"]
        icon = style_cfg["icon"]
        label = style_cfg["label"]

        ts_str = ""
        if self.show_timestamp and timestamp:
            ts_str = f"[{timestamp.strftime('%H:%M:%S')}] "

        header = Text(
            f"{ts_str}{icon} {label}",
            style=f"{color} bold",
        )

        # 处理内容格式
        body = self._format_content(content, role)

        table = Table(show_header=False, box=None, padding=(0, 0))
        table.add_row(header)
        table.add_row(body)

        # 系统消息使用简洁格式
        if role in ("system", "error", "info"):
            return Text.assemble(
                Text(f"{ts_str}{icon} ", style=f"{color}"),
                Text(content, style=f"{color}"),
            )

        return Panel(
            table,
            border_style=f"{color} dim",
            padding=(0, 1),
        )

    def _format_content(self, content: str, role: str) -> Text:
        """格式化消息内容

        对 Agent 消息进行代码块检测和语法高亮，
        对用户消息进行简单换行处理。
        """
        if not content:
            return Text("(空消息)", style="dim")

        color = self.MESSAGE_STYLES.get(role, {}).get("color", "white")

        # 检测代码块
        if "```" in content:
            return self._render_with_code_blocks(content, color)

        # 普通文本
        wrapped = textwrap.fill(content, width=self.wrap_width) if self.wrap_width else content
        return Text(wrapped, style=color)

    def _render_with_code_blocks(self, content: str, text_color: str) -> Text:
        """渲染包含代码块的内容"""
        result_parts: list[Text] = []
        lines = content.split("\n")
        in_code = False
        code_buffer: list[str] = []
        code_lang = ""
        text_buffer: list[str] = []

        for line in lines:
            if line.startswith("```"):
                if not in_code:
                    # 开始代码块
                    if text_buffer:
                        text_content = "\n".join(text_buffer)
                        if text_content:
                            result_parts.append(Text(text_content, style=text_color))
                        text_buffer = []
                    code_lang = line[3:].strip() or "text"
                    in_code = True
                else:
                    # 结束代码块
                    code_content = "\n".join(code_buffer)
                    syntax = Syntax(
                        code_content,
                        code_lang if code_lang != "text" else "python",
                        theme="default",
                        word_wrap=True,
                    )
                    result_parts.append(Text("\n"))
                    result_parts.append(syntax)  # type: ignore[arg-type]
                    result_parts.append(Text("\n"))
                    code_buffer = []
                    in_code = False
            elif in_code:
                code_buffer.append(line)
            else:
                text_buffer.append(line)

        # 处理剩余内容
        if text_buffer:
            text_content = "\n".join(text_buffer)
            if text_content:
                result_parts.append(Text(text_content, style=text_color))

        if result_parts:
            return Text.assemble(*result_parts)

        return Text(content, style=text_color)

    def render_user(self, content: str, timestamp: datetime | None = None) -> Panel:
        """渲染用户消息"""
        return self.render("user", content, timestamp)  # type: ignore[return-value]

    def render_agent(self, content: str, timestamp: datetime | None = None) -> Panel:
        """渲染 Agent 消息"""
        return self.render("agent", content, timestamp)  # type: ignore[return-value]

    def render_system(self, content: str, timestamp: datetime | None = None) -> Text:
        """渲染系统消息"""
        return self.render("system", content, timestamp)  # type: ignore[return-value]

    def render_tool(
        self,
        content: str,
        tool_name: str = "",
        timestamp: datetime | None = None,
    ) -> Text:
        """渲染工具消息"""
        prefix = f"[{tool_name}] " if tool_name else ""
        return self.render("tool", f"{prefix}{content}", timestamp)  # type: ignore[return-value]

    def __call__(
        self,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Panel | Text:
        """便捷调用"""
        return self.render(role, content, timestamp, metadata)
