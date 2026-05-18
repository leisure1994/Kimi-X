"""
语义记忆模块

提供结构化知识存储和管理，包括代码模式学习、项目结构知识图谱构建
和基于关键词的相似度搜索。使用 aiosqlite 进行异步持久化，
numpy 实现余弦相似度计算。

数据库表结构:
- code_patterns: 代码模式库
- knowledge_entries: 知识条目表
"""

from __future__ import annotations

import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np

from kimix.memory.models import CodePattern, KnowledgeEntry, ProjectMap

# SQL 语句常量
_CREATE_CODE_PATTERNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS code_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    frequency INTEGER NOT NULL DEFAULT 1,
    last_used TEXT NOT NULL
)
"""

_CREATE_KNOWLEDGE_ENTRIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0
)
"""

_CREATE_SEMANTIC_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_patterns_language ON code_patterns(language);
CREATE INDEX IF NOT EXISTS idx_patterns_freq ON code_patterns(frequency);
CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge_entries(topic);
"""

# 通用编程语言关键词（用于停用词过滤）
_COMMON_KEYWORDS = {
    "the", "and", "or", "not", "in", "is", "it", "to", "of", "a", "an",
    "for", "with", "as", "on", "at", "by", "from", "up", "about", "into",
    "if", "else", "def", "class", "import", "return", "try", "except",
    "finally", "while", "for", "in", "yield", "lambda", "pass", "break",
    "continue", "async", "await", "from", "import", "as", "self", "true",
    "false", "none", "this", "that", "function", "var", "let", "const",
}


def _tokenize(text: str) -> list[str]:
    """简单分词（模块级工具函数）

    将文本转为小写，提取字母数字 token，过滤停用词和短词。

    Args:
        text: 输入文本

    Returns:
        分词后的 token 列表
    """
    # 提取字母数字序列
    tokens: list[str] = []
    current: list[str] = []

    for char in text.lower():
        if char.isalnum() or char == "_":
            current.append(char)
        else:
            if current:
                word = "".join(current)
                if len(word) > 2 and word not in _COMMON_KEYWORDS:
                    tokens.append(word)
                current = []

    if current:
        word = "".join(current)
        if len(word) > 2 and word not in _COMMON_KEYWORDS:
            tokens.append(word)

    return tokens


def _text_to_vector(text: str, vocab: dict[str, int]) -> np.ndarray:
    """将文本转为词频向量（模块级工具函数）

    Args:
        text: 输入文本
        vocab: 词汇表映射 word -> index

    Returns:
        词频向量
    """
    tokens = _tokenize(text)
    if not tokens:
        return np.zeros(len(vocab))

    counter = Counter(tokens)
    vector = np.zeros(len(vocab))
    for word, count in counter.items():
        if word in vocab:
            vector[vocab[word]] = count
    return vector


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度（模块级工具函数）

    Args:
        a: 向量 a
        b: 向量 b

    Returns:
        余弦相似度 (-1.0 ~ 1.0)
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


class SemanticMemory:
    """语义记忆 - 结构化知识存储

    管理代码模式库和知识条目，支持从工具执行中自动学习代码模式、
    构建项目结构知识图谱和基于余弦相似度的关键词搜索。

    Attributes:
        _db_path: SQLite 数据库文件路径
        _db: aiosqlite 连接实例（惰性初始化）
    """

    def __init__(self, db_path: Path) -> None:
        """初始化语义记忆实例

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
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self._db_path))
            self._db.row_factory = aiosqlite.Row
            await self._init_tables()
        return self._db

    async def _init_tables(self) -> None:
        """初始化数据库表和索引（内部方法）"""
        db = await self._get_db()

        await db.execute(_CREATE_CODE_PATTERNS_TABLE_SQL)
        await db.execute(_CREATE_KNOWLEDGE_ENTRIES_TABLE_SQL)

        for sql in _CREATE_SEMANTIC_INDEX_SQL.strip().split(";"):
            if sql.strip():
                await db.execute(sql)

        await db.commit()

    async def learn_code_pattern(self, pattern: CodePattern) -> CodePattern:
        """学习代码模式

        将代码模式插入数据库。如果相同模式已存在，增加使用频率。

        Args:
            pattern: 代码模式条目

        Returns:
            插入/更新后的代码模式（包含数据库 id）
        """
        db = await self._get_db()

        if not pattern.last_used:
            pattern.last_used = _iso_timestamp()

        # 检查是否已存在相同模式
        cursor = await db.execute(
            "SELECT id, frequency FROM code_patterns WHERE pattern = ? AND language = ?",
            (pattern.pattern, pattern.language),
        )
        existing = await cursor.fetchone()

        if existing:
            # 更新频率
            new_freq = existing["frequency"] + pattern.frequency
            await db.execute(
                "UPDATE code_patterns SET frequency = ?, last_used = ? WHERE id = ?",
                (new_freq, pattern.last_used, existing["id"]),
            )
            pattern.id = existing["id"]
            pattern.frequency = new_freq
        else:
            # 插入新记录
            cursor = await db.execute(
                """
                INSERT INTO code_patterns (pattern, language, frequency, last_used)
                VALUES (?, ?, ?, ?)
                """,
                (
                    pattern.pattern,
                    pattern.language,
                    pattern.frequency,
                    pattern.last_used,
                ),
            )
            pattern.id = cursor.lastrowid or 0

        await db.commit()
        return pattern

    async def query_knowledge(
        self, query: str, limit: int = 10
    ) -> list[KnowledgeEntry]:
        """查询知识条目

        使用关键词相似度搜索，对查询和知识条目进行向量化后
        计算余弦相似度，返回最匹配的结果。

        Args:
            query: 搜索查询文本
            limit: 返回结果数量上限

        Returns:
            按相似度排序的知识条目列表
        """
        db = await self._get_db()

        # 获取所有知识条目
        cursor = await db.execute("SELECT * FROM knowledge_entries")
        rows = await cursor.fetchall()

        if not rows:
            return []

        # 构建词汇表
        all_texts = [query] + [row["topic"] + " " + row["content"] for row in rows]
        vocab = _build_vocab(all_texts)

        if not vocab:
            return []

        # 向量化查询
        query_vector = _text_to_vector(query, vocab)

        # 计算相似度
        scored_entries: list[tuple[float, KnowledgeEntry]] = []
        for row in rows:
            text = row["topic"] + " " + row["content"]
            entry_vector = _text_to_vector(text, vocab)
            similarity = _cosine_similarity(query_vector, entry_vector)

            entry = KnowledgeEntry(
                id=row["id"],
                topic=row["topic"],
                content=row["content"],
                source=row["source"],
                confidence=row["confidence"] * max(0.0, similarity),
            )
            scored_entries.append((similarity, entry))

        # 按相似度排序并返回前 N 个
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored_entries[:limit]]

    async def build_project_map(self, project_path: Path) -> ProjectMap:
        """构建项目知识图谱

        扫描项目目录结构，提取文件关系、模块依赖和入口点信息。

        Args:
            project_path: 项目根目录路径

        Returns:
            项目知识图谱
        """
        path = project_path.resolve()

        if not path.exists():
            return ProjectMap(project_path=str(path))

        files: list[dict[str, Any]] = []
        modules: list[dict[str, Any]] = []
        entry_points: list[str] = []
        relationships: list[dict[str, Any]] = []

        # 收集所有文件
        for root, _dirs, filenames in os.walk(path):
            # 跳过隐藏目录和常见忽略目录
            rel_root = Path(root).relative_to(path)
            if any(
                part.startswith(".")
                for part in rel_root.parts
                if part != "."
            ):
                continue
            if any(
                part in ("__pycache__", "node_modules", "venv", ".git", ".hg")
                for part in rel_root.parts
            ):
                continue

            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = str(file_path.relative_to(path))

                # 跳过隐藏文件和二进制文件
                if filename.startswith("."):
                    continue

                file_info: dict[str, Any] = {
                    "path": rel_path,
                    "name": filename,
                    "size": file_path.stat().st_size,
                }

                # 检测编程语言
                ext = Path(filename).suffix.lower()
                lang_map = {
                    ".py": "python",
                    ".js": "javascript",
                    ".ts": "typescript",
                    ".java": "java",
                    ".go": "go",
                    ".rs": "rust",
                    ".c": "c",
                    ".cpp": "cpp",
                    ".h": "c",
                    ".hpp": "cpp",
                    ".md": "markdown",
                    ".json": "json",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                    ".toml": "toml",
                    ".sh": "shell",
                    ".html": "html",
                    ".css": "css",
                }
                if ext in lang_map:
                    file_info["language"] = lang_map[ext]

                # 检测入口点
                if filename in (
                    "main.py",
                    "__main__.py",
                    "app.py",
                    "index.js",
                    "main.go",
                    "main.rs",
                ):
                    entry_points.append(rel_path)
                    file_info["is_entry"] = True

                # 检测模块
                if ext in (".py", ".js", ".ts", ".go", ".rs", ".java"):
                    module_name = str(Path(rel_path).parent).replace(os.sep, ".")
                    if module_name == ".":
                        module_name = Path(rel_path).stem

                    # 检查模块是否已记录
                    if not any(m["name"] == module_name for m in modules):
                        modules.append(
                            {
                                "name": module_name,
                                "path": str(Path(rel_path).parent),
                                "language": file_info.get("language", ""),
                            }
                        )

                files.append(file_info)

        # 构建文件关系（简单的同目录关系）
        dir_files: dict[str, list[str]] = {}
        for f in files:
            dir_path = str(Path(f["path"]).parent)
            if dir_path not in dir_files:
                dir_files[dir_path] = []
            dir_files[dir_path].append(f["path"])

        for dir_path, file_list in dir_files.items():
            if len(file_list) > 1:
                relationships.append(
                    {
                        "type": "same_directory",
                        "directory": dir_path,
                        "files": file_list,
                    }
                )

        return ProjectMap(
            project_path=str(path),
            files=files,
            modules=modules,
            entry_points=entry_points,
            relationships=relationships,
        )

    async def store_knowledge(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """存储知识条目

        Args:
            entry: 知识条目

        Returns:
            插入后的知识条目（包含数据库 id）
        """
        db = await self._get_db()

        cursor = await db.execute(
            """
            INSERT INTO knowledge_entries (topic, content, source, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (entry.topic, entry.content, entry.source, entry.confidence),
        )
        await db.commit()

        entry.id = cursor.lastrowid or 0
        return entry

    async def get_code_patterns(
        self, language: str | None = None, limit: int = 20
    ) -> list[CodePattern]:
        """获取代码模式列表

        Args:
            language: 可选的编程语言过滤
            limit: 返回数量上限

        Returns:
            代码模式列表（按使用频率降序）
        """
        db = await self._get_db()

        if language:
            cursor = await db.execute(
                """
                SELECT * FROM code_patterns
                WHERE language = ?
                ORDER BY frequency DESC
                LIMIT ?
                """,
                (language, limit),
            )
        else:
            cursor = await db.execute(
                """
                SELECT * FROM code_patterns
                ORDER BY frequency DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = await cursor.fetchall()
        return [
            CodePattern(
                id=row["id"],
                pattern=row["pattern"],
                language=row["language"],
                frequency=row["frequency"],
                last_used=row["last_used"],
            )
            for row in rows
        ]

    async def extract_patterns_from_code(
        self, code: str, language: str
    ) -> list[CodePattern]:
        """从代码中提取模式（自动学习）

        简单的启发式规则，从代码中提取函数定义、类定义和
        import 语句作为代码模式。

        Args:
            code: 源代码文本
            language: 编程语言

        Returns:
            提取的代码模式列表
        """
        patterns: list[CodePattern] = []
        lines = code.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Python 模式提取
            if language == "python":
                if stripped.startswith("def ") and "(" in stripped:
                    patterns.append(
                        CodePattern(
                            pattern=stripped,
                            language=language,
                            frequency=1,
                        )
                    )
                elif stripped.startswith("class "):
                    patterns.append(
                        CodePattern(
                            pattern=stripped,
                            language=language,
                            frequency=1,
                        )
                    )
                elif stripped.startswith(("import ", "from ")):
                    patterns.append(
                        CodePattern(
                            pattern=stripped,
                            language=language,
                            frequency=1,
                        )
                    )

        # 异步保存提取的模式
        for pattern in patterns:
            await self.learn_code_pattern(pattern)

        return patterns

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> SemanticMemory:
        """异步上下文管理器入口"""
        await self._get_db()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """异步上下文管理器出口"""
        await self.close()


def _build_vocab(texts: list[str]) -> dict[str, int]:
    """从文本集合构建词汇表（模块级工具函数）

    Args:
        texts: 文本列表

    Returns:
        词汇表映射 word -> index
    """
    vocab: dict[str, int] = {}
    for text in texts:
        for token in _tokenize(text):
            if token not in vocab:
                vocab[token] = len(vocab)
    return vocab


def _iso_timestamp() -> str:
    """生成 ISO 8601 格式时间戳（模块级工具函数）

    Returns:
        ISO 8601 格式时间戳字符串
    """
    return datetime.now(timezone.utc).isoformat()
