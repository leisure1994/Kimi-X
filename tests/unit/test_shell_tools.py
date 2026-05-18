"""
Shell 工具单元测试

测试 ShellTool 的命令执行、超时控制、环境变量管理，
以及危险命令拦截等安全功能。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kimix.tools.base import ToolContext
from kimix.tools.shell_tools import ShellTool, _is_dangerous, _is_sensitive, safe_command

IS_WINDOWS = platform.system() == "Windows"



pytestmark = pytest.mark.unit
class TestShellToolSecurity:
    """Shell 工具安全测试"""

    def test_dangerous_rm_rf_root(self) -> None:
        """测试拦截 rm -rf /"""
        is_danger, reason = _is_dangerous("rm -rf /")
        assert is_danger is True
        assert reason is not None

    def test_dangerous_fork_bomb(self) -> None:
        """测试拦截 fork 炸弹"""
        is_danger, reason = _is_dangerous(":(){ :|:& };:")
        assert is_danger is True

    def test_dangerous_mkfs(self) -> None:
        """测试拦截 mkfs"""
        is_danger, reason = _is_dangerous("mkfs.ext4 /dev/sda")
        assert is_danger is True

    def test_dangerous_dd(self) -> None:
        """测试拦截 dd 到设备"""
        is_danger, reason = _is_dangerous("dd if=/dev/zero of=/dev/sda")
        assert is_danger is True

    def test_safe_command_ls(self) -> None:
        """测试安全命令不被拦截"""
        is_danger, reason = _is_dangerous("ls -la")
        assert is_danger is False

    def test_safe_command_cat(self) -> None:
        """测试 cat 命令安全"""
        is_danger, reason = _is_dangerous("cat file.txt")
        assert is_danger is False

    def test_sensitive_sudo(self) -> None:
        """测试 sudo 被标记为敏感"""
        is_sens, reason = _is_sensitive("sudo apt install python")
        assert is_sens is True

    def test_sensitive_rm_rf(self) -> None:
        """测试 rm -rf 被标记为敏感"""
        is_sens, reason = _is_sensitive("rm -rf build/")
        assert is_sens is True


class TestShellToolExecution:
    """Shell 工具执行测试"""

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, temp_dir: Path) -> None:
        """测试执行简单命令"""
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        result = await tool.execute({"command": "echo hello"}, ctx)
        assert result.success is True
        assert "hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_empty_command(self, temp_dir: Path) -> None:
        """测试执行空命令"""
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        result = await tool.execute({"command": ""}, ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_dangerous_command_blocked(self, temp_dir: Path) -> None:
        """测试危险命令被拦截"""
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        result = await tool.execute({"command": "rm -rf /"}, ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self, temp_dir: Path) -> None:
        """测试指定工作目录执行"""
        subdir = temp_dir / "sub"
        subdir.mkdir()
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        cmd = "cd" if IS_WINDOWS else "pwd"
        result = await tool.execute({"command": cmd, "cwd": str(subdir)}, ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_env(self, temp_dir: Path) -> None:
        """测试环境变量传递"""
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        if IS_WINDOWS:
            cmd = "echo %TEST_VAR%"
        else:
            cmd = "echo $TEST_VAR"
        result = await tool.execute(
            {"command": cmd, "env": {"TEST_VAR": "hello_env"}},
            ctx,
        )
        assert result.success is True
        assert "hello_env" in result.content

    @pytest.mark.asyncio
    async def test_output_truncation(self, temp_dir: Path) -> None:
        """测试超大输出截断"""
        tool = ShellTool()
        ctx = ToolContext(work_dir=str(temp_dir))
        python_cmd = sys.executable
        result = await tool.execute(
            {"command": f'{python_cmd} -c "print(\'x\' * 10000)"'},
            ctx,
        )
        assert result.success is True


class TestSafeCommandHelper:
    """safe_command 辅助函数测试"""

    @pytest.mark.asyncio
    async def test_safe_command_basic(self, temp_dir: Path) -> None:
        """测试基本命令执行"""
        exit_code, stdout, stderr = await safe_command("echo test123", cwd=str(temp_dir))
        assert exit_code == 0
        assert "test123" in stdout

    @pytest.mark.asyncio
    async def test_safe_command_with_timeout(self, temp_dir: Path) -> None:
        """测试带超时的命令执行"""
        exit_code, stdout, stderr = await safe_command("echo hello", cwd=str(temp_dir), timeout=5)
        assert exit_code == 0
        assert "hello" in stdout

    @pytest.mark.asyncio
    async def test_safe_command_failure(self, temp_dir: Path) -> None:
        """测试命令执行失败"""
        fail_cmd = "cmd /c exit 1" if IS_WINDOWS else "false"
        exit_code, stdout, stderr = await safe_command(fail_cmd, cwd=str(temp_dir))
        assert exit_code == 1
