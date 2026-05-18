"""
Git 工具集

提供4个Git操作工具：状态查看、差异比较、日志查询和分支列表。
使用 GitPython 库进行 Git 操作，自动检测 Git 仓库。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Git 操作辅助函数
# ---------------------------------------------------------------------------

def _get_repo(path: str):
    """获取 Git 仓库对象

    Args:
        path: 文件系统路径，会在该路径及其父目录中查找 .git

    Returns:
        Repo 对象

    Raises:
        ImportError: 未安装 GitPython
        ValueError: 路径不是 Git 仓库
    """
    try:
        import git
        from git.exc import InvalidGitRepositoryError
    except ImportError:
        raise ImportError(
            "Git 工具需要 GitPython 库: pip install GitPython"
        )

    search_path = Path(path).resolve()
    try:
        repo = git.Repo(search_path, search_parent_directories=True)
        return repo
    except InvalidGitRepositoryError:
        return None
    except Exception:
        return None


def _get_repo_root(context: ToolContext) -> str:
    """从上下文中获取 Git 仓库根目录"""
    return context.work_dir


# ---------------------------------------------------------------------------
# 1. GitStatusTool
# ---------------------------------------------------------------------------


class GitStatusTool(AbstractTool):
    """查看 Git 仓库状态"""

    name = "git_status"
    description = (
        "查看 Git 仓库的当前状态，包括已修改、已暂存、未跟踪的文件。"
        "自动在当前 work_dir 及其父目录中查找 Git 仓库。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "short": {
                "type": "boolean",
                "description": "是否使用简洁格式，默认 true",
                "default": True,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        short = params.get("short", True)

        try:
            repo = _get_repo(context.work_dir)
        except ImportError as exc:
            return ToolResult.fail(str(exc))
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            if short:
                # 简洁格式
                result = repo.git.status("-s")
                if not result.strip():
                    return ToolResult.ok(
                        "工作目录干净，没有未提交的更改",
                        repo_path=repo.working_dir,
                        branch=repo.active_branch.name,
                    )
                return ToolResult.ok(
                    f"# Git 状态 ({repo.active_branch.name})\n{result}",
                    repo_path=repo.working_dir,
                    branch=repo.active_branch.name,
                )
            else:
                # 详细格式
                result = repo.git.status()
                return ToolResult.ok(
                    f"# Git 状态\n{result}",
                    repo_path=repo.working_dir,
                    branch=repo.active_branch.name,
                )

        except Exception as exc:
            return ToolResult.fail(f"获取 Git 状态失败: {exc}")


# ---------------------------------------------------------------------------
# 2. GitDiffTool
# ---------------------------------------------------------------------------


class GitDiffTool(AbstractTool):
    """查看 Git 差异"""

    name = "git_diff"
    description = (
        "查看 Git 仓库中的代码差异。支持工作区差异（未暂存）、"
        "暂存区差异（已 add 未 commit）、以及指定提交的差异。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "查看已暂存（staged）的更改，默认 false（查看工作区更改）",
                "default": False,
            },
            "file_path": {
                "type": "string",
                "description": "可选，仅查看指定文件的差异",
                "default": "",
            },
            "commit": {
                "type": "string",
                "description": "可选，查看指定提交的差异（如 HEAD~1）",
                "default": "",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        staged = params.get("staged", False)
        file_path = params.get("file_path", "")
        commit = params.get("commit", "")

        try:
            repo = _get_repo(context.work_dir)
        except ImportError as exc:
            return ToolResult.fail(str(exc))
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            args = []

            if staged:
                args.append("--staged")
            elif commit:
                args.append(commit)

            if file_path:
                # 检查文件路径沙箱
                from .file_tools import _safe_resolve
                resolved = _safe_resolve(file_path, context)
                args.append(str(resolved))

            result = repo.git.diff(*args)

            if not result.strip():
                header = "没有差异"
                if staged:
                    header = "暂存区没有更改"
                elif commit:
                    header = f"提交 {commit} 没有差异"
                else:
                    header = "工作区没有未暂存的更改"
                return ToolResult.ok(
                    header,
                    repo_path=repo.working_dir,
                )

            header = f"# Git Diff"
            if staged:
                header += " (staged)"
            elif commit:
                header += f" ({commit})"
            header += f"\n# 仓库: {repo.working_dir}\n"
            header += "#" * 60 + "\n"

            return ToolResult.ok(
                header + result,
                repo_path=repo.working_dir,
            )

        except Exception as exc:
            return ToolResult.fail(f"获取 Git diff 失败: {exc}")


# ---------------------------------------------------------------------------
# 3. GitLogTool
# ---------------------------------------------------------------------------


class GitLogTool(AbstractTool):
    """查看 Git 提交日志"""

    name = "git_log"
    description = (
        "查看 Git 仓库的提交历史。支持指定显示的条目数量、"
        "格式化输出和过滤作者等。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "n": {
                "type": "integer",
                "description": "显示的最近提交数，默认 10",
                "default": 10,
            },
            "file_path": {
                "type": "string",
                "description": "可选，仅查看指定文件的提交历史",
                "default": "",
            },
            "oneline": {
                "type": "boolean",
                "description": "是否使用简洁的单行格式，默认 true",
                "default": True,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        n = params.get("n", 10)
        file_path = params.get("file_path", "")
        oneline = params.get("oneline", True)

        try:
            repo = _get_repo(context.work_dir)
        except ImportError as exc:
            return ToolResult.fail(str(exc))
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            args = [f"-{n}"]

            if oneline:
                args.append("--oneline")
            else:
                # 详细格式：包含作者和日期
                args.append("--format=%h %an %ad %s")
                args.append("--date=short")

            if file_path:
                from .file_tools import _safe_resolve
                resolved = _safe_resolve(file_path, context)
                args.append("--")
                args.append(str(resolved))

            result = repo.git.log(*args)

            if not result.strip():
                return ToolResult.ok("没有提交历史")

            header = f"# Git Log (最近 {n} 条)\n"
            header += f"# 分支: {repo.active_branch.name}\n"
            header += f"# 仓库: {repo.working_dir}\n"
            header += "#" * 60 + "\n"

            return ToolResult.ok(
                header + result,
                repo_path=repo.working_dir,
                branch=repo.active_branch.name,
                count=n,
            )

        except Exception as exc:
            return ToolResult.fail(f"获取 Git log 失败: {exc}")


# ---------------------------------------------------------------------------
# 4. GitBranchTool
# ---------------------------------------------------------------------------


class GitBranchTool(AbstractTool):
    """查看 Git 分支列表"""

    name = "git_branch"
    description = (
        "列出 Git 仓库的所有分支，并标注当前活动分支。"
        "支持显示本地分支和远程分支。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "all": {
                "type": "boolean",
                "description": "是否显示远程分支，默认 true",
                "default": True,
            },
        },
        "required": [],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        show_all = params.get("all", True)

        try:
            repo = _get_repo(context.work_dir)
        except ImportError as exc:
            return ToolResult.fail(str(exc))
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            lines = []

            # 当前分支
            current = repo.active_branch.name
            lines.append(f"当前分支: {current}")
            lines.append("")

            # 本地分支
            local_branches = [b.name for b in repo.branches]
            lines.append("本地分支:")
            for b in sorted(local_branches):
                marker = " * " if b == current else "   "
                lines.append(f"{marker}{b}")

            # 远程分支
            if show_all:
                lines.append("")
                lines.append("远程分支:")
                for ref in repo.remotes.origin.refs if hasattr(repo, "remotes") and repo.remotes else []:
                    lines.append(f"   {ref.name}")

            # 最近提交
            try:
                latest = repo.head.commit
                lines.append("")
                lines.append(f"最新提交: {latest.hexsha[:8]} {latest.message.strip()}")
            except Exception:
                pass

            return ToolResult.ok(
                "\n".join(lines),
                repo_path=repo.working_dir,
                current_branch=current,
            )

        except Exception as exc:
            return ToolResult.fail(f"获取 Git 分支列表失败: {exc}")
