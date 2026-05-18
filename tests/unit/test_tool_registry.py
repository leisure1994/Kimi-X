"""
工具注册表单元测试

测试 ToolRegistry 的自动发现、注册、获取和 schema 导出功能。
"""

from __future__ import annotations

from typing import Any

import pytest

from kimix.tools.base import AbstractTool, ApprovalLevel, ToolContext, ToolResult
from kimix.tools.registry import ToolRegistry



pytestmark = pytest.mark.unit
class FakeReadTool(AbstractTool):
    """模拟读取工具"""
    name = "file_read"
    description = "读取文件"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
    }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok("file content")


class FakeWriteTool(AbstractTool):
    """模拟写入工具"""
    name = "file_write"
    description = "写入文件"
    approval_required = ApprovalLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["file_path", "content"],
    }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok("written")


class TestToolRegistry:
    """ToolRegistry 测试类"""

    def test_create_empty_registry(self) -> None:
        """测试创建空注册表"""
        registry = ToolRegistry()
        assert len(registry.list_tools()) == 0

    def test_register_tool(self) -> None:
        """测试注册工具"""
        registry = ToolRegistry()
        tool = FakeReadTool()
        registry.register(tool)
        assert len(registry.list_tools()) == 1
        assert registry.get("file_read") is tool

    def test_register_multiple_tools(self) -> None:
        """测试注册多个工具"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        registry.register(FakeWriteTool())
        assert len(registry.list_tools()) == 2

    def test_get_nonexistent_tool(self) -> None:
        """测试获取不存在的工具"""
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="not_found"):
            registry.get("not_found")

    def test_get_tool(self) -> None:
        """测试获取工具"""
        registry = ToolRegistry()
        tool = FakeReadTool()
        registry.register(tool)
        assert registry.get("file_read") is tool

    def test_list_tools(self) -> None:
        """测试列出所有工具"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        registry.register(FakeWriteTool())
        tools = registry.list_tools()
        names = [t.name for t in tools]
        assert "file_read" in names
        assert "file_write" in names

    def test_list_tools_sorted(self) -> None:
        """测试工具列表是否按名称排序"""
        registry = ToolRegistry()
        registry.register(FakeWriteTool())
        registry.register(FakeReadTool())
        tools = registry.list_tools()
        names = [t.name for t in tools]
        assert names == sorted(names)

    def test_has_tool(self) -> None:
        """测试检查工具是否存在"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        assert registry.has("file_read") is True
        assert registry.has("not_exist") is False

    def test_to_openai_schema(self) -> None:
        """测试导出 OpenAI 格式 schema"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        schema = registry.to_openai_schema()
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "file_read"

    def test_to_openai_schema_empty(self) -> None:
        """测试空注册表的 schema 导出"""
        registry = ToolRegistry()
        schema = registry.to_openai_schema()
        assert schema == []

    def test_unregister_tool(self) -> None:
        """测试注销工具"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        assert registry.has("file_read") is True
        registry.unregister("file_read")
        assert registry.has("file_read") is False

    def test_unregister_nonexistent(self) -> None:
        """测试注销不存在的工具"""
        registry = ToolRegistry()
        registry.unregister("nonexistent")  # 不应抛出异常

    def test_duplicate_registration(self) -> None:
        """测试重复注册（后注册者覆盖）"""
        registry = ToolRegistry()
        tool1 = FakeReadTool()
        tool2 = FakeReadTool()
        registry.register(tool1)
        registry.register(tool2)
        assert len(registry.list_tools()) == 1
        assert registry.get("file_read") is tool2

    def test_registry_len(self) -> None:
        """测试注册表长度"""
        registry = ToolRegistry()
        assert len(registry) == 0
        registry.register(FakeReadTool())
        assert len(registry) == 1

    def test_registry_contains(self) -> None:
        """测试注册表的 contains 操作"""
        registry = ToolRegistry()
        registry.register(FakeReadTool())
        assert "file_read" in registry
        assert "file_write" not in registry


class TestToolRegistryAutoDiscover:
    """ToolRegistry 自动发现测试"""

    def test_auto_discover(self) -> None:
        """测试自动发现内置工具"""
        registry = ToolRegistry()
        registry.auto_discover()
        # 验证一些关键工具被注册
        assert registry.has("file_read")
        assert registry.has("file_write")
        assert registry.has("shell")

    def test_auto_discover_idempotent(self) -> None:
        """测试自动发现是幂等的"""
        registry = ToolRegistry()
        registry.auto_discover()
        count_after_first = len(registry.list_tools())
        registry.auto_discover()
        count_after_second = len(registry.list_tools())
        assert count_after_first == count_after_second
