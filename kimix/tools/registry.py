"""
工具注册表

管理所有可用工具的注册、发现和查询，并提供 OpenAI 兼容的工具模式转换。
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Type

from .base import AbstractTool, Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表

    管理所有可用工具的注册、注销和查询。
    支持自动从模块中发现工具类并注册。

    Example:
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())

        # 获取工具
        tool = registry.get("file_read")

        # 列出所有工具
        tools = registry.list_tools()

        # 转换为 OpenAI 工具格式
        schema = registry.to_openai_schema()
    """

    def __init__(self) -> None:
        # 工具名称 → 工具实例 的映射
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """注册一个工具实例

        Args:
            tool: 工具实例，必须实现 Tool 协议

        Raises:
            ValueError: 工具名称为空或已存在
            TypeError: 工具不符合 Tool 协议
        """
        if not isinstance(tool, Tool):
            raise TypeError(f"工具 {tool!r} 不符合 Tool 协议")

        name = tool.name
        if not name:
            raise ValueError("工具名称不能为空")

        if name in self._tools:
            logger.warning("工具 %s 已存在，将被覆盖", name)

        self._tools[name] = tool
        logger.debug("已注册工具: %s", name)

    def unregister(self, tool_name: str) -> None:
        """注销一个工具

        Args:
            tool_name: 要注销的工具名称

        说明:
            如果工具不存在，静默返回不抛异常。
        """
        if tool_name not in self._tools:
            return
        del self._tools[tool_name]
        logger.debug("已注销工具: %s", tool_name)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, tool_name: str) -> Tool:
        """获取指定名称的工具

        Args:
            tool_name: 工具名称

        Returns:
            Tool: 工具实例

        Raises:
            KeyError: 工具不存在
        """
        if tool_name not in self._tools:
            raise KeyError(f"工具 '{tool_name}' 未注册")
        return self._tools[tool_name]

    def list_tools(self) -> list[Tool]:
        """列出所有已注册的工具（按名称排序）"""
        return [self._tools[name] for name in sorted(self._tools.keys())]

    def list_tool_names(self) -> list[str]:
        """列出所有已注册的工具名称"""
        return list(self._tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        """检查工具是否已注册"""
        return tool_name in self._tools

    def has(self, tool_name: str) -> bool:
        """检查工具是否已注册（has_tool 的别名）"""
        return self.has_tool(tool_name)

    def __contains__(self, tool_name: str) -> bool:
        return self.has_tool(tool_name)

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    # ------------------------------------------------------------------
    # OpenAI Schema 转换
    # ------------------------------------------------------------------

    def to_openai_schema(self) -> list[dict[str, Any]]:
        """将所有工具转换为 OpenAI 工具调用格式

        Returns:
            list[dict]: OpenAI Chat Completions API 的 tools 参数格式
        """
        schema = []
        for tool in self._tools.values():
            if isinstance(tool, AbstractTool):
                schema.append(tool.to_schema())
            else:
                # 通用 Protocol 兼容
                schema.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                })
        return schema

    # ------------------------------------------------------------------
    # 自动发现
    # ------------------------------------------------------------------

    def discover_from_module(
        self,
        module_name: str,
        base_class: Type[AbstractTool] = AbstractTool,
    ) -> int:
        """从指定模块自动发现并注册工具类

        扫描模块中所有继承自 base_class 的类（非抽象类）并实例化注册。

        Args:
            module_name: 模块完整名称（如 'kimix.tools.file_tools'）
            base_class: 要扫描的基类，默认 AbstractTool

        Returns:
            int: 注册的工具数量
        """
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning("无法导入模块 %s: %s", module_name, exc)
            return 0

        count = 0
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # 必须是指定基类的子类，且不是基类本身，也不是抽象类
            if (
                issubclass(obj, base_class)
                and obj is not base_class
                and not inspect.isabstract(obj)
                and getattr(obj, "name", "")
            ):
                try:
                    instance = obj()
                    self.register(instance)
                    count += 1
                except Exception as exc:
                    logger.warning("实例化工具 %s 失败: %s", obj.__name__, exc)

        logger.info("从 %s 自动注册了 %d 个工具", module_name, count)
        return count

    def auto_discover(self) -> int:
        """自动发现 kimix.tools 包下所有内置工具

        扫描以下模块：
        - file_tools, shell_tools, git_tools, web_tools
        - agent_tools, system_tools

        Returns:
            int: 注册的工具总数
        """
        modules = [
            "kimix.tools.file_tools",
            "kimix.tools.shell_tools",
            "kimix.tools.git_tools",
            "kimix.tools.web_tools",
            "kimix.tools.agent_tools",
            "kimix.tools.system_tools",
            "kimix.tools.sandbox",
            "kimix.tools.git_tool",
            "kimix.tools.web_search",
        ]
        total = 0
        for mod in modules:
            total += self.discover_from_module(mod)
        return total

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def register_many(self, *tools: Tool) -> None:
        """批量注册多个工具"""
        for tool in tools:
            self.register(tool)

    def clear(self) -> None:
        """清空所有已注册的工具"""
        self._tools.clear()

    def create_default_registry(self) -> "ToolRegistry":
        """创建带有所有默认工具的注册表（工厂方法）"""
        self.auto_discover()
        return self
