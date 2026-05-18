"""
情景记忆模块

提供基于 aiosqlite 的异步 SQLite 持久化存储，记录 Agent
执行过程中的离散事件。支持全文搜索、按会话查询和时间范围过滤。

数据库表结构:
- events: 主事件表，存储所有事件记录
- 自动创建 FTS5 虚拟表用于全文搜索
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from kimix.memory.models import Event


# SQL 语句常量
_CREATE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,  -- JSON 序列化的工具调用列表
    created_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
"""

_CREATE_FTS_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    content,
    event_type,
    session_id,
    content_row_id UNINDEXED,
    tokenize='porter unicode61'
)
"""

_CREATE_FTS_TRIGGER_INSERT_SQL = """
CREATE TRIGGER IF NOT EXISTS events_fts_insert
AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(content, event_type, session_id, content_row_id)
    VALUES (NEW.content, NEW.event_type, NEW.session_id, NEW.id);
END
"""

_CREATE_FTS_TRIGGER_DELETE_SQL = """
-- FTS5 删除通过 delete_old_events 方法手动处理
-- SQLite 3.40 的 FTS5 触发器删除语法有兼容性问题
SELECT 1 WHERE 0
"""


class EpisodicMemory:
    """情景记忆 - 事件历史持久化存储

    使用 aiosqlite 异步操作 SQLite 数据库存储事件记录，
    支持全文搜索、会话隔离查询和时间范围过滤。

    Attributes:
        _db_path: SQLite 数据库文件路径
        _db: aiosqlite 连接实例（惰性初始化）
    """

    def __init__(self, db_path: Path) -> None:
        """初始化情景记忆实例

        Args:
            db_path: SQLite 数据库文件路径
        """
        self._db_path: Path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        """获取数据库连接（惰性初始化，自动创建表）

        Returns:
            aiosqlite 连接实例
        """
        if self._db is None:
            # 确保父目录存在
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self._db_path))
            self._db.row_factory = aiosqlite.Row
            await self._init_tables()
        return self._db

    async def _init_tables(self) -> None:
        """初始化数据库表和索引（内部方法）"""
        db = await self._get_db()

        # 创建主事件表
        await db.execute(_CREATE_EVENTS_TABLE_SQL)

        # 创建索引
        for sql in _CREATE_INDEX_SQL.strip().split(";"):
            if sql.strip():
                await db.execute(sql)

        # 创建 FTS5 全文搜索表和触发器
        await db.execute(_CREATE_FTS_TABLE_SQL)
        await db.execute(_CREATE_FTS_TRIGGER_INSERT_SQL)
        await db.execute(_CREATE_FTS_TRIGGER_DELETE_SQL)

        await db.commit()

    async def record_event(self, event: Event) -> Event:
        """记录事件到情景记忆

        将事件插入 SQLite 数据库，FTS5 触发器自动同步全文索引。

        Args:
            event: 要记录的事件（id 字段会被数据库覆盖）

        Returns:
            插入后的事件（包含数据库生成的 id）
        """
        db = await self._get_db()

        # 如果没有时间戳，使用当前时间
        if not event.created_at:
            event.created_at = _iso_timestamp()

        tool_calls_json = json.dumps(event.tool_calls, ensure_ascii=False)

        cursor = await db.execute(
            """
            INSERT INTO events (session_id, event_type, content, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.session_id,
                event.event_type,
                event.content,
                tool_calls_json,
                event.created_at,
            ),
        )
        await db.commit()

        # 更新 id 并返回
        event.id = cursor.lastrowid or 0
        return event

    async def search_events(
        self, query: str, session_id: str | None = None, limit: int = 10
    ) -> list[Event]:
        """全文搜索事件

        使用 FTS5 全文搜索引擎查找匹配的事件记录。
        可选按会话过滤。

        Args:
            query: 搜索关键词（FTS5 语法支持 AND/OR/NOT）
            session_id: 可选的会话过滤条件
            limit: 返回结果数量上限

        Returns:
            匹配的事件列表（按相关性排序）
        """
        db = await self._get_db()

        if session_id:
            # 按会话 + 全文搜索
            cursor = await db.execute(
                """
                SELECT e.* FROM events e
                INNER JOIN events_fts fts ON e.id = fts.content_row_id
                WHERE events_fts MATCH ? AND e.session_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, session_id, limit),
            )
        else:
            # 全局全文搜索
            cursor = await db.execute(
                """
                SELECT e.* FROM events e
                INNER JOIN events_fts fts ON e.id = fts.content_row_id
                WHERE events_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )

        rows = await cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    async def get_recent_events(
        self,
        n: int = 50,
        session_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Event]:
        """获取最近的事件

        按时间倒序返回最近的事件记录，支持按会话和事件类型过滤。

        Args:
            n: 返回事件数量
            session_id: 可选的会话过滤条件
            event_type: 可选的事件类型过滤条件

        Returns:
            事件列表（按时间倒序）
        """
        db = await self._get_db()

        # 构建动态查询
        conditions: list[str] = []
        params: list[Any] = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(n)

        cursor = await db.execute(
            f"""
            SELECT * FROM events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )

        rows = await cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    async def get_events_by_time_range(
        self,
        start: str,
        end: str,
        session_id: str | None = None,
    ) -> list[Event]:
        """按时间范围查询事件

        Args:
            start: 开始时间戳（ISO 8601 格式）
            end: 结束时间戳（ISO 8601 格式）
            session_id: 可选的会话过滤条件

        Returns:
            时间范围内的事件列表（按时间正序）
        """
        db = await self._get_db()

        if session_id:
            cursor = await db.execute(
                """
                SELECT * FROM events
                WHERE created_at >= ? AND created_at <= ? AND session_id = ?
                ORDER BY created_at ASC
                """,
                (start, end, session_id),
            )
        else:
            cursor = await db.execute(
                """
                SELECT * FROM events
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at ASC
                """,
                (start, end),
            )

        rows = await cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    async def delete_old_events(self, before: str) -> int:
        """删除指定时间之前的事件

        用于定期清理过期历史数据。
        同时清理 FTS5 全文索引中的对应条目。

        Args:
            before: 截止时间戳（ISO 8601 格式）

        Returns:
            删除的事件数量
        """
        db = await self._get_db()

        # 先获取要删除的 rowid 列表
        cursor = await db.execute(
            "SELECT rowid FROM events WHERE created_at < ?",
            (before,),
        )
        rows = await cursor.fetchall()
        rowids = [row[0] for row in rows]

        # 从 FTS5 索引中删除（SQLite 3.40 触发器有兼容性问题，手动处理）
        for rid in rowids:
            await db.execute("DELETE FROM events_fts WHERE rowid = ?", (rid,))

        # 从主表中删除
        cursor = await db.execute(
            "DELETE FROM events WHERE created_at < ?",
            (before,),
        )
        await db.commit()
        return cursor.rowcount or 0

    async def get_event_count(
        self, session_id: str | None = None
    ) -> int:
        """获取事件总数

        Args:
            session_id: 可选的会话过滤条件

        Returns:
            事件数量
        """
        db = await self._get_db()

        if session_id:
            cursor = await db.execute(
                "SELECT COUNT(*) as count FROM events WHERE session_id = ?",
                (session_id,),
            )
        else:
            cursor = await db.execute("SELECT COUNT(*) as count FROM events")

        row = await cursor.fetchone()
        return row["count"] if row else 0

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> EpisodicMemory:
        """异步上下文管理器入口"""
        await self._get_db()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()


def _row_to_event(row: aiosqlite.Row) -> Event:
    """将数据库行转换为 Event 模型（模块级工具函数）

    Args:
        row: aiosqlite Row 对象

    Returns:
        Event 实例
    """
    tool_calls: list[dict[str, Any]] = []
    if row["tool_calls"]:
        try:
            tool_calls = json.loads(row["tool_calls"])
        except json.JSONDecodeError:
            tool_calls = []

    return Event(
        id=row["id"],
        session_id=row["session_id"],
        event_type=row["event_type"],
        content=row["content"],
        tool_calls=tool_calls,
        created_at=row["created_at"],
    )


def _iso_timestamp() -> str:
    """生成 ISO 8601 格式时间戳（模块级工具函数）

    Returns:
        ISO 8601 格式时间戳字符串
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
