"""配置管理包.

提供 Kimi-Agent 的全局配置管理能力，包括:
- KimixConfig: 主配置类，整合所有子配置
- AuthManager: API Key 认证管理
- defaults: 默认配置常量

配置加载优先级:
    1. 环境变量（格式: KIMIX_<SECTION>__<KEY>）
    2. YAML 配置文件（~/.kimix/config.yaml）
    3. 代码默认值

示例:
    >>> from kimix.config import KimixConfig, AuthManager
    >>> config = KimixConfig()
    >>> config.ensure_directories()
    >>> print(config.model.default)
    >>> print(config.sandbox.blocked_commands)
"""

from __future__ import annotations

from kimix.config.auth import AuthCredentials, AuthManager
from kimix.config.settings import (
    AuthConfig,
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

__all__ = [
    # 主配置类
    "KimixConfig",
    # 认证管理
    "AuthManager",
    "AuthCredentials",
    # 子配置类
    "AuthConfig",
    "ModelConfig",
    "ModesConfig",
    "MemoryConfig",
    "SubagentsConfig",
    "ToolsConfig",
    "SandboxConfig",
    "CostConfig",
    "UIConfig",
]
