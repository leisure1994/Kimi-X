"""工具函数包.

提供 Kimi-Agent 的基础设施工具函数，包括:
- Sandbox: 沙箱隔离环境
- get_logger: 结构化日志记录
- 验证工具: 路径验证、命令验证等
- 辅助函数: 文件大小格式化、时间格式化等

示例:
    >>> from kimix.utils import Sandbox, get_logger
    >>> sandbox = Sandbox()
    >>> logger = get_logger("my_module")
"""

from __future__ import annotations

from kimix.utils.helpers import (
    async_to_sync,
    count_lines,
    count_tokens_approximate,
    format_datetime,
    format_duration,
    format_file_size,
    format_timestamp,
    get_file_info,
    parse_file_size,
    run_with_retry,
    run_with_timeout,
    time_ago,
    truncate_text,
)
from kimix.utils.logger import get_logger, set_global_level
from kimix.utils.sandbox import Sandbox, SafetyCheckResult, SafetyLevel, SandboxConfig
from kimix.utils.validators import (
    validate_allowed_path,
    validate_api_key_format,
    validate_command,
    validate_extension,
    validate_file_size,
    validate_not_empty,
    validate_one_of,
    validate_path,
    validate_positive_int,
    validate_range,
    validate_relative_path,
    validate_shell_safe,
)

__all__ = [
    # 沙箱
    "Sandbox",
    "SafetyCheckResult",
    "SafetyLevel",
    "SandboxConfig",
    # 日志
    "get_logger",
    "set_global_level",
    # 验证器
    "validate_path",
    "validate_relative_path",
    "validate_allowed_path",
    "validate_command",
    "validate_shell_safe",
    "validate_api_key_format",
    "validate_range",
    "validate_positive_int",
    "validate_not_empty",
    "validate_one_of",
    "validate_file_size",
    "validate_extension",
    # 辅助函数
    "format_file_size",
    "parse_file_size",
    "format_duration",
    "format_datetime",
    "format_timestamp",
    "time_ago",
    "truncate_text",
    "count_lines",
    "count_tokens_approximate",
    "get_file_info",
    "run_with_timeout",
    "run_with_retry",
    "async_to_sync",
]
