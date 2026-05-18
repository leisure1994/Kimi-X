"""API Key 认证管理模块.

提供安全的 API Key 存储和管理功能，支持以下方式获取 API Key:
1. 环境变量（MOONSHOT_API_KEY / KIMIX_AUTH__API_KEY）
2. 配置文件（~/.kimix/config.yaml）
3. 用户交互式输入

安全特性:
- API Key 在内存和日志中脱敏显示
- 支持验证 API Key 格式
- 提供 API 连通性测试

示例:
    >>> from kimix.config import AuthManager
    >>> auth = AuthManager()
    >>> api_key = auth.get_api_key()
    >>> print(auth.mask_key(api_key))
    'sk-****abcd'
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from kimix.config import defaults


class AuthCredentials(BaseModel):
    """认证凭据数据模型.

    存储 API Key 和相关认证信息，支持脱敏显示。

    Attributes:
        api_key: Moonshot API Key
        base_url: API 基础 URL
    """

    api_key: str = Field(
        default="",
        description="Moonshot API Key",
    )
    base_url: str = Field(
        default=defaults.DEFAULT_API_BASE_URL,
        description="API 基础 URL",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str) -> str:
        """验证 API Key 格式.

        Kimi API Key 通常以 'sk-' 开头，长度约为 50-60 字符。
        空字符串表示未设置，不做验证。

        Args:
            v: API Key 字符串

        Returns:
            str: 验证后的 API Key

        Raises:
            ValueError: API Key 格式不正确
        """
        if not v:
            return v
        # Moonshot API Key 格式: sk- 开头，后跟字母数字
        if not v.startswith("sk-"):
            raise ValueError("API Key 必须以 'sk-' 开头")
        if len(v) < 20:
            raise ValueError("API Key 长度太短，疑似无效")
        return v

    def is_configured(self) -> bool:
        """检查认证信息是否已配置.

        Returns:
            bool: API Key 是否已设置
        """
        return bool(self.api_key)

    def masked_key(self) -> str:
        """获取脱敏显示的 API Key.

        用于日志输出和界面显示，保护密钥安全。

        Returns:
            str: 脱敏后的 API Key，如 'sk-****abcd'
        """
        return AuthManager.mask_key(self.api_key)


class AuthManager:
    """API Key 认证管理器.

    统一管理 API Key 的获取、验证和存储。

    Attributes:
        credentials: 当前认证凭据

    示例:
        >>> auth = AuthManager()
        >>> key = auth.get_api_key()
        >>> auth.test_connection()
    """

    # API Key 的环境变量名
    ENV_VAR_NAME: str = "MOONSHOT_API_KEY"
    """主环境变量名."""

    ALT_ENV_VAR_NAMES: list[str] = [
        "KIMIX_AUTH__API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_KEY",
    ]
    """备用环境变量名列表."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """初始化认证管理器.

        依次从以下来源获取 API Key（优先级从高到低）:
        1. 传入的参数
        2. 环境变量
        3. 配置文件

        Args:
            api_key: 显式传入的 API Key
            base_url: 显式传入的 API 基础 URL
        """
        self.credentials = AuthCredentials()

        if api_key:
            self.credentials.api_key = api_key
        if base_url:
            self.credentials.base_url = base_url

        # 如果未传入 api_key，尝试从其他来源获取
        if not self.credentials.api_key:
            self.credentials.api_key = self._find_api_key()

    def _find_api_key(self) -> str:
        """从多个来源查找 API Key.

        查找顺序:
        1. 主环境变量 MOONSHOT_API_KEY
        2. 备用环境变量
        3. 配置文件

        Returns:
            str: 找到的 API Key，未找到时返回空字符串
        """
        # 1. 检查主环境变量
        if key := os.environ.get(self.ENV_VAR_NAME, "").strip():
            return key

        # 2. 检查备用环境变量
        for var_name in self.ALT_ENV_VAR_NAMES:
            if key := os.environ.get(var_name, "").strip():
                return key

        # 3. 检查配置文件
        return self._load_key_from_config()

    @staticmethod
    def _load_key_from_config() -> str:
        """从配置文件加载 API Key.

        Returns:
            str: 配置文件中的 API Key，未找到时返回空字符串
        """
        config_path = Path.home() / defaults.CONFIG_DIR_NAME / defaults.CONFIG_FILE_NAME

        if not config_path.exists():
            return ""

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            auth_section = data.get("auth", {})
            api_key = auth_section.get("api_key", "")

            # 如果配置值是环境变量引用，解析它
            if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
                var_name = api_key[2:-1]
                api_key = os.environ.get(var_name, "")

            return api_key.strip() if api_key else ""

        except Exception:  # noqa: BLE001
            return ""

    def get_api_key(self) -> str:
        """获取 API Key.

        Returns:
            str: API Key，未设置时返回空字符串
        """
        return self.credentials.api_key

    def get_base_url(self) -> str:
        """获取 API 基础 URL.

        Returns:
            str: API 基础 URL
        """
        return self.credentials.base_url

    def is_configured(self) -> bool:
        """检查认证是否已配置.

        Returns:
            bool: API Key 是否已设置
        """
        return self.credentials.is_configured()

    @staticmethod
    def mask_key(api_key: str, visible_start: int = 6, visible_end: int = 4) -> str:
        """对 API Key 进行脱敏处理.

        保留开头和结尾的部分字符，中间用 * 号代替。

        Args:
            api_key: 原始 API Key
            visible_start: 开头保留的字符数
            visible_end: 结尾保留的字符数

        Returns:
            str: 脱敏后的 API Key，如 'sk-abc****wxyz'
        """
        if not api_key:
            return "<未设置>"

        key = api_key
        min_length = visible_start + visible_end + 4

        if len(key) <= min_length:
            return key[:3] + "****" + key[-2:] if len(key) > 5 else "****"

        return f"{key[:visible_start]}****{key[-visible_end:]}"

    def validate_key_format(self, api_key: str | None = None) -> bool:
        """验证 API Key 格式是否正确.

        Args:
            api_key: 要验证的 API Key，默认使用当前存储的 Key

        Returns:
            bool: 格式是否有效
        """
        key = api_key or self.credentials.api_key
        if not key:
            return False
        return key.startswith("sk-") and len(key) >= 20

    async def test_connection(self, api_key: str | None = None) -> dict[str, Any]:
        """测试 API 连通性.

        发送一个简单的请求到 Kimi API，验证 Key 是否有效。

        Args:
            api_key: 要测试的 API Key，默认使用当前存储的 Key

        Returns:
            dict: 测试结果，包含 success, latency_ms, message 等字段
        """
        import asyncio

        import httpx

        key = api_key or self.credentials.api_key
        if not key:
            return {
                "success": False,
                "latency_ms": 0,
                "message": "API Key 未设置",
            }

        url = f"{self.credentials.base_url}/models"
        headers = {"Authorization": f"Bearer {key}"}

        start_time = asyncio.get_event_loop().time()

        try:
            async with httpx.AsyncClient(timeout=defaults.HEALTH_CHECK_TIMEOUT) as client:
                response = await client.get(url, headers=headers)

            latency_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )

            if response.status_code == 200:
                return {
                    "success": True,
                    "latency_ms": latency_ms,
                    "message": f"连接成功（{latency_ms}ms）",
                }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "latency_ms": latency_ms,
                    "message": "API Key 无效或已过期",
                    "status_code": response.status_code,
                }
            else:
                return {
                    "success": False,
                    "latency_ms": latency_ms,
                    "message": f"API 返回错误: HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

        except httpx.TimeoutException:
            return {
                "success": False,
                "latency_ms": defaults.HEALTH_CHECK_TIMEOUT * 1000,
                "message": "连接超时",
            }
        except httpx.NetworkError as exc:
            return {
                "success": False,
                "latency_ms": 0,
                "message": f"网络错误: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "latency_ms": 0,
                "message": f"未知错误: {exc}",
            }

    def set_api_key(self, api_key: str) -> None:
        """设置 API Key.

        Args:
            api_key: 新的 API Key

        Raises:
            ValueError: API Key 格式不正确
        """
        # 验证格式
        validated = AuthCredentials.validate_api_key_format(api_key.strip())
        self.credentials.api_key = validated

    def save_to_config(self, config_path: Path | None = None) -> None:
        """将认证信息保存到配置文件.

        只更新 auth 部分，保留配置文件的其余内容。

        Args:
            config_path: 配置文件路径，默认使用 ~/.kimix/config.yaml

        Raises:
            ValueError: API Key 未设置
        """
        if not self.credentials.api_key:
            raise ValueError("API Key 未设置，无法保存")

        import yaml

        target = config_path or (
            Path.home() / defaults.CONFIG_DIR_NAME / defaults.CONFIG_FILE_NAME
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有配置
        existing: dict[str, Any] = {}
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                existing = {}

        # 更新 auth 部分
        existing["auth"] = {
            "api_key": self.credentials.api_key,
            "base_url": self.credentials.base_url,
        }

        # 写回文件
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                existing,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def __repr__(self) -> str:
        """返回对象的字符串表示.

        Returns:
            str: 脱敏后的对象表示
        """
        masked = self.mask_key(self.credentials.api_key)
        return f"AuthManager(api_key='{masked}', base_url='{self.credentials.base_url}')"

    def __str__(self) -> str:
        """返回用户友好的字符串表示.

        Returns:
            str: 脱敏后的对象表示
        """
        return self.__repr__()
