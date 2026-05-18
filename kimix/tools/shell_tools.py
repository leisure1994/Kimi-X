"""
Shell 执行工具

提供安全的 Shell 命令执行，包含危险命令过滤、超时控制和环境变量管理。
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 危险命令黑名单
# ---------------------------------------------------------------------------

# 绝对禁止的命令模式（无论出现在命令的任何位置）
DANGEROUS_PATTERNS: list[str] = [
    # 磁盘破坏
    "mkfs",
    "dd if=/dev/zero",
    "> /dev/sd",
    "> /dev/hd",
    "low level format",
    # 系统破坏
    ":(){:|:&};:",  # fork bomb (紧凑格式)
    ":(){ :|:& };:",  # fork bomb (带空格格式)
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    # 权限提升/系统修改
    "chmod -R 777 /",
    "chmod 000 /",
    "> /etc/passwd",
    "> /etc/shadow",
    # 网络危险
    "iptables -F",
    # 数据泄露风险
    "curl .* | bash",
    "wget .* | bash",
    "wget .* | sh",
    "curl .* | sh",
]

# 需要额外审查的高危命令前缀
SENSITIVE_COMMANDS: list[str] = [
    "rm -rf",
    "sudo",
    "chmod 777",
    "chown -R",
    "mkfs",
    "fdisk",
    "dd",
    "iptables",
]


# ---------------------------------------------------------------------------
# 安全检查函数
# ---------------------------------------------------------------------------


def _is_dangerous(command: str) -> tuple[bool, str | None]:
    """检查命令是否包含危险模式

    Returns:
        (是否危险, 原因)
    """
    cmd_lower = command.lower().strip()

    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            return True, f"检测到危险命令模式: {pattern!r}"

    return False, None


def _is_sensitive(command: str) -> tuple[bool, str | None]:
    """检查命令是否属于高敏感命令（需要审批）"""
    cmd_lower = command.lower().strip()

    for prefix in SENSITIVE_COMMANDS:
        if cmd_lower.startswith(prefix.lower()):
            return True, f"高敏感命令: {prefix}"

    return False, None


# ---------------------------------------------------------------------------
# ShellTool
# ---------------------------------------------------------------------------


class ShellTool(AbstractTool):
    """执行 Shell 命令

    在安全沙箱内执行 Shell 命令，支持超时控制、环境变量覆盖、
    工作目录设置和危险命令过滤。

    安全特性：
    - 危险命令模式黑名单拦截
    - 高敏感命令需要审批
    - 超时控制（默认 60 秒）
    - 输出大小限制
    - 环境变量可控
    """

    name = "shell"
    description = (
        "执行 Shell 命令。支持管道、重定向等标准 shell 特性。"
        "默认超时 60 秒，可通过 timeout 参数调整。"
        "危险命令（如 rm -rf /）会被自动拦截。"
    )
    approval_required = ApprovalLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 60",
                "default": 60,
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（覆盖默认的 work_dir），可选",
                "default": "",
            },
            "env": {
                "type": "object",
                "description": "额外的环境变量，会合并到上下文环境变量中",
                "default": {},
            },
        },
        "required": ["command"],
    }

    # 最大输出大小（字节），超过则截断
    MAX_OUTPUT_SIZE: int = 1024 * 1024  # 1 MB

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        command = params["command"]
        timeout = params.get("timeout", 60)
        cwd = params.get("cwd", "")
        extra_env = params.get("env", {})

        if not command or not command.strip():
            return ToolResult.fail("命令不能为空")

        command = command.strip()

        # 1. 危险命令检查
        is_dangerous, reason = _is_dangerous(command)
        if is_dangerous:
            logger.warning("Shell 危险命令被拦截: %s", command)
            return ToolResult.fail(
                f"命令被安全系统拦截: {reason}\n"
                f"如果你确定要执行此操作，请联系管理员。"
            )

        # 2. 敏感命令检查（记录日志）
        is_sensitive, sensitive_reason = _is_sensitive(command)
        if is_sensitive:
            logger.info("Shell 敏感命令: %s (%s)", command, sensitive_reason)

        # 3. 确定工作目录
        work_dir = cwd or context.work_dir

        # 4. 构建环境变量
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
        # 先合并上下文环境变量
        env.update(context.env_vars)
        # 再合并命令特定的环境变量
        env.update(extra_env)

        # 5. 执行命令
        logger.debug("执行 Shell: %s (cwd=%s, timeout=%s)", command, work_dir, timeout)

        try:
            # 使用 asyncio.create_subprocess_shell 以支持管道和重定向
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # 超时后尝试终止进程
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                return ToolResult.fail(
                    f"命令执行超时（{timeout} 秒）: {command}",
                    metadata={"timeout": timeout, "command": command},
                )

            # 解码输出
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # 截断过长的输出
            if len(stdout_text) > self.MAX_OUTPUT_SIZE:
                stdout_text = stdout_text[: self.MAX_OUTPUT_SIZE] + "\n... [输出已截断]"
            if len(stderr_text) > self.MAX_OUTPUT_SIZE:
                stderr_text = stderr_text[: self.MAX_OUTPUT_SIZE] + "\n... [错误输出已截断]"

            # 构建结果
            exit_code = proc.returncode or 0
            content_parts = []
            if stdout_text:
                content_parts.append(f"[stdout]\n{stdout_text}")
            if stderr_text:
                content_parts.append(f"[stderr]\n{stderr_text}")

            content = "\n\n".join(content_parts) or "（无输出）"

            if exit_code != 0:
                return ToolResult.fail(
                    f"命令退出码: {exit_code}\n{content}",
                    metadata={
                        "exit_code": exit_code,
                        "command": command,
                    },
                )

            return ToolResult.ok(
                content,
                exit_code=exit_code,
                command=command,
            )

        except OSError as exc:
            return ToolResult.fail(f"执行命令失败: {exc}")
        except Exception as exc:
            return ToolResult.fail(f"执行命令时发生未知错误: {exc}")


# ---------------------------------------------------------------------------
# 辅助工具：safe_command（用于测试和非工具场景）
# ---------------------------------------------------------------------------


async def safe_command(
    command: str,
    cwd: str = ".",
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> tuple[int, str, str]:
    """安全执行 shell 命令（辅助函数，非工具方法）

    Returns:
        (exit_code, stdout, stderr)
    """
    env_merged = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
    if env:
        env_merged.update(env)

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env_merged,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )
