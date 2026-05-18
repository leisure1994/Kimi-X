"""
UI 包 - 用户界面层

提供 CLI 和 TUI 两种界面模式：
- CLI 模式: 适用于一次性问答和非交互式场景
- TUI 模式: 适用于交互式会话，提供 Rich 实时渲染

所有渲染组件支持中文显示，亮色/暗色主题自适应。
"""

from __future__ import annotations

from kimix.ui.renderers import (
    ThinkingRenderer,
    ToolCallRenderer,
    ToolResultRenderer,
    CostRenderer,
    MessageRenderer,
)
from kimix.ui.components import (
    StatusBar,
    InputBox,
    ChatHistory,
    ModeSelector,
)
from kimix.ui.cli import CLIInterface
from kimix.ui.tui import TUIApp

__all__ = [
    # 渲染器
    "ThinkingRenderer",
    "ToolCallRenderer",
    "ToolResultRenderer",
    "CostRenderer",
    "MessageRenderer",
    # 组件
    "StatusBar",
    "InputBox",
    "ChatHistory",
    "ModeSelector",
    # 界面
    "CLIInterface",
    "TUIApp",
]
