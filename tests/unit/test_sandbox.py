"""
沙箱系统单元测试

测试 Sandbox 的命令检查、路径检查、命令注入检测
和安全配置功能。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kimix.utils.sandbox import (
    SafetyCheckResult,
    SafetyLevel,
    Sandbox,
    SandboxConfig,
)



pytestmark = pytest.mark.unit
class TestSafetyCheckResult:
    """SafetyCheckResult 测试结果"""

    def test_allowed_result(self) -> None:
        """测试允许的结果"""
        result = SafetyCheckResult(allowed=True, level=SafetyLevel.SAFE)
        assert result.allowed is True
        assert result.level == SafetyLevel.SAFE

    def test_blocked_result(self) -> None:
        """测试阻止的结果"""
        result = SafetyCheckResult(
            allowed=False,
            level=SafetyLevel.BLOCKED_COMMAND,
            matched_rule="rm -rf /",
        )
        assert result.allowed is False
        assert result.matched_rule == "rm -rf /"

    def test_to_dict(self) -> None:
        """测试转换为字典"""
        result = SafetyCheckResult(allowed=True, level=SafetyLevel.SAFE)
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["level"] == "safe"


class TestSandboxCommandCheck:
    """Sandbox 命令检查测试"""

    def test_safe_command(self) -> None:
        """测试安全命令"""
        sandbox = Sandbox()
        result = sandbox.check_command("ls -la")
        assert result.allowed is True

    def test_dangerous_rm_rf_root(self) -> None:
        """测试 rm -rf / 被拦截"""
        sandbox = Sandbox()
        result = sandbox.check_command("rm -rf /")
        assert result.allowed is False

    def test_dangerous_mkfs(self) -> None:
        """测试 mkfs 被拦截"""
        sandbox = Sandbox()
        result = sandbox.check_command("mkfs.ext4 /dev/sda")
        assert result.allowed is False

    def test_dangerous_dd(self) -> None:
        """测试 dd 被拦截"""
        sandbox = Sandbox()
        result = sandbox.check_command("dd if=/dev/zero of=/dev/sda")
        assert result.allowed is False

    def test_safe_command_ls(self) -> None:
        """测试 ls 安全"""
        sandbox = Sandbox()
        result = sandbox.check_command("ls -la")
        assert result.allowed is True

    def test_empty_command(self) -> None:
        """测试空命令"""
        sandbox = Sandbox()
        result = sandbox.check_command("")
        assert result.allowed is True

    def test_disabled_sandbox(self) -> None:
        """测试禁用沙箱"""
        sandbox = Sandbox(enabled=False)
        result = sandbox.check_command("rm -rf /")
        assert result.allowed is True

    def test_command_injection_semicolon(self) -> None:
        """测试分号命令注入"""
        sandbox = Sandbox()
        result = sandbox.check_command("ls ; rm -rf /")
        assert result.allowed is False


class TestSandboxPathCheck:
    """Sandbox 路径检查测试"""

    def test_safe_relative_path(self) -> None:
        """测试安全相对路径"""
        sandbox = Sandbox()
        result = sandbox.check_path("./src/main.py")
        assert result.allowed is True

    def test_disabled_sandbox_path(self) -> None:
        """测试禁用沙箱时的路径检查"""
        sandbox = Sandbox(enabled=False)
        result = sandbox.check_path("/etc/passwd")
        assert result.allowed is True


class TestSandboxNetworkCheck:
    """Sandbox 网络检查测试"""

    def test_network_allowed(self) -> None:
        """测试允许网络"""
        sandbox = Sandbox(allow_network=True)
        result = sandbox.check_network()
        assert result.allowed is True

    def test_network_blocked(self) -> None:
        """测试禁用网络"""
        sandbox = Sandbox(allow_network=False)
        result = sandbox.check_network()
        assert result.allowed is False


class TestSandboxConfig:
    """SandboxConfig 配置测试"""

    def test_default_config(self) -> None:
        """测试默认配置"""
        config = SandboxConfig()
        assert config.enabled is True
        assert config.allow_network is True

    def test_custom_config(self) -> None:
        """测试自定义配置"""
        config = SandboxConfig(enabled=False, allow_network=False)
        assert config.enabled is False
        assert config.allow_network is False


class TestSandboxFromConfig:
    """Sandbox 从配置创建测试"""

    def test_from_empty_config(self) -> None:
        """测试从空配置创建"""
        mock_config = MagicMock()
        mock_config.sandbox = None
        sandbox = Sandbox.from_config(mock_config)
        assert isinstance(sandbox, Sandbox)
