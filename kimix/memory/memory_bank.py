"""
Memory Bank — 持久化项目记忆

跨会话保留项目知识，类似 Claude Code 的 CLAUDE.md：
- 项目结构记忆（目录、文件、依赖关系）
- 编码规范（风格、约定）
- 已知问题与解决方案
- API 使用模式
- 架构决策记录

存储位置: <project>/.kimix/memory_bank.jsonl

运行方式:
    bank = MemoryBank("/path/to/project")
    bank.remember("api_pattern", "使用 Pydantic 模型验证所有输入")
    print(bank.recall("api_pattern"))
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """记忆条目"""
    key: str
    content: str
    category: str  # "pattern", "decision", "issue", "api", "style"
    created_at: float
    updated_at: float
    source: str = ""  # 来源（如 "agent", "user", "file"）
    confidence: float = 1.0  # 置信度 0-1


class MemoryBank:
    """项目记忆银行

    用法:
        bank = MemoryBank("/path/to/project")

        # 记录知识
        bank.remember("db_pattern", "所有查询使用参数化防止 SQL 注入", "pattern")
        bank.remember("auth_issue", "JWT 过期时间设置过短导致频繁重登", "issue")

        # 检索知识
        patterns = bank.recall_by_category("pattern")
        all_knowledge = bank.search("JWT")

        # 持久化（自动保存）
        bank.save()
    """

    BANK_DIR = ".kimix"
    BANK_FILE = "memory_bank.jsonl"

    def __init__(self, project_path: str | Path, auto_save: bool = True) -> None:
        """初始化记忆银行

        Args:
            project_path: 项目根目录
            auto_save: 修改后自动保存
        """
        self.project_path = Path(project_path).resolve()
        self.bank_dir = self.project_path / self.BANK_DIR
        self.bank_file = self.bank_dir / self.BANK_FILE
        self.auto_save = auto_save
        self._entries: dict[str, MemoryEntry] = {}

        # 加载已有记忆
        self._load()

    def _load(self) -> None:
        """从磁盘加载记忆"""
        if not self.bank_file.exists():
            return

        try:
            with open(self.bank_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    entry = MemoryEntry(
                        key=data["key"],
                        content=data["content"],
                        category=data.get("category", "general"),
                        created_at=data["created_at"],
                        updated_at=data["updated_at"],
                        source=data.get("source", ""),
                        confidence=data.get("confidence", 1.0),
                    )
                    self._entries[entry.key] = entry
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[MemoryBank] 加载记忆失败: {e}")

    def save(self) -> None:
        """保存记忆到磁盘"""
        self.bank_dir.mkdir(parents=True, exist_ok=True)

        # 写入 .gitignore（避免记忆进入版本控制）
        gitignore = self.bank_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")

        with open(self.bank_file, "w", encoding="utf-8") as f:
            for entry in self._entries.values():
                data = {
                    "key": entry.key,
                    "content": entry.content,
                    "category": entry.category,
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                    "source": entry.source,
                    "confidence": entry.confidence,
                }
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def remember(
        self,
        key: str,
        content: str,
        category: str = "general",
        source: str = "agent",
        confidence: float = 1.0,
    ) -> None:
        """记录记忆

        Args:
            key: 记忆键（如 "auth_pattern", "db_issue_001"）
            content: 记忆内容
            category: 类别（pattern/decision/issue/api/style）
            source: 来源
            confidence: 置信度
        """
        now = time.time()

        if key in self._entries:
            # 更新已有记忆
            existing = self._entries[key]
            existing.content = content
            existing.updated_at = now
            existing.confidence = max(existing.confidence, confidence)
        else:
            self._entries[key] = MemoryEntry(
                key=key,
                content=content,
                category=category,
                created_at=now,
                updated_at=now,
                source=source,
                confidence=confidence,
            )

        if self.auto_save:
            self.save()

    def recall(self, key: str) -> MemoryEntry | None:
        """按键检索记忆"""
        return self._entries.get(key)

    def recall_by_category(self, category: str) -> list[MemoryEntry]:
        """按类别检索记忆"""
        return [e for e in self._entries.values() if e.category == category]

    def search(self, query: str) -> list[MemoryEntry]:
        """关键词搜索记忆"""
        query_lower = query.lower()
        results = []
        for entry in self._entries.values():
            if (query_lower in entry.key.lower() or
                query_lower in entry.content.lower() or
                query_lower in entry.category.lower()):
                results.append(entry)
        # 按更新时间排序
        results.sort(key=lambda e: e.updated_at, reverse=True)
        return results

    def forget(self, key: str) -> bool:
        """删除记忆"""
        if key in self._entries:
            del self._entries[key]
            if self.auto_save:
                self.save()
            return True
        return False

    def get_summary(self) -> dict[str, Any]:
        """获取记忆摘要"""
        categories: dict[str, int] = {}
        for e in self._entries.values():
            categories[e.category] = categories.get(e.category, 0) + 1

        return {
            "project": str(self.project_path),
            "total_entries": len(self._entries),
            "categories": categories,
            "last_updated": max(
                (e.updated_at for e in self._entries.values()),
                default=0,
            ),
        }

    def generate_context_prompt(self, max_entries: int = 20) -> str:
        """生成用于注入 LLM 上下文的提示词

        返回格式化后的记忆文本，便于放在 system prompt 中。
        """
        if not self._entries:
            return ""

        # 按置信度和更新时间排序
        entries = sorted(
            self._entries.values(),
            key=lambda e: (e.confidence, e.updated_at),
            reverse=True,
        )[:max_entries]

        lines = ["## 项目记忆（来自历史会话）", ""]
        for e in entries:
            lines.append(f"### {e.key} [{e.category}]")
            lines.append(e.content)
            lines.append("")

        return "\n".join(lines)

    def to_tool_schema(self) -> dict[str, Any]:
        """工具注册表 schema"""
        return {
            "name": "memory_bank",
            "description": "持久化项目知识：记录编码规范、已知问题、API 用法等，跨会话保留",
            "functions": {
                "remember": "记录记忆（key, content, category）",
                "recall": "检索记忆（key）",
                "search": "搜索记忆（query）",
                "summary": "查看记忆摘要",
            },
        }


class ProjectAnalyzer:
    """项目结构分析器 — 自动生成初始记忆"""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)

    def analyze(self) -> dict[str, Any]:
        """分析项目结构，返回记忆条目字典"""
        memory: dict[str, str] = {}

        # 1. 检测技术栈
        if (self.project_path / "package.json").exists():
            memory["tech_stack"] = "Node.js / JavaScript 项目"
        elif (self.project_path / "requirements.txt").exists():
            memory["tech_stack"] = "Python 项目"
        elif (self.project_path / "Cargo.toml").exists():
            memory["tech_stack"] = "Rust 项目"
        elif (self.project_path / "go.mod").exists():
            memory["tech_stack"] = "Go 项目"

        # 2. 检测测试框架
        if (self.project_path / "pytest.ini").exists():
            memory["test_framework"] = "使用 pytest 进行测试"
        elif list(self.project_path.glob("**/*.test.js")):
            memory["test_framework"] = "使用 Jest 进行测试"

        # 3. 检测代码风格工具
        if (self.project_path / ".pre-commit-config.yaml").exists():
            memory["linting"] = "使用 pre-commit 进行代码检查"
        elif (self.project_path / "pyproject.toml").exists():
            memory["linting"] = "使用 pyproject.toml 管理工具配置"

        # 4. 目录结构概览
        top_dirs = [d.name for d in self.project_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        memory["project_structure"] = f"顶层目录: {', '.join(top_dirs[:10])}"

        return memory

    def init_memory_bank(self, bank: MemoryBank) -> None:
        """将分析结果写入记忆银行"""
        analysis = self.analyze()
        for key, content in analysis.items():
            bank.remember(key, content, category="project", source="analyzer")
