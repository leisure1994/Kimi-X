"""日志配置模块.

提供结构化日志记录能力，支持:
- 控制台彩色输出（Rich Handler）
- 文件日志（按大小轮转）
- JSON 结构化格式（可选）
- 日志级别动态调整

日志文件存储在 ~/.kimix/logs/ 目录下，按大小自动轮转。

示例:
    >>> from kimix.utils.logger import get_logger
    >>> logger = get_logger("my_module")
    >>> logger.info("操作成功")
    >>> logger.warning("警告信息")
    >>> logger.error("错误发生", exc_info=True)
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器.

    为不同日志级别添加 ANSI 颜色，便于在终端中区分。
    """

    # ANSI 颜色码
    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",      # 青色
        "INFO": "\033[32m",       # 绿色
        "WARNING": "\033[33m",    # 黄色
        "ERROR": "\033[31m",      # 红色
        "CRITICAL": "\033[35m",   # 紫色
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def __init__(self, fmt: str | None = None, use_color: bool = True) -> None:
        """初始化格式化器.

        Args:
            fmt: 日志格式字符串
            use_color: 是否使用颜色
        """
        super().__init__(fmt or self._default_format())
        self.use_color = use_color and sys.stdout.isatty()

    @staticmethod
    def _default_format() -> str:
        """获取默认格式字符串."""
        return (
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录.

        为日志级别添加颜色。

        Args:
            record: 日志记录对象

        Returns:
            str: 格式化后的日志字符串
        """
        if self.use_color:
            levelname = record.levelname
            color = self.COLORS.get(levelname, self.RESET)
            record.levelname = f"{color}{self.BOLD}{levelname}{self.RESET}"
            # 格式化后恢复原始值
            formatted = super().format(record)
            record.levelname = levelname
            return formatted
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器.

    以键值对格式输出日志，便于日志收集系统解析。
    """

    def __init__(self, fmt: str | None = None) -> None:
        """初始化格式化器.

        Args:
            fmt: 可选的格式字符串，默认使用结构化格式
        """
        super().__init__(fmt or self._default_format())

    @staticmethod
    def _default_format() -> str:
        """获取默认结构化格式."""
        return (
            "timestamp=%(asctime)s "
            "level=%(levelname)s "
            "logger=%(name)s "
            "message=%(message)s"
        )


def get_logs_dir() -> Path:
    """获取日志目录路径.

    日志目录位于 ~/.kimix/logs/

    Returns:
        Path: 日志目录绝对路径
    """
    logs_dir = Path.home() / ".kimix" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_logger(
    name: str,
    level: int | str = logging.INFO,
    log_to_file: bool = True,
    structured: bool = False,
) -> logging.Logger:
    """获取配置好的日志记录器.

    创建或获取指定名称的日志记录器，配置控制台输出和文件输出。

    Args:
        name: 日志记录器名称，通常使用模块名
        level: 日志级别，可以是 int 或 str（如 "DEBUG", "INFO"）
        log_to_file: 是否写入文件日志
        structured: 是否使用结构化格式（键值对）

    Returns:
        logging.Logger: 配置好的日志记录器

    示例:
        >>> logger = get_logger("my_module")
        >>> logger.info("普通信息")
        >>> logger = get_logger("debug_module", level="DEBUG")
        >>> logger.debug("调试信息")
    """
    # 确保名称使用 kimix 命名空间
    if not name.startswith("kimix"):
        name = f"kimix.{name}"

    logger = logging.getLogger(name)

    # 转换字符串级别为 int
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    logger.setLevel(level)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if structured:
        console_formatter = StructuredFormatter()
    else:
        console_formatter = ColoredFormatter()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_to_file:
        file_handler = _create_file_handler(name, level, structured)
        if file_handler:
            logger.addHandler(file_handler)

    # 不传播到根日志记录器，避免重复输出
    logger.propagate = False

    return logger


def _create_file_handler(
    name: str,
    level: int,
    structured: bool = False,
) -> logging.handlers.RotatingFileHandler | None:
    """创建文件日志处理器.

    使用 RotatingFileHandler 实现按大小自动轮转。

    Args:
        name: 日志记录器名称
        level: 日志级别
        structured: 是否使用结构化格式

    Returns:
        RotatingFileHandler | None: 文件处理器，失败时返回 None
    """
    try:
        logs_dir = get_logs_dir()

        # 从模块名中提取简短名称
        short_name = name.replace("kimix.", "").replace(".", "_")
        log_file = logs_dir / f"{short_name}.log"

        # 创建 RotatingFileHandler（最大 10MB，保留 5 个备份）
        handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        handler.setLevel(level)

        if structured:
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
        handler.setFormatter(formatter)

        return handler

    except (OSError, PermissionError) as exc:
        # 无法创建日志文件时，使用控制台输出警告
        fallback = logging.StreamHandler(sys.stderr)
        fallback.setLevel(logging.WARNING)
        fallback.setFormatter(logging.Formatter("[日志初始化警告] %(message)s"))
        fallback.emit(
            logging.LogRecord(
                name="kimix.logging",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg=f"无法创建日志文件: {exc}",
                args=(),
                exc_info=None,
            )
        )
        return None


def set_global_level(level: int | str) -> None:
    """设置全局日志级别.

    修改所有 kimix.* 日志记录器的级别。

    Args:
        level: 日志级别，如 "DEBUG", "INFO", "WARNING"

    示例:
        >>> set_global_level("DEBUG")  # 开启调试模式
        >>> set_global_level("WARNING")  # 只显示警告和错误
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("kimix")
    root.setLevel(level)

    for handler in root.handlers:
        handler.setLevel(level)

    # 递归设置所有子记录器
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith("kimix"):
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            for handler in logger.handlers:
                handler.setLevel(level)


def get_logger_names() -> list[str]:
    """获取所有已创建的 kimix 日志记录器名称.

    Returns:
        list[str]: 日志记录器名称列表
    """
    return [
        name
        for name in logging.root.manager.loggerDict
        if name.startswith("kimix")
    ]
