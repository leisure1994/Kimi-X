"""
配置管理模块单元测试

测试 KimixConfig、AuthManager 及各子配置类的功能。
覆盖配置创建、验证和认证管理。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kimix.config import (
    AuthConfig,
    AuthCredentials,
    AuthManager,
    CostConfig,
    KimixConfig,
    MemoryConfig,
    ModesConfig,
    ModelConfig,
    SandboxConfig,
    SubagentsConfig,
    ToolsConfig,
    UIConfig,
)
from kimix.config import defaults



pytestmark = pytest.mark.unit
class TestKimixConfig:
    """KimixConfig 主配置类测试"""

    def test_default_config_creation(self) -> None:
        """测试使用默认值创建配置"""
        config = KimixConfig()
        assert config.model.default == defaults.DEFAULT_MODEL
        assert config.model.temperature == defaults.DEFAULT_TEMPERATURE
        assert config.model.thinking is True

    def test_config_with_custom_values(self) -> None:
        """测试使用自定义值创建配置"""
        config = KimixConfig(
            model={"default": "custom-model", "temperature": 0.5},
            auth={"api_key": "sk-test12345678901234567890"},
        )
        assert config.model.default == "custom-model"
        assert config.model.temperature == 0.5
        assert config.auth.api_key == "sk-test12345678901234567890"

    def test_config_ensure_directories(self) -> None:
        """测试目录创建功能"""
        config = KimixConfig()
        config.ensure_directories()

    def test_config_str_contains_model(self) -> None:
        """测试配置字符串包含模型信息"""
        config = KimixConfig()
        str_repr = str(config)
        assert "kimi" in str_repr.lower() or "model" in str_repr.lower()

    def test_config_sub_config_access(self) -> None:
        """测试子配置访问"""
        config = KimixConfig()
        assert isinstance(config.model, ModelConfig)
        assert isinstance(config.auth, AuthConfig)
        assert isinstance(config.tools, ToolsConfig)
        assert isinstance(config.memory, MemoryConfig)
        assert isinstance(config.modes, ModesConfig)
        assert isinstance(config.subagents, SubagentsConfig)
        assert isinstance(config.sandbox, SandboxConfig)
        assert isinstance(config.cost, CostConfig)
        assert isinstance(config.ui, UIConfig)


class TestModelConfig:
    """ModelConfig 模型配置测试"""

    def test_default_model_config(self) -> None:
        """测试默认模型配置"""
        cfg = ModelConfig()
        assert cfg.default == defaults.DEFAULT_MODEL
        assert cfg.max_tokens == defaults.DEFAULT_MAX_TOKENS
        assert cfg.temperature == defaults.DEFAULT_TEMPERATURE
        assert cfg.thinking is True

    def test_model_config_custom(self) -> None:
        """测试自定义模型配置"""
        cfg = ModelConfig(default="test-model", max_tokens=4096, temperature=0.7)
        assert cfg.default == "test-model"
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.7


class TestAuthConfig:
    """AuthConfig 认证配置测试"""

    def test_default_auth_config(self) -> None:
        """测试默认认证配置"""
        cfg = AuthConfig()
        assert cfg.api_key == ""
        assert cfg.base_url == "https://api.kimi.com/coding/v1"

    def test_auth_config_with_key(self) -> None:
        """测试带 API Key 的认证配置"""
        cfg = AuthConfig(api_key="sk-test123")
        assert cfg.api_key == "sk-test123"


class TestToolsConfig:
    """ToolsConfig 工具配置测试"""

    def test_default_tools_config(self) -> None:
        """测试默认工具配置包含启用的工具列表"""
        cfg = ToolsConfig()
        assert len(cfg.enabled) > 0
        assert "file_read" in cfg.enabled
        assert "shell" in cfg.enabled

    def test_tools_config_custom_disabled(self) -> None:
        """测试自定义禁用工具"""
        cfg = ToolsConfig(disabled=["shell"])
        assert "shell" in cfg.disabled


class TestSandboxConfig:
    """SandboxConfig 沙箱配置测试"""

    def test_default_sandbox_config(self) -> None:
        """测试默认沙箱配置"""
        cfg = SandboxConfig()
        assert cfg.enabled is True
        assert cfg.blocked_commands is not None
        assert len(cfg.blocked_commands) > 0
        assert cfg.allowed_paths == ["."]

    def test_sandbox_config_disabled(self) -> None:
        """测试禁用沙箱"""
        cfg = SandboxConfig(enabled=False)
        assert cfg.enabled is False


class TestMemoryConfig:
    """MemoryConfig 记忆配置测试"""

    def test_default_memory_config(self) -> None:
        """测试默认记忆配置"""
        cfg = MemoryConfig()
        assert cfg.max_working_cache == defaults.MAX_WORKING_CACHE_MB
        assert cfg.enabled is True

    def test_memory_config_custom(self) -> None:
        """测试自定义记忆配置"""
        cfg = MemoryConfig(max_working_cache=200, enabled=False)
        assert cfg.max_working_cache == 200
        assert cfg.enabled is False


class TestCostConfig:
    """CostConfig 成本配置测试"""

    def test_default_cost_config(self) -> None:
        """测试默认成本配置"""
        cfg = CostConfig()
        assert cfg.budget_limit == defaults.BUDGET_LIMIT
        assert cfg.warning_threshold == defaults.WARNING_THRESHOLD
        assert cfg.cache_optimization is True

    def test_cost_config_custom_budget(self) -> None:
        """测试自定义预算"""
        cfg = CostConfig(budget_limit=50.0)
        assert cfg.budget_limit == 50.0


class TestAuthManager:
    """AuthManager 认证管理器测试"""

    def test_auth_manager_init(self) -> None:
        """测试认证管理器初始化"""
        manager = AuthManager(api_key="")
        assert manager.credentials.api_key == ""

    def test_set_api_key(self) -> None:
        """测试设置 API Key"""
        manager = AuthManager(api_key="")
        manager.set_api_key("sk-test12345678901234567890")
        assert manager.credentials.api_key == "sk-test12345678901234567890"

    def test_get_api_key(self) -> None:
        """测试获取 API Key"""
        manager = AuthManager(api_key="sk-secret")
        assert manager.get_api_key() == "sk-secret"

    def test_api_key_empty(self) -> None:
        """测试空 API Key"""
        manager = AuthManager(api_key="")
        assert manager.get_api_key() == ""

    def test_auth_credentials_model(self) -> None:
        """测试认证凭据模型"""
        creds = AuthCredentials(api_key="sk-test12345678901234567890")
        assert creds.api_key == "sk-test12345678901234567890"
        assert creds.base_url == "https://api.kimi.com/coding/v1"

    def test_auth_credentials_custom_url(self) -> None:
        """测试自定义认证凭据 URL"""
        creds = AuthCredentials(api_key="sk-key12345678901234567890", base_url="http://custom.url")
        assert creds.base_url == "http://custom.url"

    def test_mask_key(self) -> None:
        """测试 API Key 脱敏"""
        masked = AuthManager.mask_key("sk-abcdefghijklmnopqrstuvwxyz")
        assert "****" in masked
        assert masked.startswith("sk-abc")

    def test_mask_key_empty(self) -> None:
        """测试空 Key 脱敏"""
        masked = AuthManager.mask_key("")
        assert masked == "<未设置>"

    def test_validate_key_format_valid(self) -> None:
        """测试验证有效 Key 格式"""
        manager = AuthManager(api_key="sk-abcdefghijklmnopqrstuvwxyz")
        assert manager.validate_key_format() is True

    def test_validate_key_format_invalid(self) -> None:
        """测试验证无效 Key 格式"""
        manager = AuthManager(api_key="bad-key")
        assert manager.validate_key_format() is False
