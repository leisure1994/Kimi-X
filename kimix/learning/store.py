"""自学习系统持久化存储.

基于 aiosqlite 实现经验记录、策略 Playbook、技能模式和 Prompt 版本的
CRUD 操作。使用 FTS5 支持全文检索。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from .models import (
    ExperienceRecord,
    PromptVersion,
    SkillPattern,
    StrategyPlaybook,
    TaskOutcome,
)

logger = logging.getLogger(__name__)

# 建表 SQL
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT '',
    task_description TEXT NOT NULL DEFAULT '',
    context_tags TEXT NOT NULL DEFAULT '[]',
    tools_used TEXT NOT NULL DEFAULT '[]',
    steps_count INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL DEFAULT 'success',
    error_type TEXT NOT NULL DEFAULT '',
    lesson TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    token_cost INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS strategies (
    task_type TEXT PRIMARY KEY,
    strategy_text TEXT NOT NULL DEFAULT '',
    success_rate REAL NOT NULL DEFAULT 0.5,
    avg_steps REAL NOT NULL DEFAULT 0.0,
    avg_duration REAL NOT NULL DEFAULT 0.0,
    preferred_tools TEXT NOT NULL DEFAULT '[]',
    anti_patterns TEXT NOT NULL DEFAULT '[]',
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    trigger_tags TEXT NOT NULL DEFAULT '[]',
    tool_sequence TEXT NOT NULL DEFAULT '[]',
    success_rate REAL NOT NULL DEFAULT 0.0,
    usage_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    version INTEGER PRIMARY KEY,
    prompt_text TEXT NOT NULL DEFAULT '',
    avg_score REAL NOT NULL DEFAULT 0.0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_exp_task_type ON experiences(task_type);
CREATE INDEX IF NOT EXISTS idx_exp_outcome ON experiences(outcome);
CREATE INDEX IF NOT EXISTS idx_exp_timestamp ON experiences(timestamp DESC);
"""


class LearningStore:
    """自学习系统存储层.

    管理 SQLite 数据库连接和所有学习数据的持久化操作。
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """初始化数据库连接和表结构."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()
        logger.debug(f"学习存储初始化完成: {self._db_path}")

    async def close(self) -> None:
        """关闭数据库连接."""
        if self._db:
            await self._db.close()
            self._db = None

    # ========================
    # 经验记录 CRUD
    # ========================

    async def save_experience(self, exp: ExperienceRecord) -> str:
        """保存一条经验记录.

        Args:
            exp: 经验记录对象

        Returns:
            记录 ID
        """
        if not exp.id:
            exp.id = uuid.uuid4().hex[:12]
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO experiences
            (id, timestamp, task_type, task_description, context_tags, tools_used,
             steps_count, outcome, error_type, lesson, score, duration_seconds, token_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                exp.id,
                exp.timestamp,
                exp.task_type,
                exp.task_description,
                json.dumps(exp.context_tags),
                json.dumps(exp.tools_used),
                exp.steps_count,
                exp.outcome.value,
                exp.error_type,
                exp.lesson,
                exp.score,
                exp.duration_seconds,
                exp.token_cost,
            ),
        )
        await self._db.commit()
        return exp.id

    async def get_experiences(
        self,
        task_type: str | None = None,
        outcome: TaskOutcome | None = None,
        limit: int = 50,
    ) -> list[ExperienceRecord]:
        """检索经验记录.

        Args:
            task_type: 按任务类型筛选
            outcome: 按结果筛选
            limit: 最大返回数量

        Returns:
            经验记录列表（按时间倒序）
        """
        assert self._db is not None
        conditions: list[str] = []
        params: list[Any] = []

        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        if outcome:
            conditions.append("outcome = ?")
            params.append(outcome.value)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM experiences{where_clause} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_experience(row) for row in rows]

    async def get_recent_experiences(self, limit: int = 20) -> list[ExperienceRecord]:
        """获取最近的经验记录."""
        return await self.get_experiences(limit=limit)

    async def count_experiences(self) -> int:
        """获取经验记录总数."""
        assert self._db is not None
        cursor = await self._db.execute("SELECT COUNT(*) FROM experiences")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def prune_experiences(self, max_count: int) -> int:
        """修剪超出数量的旧经验（保留高分记录）.

        Args:
            max_count: 保留的最大数量

        Returns:
            删除的记录数
        """
        assert self._db is not None
        total = await self.count_experiences()
        if total <= max_count:
            return 0

        # 删除低分且旧的记录
        to_delete = total - max_count
        await self._db.execute(
            """DELETE FROM experiences WHERE id IN (
                SELECT id FROM experiences ORDER BY score ASC, timestamp ASC LIMIT ?
            )""",
            (to_delete,),
        )
        await self._db.commit()
        return to_delete

    # ========================
    # 策略 Playbook CRUD
    # ========================

    async def save_strategy(self, strategy: StrategyPlaybook) -> None:
        """保存或更新策略 Playbook."""
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO strategies
            (task_type, strategy_text, success_rate, avg_steps, avg_duration,
             preferred_tools, anti_patterns, sample_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                strategy.task_type,
                strategy.strategy_text,
                strategy.success_rate,
                strategy.avg_steps,
                strategy.avg_duration,
                json.dumps(strategy.preferred_tools),
                json.dumps(strategy.anti_patterns),
                strategy.sample_count,
                strategy.last_updated,
            ),
        )
        await self._db.commit()

    async def get_strategy(self, task_type: str) -> StrategyPlaybook | None:
        """获取指定任务类型的策略."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM strategies WHERE task_type = ?", (task_type,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_strategy(row)

    async def get_all_strategies(self) -> list[StrategyPlaybook]:
        """获取所有策略."""
        assert self._db is not None
        cursor = await self._db.execute("SELECT * FROM strategies")
        rows = await cursor.fetchall()
        return [self._row_to_strategy(row) for row in rows]

    # ========================
    # 技能模式 CRUD
    # ========================

    async def save_skill_pattern(self, pattern: SkillPattern) -> str:
        """保存技能模式."""
        if not pattern.id:
            pattern.id = uuid.uuid4().hex[:12]
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO skill_patterns
            (id, name, description, trigger_tags, tool_sequence, success_rate, usage_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern.id,
                pattern.name,
                pattern.description,
                json.dumps(pattern.trigger_tags),
                json.dumps(pattern.tool_sequence),
                pattern.success_rate,
                pattern.usage_count,
            ),
        )
        await self._db.commit()
        return pattern.id

    async def get_skill_patterns(self) -> list[SkillPattern]:
        """获取所有技能模式."""
        assert self._db is not None
        cursor = await self._db.execute("SELECT * FROM skill_patterns")
        rows = await cursor.fetchall()
        return [self._row_to_skill_pattern(row) for row in rows]

    # ========================
    # Prompt 版本 CRUD
    # ========================

    async def save_prompt_version(self, pv: PromptVersion) -> None:
        """保存 Prompt 版本."""
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO prompt_versions
            (version, prompt_text, avg_score, sample_count, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                pv.version,
                pv.prompt_text,
                pv.avg_score,
                pv.sample_count,
                pv.created_at,
                1 if pv.is_active else 0,
            ),
        )
        await self._db.commit()

    async def get_active_prompt(self) -> PromptVersion | None:
        """获取当前活跃的 Prompt 版本."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM prompt_versions WHERE is_active = 1 ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_prompt_version(row)

    async def get_latest_prompt_version(self) -> int:
        """获取最新 Prompt 版本号."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT MAX(version) FROM prompt_versions"
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

    async def deactivate_all_prompts(self) -> None:
        """将所有 Prompt 设为非活跃."""
        assert self._db is not None
        await self._db.execute("UPDATE prompt_versions SET is_active = 0")
        await self._db.commit()

    # ========================
    # 行转模型辅助方法
    # ========================

    @staticmethod
    def _row_to_experience(row: Any) -> ExperienceRecord:
        return ExperienceRecord(
            id=row[0],
            timestamp=row[1],
            task_type=row[2],
            task_description=row[3],
            context_tags=json.loads(row[4]),
            tools_used=json.loads(row[5]),
            steps_count=row[6],
            outcome=TaskOutcome(row[7]),
            error_type=row[8],
            lesson=row[9],
            score=row[10],
            duration_seconds=row[11],
            token_cost=row[12],
        )

    @staticmethod
    def _row_to_strategy(row: Any) -> StrategyPlaybook:
        return StrategyPlaybook(
            task_type=row[0],
            strategy_text=row[1],
            success_rate=row[2],
            avg_steps=row[3],
            avg_duration=row[4],
            preferred_tools=json.loads(row[5]),
            anti_patterns=json.loads(row[6]),
            sample_count=row[7],
            last_updated=row[8],
        )

    @staticmethod
    def _row_to_skill_pattern(row: Any) -> SkillPattern:
        return SkillPattern(
            id=row[0],
            name=row[1],
            description=row[2],
            trigger_tags=json.loads(row[3]),
            tool_sequence=json.loads(row[4]),
            success_rate=row[5],
            usage_count=row[6],
        )

    @staticmethod
    def _row_to_prompt_version(row: Any) -> PromptVersion:
        return PromptVersion(
            version=row[0],
            prompt_text=row[1],
            avg_score=row[2],
            sample_count=row[3],
            created_at=row[4],
            is_active=bool(row[5]),
        )
