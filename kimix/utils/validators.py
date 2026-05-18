"""验证工具模块.

提供常用的验证函数，用于检查路径、命令、配置值等的合法性。

所有验证函数遵循以下约定:
- 返回 bool 表示验证结果
- 可选的 raise_error 参数控制是否抛出异常
- 异常消息使用中文，便于用户理解

示例:
    >>> from kimix.utils.validators import validate_path, validate_command
    >>> validate_path("./src/main.py")
    True
    >>> validate_command("ls -la")
    True
    >>> validate_api_key_format("sk-test123")
    False
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from kimix.config import defaults


# ========================
# 路径验证
# ========================


def validate_path(
    path: str | Path,
    must_exist: bool = False,
    allow_dir: bool = True,
    allow_file: bool = True,
    raise_error: bool = False,
) -> bool:
    """验证路径是否合法.

    检查路径格式是否正确，可选检查文件/目录是否存在。

    Args:
        path: 要验证的路径
        must_exist: 是否要求路径已存在
        allow_dir: 是否允许目录
        allow_file: 是否允许文件
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过

    Raises:
        ValueError: raise_error=True 且验证失败时

    示例:
        >>> validate_path("./src")
        True
        >>> validate_path("/nonexistent", must_exist=True)
        False
    """
    path_obj = Path(path)

    # 检查空路径
    if not str(path).strip():
        if raise_error:
            raise ValueError("路径不能为空")
        return False

    # 检查是否存在（如果需要）
    if must_exist and not path_obj.exists():
        if raise_error:
            raise ValueError(f"路径不存在: {path}")
        return False

    # 检查类型
    if path_obj.exists():
        if path_obj.is_dir() and not allow_dir:
            if raise_error:
                raise ValueError(f"不允许目录路径: {path}")
            return False
        if path_obj.is_file() and not allow_file:
            if raise_error:
                raise ValueError(f"不允许文件路径: {path}")
            return False

    return True


def validate_relative_path(path: str | Path, raise_error: bool = False) -> bool:
    """验证路径是否为相对路径且安全.

    防止路径遍历攻击（如 ../../../etc/passwd）。

    Args:
        path: 要验证的路径
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    path_str = str(path)

    # 检查路径遍历
    dangerous_patterns = ["..", "~", "/"]
    for pattern in dangerous_patterns:
        if pattern in path_str:
            if raise_error:
                raise ValueError(f"路径包含危险模式 '{pattern}': {path}")
            return False

    return True


def validate_allowed_path(
    path: str | Path,
    allowed_paths: list[str] | None = None,
    raise_error: bool = False,
) -> bool:
    """验证路径是否在允许的范围内.

    Args:
        path: 要验证的路径
        allowed_paths: 允许的路径列表，默认使用当前目录
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    path_obj = Path(path).resolve()
    allowed = allowed_paths or defaults.DEFAULT_ALLOWED_PATHS

    # 检查是否在允许范围内
    cwd = Path.cwd().resolve()

    # 工作目录下的路径总是允许的
    if str(path_obj).startswith(str(cwd)):
        return True

    # 检查其他允许的路径
    for allowed_path in allowed:
        allowed_expanded = Path(allowed_path).expanduser().resolve()
        if str(path_obj).startswith(str(allowed_expanded)):
            return True

    if raise_error:
        raise ValueError(f"路径不在允许范围内: {path}")
    return False


# ========================
# 命令验证
# ========================


def validate_command(
    command: str | list[str],
    blocked_commands: list[str] | None = None,
    raise_error: bool = False,
) -> bool:
    """验证命令是否安全.

    检查命令是否包含危险的子命令或模式。

    Args:
        command: 要验证的命令（字符串或参数列表）
        blocked_commands: 禁止的命令列表
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if isinstance(command, list):
        command_str = " ".join(shlex.quote(arg) for arg in command)
    else:
        command_str = command

    if not command_str.strip():
        if raise_error:
            raise ValueError("命令不能为空")
        return False

    blocked = blocked_commands or defaults.DEFAULT_BLOCKED_COMMANDS

    for blocked_cmd in blocked:
        if blocked_cmd in command_str:
            if raise_error:
                raise ValueError(f"命令包含禁止的操作: '{blocked_cmd}'")
            return False

    return True


def validate_shell_safe(command: str, raise_error: bool = False) -> bool:
    """验证命令是否安全（严格模式）.

    检查命令中是否包含危险的 shell 元字符或模式。

    Args:
        command: 要验证的命令
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    dangerous_patterns = [
        ";",           # 命令分隔
        "&&",          # 逻辑与
        "||",          # 逻辑或
        "|",           # 管道
        "`",           # 命令替换
        "$()",         # 命令替换
        "${",          # 变量扩展
        ">",           # 重定向
        "<",           # 重定向
        "* * *",       # cron 格式
    ]

    for pattern in dangerous_patterns:
        if pattern in command:
            if raise_error:
                raise ValueError(f"命令包含危险的 shell 模式: '{pattern}'")
            return False

    return True


# ========================
# API Key 验证
# ========================


def validate_api_key_format(api_key: str, raise_error: bool = False) -> bool:
    """验证 API Key 格式.

    检查 API Key 是否符合 Moonshot API Key 的格式要求。

    Args:
        api_key: 要验证的 API Key
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if not api_key:
        if raise_error:
            raise ValueError("API Key 不能为空")
        return False

    if not isinstance(api_key, str):
        if raise_error:
            raise ValueError("API Key 必须是字符串")
        return False

    if not api_key.startswith("sk-"):
        if raise_error:
            raise ValueError("API Key 必须以 'sk-' 开头")
        return False

    if len(api_key) < 20:
        if raise_error:
            raise ValueError("API Key 长度太短，疑似无效")
        return False

    return True


# ========================
# 数值验证
# ========================


def validate_range(
    value: int | float,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    raise_error: bool = False,
) -> bool:
    """验证数值是否在指定范围内.

    Args:
        value: 要验证的数值
        min_val: 最小值（包含）
        max_val: 最大值（包含）
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if min_val is not None and value < min_val:
        if raise_error:
            raise ValueError(f"值 {value} 小于最小值 {min_val}")
        return False

    if max_val is not None and value > max_val:
        if raise_error:
            raise ValueError(f"值 {value} 大于最大值 {max_val}")
        return False

    return True


def validate_positive_int(value: Any, raise_error: bool = False) -> bool:
    """验证值是否为正整数.

    Args:
        value: 要验证的值
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if not isinstance(value, int) or isinstance(value, bool):
        if raise_error:
            raise ValueError(f"必须是整数，当前类型: {type(value).__name__}")
        return False

    if value <= 0:
        if raise_error:
            raise ValueError(f"必须是正整数，当前值: {value}")
        return False

    return True


# ========================
# 字符串验证
# ========================


def validate_not_empty(value: str, field_name: str = "字段", raise_error: bool = False) -> bool:
    """验证字符串非空.

    Args:
        value: 要验证的字符串
        field_name: 字段名称（用于错误消息）
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if not value or not str(value).strip():
        if raise_error:
            raise ValueError(f"{field_name}不能为空")
        return False
    return True


def validate_one_of(
    value: Any,
    choices: set[Any],
    field_name: str = "字段",
    raise_error: bool = False,
) -> bool:
    """验证值是否在允许的选项中.

    Args:
        value: 要验证的值
        choices: 允许的选项集合
        field_name: 字段名称（用于错误消息）
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    if value not in choices:
        if raise_error:
            raise ValueError(
                f"{field_name}的值 '{value}' 不在允许范围内，"
                f"可选: {choices}"
            )
        return False
    return True


# ========================
# 文件验证
# ========================


def validate_file_size(
    path: str | Path,
    max_size_mb: int = 10,
    raise_error: bool = False,
) -> bool:
    """验证文件大小是否在限制内.

    Args:
        path: 文件路径
        max_size_mb: 最大允许大小（MB）
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    path_obj = Path(path)

    if not path_obj.exists():
        if raise_error:
            raise ValueError(f"文件不存在: {path}")
        return False

    if not path_obj.is_file():
        if raise_error:
            raise ValueError(f"不是文件: {path}")
        return False

    size_mb = path_obj.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        if raise_error:
            raise ValueError(
                f"文件大小 {size_mb:.2f}MB 超过限制 {max_size_mb}MB"
            )
        return False

    return True


def validate_extension(
    path: str | Path,
    allowed_extensions: set[str],
    raise_error: bool = False,
) -> bool:
    """验证文件扩展名是否在允许列表中.

    Args:
        path: 文件路径
        allowed_extensions: 允许的扩展名集合（如 {'.py', '.txt'}）
        raise_error: 验证失败时是否抛出异常

    Returns:
        bool: 验证是否通过
    """
    path_obj = Path(path)
    ext = path_obj.suffix.lower()

    # 规范化扩展名
    normalized_extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_extensions}

    if ext not in normalized_extensions:
        if raise_error:
            raise ValueError(
                f"不支持的文件类型 '{ext}'，"
                f"允许的类型: {normalized_extensions}"
            )
        return False

    return True
