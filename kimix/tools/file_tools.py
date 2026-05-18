"""
文件操作工具集

提供8个文件操作工具，支持读取、写入、编辑、补丁、目录列表、
正则搜索、文件名搜索和文件信息查询。所有操作均在沙箱路径限制内进行。
"""

from __future__ import annotations

import asyncio
import fnmatch
import mimetypes
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult


# ---------------------------------------------------------------------------
# 路径安全检查辅助函数
# ---------------------------------------------------------------------------

def _resolve_path(file_path: str, context: ToolContext) -> Path:
    """将路径解析为绝对路径（基于 work_dir）"""
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(context.work_dir) / path
    return path.resolve()


def _check_sandbox(path: Path, context: ToolContext) -> None:
    """检查路径是否在沙箱允许范围内

    当 sandbox_enabled 为 True 时，目标路径必须在 work_dir 或
    allowed_paths 之一内。如果越界，抛出 PermissionError。
    """
    if not context.sandbox_enabled:
        return

    allowed = [Path(context.work_dir).resolve()]
    for p in context.allowed_paths:
        allowed.append(Path(p).resolve())

    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        # 无法解析的路径视为越界
        raise PermissionError(f"路径无法解析: {path}")

    for base in allowed:
        try:
            resolved.relative_to(base)
            return
        except ValueError:
            continue

    raise PermissionError(
        f"路径越界: {resolved} 不在允许的沙箱路径内 ({[str(b) for b in allowed]})"
    )


def _safe_resolve(file_path: str, context: ToolContext) -> Path:
    """安全解析路径：先解析为绝对路径，再检查沙箱"""
    path = _resolve_path(file_path, context)
    _check_sandbox(path, context)
    return path


# ---------------------------------------------------------------------------
# 1. ReadFileTool
# ---------------------------------------------------------------------------


class ReadFileTool(AbstractTool):
    """读取文件内容

    支持 UTF-8 文本文件和 PDF 文件（自动转换为文本）。
    对于二进制文件，返回文件类型和大小信息。
    """

    name = "file_read"
    description = "读取指定文件的内容。支持文本文件（UTF-8）和PDF文件（自动转换）。对于超过最大行数的文件，支持偏移读取。"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要读取的文件路径（相对 work_dir 或绝对路径）",
            },
            "offset": {
                "type": "integer",
                "description": "起始行号（1-based），默认从第1行开始",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "最多读取行数，默认1000行",
                "default": 1000,
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = params["file_path"]
        offset = params.get("offset", 1)
        limit = params.get("limit", 1000)

        try:
            path = _safe_resolve(file_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not path.exists():
            return ToolResult.fail(f"文件不存在: {path}")
        if not path.is_file():
            return ToolResult.fail(f"不是文件: {path}")

        # 检测文件类型
        mime, _ = mimetypes.guess_type(str(path))

        # PDF 处理
        if mime == "application/pdf" or path.suffix.lower() == ".pdf":
            return await self._read_pdf(path)

        # 二进制文件检测
        try:
            with open(path, "rb") as f:
                raw = f.read(4096)
                if b"\x00" in raw:
                    # 二进制文件
                    size = path.stat().st_size
                    return ToolResult.ok(
                        f"[二进制文件] {path.name}\n"
                        f"大小: {size:,} 字节\n"
                        f"类型: {mime or 'unknown'}",
                        file_path=str(path),
                        file_type="binary",
                        file_size=size,
                    )
        except OSError as exc:
            return ToolResult.fail(f"读取文件失败: {exc}")

        # 文本文件读取
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 尝试其他编码
            for enc in ["gbk", "gb2312", "latin-1"]:
                try:
                    content = path.read_text(encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return ToolResult.fail(f"无法解码文件（尝试了 utf-8/gbk/gb2312/latin-1）: {path}")
        except OSError as exc:
            return ToolResult.fail(f"读取文件失败: {exc}")

        lines = content.split("\n")
        total_lines = len(lines)

        # 应用 offset/limit
        start = max(0, offset - 1)
        end = min(total_lines, start + limit)
        selected = lines[start:end]

        # 添加行号
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:6d}\t{line}")

        header = f"# 文件: {path}\n"
        if total_lines > limit:
            header += f"# 显示 {start + 1}-{end} / 共 {total_lines} 行\n"
        header += "#" * 60 + "\n"

        return ToolResult.ok(
            header + "\n".join(numbered),
            file_path=str(path),
            total_lines=total_lines,
            shown_start=start + 1,
            shown_end=end,
            file_type="text",
        )

    async def _read_pdf(self, path: Path) -> ToolResult:
        """尝试使用外部工具转换 PDF 为文本"""
        # 先尝试 pdftotext
        try:
            result = subprocess.run(
                ["pdftotext", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return ToolResult.ok(
                    result.stdout,
                    file_path=str(path),
                    file_type="pdf",
                    converter="pdftotext",
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 尝试 pdfplumber
        try:
            import pdfplumber  # type: ignore[import-untyped]

            text_parts = []
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"--- 第 {i + 1} 页 ---\n{page_text}")
            return ToolResult.ok(
                "\n\n".join(text_parts),
                file_path=str(path),
                file_type="pdf",
                converter="pdfplumber",
                total_pages=len(pdf.pages),
            )
        except ImportError:
            pass
        except Exception as exc:
            return ToolResult.fail(f"PDF 解析失败: {exc}")

        return ToolResult.fail(
            "PDF 解析需要安装额外依赖: pip install pdfplumber "
            "或安装系统工具 pdftotext (poppler-utils)"
        )


# ---------------------------------------------------------------------------
# 2. WriteFileTool
# ---------------------------------------------------------------------------


class WriteFileTool(AbstractTool):
    """写入文件内容"""

    name = "file_write"
    description = "将内容写入指定文件。如果文件已存在则覆盖（破坏性操作）。自动创建不存在的父目录。"
    approval_required = ApprovalLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "目标文件路径（相对 work_dir 或绝对路径）",
            },
            "content": {
                "type": "string",
                "description": "要写入的文本内容",
            },
            "append": {
                "type": "boolean",
                "description": "是否追加模式，默认 false（覆盖）",
                "default": False,
            },
        },
        "required": ["file_path", "content"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = params["file_path"]
        content = params["content"]
        append = params.get("append", False)

        try:
            path = _safe_resolve(file_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        # 安全检查：禁止写入到已存在的目录
        if path.exists() and path.is_dir():
            return ToolResult.fail(f"目标路径是目录，不能写入: {path}")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)

            written = len(content.encode("utf-8"))
            action = "追加" if append else "写入"
            return ToolResult.ok(
                f"{action}成功: {path} ({written:,} 字节)",
                file_path=str(path),
                bytes_written=written,
                append=append,
            )
        except OSError as exc:
            return ToolResult.fail(f"写入文件失败: {exc}")


# ---------------------------------------------------------------------------
# 3. EditFileTool
# ---------------------------------------------------------------------------


class EditFileTool(AbstractTool):
    """编辑文件（搜索替换）"""

    name = "file_edit"
    description = (
        "在文件中搜索指定内容并替换为新内容。支持普通字符串匹配和正则表达式。"
        "如果 old_string 不存在则返回错误。"
    )
    approval_required = ApprovalLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要编辑的文件路径",
            },
            "old_string": {
                "type": "string",
                "description": "要搜索的原始字符串",
            },
            "new_string": {
                "type": "string",
                "description": "替换后的新字符串",
            },
            "use_regex": {
                "type": "boolean",
                "description": "是否使用正则表达式匹配，默认 false",
                "default": False,
            },
            "replace_all": {
                "type": "boolean",
                "description": "是否替换所有匹配项，默认 false（仅替换第一个）",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = params["file_path"]
        old_string = params["old_string"]
        new_string = params["new_string"]
        use_regex = params.get("use_regex", False)
        replace_all = params.get("replace_all", False)

        try:
            path = _safe_resolve(file_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not path.exists():
            return ToolResult.fail(f"文件不存在: {path}")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult.fail(f"读取文件失败: {exc}")

        original = content
        flags = 0 if use_regex else re.escape(old_string)

        try:
            if use_regex:
                if replace_all:
                    new_content, count = re.subn(old_string, new_string, content)
                else:
                    new_content, count = re.subn(
                        old_string, new_string, content, count=1
                    )
            else:
                if replace_all:
                    new_content = content.replace(old_string, new_string)
                    count = original.count(old_string)
                else:
                    new_content = content.replace(old_string, new_string, 1)
                    count = 1 if old_string in content else 0
        except re.error as exc:
            return ToolResult.fail(f"正则表达式错误: {exc}")

        if count == 0:
            return ToolResult.fail(
                f"未找到匹配内容: {old_string!r}\n"
                f"提示：文件内容前200字符:\n{content[:200]!r}"
            )

        # 写入修改后的内容
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            return ToolResult.fail(f"写入文件失败: {exc}")

        return ToolResult.ok(
            f"编辑成功: {path}\n替换了 {count} 处",
            file_path=str(path),
            replacements=count,
            old_length=len(original),
            new_length=len(new_content),
        )


# ---------------------------------------------------------------------------
# 4. ApplyPatchTool
# ---------------------------------------------------------------------------


class ApplyPatchTool(AbstractTool):
    """应用 unified diff 补丁"""

    name = "file_patch"
    description = "对文件应用 unified diff 格式的补丁。支持标准 diff/patch 格式，类似于 git diff 的输出。"
    approval_required = ApprovalLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": "unified diff 格式的补丁内容（以 --- 开头）",
            },
            "file_path": {
                "type": "string",
                "description": "可选，如果补丁中没有文件路径则使用此路径",
                "default": "",
            },
        },
        "required": ["patch"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        patch_content = params["patch"]
        file_path_override = params.get("file_path", "")

        # 尝试用 python-patch 库
        try:
            import patch_ng

            from io import BytesIO

            patch_obj = patch_ng.PatchSet(
                BytesIO(patch_content.encode("utf-8")),
            )
            # patch_ng 需要基于工作目录应用
            work_dir = Path(context.work_dir).resolve()
            success = patch_obj.apply(root=work_dir)
            if success:
                return ToolResult.ok(
                    f"补丁应用成功，涉及 {len(patch_obj)} 个文件",
                    files_affected=len(patch_obj),
                )
            else:
                return ToolResult.fail("补丁应用失败（部分文件无法匹配）")
        except ImportError:
            pass

        # 备用：使用系统 patch 命令
        try:
            proc = await asyncio.create_subprocess_exec(
                "patch",
                "-p0",
                "--dry-run",
                "-i",
                "-",
                cwd=context.work_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(patch_content.encode("utf-8")),
                timeout=30,
            )
            if proc.returncode != 0:
                return ToolResult.fail(
                    f"补丁预检查失败:\n{stderr.decode('utf-8', errors='replace')}"
                )

            # 正式应用
            proc = await asyncio.create_subprocess_exec(
                "patch",
                "-p0",
                "-i",
                "-",
                cwd=context.work_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(patch_content.encode("utf-8")),
                timeout=30,
            )
            if proc.returncode == 0:
                return ToolResult.ok(
                    f"补丁应用成功:\n{stdout.decode('utf-8', errors='replace')}",
                )
            else:
                return ToolResult.fail(
                    f"补丁应用失败:\n{stderr.decode('utf-8', errors='replace')}"
                )
        except FileNotFoundError:
            pass
        except asyncio.TimeoutError:
            return ToolResult.fail("补丁应用超时")

        # 最简实现：手动解析 unified diff 并应用
        return await self._apply_manual_patch(patch_content, context, file_path_override)

    async def _apply_manual_patch(
        self,
        patch: str,
        context: ToolContext,
        file_path_override: str,
    ) -> ToolResult:
        """手动解析并应用简单的 unified diff 补丁"""
        lines = patch.split("\n")
        if not lines or not lines[0].startswith("---"):
            return ToolResult.fail("不支持的补丁格式，需要 unified diff（以 --- 开头）")

        # 解析补丁头
        old_file = lines[0][4:].split("\t")[0].strip()
        new_file = lines[1][4:].split("\t")[0].strip() if len(lines) > 1 else old_file

        target_file = file_path_override or new_file or old_file
        if not target_file:
            return ToolResult.fail("无法确定目标文件路径，请提供 file_path 参数")

        try:
            path = _safe_resolve(target_file, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not path.exists():
            return ToolResult.fail(f"目标文件不存在: {path}")

        try:
            original_content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult.fail(f"读取文件失败: {exc}")

        # 提取 hunk 内容（简化版：找到 @@ 行并解析上下文）
        # 这是一个简化实现，仅处理单 hunk、无模糊匹配的情况
        try:
            # 找到第一个 @@ 行后的内容
            hunk_start = None
            for i, line in enumerate(lines):
                if line.startswith("@@"):
                    hunk_start = i
                    break

            if hunk_start is None:
                return ToolResult.fail("补丁中没有找到 @@ hunk 标记")

            # 构建新内容
            new_lines = []
            i = hunk_start + 1
            while i < len(lines):
                line = lines[i]
                if line.startswith("@@"):
                    # 新 hunk —— 简化处理：跳过
                    i += 1
                    continue
                elif line.startswith("+"):
                    new_lines.append(line[1:])
                elif line.startswith("-"):
                    # 删除行 —— 跳过
                    pass
                elif line.startswith("\\"):
                    # "\ No newline at end of file" —— 跳过
                    pass
                elif line.startswith("---") or line.startswith("+++"):
                    pass
                else:
                    # 上下文行（空格开头或无标记）
                    if line.startswith(" "):
                        new_lines.append(line[1:])
                    elif line:
                        new_lines.append(line)
                i += 1

            new_content = "\n".join(new_lines)
            path.write_text(new_content, encoding="utf-8")
            return ToolResult.ok(
                f"补丁已手动应用到: {path}",
                file_path=str(path),
            )

        except Exception as exc:
            return ToolResult.fail(f"手动应用补丁失败: {exc}")


# ---------------------------------------------------------------------------
# 5. ListDirTool
# ---------------------------------------------------------------------------


class ListDirTool(AbstractTool):
    """列出目录内容（gitignore-aware）"""

    name = "dir_list"
    description = "列出指定目录下的文件和子目录。支持递归列出，遵守 .gitignore 规则。"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "dir_path": {
                "type": "string",
                "description": "目录路径，默认当前工作目录",
                "default": ".",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归列出子目录内容，默认 false",
                "default": False,
            },
            "show_hidden": {
                "type": "boolean",
                "description": "是否显示隐藏文件（以.开头的），默认 false",
                "default": False,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        dir_path = params.get("dir_path", ".")
        recursive = params.get("recursive", False)
        show_hidden = params.get("show_hidden", False)

        try:
            path = _safe_resolve(dir_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not path.exists():
            return ToolResult.fail(f"目录不存在: {path}")
        if not path.is_dir():
            return ToolResult.fail(f"不是目录: {path}")

        # 加载 gitignore 规则
        gitignore_patterns = self._load_gitignore(path)

        try:
            entries = self._list_directory(
                path, recursive, show_hidden, gitignore_patterns, path
            )
        except OSError as exc:
            return ToolResult.fail(f"列出目录失败: {exc}")

        if not entries:
            return ToolResult.ok(f"目录为空: {path}")

        return ToolResult.ok(
            "\n".join(entries),
            dir_path=str(path),
            entry_count=len(entries),
        )

    def _load_gitignore(self, root: Path) -> list[str]:
        """加载目录下的 .gitignore 规则（简化版）"""
        patterns = []
        gitignore_file = root / ".gitignore"
        if gitignore_file.exists():
            try:
                content = gitignore_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
            except OSError:
                pass
        # 始终忽略 .git 目录
        patterns.append(".git/")
        patterns.append(".git")
        return patterns

    def _is_ignored(self, rel_path: str, patterns: list[str]) -> bool:
        """检查路径是否被 gitignore 忽略"""
        for pattern in patterns:
            # 简单匹配
            if pattern.endswith("/"):
                # 目录匹配
                if fnmatch.fnmatch(rel_path + "/", pattern) or fnmatch.fnmatch(
                    rel_path, pattern.rstrip("/")
                ):
                    return True
            else:
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(
                    rel_path, "*/" + pattern
                ):
                    return True
        return False

    def _list_directory(
        self,
        path: Path,
        recursive: bool,
        show_hidden: bool,
        gitignore_patterns: list[str],
        root: Path,
    ) -> list[str]:
        """递归列出目录内容"""
        entries = []

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return [f"[权限拒绝] {path}"]

        for item in items:
            rel = item.relative_to(root)
            rel_str = str(rel).replace("\\", "/")

            # 隐藏文件过滤
            if not show_hidden and item.name.startswith("."):
                continue

            # gitignore 过滤
            if gitignore_patterns and self._is_ignored(rel_str, gitignore_patterns):
                continue

            if item.is_dir():
                entries.append(f"📁 {rel_str}/")
                if recursive:
                    sub_entries = self._list_directory(
                        item, True, show_hidden, gitignore_patterns, root
                    )
                    entries.extend(f"  {e}" for e in sub_entries)
            else:
                size = item.stat().st_size
                size_str = self._format_size(size)
                entries.append(f"📄 {rel_str} ({size_str})")

        return entries

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# 6. GrepFilesTool
# ---------------------------------------------------------------------------


class GrepFilesTool(AbstractTool):
    """正则搜索文件内容"""

    name = "file_grep"
    description = "在指定路径下使用正则表达式搜索文件内容。支持按文件扩展名过滤。"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "正则表达式搜索模式",
            },
            "path": {
                "type": "string",
                "description": "搜索路径，默认工作目录",
                "default": ".",
            },
            "file_pattern": {
                "type": "string",
                "description": "文件名匹配模式，如 *.py",
                "default": "",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归搜索子目录，默认 true",
                "default": True,
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数，默认 50",
                "default": 50,
            },
        },
        "required": ["pattern"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        pattern = params["pattern"]
        search_path = params.get("path", ".")
        file_pattern = params.get("file_pattern", "")
        recursive = params.get("recursive", True)
        max_results = params.get("max_results", 50)

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult.fail(f"正则表达式错误: {exc}")

        try:
            root = _safe_resolve(search_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not root.exists():
            return ToolResult.fail(f"路径不存在: {root}")

        results: list[str] = []
        files_searched = 0
        total_matches = 0

        try:
            if root.is_file():
                files = [root]
            else:
                if recursive:
                    files = [
                        p
                        for p in root.rglob("*")
                        if p.is_file()
                        and not p.name.startswith(".")
                        and ".git" not in p.parts
                    ]
                else:
                    files = [
                        p
                        for p in root.iterdir()
                        if p.is_file() and not p.name.startswith(".")
                    ]

            # 文件名过滤
            if file_pattern:
                files = [f for f in files if fnmatch.fnmatch(f.name, file_pattern)]

            for file_path in files:
                if len(results) >= max_results:
                    break

                files_searched += 1

                # 跳过二进制文件
                try:
                    with open(file_path, "rb") as f:
                        sample = f.read(2048)
                        if b"\x00" in sample:
                            continue
                except OSError:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                lines = content.split("\n")
                for line_no, line in enumerate(lines, 1):
                    if regex.search(line):
                        total_matches += 1
                        rel_path = file_path
                        if root.is_dir():
                            try:
                                rel_path = file_path.relative_to(root)
                            except ValueError:
                                pass
                        results.append(
                            f"{rel_path}:{line_no}\t{line.strip()[:200]}"
                        )
                        if len(results) >= max_results:
                            break

        except OSError as exc:
            return ToolResult.fail(f"搜索过程中出错: {exc}")

        if not results:
            return ToolResult.ok(
                f"未找到匹配 '{pattern}' 的结果\n"
                f"（搜索了 {files_searched} 个文件）"
            )

        header = f"# 搜索: {pattern}\n# 路径: {root}\n# 结果: {total_matches} 处匹配"
        if total_matches > max_results:
            header += f"（显示前 {max_results} 条）"
        header += "\n" + "#" * 60 + "\n"

        return ToolResult.ok(
            header + "\n".join(results),
            pattern=pattern,
            total_matches=total_matches,
            files_searched=files_searched,
        )


# ---------------------------------------------------------------------------
# 7. FileSearchTool
# ---------------------------------------------------------------------------


class FileSearchTool(AbstractTool):
    """模糊搜索文件名"""

    name = "file_search"
    description = "根据名称模糊搜索文件或目录。支持通配符和大小写不敏感匹配。"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词（支持 * 和 ? 通配符）",
            },
            "path": {
                "type": "string",
                "description": "搜索路径，默认工作目录",
                "default": ".",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归搜索，默认 true",
                "default": True,
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数，默认 30",
                "default": 30,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        query = params["query"]
        search_path = params.get("path", ".")
        recursive = params.get("recursive", True)
        max_results = params.get("max_results", 30)

        try:
            root = _safe_resolve(search_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not root.exists():
            return ToolResult.fail(f"路径不存在: {root}")

        # 转换查询为正则表达式
        regex_pattern = fnmatch.translate(query)
        try:
            regex = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as exc:
            return ToolResult.fail(f"搜索模式错误: {exc}")

        results: list[str] = []

        try:
            if root.is_file():
                paths = [root]
            else:
                if recursive:
                    paths = list(root.rglob("*"))
                else:
                    paths = list(root.iterdir())

            for p in paths:
                if ".git" in p.parts:
                    continue
                if regex.search(p.name):
                    try:
                        rel = p.relative_to(root) if root.is_dir() else p.name
                    except ValueError:
                        rel = p.name
                    marker = "📁" if p.is_dir() else "📄"
                    results.append(f"{marker} {rel}")
                    if len(results) >= max_results:
                        break

        except OSError as exc:
            return ToolResult.fail(f"搜索过程中出错: {exc}")

        if not results:
            return ToolResult.ok(
                f"未找到匹配 '{query}' 的文件或目录"
            )

        header = f"# 文件名搜索: {query}\n# 路径: {root}\n"
        header += "#" * 60 + "\n"

        return ToolResult.ok(
            header + "\n".join(results),
            query=query,
            match_count=len(results),
        )


# ---------------------------------------------------------------------------
# 8. GetFileInfoTool
# ---------------------------------------------------------------------------


class GetFileInfoTool(AbstractTool):
    """获取文件信息"""

    name = "file_info"
    description = "获取文件或目录的详细信息：大小、修改时间、权限、类型等。"
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件或目录路径",
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = params["file_path"]

        try:
            path = _safe_resolve(file_path, context)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))

        if not path.exists():
            return ToolResult.fail(f"路径不存在: {path}")

        try:
            stat = path.stat()
            mime, _ = mimetypes.guess_type(str(path))

            info_lines = [
                f"路径: {path}",
                f"类型: {'目录' if path.is_dir() else '文件'}",
                f"大小: {self._format_size(stat.st_size)}",
                f"权限: {oct(stat.st_mode)[-3:]}",
                f"修改时间: {datetime.fromtimestamp(stat.st_mtime).isoformat()}",
                f"访问时间: {datetime.fromtimestamp(stat.st_atime).isoformat()}",
                f"创建时间: {datetime.fromtimestamp(stat.st_ctime).isoformat()}",
                f"MIME类型: {mime or 'unknown'}",
            ]

            if path.is_file():
                # 尝试统计行数
                try:
                    content = path.read_text(encoding="utf-8")
                    lines = content.count("\n") + 1
                    info_lines.append(f"行数: {lines}")
                except (OSError, UnicodeDecodeError):
                    pass

            return ToolResult.ok(
                "\n".join(info_lines),
                file_path=str(path),
                size=stat.st_size,
                mtime=stat.st_mtime,
                mime=mime,
            )

        except OSError as exc:
            return ToolResult.fail(f"获取文件信息失败: {exc}")

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
