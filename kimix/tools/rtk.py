"""
RTK (Reduce Token Kit) — Token 压缩与命令重写系统

自动压缩终端命令输出，减少 60-90% Token 消耗。
核心能力：
- ls: 精简目录树（节省 80%）
- git status: 压缩 git 输出（节省 80%）
- git diff: 精简 diff（节省 75%）
- cargo test: 只显示失败项（节省 90%）
- read/cat: 自动去注释+空行

集成到 Agent 的 shell 调用层，自动前缀 rtk。
"""

from __future__ import annotations

import re
from typing import Any


class RTKCompressor:
    """RTK Token 压缩器

    模拟 rtk 命令的行为，在 Python 中实现核心压缩逻辑。
    可以集成到 Agent 的 shell 调用层。

    使用方式:
        compressor = RTKCompressor()
        # 压缩 ls 输出
        compressed = compressor.compress_ls(original_output)
        # 压缩 git diff
        compressed = compressor.compress_git_diff(diff_output)
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.stats = {
            "total_input": 0,
            "total_output": 0,
            "commands": {},
        }

    # ── 主压缩接口 ──

    def compress(self, command: str, output: str) -> str:
        """根据命令类型自动选择压缩策略

        Args:
            command: 原始命令（如 "ls -la", "git status"）
            output: 命令输出

        Returns:
            压缩后的输出
        """
        if not self.enabled or not output:
            return output

        self.stats["total_input"] += len(output)

        # 解析命令名
        cmd_name = command.strip().split()[0] if command.strip() else ""

        # 选择压缩策略
        compressed = output
        if cmd_name == "ls":
            compressed = self.compress_ls(output)
        elif cmd_name == "git":
            git_subcmd = command.strip().split()[1] if len(command.strip().split()) > 1 else ""
            if git_subcmd == "status":
                compressed = self.compress_git_status(output)
            elif git_subcmd == "diff":
                compressed = self.compress_git_diff(output)
            elif git_subcmd == "log":
                compressed = self.compress_git_log(output)
        elif cmd_name in ("cat", "read"):
            compressed = self.compress_read(output)
        elif cmd_name in ("pytest", "cargo", "npm", "go"):
            compressed = self.compress_test_output(output)
        elif cmd_name in ("find", "grep"):
            compressed = self.compress_find(output)
        else:
            # 通用压缩：去除多余空行
            compressed = self._generic_compress(output)

        self.stats["total_output"] += len(compressed)
        self.stats["commands"][cmd_name] = self.stats["commands"].get(cmd_name, 0) + 1

        return compressed

    # ── 具体压缩策略 ──

    def compress_ls(self, output: str) -> str:
        """压缩 ls 输出（精简目录树）"""
        lines = output.strip().split("\n")
        if not lines:
            return output

        # 统计文件类型
        files = []
        dirs = []
        symlinks = []
        others = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("total"):
                continue
            if line.startswith("d"):
                dirs.append(line.split()[-1] + "/")
            elif line.startswith("l"):
                symlinks.append(line.split()[-1] + "@")
            elif line.startswith("-"):
                files.append(line.split()[-1])
            else:
                others.append(line.split()[-1])

        # 精简格式
        result_parts = []
        if dirs:
            result_parts.append(f"📁 {len(dirs)} dirs: {', '.join(dirs[:20])}")
        if files:
            result_parts.append(f"📄 {len(files)} files: {', '.join(files[:30])}")
        if symlinks:
            result_parts.append(f"🔗 {len(symlinks)} links: {', '.join(symlinks[:10])}")
        if others:
            result_parts.append(f"❓ {len(others)} others")

        return "\n".join(result_parts) if result_parts else output

    def compress_git_status(self, output: str) -> str:
        """压缩 git status 输出"""
        lines = output.strip().split("\n")
        staged = []
        unstaged = []
        untracked = []

        section = "header"
        for line in lines:
            line = line.strip()
            if line.startswith("Changes to be committed"):
                section = "staged"
                continue
            elif line.startswith("Changes not staged"):
                section = "unstaged"
                continue
            elif line.startswith("Untracked files"):
                section = "untracked"
                continue

            if line.startswith("modified:") or line.startswith("new file:") or line.startswith("deleted:"):
                file = line.split(":", 1)[1].strip()
                if section == "staged":
                    staged.append(f"+ {file}")
                elif section == "unstaged":
                    unstaged.append(f"~ {file}")
                elif section == "untracked":
                    untracked.append(f"? {file}")

        result = []
        if staged:
            result.append(f"Staged ({len(staged)}): {', '.join(s[:30] for s in staged)}")
        if unstaged:
            result.append(f"Unstaged ({len(unstaged)}): {', '.join(s[:30] for s in unstaged)}")
        if untracked:
            result.append(f"Untracked ({len(untracked)}): {', '.join(s[:30] for s in untracked)}")

        return "\n".join(result) if result else output

    def compress_git_diff(self, output: str) -> str:
        """压缩 git diff 输出"""
        # 只保留文件名和变更统计
        file_changes = []
        current_file = ""
        added = 0
        removed = 0

        for line in output.split("\n"):
            if line.startswith("diff --git"):
                if current_file and (added > 0 or removed > 0):
                    file_changes.append(f"{current_file}: +{added}/-{removed}")
                current_file = line.split()[-1].split("/")[-1] if len(line.split()) > 2 else ""
                added = 0
                removed = 0
            elif line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1

        if current_file and (added > 0 or removed > 0):
            file_changes.append(f"{current_file}: +{added}/-{removed}")

        return "\n".join(file_changes) if file_changes else output

    def compress_git_log(self, output: str) -> str:
        """压缩 git log 输出"""
        lines = output.strip().split("\n")
        commits = []
        for line in lines:
            line = line.strip()
            if line.startswith("commit "):
                commit_hash = line.split()[1][:8]
            elif line.startswith("Author:"):
                author = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                date = line.split(":", 1)[1].strip()
            elif line and not line.startswith(" "):
                message = line[:80]
                commits.append(f"{commit_hash} | {date[:10]} | {message}")

        return "\n".join(commits[:20]) if commits else output

    def compress_read(self, output: str) -> str:
        """压缩 cat/read 输出（自动去注释+空行）"""
        lines = output.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip()
            # 跳过空行
            if not stripped:
                continue
            # 跳过单行注释（保留文档字符串）
            if stripped.startswith("#") and not stripped.startswith("###"):
                continue
            # 跳过行尾注释
            if "#" in line:
                line = line.split("#")[0].rstrip()
            filtered.append(line)

        return "\n".join(filtered)

    def compress_test_output(self, output: str) -> str:
        """压缩测试输出（只显示失败项）"""
        lines = output.split("\n")
        failures = []
        summary = ""

        for line in lines:
            line = line.strip()
            if "FAILED" in line or "ERROR" in line or "fail" in line.lower():
                failures.append(line)
            if "passed" in line.lower() or "failed" in line.lower() or "error" in line.lower():
                if "=" in line or "-" in line or "summary" in line.lower():
                    summary = line

        if failures:
            return f"Failures ({len(failures)}):\n" + "\n".join(failures[:10]) + f"\n{summary}"
        elif summary:
            return f"All passed! {summary}"
        return output

    def compress_find(self, output: str) -> str:
        """压缩 find/grep 输出"""
        lines = output.strip().split("\n")
        if len(lines) > 50:
            return f"Found {len(lines)} matches:\n" + "\n".join(lines[:20]) + f"\n... and {len(lines) - 20} more"
        return output

    def _generic_compress(self, output: str) -> str:
        """通用压缩"""
        # 去除连续空行
        lines = output.split("\n")
        filtered = []
        prev_empty = False
        for line in lines:
            is_empty = not line.strip()
            if is_empty and prev_empty:
                continue
            filtered.append(line)
            prev_empty = is_empty

        return "\n".join(filtered)

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        """获取压缩统计"""
        total_in = self.stats["total_input"]
        total_out = self.stats["total_output"]
        saved = total_in - total_out if total_in > 0 else 0
        ratio = round(saved / total_in * 100, 1) if total_in > 0 else 0

        return {
            "total_input_chars": total_in,
            "total_output_chars": total_out,
            "saved_chars": saved,
            "compression_ratio": f"{ratio}%",
            "commands_used": self.stats["commands"],
            "enabled": self.enabled,
        }

    def reset_stats(self) -> None:
        """重置统计"""
        self.stats = {
            "total_input": 0,
            "total_output": 0,
            "commands": {},
        }
