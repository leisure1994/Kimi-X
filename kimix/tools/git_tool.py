"""
Git 工作流工具

Agent 可调用：
- git_status: 查看仓库状态
- git_diff: 查看修改内容
- git_commit: 提交修改（带信息）
- git_push: 推送到远程
- git_log: 查看提交历史
- git_branch: 查看/创建分支
- git_checkout: 切换分支
- git_stash: 暂存修改

所有操作返回结构化结果，便于 Agent 解析和决策。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GitResult:
    """Git 操作结果"""
    success: bool
    stdout: str
    stderr: str
    returncode: int
    files_changed: list[str] = field(default_factory=list)
    branch: str | None = None


class GitTool:
    """Git 工作流工具集

    用法:
        git = GitTool("/path/to/repo")
        status = git.status()
        if status.files_changed:
            git.commit("修复 bug #123")
            git.push()
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()

    def _run(self, *args: str) -> GitResult:
        """执行 git 命令"""
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30,
            )
            return GitResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired as e:
            return GitResult(
                success=False,
                stdout=e.stdout or "",
                stderr="[TIMEOUT] Git 操作超时",
                returncode=-9,
            )
        except FileNotFoundError:
            return GitResult(
                success=False,
                stdout="",
                stderr="git 命令未找到，请安装 Git",
                returncode=-1,
            )

    def status(self) -> GitResult:
        """查看仓库状态"""
        r = self._run("status", "--short")
        r.files_changed = [line[3:] for line in r.stdout.strip().split("\n") if line.strip()]
        return r

    def diff(self, staged: bool = False, file: str | None = None) -> GitResult:
        """查看修改内容

        Args:
            staged: 查看已暂存的修改
            file: 指定文件（可选）
        """
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file:
            args.append(file)
        return self._run(*args)

    def add(self, path: str = ".") -> GitResult:
        """暂存修改

        Args:
            path: 文件路径（默认全部）
        """
        return self._run("add", path)

    def commit(self, message: str, allow_empty: bool = False) -> GitResult:
        """提交修改

        Args:
            message: 提交信息
            allow_empty: 允许空提交
        """
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        return self._run(*args)

    def push(self, remote: str = "origin", branch: str | None = None) -> GitResult:
        """推送到远程

        Args:
            remote: 远程名
            branch: 分支名（默认当前分支）
        """
        args = ["push", remote]
        if branch:
            args.append(branch)
        return self._run(*args)

    def log(self, n: int = 10, oneline: bool = True) -> GitResult:
        """查看提交历史

        Args:
            n: 显示条数
            oneline: 单行格式
        """
        args = ["log", f"-{n}"]
        if oneline:
            args.append("--oneline")
        return self._run(*args)

    def branch_list(self) -> GitResult:
        """列出分支"""
        r = self._run("branch", "--list", "--format=%(refname:short)")
        r.files_changed = [line.strip() for line in r.stdout.split("\n") if line.strip()]
        return r

    def branch_create(self, name: str, checkout: bool = False) -> GitResult:
        """创建分支

        Args:
            name: 分支名
            checkout: 创建后切换
        """
        args = ["checkout", "-b", name] if checkout else ["branch", name]
        return self._run(*args)

    def checkout(self, branch: str) -> GitResult:
        """切换分支"""
        return self._run("checkout", branch)

    def stash(self, message: str | None = None) -> GitResult:
        """暂存当前修改"""
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        return self._run(*args)

    def stash_pop(self) -> GitResult:
        """恢复暂存"""
        return self._run("stash", "pop")

    def pull(self, remote: str = "origin", branch: str | None = None) -> GitResult:
        """拉取远程更新"""
        args = ["pull", remote]
        if branch:
            args.append(branch)
        return self._run(*args)

    def clone(self, url: str, dest: str | None = None) -> GitResult:
        """克隆仓库（在 repo_path 父目录执行）"""
        args = ["clone", url]
        if dest:
            args.append(dest)
        try:
            result = subprocess.run(
                ["git", *args],
                capture_output=True,
                text=True,
                cwd=self.repo_path.parent,
                timeout=120,
            )
            return GitResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired as e:
            return GitResult(
                success=False,
                stdout=e.stdout or "",
                stderr="[TIMEOUT] 克隆超时",
                returncode=-9,
            )

    # ── 工具接口（Agent 可调用） ──

    def to_tool_schema(self) -> dict[str, Any]:
        """返回工具注册表用的 schema"""
        return {
            "name": "git",
            "description": "Git 版本控制操作：查看状态、diff、提交、推送、分支管理等",
            "functions": {
                "status": "查看仓库状态，返回修改的文件列表",
                "diff": "查看修改内容，可选 staged/file 参数",
                "add": "暂存修改，默认全部",
                "commit": "提交修改，需要 message",
                "push": "推送到远程",
                "log": "查看提交历史",
                "branch_list": "列出分支",
                "branch_create": "创建分支",
                "checkout": "切换分支",
                "stash": "暂存当前修改",
                "stash_pop": "恢复暂存",
                "pull": "拉取远程更新",
                "clone": "克隆仓库",
            },
        }
