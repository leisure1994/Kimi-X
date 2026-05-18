"""
Kimi-Agent (kimix) 工作模式模块

提供 5 种工作模式的实现和模式路由器。

模式层级（从保守到激进）：
- Explore: 只读探索
- Plan: 只读+生成计划
- Agent: 交互执行（默认）
- Auto: 自适应自主执行
- YOLO: 全自主执行
"""

from __future__ import annotations

from kimix.modes.base import BaseMode, ApprovalLevel
from kimix.modes.explore import ExploreMode
from kimix.modes.plan import PlanMode
from kimix.modes.agent import AgentMode as AgentModeClass
from kimix.modes.auto import AutoMode
from kimix.modes.yolo import YoloMode
from kimix.modes.router import ModeRouter, TaskAnalysis

__all__ = [
    # 基类和通用类型
    "BaseMode",
    "ApprovalLevel",
    # 模式实现
    "ExploreMode",
    "PlanMode",
    "AgentModeClass",
    "AutoMode",
    "YoloMode",
    # 路由器
    "ModeRouter",
    "TaskAnalysis",
]
