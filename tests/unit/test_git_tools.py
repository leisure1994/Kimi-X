"""
Git 工具单元测试

测试 GitStatusTool、GitDiffTool、GitLogTool、GitBranchTool
等 Git 工具的功能。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kimix.tools.base import ToolContext
from kimix.tools.git_tools import (
    GitBranchTool,
    GitDiffTool,
    GitLogTool,
    GitStatusTool,
    _get_repo,
)



pytestmark = pytest.mark.unit
class TestGitStatusTool:
    """GitStatusTool 测试"""

    @pytest.mark.asyncio
    async def test_git_status_clean(self, temp_git_repo: Path) -> None:
        """测试干净仓库的状态"""
        tool = GitStatusTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"short": True}, ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_git_status_with_changes(self, temp_git_repo: Path) -> None:
        """测试有修改的状态"""
        (temp_git_repo / "new_file.txt").write_text("new content")
        tool = GitStatusTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"short": True}, ctx)
        assert result.success is True


class TestGitDiffTool:
    """GitDiffTool 测试"""

    @pytest.mark.asyncio
    async def test_git_diff_no_changes(self, temp_git_repo: Path) -> None:
        """测试无差异时的 diff"""
        tool = GitDiffTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({}, ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_git_diff_with_changes(self, temp_git_repo: Path) -> None:
        """测试有修改时的 diff"""
        (temp_git_repo / "README.md").write_text("# Modified\n")
        tool = GitDiffTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({}, ctx)
        assert result.success is True


class TestGitLogTool:
    """GitLogTool 测试"""

    @pytest.mark.asyncio
    async def test_git_log(self, temp_git_repo: Path) -> None:
        """测试查看日志"""
        tool = GitLogTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"n": 5, "oneline": True}, ctx)
        assert result.success is True
        assert "init" in result.content.lower()

    @pytest.mark.asyncio
    async def test_git_log_full(self, temp_git_repo: Path) -> None:
        """测试完整日志格式"""
        tool = GitLogTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"n": 10}, ctx)
        assert result.success is True


class TestGitBranchTool:
    """GitBranchTool 测试"""

    @pytest.mark.asyncio
    async def test_git_branch_list(self, temp_git_repo: Path) -> None:
        """测试列出分支"""
        tool = GitBranchTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"all": False}, ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_git_branch_with_all(self, temp_git_repo: Path) -> None:
        """测试列出所有分支（含远程）"""
        tool = GitBranchTool()
        ctx = ToolContext(work_dir=str(temp_git_repo), session_id="test")
        result = await tool.execute({"all": True}, ctx)
        assert result.success is True


class TestGetRepo:
    """_get_repo 辅助函数测试"""

    def test_get_repo_valid(self, temp_git_repo: Path) -> None:
        """测试获取有效的 Git 仓库"""
        repo = _get_repo(str(temp_git_repo))
        assert repo is not None

    def test_get_repo_invalid(self, temp_dir: Path) -> None:
        """测试获取无效的 Git 仓库"""
        result = _get_repo(str(temp_dir))
        assert result is None
