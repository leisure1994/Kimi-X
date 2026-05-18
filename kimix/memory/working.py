"""
工作记忆模块

提供短期记忆存储，包括文件内容 LRU 缓存、变量空间和
最近工具结果缓存。所有数据保存在内存中，进程结束后自动清除。

设计要点:
- 文件缓存使用 LRU 策略，总大小限制 100MB
- 变量空间支持任意可序列化值
- 工具结果缓存最近 N 条结果
"""

from __future__ import annotations

import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any


class _FileCacheEntry:
    """文件缓存条目（内部类）

    Attributes:
        content: 文件内容文本
        size: 内容字节大小
        cached_at: 缓存时间戳
    """

    __slots__ = ("content", "size", "cached_at")

    def __init__(self, content: str) -> None:
        self.content: str = content
        self.size: int = len(content.encode("utf-8"))
        self.cached_at: float = time.time()


class WorkingMemory:
    """工作记忆 - 短期缓存系统

    管理当前会话的临时数据，包括文件内容缓存、变量空间和
    工具结果缓存。数据仅保存在内存中，进程结束后自动清除。

    Attributes:
        MAX_CACHE_SIZE: 文件缓存最大容量（字节，默认 100MB）
        MAX_TOOL_RESULTS: 工具结果缓存最大条数（默认 50）
    """

    MAX_CACHE_SIZE: int = 100 * 1024 * 1024  # 100MB
    MAX_TOOL_RESULTS: int = 50

    def __init__(self) -> None:
        """初始化工作记忆实例"""
        # 文件内容 LRU 缓存: path -> _FileCacheEntry
        self._file_cache: OrderedDict[str, _FileCacheEntry] = OrderedDict()
        # 当前缓存总大小（字节）
        self._current_cache_size: int = 0
        # 变量空间: name -> value
        self._variables: dict[str, Any] = {}
        # 最近工具结果缓存: (tool_name, params_hash) -> result
        self._tool_results: OrderedDict[str, Any] = OrderedDict()

    def cache_file(self, path: Path, content: str) -> None:
        """缓存文件内容（LRU 淘汰策略）

        将文件内容加入缓存。如果缓存总大小超过 MAX_CACHE_SIZE，
        将按 LRU 策略淘汰最久未使用的条目。

        Args:
            path: 文件路径（用于缓存键）
            content: 文件内容文本

        Raises:
            ValueError: 内容大小超过最大缓存限制
        """
        key: str = str(path.resolve())
        entry = _FileCacheEntry(content)

        # 检查单个条目大小
        if entry.size > self.MAX_CACHE_SIZE:
            raise ValueError(
                f"文件内容大小 ({entry.size} 字节) 超过缓存上限 "
                f"({self.MAX_CACHE_SIZE} 字节)"
            )

        # 如果键已存在，先释放旧空间
        if key in self._file_cache:
            old_entry = self._file_cache.pop(key)
            self._current_cache_size -= old_entry.size

        # LRU 淘汰: 释放空间直到足够
        while (
            self._current_cache_size + entry.size > self.MAX_CACHE_SIZE
            and self._file_cache
        ):
            self._evict_lru()

        self._file_cache[key] = entry
        self._current_cache_size += entry.size

    def get_cached_file(self, path: Path) -> str | None:
        """获取缓存的文件内容

        根据路径查找缓存的文件内容，访问后该条目会被标记为
        最近使用（移至 LRU 尾部）。

        Args:
            path: 文件路径

        Returns:
            文件内容文本，如果未缓存则返回 None
        """
        key: str = str(path.resolve())
        entry = self._file_cache.get(key)
        if entry is None:
            return None

        # 移动到末尾（最近使用）
        self._file_cache.move_to_end(key)
        return entry.content

    def store_variable(self, name: str, value: Any) -> None:
        """存储变量到变量空间

        Args:
            name: 变量名称
            value: 变量值（任意可序列化类型）
        """
        self._variables[name] = value

    def get_variable(self, name: str) -> Any:
        """获取变量空间中的值

        Args:
            name: 变量名称

        Returns:
            变量值，如果不存在则返回 None
        """
        return self._variables.get(name)

    def cache_tool_result(
        self, tool_name: str, params: dict[str, Any], result: Any
    ) -> None:
        """缓存工具执行结果

        将工具调用结果加入 LRU 缓存，键为工具名+参数哈希的组合。
        缓存条数超过 MAX_TOOL_RESULTS 时淘汰最久未使用的条目。

        Args:
            tool_name: 工具名称
            params: 工具调用参数
            result: 工具执行结果
        """
        # 使用参数哈希作为缓存键的一部分
        params_str = str(sorted(params.items())) if params else ""
        cache_key = f"{tool_name}:{hash(params_str)}"

        # 如果已存在，移到末尾
        if cache_key in self._tool_results:
            self._tool_results.move_to_end(cache_key)
            self._tool_results[cache_key] = result
            return

        # LRU 淘汰
        while len(self._tool_results) >= self.MAX_TOOL_RESULTS:
            self._tool_results.popitem(last=False)

        self._tool_results[cache_key] = result

    def get_cached_tool_result(
        self, tool_name: str, params: dict[str, Any]
    ) -> Any:
        """获取缓存的工具结果

        Args:
            tool_name: 工具名称
            params: 工具调用参数

        Returns:
            工具执行结果，如果未缓存则返回 None
        """
        params_str = str(sorted(params.items())) if params else ""
        cache_key = f"{tool_name}:{hash(params_str)}"

        if cache_key in self._tool_results:
            self._tool_results.move_to_end(cache_key)
            return self._tool_results[cache_key]
        return None

    def get_all_variables(self) -> dict[str, Any]:
        """获取所有变量

        Returns:
            变量空间的完整副本
        """
        return dict(self._variables)

    def clear_file_cache(self) -> None:
        """清空文件缓存"""
        self._file_cache.clear()
        self._current_cache_size = 0

    def clear_variables(self) -> None:
        """清空变量空间"""
        self._variables.clear()

    def clear_tool_cache(self) -> None:
        """清空工具结果缓存"""
        self._tool_results.clear()

    def get_stats(self) -> dict[str, Any]:
        """获取工作记忆统计信息

        Returns:
            包含缓存状态的字典:
            - file_cache_entries: 文件缓存条目数
            - file_cache_size_mb: 文件缓存大小 (MB)
            - variable_count: 变量数量
            - tool_cache_entries: 工具缓存条目数
        """
        return {
            "file_cache_entries": len(self._file_cache),
            "file_cache_size_mb": round(
                self._current_cache_size / (1024 * 1024), 2
            ),
            "variable_count": len(self._variables),
            "tool_cache_entries": len(self._tool_results),
        }

    def _evict_lru(self) -> None:
        """淘汰最久未使用的文件缓存条目（内部方法）"""
        if not self._file_cache:
            return
        key, entry = self._file_cache.popitem(last=False)
        self._current_cache_size -= entry.size
