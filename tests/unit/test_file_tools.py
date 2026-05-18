"""
文件工具单元测试

测试 ReadFileTool、WriteFileTool、EditFileTool、ListDirTool、
GrepFilesTool、FileSearchTool、GetFileInfoTool 等文件操作工具的 CRUD 功能。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kimix.tools.base import ToolContext, ToolResult
from kimix.tools.file_tools import (
    EditFileTool,
    FileSearchTool,
    GetFileInfoTool,
    GrepFilesTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)



pytestmark = pytest.mark.unit
class TestReadFileTool:
    """ReadFileTool 读取文件测试"""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试读取存在的文件"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")
        tool = ReadFileTool()
        result = await tool.execute({"file_path": str(test_file)}, tool_context)
        assert result.success is True
        assert "Hello, World!" in result.content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试读取不存在的文件"""
        tool = ReadFileTool()
        result = await tool.execute({"file_path": str(temp_dir / "noexist.txt")}, tool_context)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_read_empty_file(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试读取空文件"""
        test_file = temp_dir / "empty.txt"
        test_file.write_text("", encoding="utf-8")
        tool = ReadFileTool()
        result = await tool.execute({"file_path": str(test_file)}, tool_context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_read_file_too_large(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试读取超大文件（应截断）"""
        test_file = temp_dir / "large.txt"
        test_file.write_bytes(b"x" * (15 * 1024 * 1024))
        tool = ReadFileTool()
        result = await tool.execute({"file_path": str(test_file)}, tool_context)
        assert result.success is True


class TestWriteFileTool:
    """WriteFileTool 写入文件测试"""

    @pytest.mark.asyncio
    async def test_write_new_file(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试写入新文件"""
        tool = WriteFileTool()
        result = await tool.execute(
            {"file_path": str(temp_dir / "output.txt"), "content": "test content"},
            tool_context,
        )
        assert result.success is True
        assert (temp_dir / "output.txt").read_text() == "test content"

    @pytest.mark.asyncio
    async def test_write_overwrite_existing(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试覆盖已有文件"""
        existing = temp_dir / "exist.txt"
        existing.write_text("old content")
        tool = WriteFileTool()
        result = await tool.execute(
            {"file_path": str(existing), "content": "new content"},
            tool_context,
        )
        assert result.success is True
        assert existing.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_write_empty_content(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试写入空内容"""
        tool = WriteFileTool()
        result = await tool.execute(
            {"file_path": str(temp_dir / "empty.txt"), "content": ""},
            tool_context,
        )
        assert result.success is True
        assert (temp_dir / "empty.txt").read_text() == ""

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试写入时自动创建父目录"""
        tool = WriteFileTool()
        result = await tool.execute(
            {"file_path": str(temp_dir / "nested" / "deep" / "file.txt"), "content": "nested"},
            tool_context,
        )
        assert result.success is True
        assert (temp_dir / "nested" / "deep" / "file.txt").exists()


class TestEditFileTool:
    """EditFileTool 编辑文件测试"""

    @pytest.mark.asyncio
    async def test_edit_replace(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试字符串替换编辑"""
        test_file = temp_dir / "edit.txt"
        test_file.write_text("Hello foo bar", encoding="utf-8")
        tool = EditFileTool()
        result = await tool.execute(
            {"file_path": str(test_file), "old_string": "foo", "new_string": "baz"},
            tool_context,
        )
        assert result.success is True
        assert "baz" in test_file.read_text()
        assert "foo" not in test_file.read_text()

    @pytest.mark.asyncio
    async def test_edit_nonexistent_file(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试编辑不存在的文件"""
        tool = EditFileTool()
        result = await tool.execute(
            {"file_path": str(temp_dir / "noexist.txt"), "old_string": "a", "new_string": "b"},
            tool_context,
        )
        assert result.success is False


class TestListDirTool:
    """ListDirTool 目录列表测试"""

    @pytest.mark.asyncio
    async def test_list_directory(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试列出目录内容"""
        (temp_dir / "file1.txt").write_text("content1")
        (temp_dir / "file2.py").write_text("content2")
        tool = ListDirTool()
        result = await tool.execute({"dir_path": str(temp_dir)}, tool_context)
        assert result.success is True
        assert "file1.txt" in result.content or "file2" in result.content

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试列出不存在的目录"""
        tool = ListDirTool()
        result = await tool.execute({"dir_path": str(temp_dir / "nodir")}, tool_context)
        assert result.success is False


class TestGrepFilesTool:
    """GrepFilesTool 文件搜索测试"""

    @pytest.mark.asyncio
    async def test_grep_find_pattern(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试查找文本模式"""
        (temp_dir / "a.py").write_text("def hello():\n    pass\n")
        (temp_dir / "b.py").write_text("def world():\n    pass\n")
        tool = GrepFilesTool()
        result = await tool.execute({"pattern": "def ", "path": str(temp_dir)}, tool_context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_grep_no_match(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试无匹配的情况"""
        (temp_dir / "test.txt").write_text("hello world")
        tool = GrepFilesTool()
        result = await tool.execute(
            {"pattern": "xyz_not_found_123", "path": str(temp_dir)},
            tool_context,
        )
        assert result.success is True


class TestFileSearchTool:
    """FileSearchTool 文件名搜索测试"""

    @pytest.mark.asyncio
    async def test_search_by_name(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试按名称搜索文件"""
        (temp_dir / "test_module.py").write_text("")
        (temp_dir / "test_utils.py").write_text("")
        tool = FileSearchTool()
        result = await tool.execute({"query": "test_", "root": str(temp_dir)}, tool_context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_search_no_results(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试无结果搜索"""
        (temp_dir / "a.py").write_text("")
        tool = FileSearchTool()
        result = await tool.execute(
            {"query": "nonexistent_file_xyz", "root": str(temp_dir)},
            tool_context,
        )
        assert result.success is True


class TestGetFileInfoTool:
    """GetFileInfoTool 文件信息测试"""

    @pytest.mark.asyncio
    async def test_get_file_info(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试获取文件信息"""
        test_file = temp_dir / "info.txt"
        test_file.write_text("Hello\nWorld\n", encoding="utf-8")
        tool = GetFileInfoTool()
        result = await tool.execute({"file_path": str(test_file)}, tool_context)
        assert result.success is True
        assert "info.txt" in result.content

    @pytest.mark.asyncio
    async def test_get_nonexistent_info(self, temp_dir: Path, tool_context: ToolContext) -> None:
        """测试获取不存在路径的信息"""
        tool = GetFileInfoTool()
        result = await tool.execute({"file_path": str(temp_dir / "nope")}, tool_context)
        assert result.success is False

    def test_format_size(self) -> None:
        """测试文件大小格式化"""
        tool = GetFileInfoTool()
        assert "B" in tool._format_size(100)
        assert "KB" in tool._format_size(1024 * 10)
        assert "MB" in tool._format_size(1024 * 1024 * 10)


class TestFileAccessSecurity:
    """文件访问安全测试"""

    @pytest.mark.asyncio
    async def test_access_outside_work_dir(self, temp_dir: Path) -> None:
        """测试访问工作目录外的文件应被拒绝"""
        ctx = ToolContext(work_dir=str(temp_dir))
        tool = ReadFileTool()
        result = await tool.execute({"file_path": "/etc/passwd"}, ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, temp_dir: Path) -> None:
        """测试路径穿越防护"""
        ctx = ToolContext(work_dir=str(temp_dir))
        tool = ReadFileTool()
        result = await tool.execute({"file_path": "../../../etc/passwd"}, ctx)
        assert result.success is False
