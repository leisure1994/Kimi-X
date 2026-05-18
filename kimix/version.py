"""版本信息模块.

管理 Kimi-Agent 的版本号、发布日期和版本相关工具函数。
遵循语义化版本规范 (SemVer): https://semver.org/lang/zh-CN/
"""

from __future__ import annotations

# 版本号遵循语义化版本规范: 主版本.次版本.修订号
# - 主版本: 不兼容的 API 变更
# - 次版本: 向下兼容的功能新增
# - 修订号: 向下兼容的问题修复
__version__ = "0.87"
__version_info__ = (0, 87, 0)

# 发布信息
__release_date__ = "2026-05-18"
__author__ = "Kimi-Agent Team"
__license__ = "MIT"

# 版本阶段标识
__version_stage__ = ""


def get_version_string() -> str:
    """获取完整的版本字符串.

    包含版本号和阶段标识，用于 --version 输出。

    Returns:
        str: 完整版本字符串，如 "1.0.0-beta"
    """
    if __version_stage__:
        return f"{__version__}-{__version_stage__}"
    return __version__


def parse_version(version_str: str) -> tuple[int, int, int]:
    """解析版本字符串为元组。

    Args:
        version_str: 版本字符串，如 "1.2.3"

    Returns:
        tuple[int, int, int]: 版本号元组 (主版本, 次版本, 修订号)

    Raises:
        ValueError: 版本号格式不正确
    """
    parts = version_str.split(".")
    if len(parts) != 3:
        raise ValueError(f"版本号格式错误: {version_str!r}，应为 'x.y.z'")
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise ValueError(f"版本号格式错误: {version_str!r}") from exc


def check_version_compatibility(required: str, current: str | None = None) -> bool:
    """检查当前版本是否满足最低版本要求。

    Args:
        required: 最低要求的版本号，如 "1.0.0"
        current: 当前版本号，默认使用 __version__

    Returns:
        bool: 当前版本是否满足要求
    """
    if current is None:
        current = __version__
    required_info = parse_version(required)
    current_info = parse_version(current)
    return current_info >= required_info
