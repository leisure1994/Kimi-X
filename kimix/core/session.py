"""
会话管理模块

提供 Session（会话）数据模型和 SessionManager（会话管理器）。
会话管理器使用 SQLite 进行持久化，支持：
- 创建、加载、保存会话
- 列出所有会话
- 会话元数据管理
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from pydantic import BaseModel, Field


# 默认会话数据库路径
DEFAULT_DB_PATH = Path.home() / ".kimix" / "sessions.db"


class Session(BaseModel):
    """会话数据模型
    
    一个会话代表与 Agent 的一次连续对话，包含多个回合（Turn）。
    
    Attributes:
        id: 会话唯一标识符（UUID）
        name: 会话名称（可自定义，默认基于时间）
        turns: 会话中的回合 ID 列表（有序）
        created_at: 创建时间（ISO 格式）
        updated_at: 最后更新时间（ISO 格式）
        project_path: 关联的项目路径
        metadata: 额外元数据
    
    Examples:
        >>> session = Session(
        ...     id="sess-001",
        ...     name="项目分析会话",
        ...     project_path="/home/user/my-project",
        ... )
        >>> session.name
        '项目分析会话'
    """
    id: str = Field(
        default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}",
        description="会话唯一标识符",
    )
    name: str = Field(
        default="",
        description="会话名称",
    )
    turns: list[str] = Field(
        default_factory=list,
        description="回合 ID 列表（按顺序）",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="创建时间",
    )
    updated_at: str = Field(
        default="",
        description="最后更新时间",
    )
    project_path: str = Field(
        default=".",
        description="关联项目路径",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="额外元数据",
    )

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.name:
            # 自动生成会话名称
            now = datetime.now(timezone.utc)
            self.name = f"会话 {now.strftime('%m-%d %H:%M')}"
        if not self.updated_at:
            self.updated_at = self.created_at

    def add_turn(self, turn_id: str) -> None:
        """添加回合到会话
        
        Args:
            turn_id: 回合 ID
        """
        self.turns.append(turn_id)
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """从字典反序列化"""
        return cls(**data)


class SessionManager:
    """会话管理器
    
    管理所有会话的生命周期，提供 SQLite 持久化存储。
    
    Attributes:
        db_path: SQLite 数据库文件路径
        current_session: 当前活跃会话（内存中）
    
    Examples:
        >>> import asyncio
        >>> async def example():
        ...     sm = SessionManager()
        ...     await sm.initialize()
        ...     session = await sm.create(name="测试会话")
        ...     print(session.id)
        ...     sessions = await sm.list_sessions()
        ...     print(len(sessions))
        >>> asyncio.run(example())
    """

    # 数据库表结构
    _CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        turns TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        project_path TEXT NOT NULL DEFAULT '.',
        metadata TEXT NOT NULL DEFAULT '{}'
    );
    """

    _CREATE_INDEX_SQL = """
    CREATE INDEX IF NOT EXISTS idx_sessions_updated 
    ON sessions(updated_at DESC);
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """初始化会话管理器
        
        Args:
            db_path: SQLite 数据库路径，默认 ~/.kimix/sessions.db
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.current_session: Session | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库
        
        创建必要的表和索引。幂等操作，可安全多次调用。
        """
        if self._initialized:
            return

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(self._CREATE_TABLE_SQL)
            await db.execute(self._CREATE_INDEX_SQL)
            await db.commit()

        self._initialized = True

    async def create(
        self,
        name: str = "",
        project_path: str = ".",
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """创建新会话
        
        Args:
            name: 会话名称（为空则自动生成）
            project_path: 关联的项目路径
            metadata: 额外元数据
        
        Returns:
            新创建的 Session 对象
        """
        await self.initialize()

        session = Session(
            name=name,
            project_path=project_path,
            metadata=metadata or {},
        )

        await self._save_to_db(session)
        self.current_session = session

        return session

    async def load(self, session_id: str) -> Session | None:
        """加载指定会话
        
        Args:
            session_id: 会话 ID
        
        Returns:
            Session 对象，不存在则返回 None
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return None

        session = self._row_to_session(row)
        self.current_session = session
        return session

    async def save(self, session: Session) -> None:
        """保存会话到数据库
        
        Args:
            session: 要保存的 Session 对象
        """
        await self.initialize()
        session.updated_at = datetime.utcnow().isoformat()
        await self._save_to_db(session)

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """列出所有会话（按更新时间倒序）
        
        Args:
            limit: 最大返回数量
            offset: 偏移量（用于分页）
        
        Returns:
            Session 对象列表
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM sessions 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_session(row) for row in rows]

    async def delete(self, session_id: str) -> bool:
        """删除会话
        
        Args:
            session_id: 要删除的会话 ID
        
        Returns:
            是否成功删除
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )
            await db.commit()

        # 如果删除的是当前会话，清空引用
        if self.current_session and self.current_session.id == session_id:
            self.current_session = None

        return cursor.rowcount > 0

    async def rename(self, session_id: str, new_name: str) -> bool:
        """重命名会话
        
        Args:
            session_id: 会话 ID
            new_name: 新名称
        
        Returns:
            是否成功
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, datetime.utcnow().isoformat(), session_id),
            )
            await db.commit()

        # 更新内存中的会话
        if self.current_session and self.current_session.id == session_id:
            self.current_session.name = new_name

        return True

    async def search_sessions(self, query: str, limit: int = 10) -> list[Session]:
        """搜索会话（按名称模糊匹配）
        
        Args:
            query: 搜索关键词
            limit: 最大返回数量
        
        Returns:
            匹配的 Session 列表
        """
        await self.initialize()

        pattern = f"%{query}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM sessions 
                WHERE name LIKE ? OR project_path LIKE ?
                ORDER BY updated_at DESC 
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_session(row) for row in rows]

    async def get_current_session(self) -> Session | None:
        """获取当前活跃会话
        
        Returns:
            当前会话，未设置则返回 None
        """
        return self.current_session

    async def set_current_session(self, session: Session) -> None:
        """设置当前活跃会话"""
        self.current_session = session

    async def close(self) -> None:
        """关闭管理器，清理资源"""
        self.current_session = None
        self._initialized = False

    async def _save_to_db(self, session: Session) -> None:
        """内部方法：将会话写入数据库
        
        Args:
            session: Session 对象
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO sessions 
                (id, name, turns, created_at, updated_at, project_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.name,
                    json.dumps(session.turns, ensure_ascii=False),
                    session.created_at,
                    session.updated_at,
                    session.project_path,
                    json.dumps(session.metadata, ensure_ascii=False, default=str),
                ),
            )
            await db.commit()

    def _row_to_session(self, row: aiosqlite.Row) -> Session:
        """内部方法：将数据库行转换为 Session 对象
        
        Args:
            row: 数据库行
        
        Returns:
            Session 对象
        """
        return Session(
            id=row["id"],
            name=row["name"],
            turns=json.loads(row["turns"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            project_path=row["project_path"],
            metadata=json.loads(row["metadata"]),
        )


# 同步兼容接口（用于非 async 上下文）

class SyncSessionManager:
    """同步会话管理器包装器
    
    为不方便使用 async 的上下文提供同步接口。
    内部仍然使用 SessionManager，但通过 asyncio.run 包装。
    
    Examples:
        >>> sm = SyncSessionManager()
        >>> session = sm.create("测试")
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """初始化
        
        Args:
            db_path: 数据库路径
        """
        import asyncio
        self._async_manager = SessionManager(db_path)
        self._loop = asyncio.new_event_loop()

    def create(
        self,
        name: str = "",
        project_path: str = ".",
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """创建新会话（同步）"""
        import asyncio
        return asyncio.run(
            self._async_manager.create(name, project_path, metadata)
        )

    def load(self, session_id: str) -> Session | None:
        """加载会话（同步）"""
        import asyncio
        return asyncio.run(self._async_manager.load(session_id))

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """列出会话（同步）"""
        import asyncio
        return asyncio.run(self._async_manager.list_sessions(limit))

    def delete(self, session_id: str) -> bool:
        """删除会话（同步）"""
        import asyncio
        return asyncio.run(self._async_manager.delete(session_id))

    def close(self) -> None:
        """关闭并清理"""
        self._loop.close()
