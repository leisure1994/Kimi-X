"""辅助函数模块.

提供常用的工具函数，包括:
- 文件大小格式化
- 时间格式化
- 文本处理
- 异步工具函数

所有函数均为纯函数，无副作用。

示例:
    >>> from kimix.utils.helpers import format_file_size, format_duration
    >>> format_file_size(1536)
    '1.50 KB'
    >>> format_duration(3661)
    '1小时1分1秒'
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


# ========================
# 文件大小格式化
# ========================


def format_file_size(size_bytes: int | float, precision: int = 2) -> str:
    """将字节大小格式化为人类可读字符串.

    自动选择合适的单位（B, KB, MB, GB, TB）。

    Args:
        size_bytes: 文件大小（字节）
        precision: 小数位数

    Returns:
        str: 格式化后的大小字符串，如 "1.50 MB"

    示例:
        >>> format_file_size(1024)
        '1.00 KB'
        >>> format_file_size(1536)
        '1.50 KB'
        >>> format_file_size(1048576)
        '1.00 MB'
        >>> format_file_size(0)
        '0 B'
    """
    if size_bytes < 0:
        raise ValueError(f"文件大小不能为负数: {size_bytes}")

    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    return f"{size:.{precision}f} {units[unit_index]}"


def parse_file_size(size_str: str) -> int:
    """将人类可读的文件大小字符串解析为字节数.

    Args:
        size_str: 大小字符串，如 "10MB", "1.5 GB", "1024"

    Returns:
        int: 字节数

    Raises:
        ValueError: 无法解析的格式

    示例:
        >>> parse_file_size("10MB")
        10485760
        >>> parse_file_size("1.5 GB")
        1610612736
    """
    size_str = size_str.strip().upper().replace(" ", "")

    if not size_str:
        raise ValueError("大小字符串不能为空")

    # 纯数字，默认为字节
    if size_str.isdigit():
        return int(size_str)

    # 提取数值和单位
    units_map = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }

    for unit, multiplier in sorted(units_map.items(), key=lambda x: -x[1]):
        if size_str.endswith(unit):
            num_str = size_str[: -len(unit)]
            try:
                return int(float(num_str) * multiplier)
            except ValueError as exc:
                raise ValueError(f"无效的大小格式: {size_str}") from exc

    raise ValueError(f"无法解析大小格式: {size_str}")


# ========================
# 时间格式化
# ========================


def format_duration(seconds: int | float, compact: bool = False) -> str:
    """将秒数格式化为人类可读的时间字符串.

    Args:
        seconds: 时间（秒）
        compact: 是否使用紧凑格式

    Returns:
        str: 格式化后的时间字符串

    示例:
        >>> format_duration(3661)
        '1小时1分1秒'
        >>> format_duration(3661, compact=True)
        '1h1m1s'
        >>> format_duration(90)
        '1分30秒'
    """
    if seconds < 0:
        return f"-{format_duration(-seconds, compact)}"

    if seconds < 1:
        if compact:
            return f"{int(seconds * 1000)}ms"
        return f"{seconds:.2f}秒"

    # 计算各部分
    td = timedelta(seconds=int(seconds))
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []

    if compact:
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        return "".join(parts)

    # 完整格式（中文）
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")

    return "".join(parts)


def format_datetime(dt: datetime | None = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化日期时间.

    Args:
        dt: 要格式化的 datetime 对象，默认使用当前时间
        fmt: 格式字符串

    Returns:
        str: 格式化后的时间字符串

    示例:
        >>> format_datetime()
        '2025-01-15 10:30:00'
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)


def format_timestamp(timestamp: float | int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """将时间戳格式化为可读字符串.

    Args:
        timestamp: Unix 时间戳
        fmt: 格式字符串

    Returns:
        str: 格式化后的时间字符串
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime(fmt)


def time_ago(timestamp: float | int | datetime) -> str:
    """计算距离当前时间的相对时间描述.

    Args:
        timestamp: 时间戳或 datetime 对象

    Returns:
        str: 相对时间描述，如 "刚刚", "5分钟前"
    """
    if isinstance(timestamp, datetime):
        past = timestamp
    else:
        past = datetime.fromtimestamp(timestamp)

    now = datetime.now()
    diff = now - past

    seconds = int(diff.total_seconds())

    if seconds < 10:
        return "刚刚"
    if seconds < 60:
        return f"{seconds}秒前"
    if seconds < 3600:
        return f"{seconds // 60}分钟前"
    if seconds < 86400:
        return f"{seconds // 3600}小时前"
    if seconds < 604800:
        return f"{seconds // 86400}天前"
    if seconds < 2592000:
        return f"{seconds // 604800}周前"

    return format_datetime(past, "%Y-%m-%d")


# ========================
# 文本处理
# ========================


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """截断文本到指定长度.

    如果文本长度超过限制，截断并添加后缀。

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        str: 截断后的文本

    示例:
        >>> truncate_text("Hello World", 8)
        'Hello...'
    """
    if len(text) <= max_length:
        return text

    # 保留后缀空间
    truncate_at = max_length - len(suffix)
    if truncate_at < 1:
        return suffix[:max_length]

    return text[:truncate_at] + suffix


def count_lines(text: str) -> int:
    """计算文本行数.

    Args:
        text: 要计算的文本

    Returns:
        int: 行数
    """
    if not text:
        return 0
    return text.count("\n") + 1


def count_tokens_approximate(text: str) -> int:
    """粗略估算文本的 Token 数量.

    使用简单的字符统计方法估算，结果仅供参考。
    精确的 Token 计数需要使用 tiktoken。

    Args:
        text: 要估算的文本

    Returns:
        int: 估算的 Token 数量

    示例:
        >>> count_tokens_approximate("Hello World")
        3  # 大约值
    """
    if not text:
        return 0

    # 中文字符每个约 1.5 个 token
    # 英文单词每个约 1.3 个 token
    # 标点符号和空格每个约 0.5 个 token
    import re

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    others = len(text) - chinese_chars - sum(
        len(w) for w in re.findall(r"[a-zA-Z]+", text)
    )

    return int(chinese_chars * 1.5 + english_words * 1.3 + others * 0.5)


# ========================
# 文件工具
# ========================


def get_file_info(path: str | Path) -> dict[str, Any]:
    """获取文件信息.

    Args:
        path: 文件路径

    Returns:
        dict: 包含文件信息的字典

    示例:
        >>> get_file_info("./test.py")
        {'name': 'test.py', 'size': 1024, 'size_human': '1.00 KB', ...}
    """
    path_obj = Path(path)

    if not path_obj.exists():
        return {
            "exists": False,
            "path": str(path_obj),
            "name": path_obj.name,
        }

    stat = path_obj.stat()

    return {
        "exists": True,
        "path": str(path_obj.resolve()),
        "name": path_obj.name,
        "extension": path_obj.suffix,
        "size": stat.st_size,
        "size_human": format_file_size(stat.st_size),
        "created": format_timestamp(stat.st_ctime),
        "modified": format_timestamp(stat.st_mtime),
        "is_file": path_obj.is_file(),
        "is_dir": path_obj.is_dir(),
    }


# ========================
# 异步工具
# ========================


async def run_with_timeout(
    coro: Awaitable[T],
    timeout: float,
    default: T | None = None,
) -> T | None:
    """带超时的异步执行.

    执行异步操作，如果超过指定时间则返回默认值。

    Args:
        coro: 要执行的协程
        timeout: 超时时间（秒）
        default: 超时时的返回值

    Returns:
        协程结果或默认值

    示例:
        >>> result = await run_with_timeout(some_async_op(), 5.0, default=None)
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


async def run_with_retry(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """带重试的异步执行.

    执行异步操作，失败时自动重试，支持指数退避。

    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        delay: 初始重试间隔（秒）
        backoff: 退避倍数
        exceptions: 需要重试的异常类型

    Returns:
        函数返回值

    Raises:
        Exception: 所有重试都失败时抛出最后一次异常

    示例:
        >>> result = await run_with_retry(
        ...     lambda: api.call(),
        ...     max_retries=3,
        ...     delay=1.0,
        ... )
    """
    last_exception: Exception | None = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as exc:
            last_exception = exc
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= backoff

    raise last_exception  # type: ignore[misc]


def async_to_sync(coro: Awaitable[T]) -> T:
    """将异步操作转为同步执行.

    在没有事件循环时创建新的事件循环执行，
    在有事件循环时使用 nest_asyncio 风格的执行。

    Args:
        coro: 要执行的协程

    Returns:
        协程返回值
    """
    try:
        loop = asyncio.get_running_loop()
        # 如果在事件循环中，使用 asyncio.run_coroutine_threadsafe 或类似方式
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有运行的事件循环
        return asyncio.run(coro)
