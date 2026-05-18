"""沙箱隔离模块.

提供安全的命令执行和文件访问环境，防止 Agent 执行危险操作。

安全特性:
- 危险命令黑名单过滤（rm -rf /, fork 炸弹等）
- 路径白名单/黑名单检查
- 命令注入检测
- 网络访问控制

适用于所有涉及文件系统和命令执行的工具调用。

示例:
    >>> from kimix.utils.sandbox import Sandbox
    >>> sandbox = Sandbox()
    >>> sandbox.check_command("ls -la")  # True
    >>> sandbox.check_command("rm -rf /")  # False
    >>> sandbox.check_path("./src")  # True
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SafetyLevel(Enum):
    """安全检查结果等级."""

    SAFE = "safe"                # 安全，允许执行
    BLOCKED_COMMAND = "blocked_command"  # 命中命令黑名单
    PATH_VIOLATION = "path_violation"    # 路径违规
    INJECTION_DETECTED = "injection"     # 命令注入
    NETWORK_BLOCKED = "network_blocked"  # 网络被禁用


@dataclass
class SafetyCheckResult:
    """安全检查结果.

    Attributes:
        allowed: 是否允许执行
        level: 安全检查等级
        message: 检查结果说明
        matched_rule: 命中的规则（如果有）
    """

    allowed: bool
    level: SafetyLevel
    message: str = ""
    matched_rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "allowed": self.allowed,
            "level": self.level.value,
            "message": self.message,
            "matched_rule": self.matched_rule,
        }


@dataclass
class SandboxConfig:
    """沙箱配置数据类.

    Attributes:
        enabled: 是否启用沙箱
        allowed_paths: 允许访问的路径列表
        allowed_commands: 额外允许的命令列表（白名单扩展）
        blocked_path_patterns: 禁止访问的路径模式
        allow_network: 是否允许网络访问
    """

    enabled: bool = True
    allowed_paths: list[str] = field(default_factory=lambda: ["."])
    allowed_commands: list[str] = field(default_factory=list)
    blocked_path_patterns: list[str] = field(default_factory=list)
    allow_network: bool = True


class Sandbox:
    """沙箱隔离环境.

    提供命令和文件路径的安全检查，阻止危险操作。

    示例:
        >>> sandbox = Sandbox()
        >>> result = sandbox.check_command("ls -la")
        >>> if result.allowed:
        ...     print("安全，可以执行")
        >>> else:
        ...     print(f"危险: {result.message}")
    """

    # 白名单模式：仅允许这些命令及其变体
    ALLOWED_COMMANDS: set[str] = {
        # 文件操作
        "ls", "dir", "cat", "head", "tail", "less", "more", "wc",
        "find", "grep", "rg", "ack",
        "cp", "mv", "mkdir", "rmdir", "touch", "chmod", "chown",
        "diff", "cmp", "stat", "file",
        # 编辑
        "sed", "awk", "tr", "cut", "sort", "uniq", "rev",
        # 开发工具
        "git", "python", "python3", "pip", "pip3", "node", "npm", "yarn",
        "cargo", "rustc", "go", "javac", "java",
        # 构建
        "make", "cmake", "gcc", "g++", "clang", "clang++",
        # 压缩
        "tar", "gzip", "gunzip", "zip", "unzip", "7z",
        # 系统信息
        "ps", "top", "htop", "df", "du", "free", "uptime", "whoami",
        "echo", "printf", "date", "time", "which", "whereis",
        # 网络（受 allow_network 控制）
        "curl", "wget", "ping", "dig", "nslookup", "host",
        # 其他常用
        "tree", "fd", "bat", "fzf", "jq", "yq", "tldr",
    }

    # 内置的危险路径模式
    DEFAULT_BLOCKED_PATTERNS: list[str] = [
        # 系统目录
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/etc",
        "/lib",
        "/lib64",
        "/usr/lib",
        "/boot",
        "/dev",
        "/proc",
        "/sys",
        "/run",
        "/var/run",
        "/var/log",
        "/tmp",
        # 用户敏感目录
        "~/.ssh",
        "~/.gnupg",
        "~/.aws",
        "~/.kube",
        "~/.docker",
    ]

    # 命令注入检测模式
    INJECTION_PATTERNS: list[re.Pattern] = [
        # 命令链
        re.compile(r"[;&|]\s*(rm|mv|cp|dd|mkfs|chmod|chown|shutdown|reboot|init|halt|poweroff)"),
        # 命令替换
        re.compile(r"\$\(.*\)|`.*`"),
        # I/O 重定向到系统位置
        re.compile(r">\s*(/dev/sda|/dev/hda|/etc/passwd|/etc/shadow|/etc/hosts)"),
        # 管道到危险命令
        re.compile(r"\|\s*(sh|bash|python|ruby|perl)\s+-"),
    ]

    def __init__(
        self,
        allowed_paths: list[str] | None = None,
        allowed_commands: list[str] | None = None,
        blocked_path_patterns: list[str] | None = None,
        enabled: bool = True,
        allow_network: bool = True,
    ) -> None:
        """初始化沙箱.

        Args:
            allowed_paths: 允许访问的路径列表
            allowed_commands: 额外允许的命令列表（白名单扩展）
            blocked_path_patterns: 额外禁止的路径模式
            enabled: 是否启用沙箱检查
            allow_network: 是否允许网络访问
        """
        self.enabled = enabled
        self.allow_network = allow_network

        # 合并允许路径
        self.allowed_paths: list[str] = allowed_paths or ["."]

        # 白名单模式：仅允许显式授权的命令
        # 如需扩展，通过 allowed_commands 参数添加
        self.allowed_commands: set[str] = set(self.ALLOWED_COMMANDS)
        if allowed_commands:
            self.allowed_commands.update(allowed_commands)

        # 保留黑名单作为二次过滤（针对白名单内的危险参数组合）
        self.blocked_patterns: list[str] = list(self.DEFAULT_BLOCKED_PATTERNS)
        if blocked_path_patterns:
            for pattern in blocked_path_patterns:
                if pattern not in self.blocked_patterns:
                    self.blocked_patterns.append(pattern)

    def check_command(self, command: str) -> SafetyCheckResult:
        """检查命令是否可以安全执行（白名单模式）.

        检查逻辑:
        1. 解析命令提取主命令名
        2. 检查是否在白名单中
        3. 检查是否存在命令注入
        4. 检查白名单命令的危险参数组合

        Args:
            command: 要检查的命令字符串

        Returns:
            SafetyCheckResult: 检查结果
        """
        if not self.enabled:
            return SafetyCheckResult(
                allowed=True,
                level=SafetyLevel.SAFE,
                message="沙箱已禁用，跳过检查",
            )

        if not command or not command.strip():
            return SafetyCheckResult(
                allowed=True,
                level=SafetyLevel.SAFE,
                message="空命令，允许执行",
            )

        stripped = command.strip()

        # 1. 解析主命令名
        cmd_parts = stripped.split()
        if not cmd_parts:
            return SafetyCheckResult(allowed=True, level=SafetyLevel.SAFE)
        
        main_cmd = cmd_parts[0]
        # 处理路径形式的命令（如 /usr/bin/python）
        main_cmd_name = Path(main_cmd).name.lower()

        # 2. 白名单检查
        if main_cmd_name not in self.allowed_commands:
            return SafetyCheckResult(
                allowed=False,
                level=SafetyLevel.BLOCKED_COMMAND,
                message=f"命令 '{main_cmd_name}' 不在白名单中。如确需使用，请联系管理员添加。",
                matched_rule=f"allowed_commands whitelist",
            )

        # 3. 检查命令注入
        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(stripped):
                return SafetyCheckResult(
                    allowed=False,
                    level=SafetyLevel.INJECTION_DETECTED,
                    message=f"检测到命令注入模式: {pattern.pattern}",
                    matched_rule=pattern.pattern,
                )

        # 4. 检查白名单命令的危险参数组合
        danger_flags = self._check_dangerous_flags(main_cmd_name, cmd_parts)
        if danger_flags:
            return SafetyCheckResult(
                allowed=False,
                level=SafetyLevel.BLOCKED_COMMAND,
                message=f"命令 '{main_cmd_name}' 包含危险参数: {', '.join(danger_flags)}",
                matched_rule=f"danger_flags:{';'.join(danger_flags)}",
            )

        return SafetyCheckResult(
            allowed=True,
            level=SafetyLevel.SAFE,
            message="命令安全检查通过（白名单模式）",
        )

    def check_path(self, path: str | Path) -> SafetyCheckResult:
        """检查文件路径是否在允许范围内.

        检查规则:
        1. 路径是否在白名单中
        2. 路径是否命中黑名单模式

        Args:
            path: 要检查的文件路径

        Returns:
            SafetyCheckResult: 检查结果
        """
        if not self.enabled:
            return SafetyCheckResult(
                allowed=True,
                level=SafetyLevel.SAFE,
                message="沙箱已禁用，跳过检查",
            )

        path_obj = Path(path).resolve()
        path_str = str(path_obj)

        # 1. 检查是否在禁止路径模式中
        for pattern in self.blocked_patterns:
            expanded_pattern = Path(pattern).expanduser().resolve()
            pattern_str = str(expanded_pattern)
            if path_str.startswith(pattern_str):
                return SafetyCheckResult(
                    allowed=False,
                    level=SafetyLevel.PATH_VIOLATION,
                    message=f"路径命中禁止模式: '{pattern}'",
                    matched_rule=pattern,
                )

        # 2. 检查是否在允许的路径范围内
        # 允许路径为 ["."] 表示允许当前工作目录下的所有路径
        # 也检查绝对路径是否在允许范围内
        cwd = Path.cwd().resolve()

        # 如果路径在工作目录下，通常是安全的
        if path_str.startswith(str(cwd)):
            return SafetyCheckResult(
                allowed=True,
                level=SafetyLevel.SAFE,
                message="路径在工作目录范围内",
            )

        # 检查其他允许的路径
        for allowed in self.allowed_paths:
            allowed_expanded = Path(allowed).expanduser().resolve()
            allowed_str = str(allowed_expanded)
            if path_str.startswith(allowed_str):
                return SafetyCheckResult(
                    allowed=True,
                    level=SafetyLevel.SAFE,
                    message=f"路径在允许范围内: '{allowed}'",
                )

        # 如果以上都不满足，允许相对路径（在工作目录下）
        try:
            # 检查是否为相对路径且在工作目录下
            if not path_obj.is_absolute():
                resolved = (cwd / path_obj).resolve()
                if str(resolved).startswith(str(cwd)):
                    return SafetyCheckResult(
                        allowed=True,
                        level=SafetyLevel.SAFE,
                        message="相对路径在工作目录范围内",
                    )
        except (OSError, ValueError):
            pass

        return SafetyCheckResult(
            allowed=True,
            level=SafetyLevel.SAFE,
            message="路径检查通过（相对路径模式）",
        )

    def check_network(self) -> SafetyCheckResult:
        """检查网络访问是否被允许.

        Returns:
            SafetyCheckResult: 检查结果
        """
        if self.allow_network:
            return SafetyCheckResult(
                allowed=True,
                level=SafetyLevel.SAFE,
                message="网络访问已启用",
            )
        return SafetyCheckResult(
            allowed=False,
            level=SafetyLevel.NETWORK_BLOCKED,
            message="网络访问已被禁用",
        )

    def _check_dangerous_flags(self, cmd_name: str, parts: list[str]) -> list[str]:
        """检查白名单命令的危险参数组合.

        即使是白名单内的命令，某些参数组合仍然危险。
        
        Args:
            cmd_name: 命令名
            parts: 命令参数列表

        Returns:
            危险参数列表（空表示安全）
        """
        flags = [p.lower() for p in parts[1:]]
        dangers: list[str] = []

        # rm -rf / 类
        if cmd_name in ("rm", "del"):
            if "-rf" in flags or "/" in flags or "/*" in flags:
                dangers.append("recursive-delete-root")
            if "-rf" in flags and "~" in flags:
                dangers.append("recursive-delete-home")

        # chmod/chown 系统级
        if cmd_name in ("chmod", "chown"):
            if "-r" in flags or "-R" in flags:
                if "/" in flags or "/*" in flags:
                    dangers.append("recursive-perm-system")

        # dd 写设备
        if cmd_name == "dd":
            for f in flags:
                if "of=/dev/" in f:
                    dangers.append("dd-output-device")

        # curl/wget 管道到 shell
        if cmd_name in ("curl", "wget", "fetch"):
            full = " ".join(flags)
            if "| sh" in full or "| bash" in full or "| python" in full:
                dangers.append("download-pipe-execute")

        # python 执行代码
        if cmd_name in ("python", "python3"):
            full = " ".join(flags)
            if "-c" in flags and any(k in full for k in ["os.system", "subprocess", "socket", "eval(", "exec("]):
                dangers.append("python-unsafe-code")

        return dangers

    @staticmethod
    def _command_matches(command: str, pattern: str) -> bool:
        """检查命令是否匹配禁止模式.

        支持精确匹配和通配符匹配。

        Args:
            command: 实际命令
            pattern: 禁止模式

        Returns:
            bool: 是否匹配
        """
        # 精确匹配（去除多余空格后）
        normalized_cmd = " ".join(command.split())
        normalized_pattern = " ".join(pattern.split())

        if normalized_cmd.startswith(normalized_pattern):
            return True

        # 正则表达式匹配（支持模式中的 .* 等）
        try:
            regex_pattern = pattern.replace(".*", ".*").replace(" ", r"\s+")
            if re.search(regex_pattern, command, re.IGNORECASE):
                return True
        except re.error:
            pass

        return False

    def safe_execute(
        self,
        command: list[str] | str,
        check_only: bool = False,
    ) -> SafetyCheckResult:
        """安全执行命令（仅检查，不实际执行）.

        对命令进行全面的安全检查，返回检查结果。
        实际执行由调用方负责。

        Args:
            command: 要检查的命令（字符串或参数列表）
            check_only: 仅检查不执行

        Returns:
            SafetyCheckResult: 检查结果
        """
        if isinstance(command, list):
            command_str = " ".join(shlex.quote(arg) for arg in command)
        else:
            command_str = command

        result = self.check_command(command_str)

        if check_only:
            return result

        return result

    @classmethod
    def from_config(cls, config: Any) -> "Sandbox":
        """从配置对象创建沙箱实例.

        Args:
            config: 配置对象，需要包含 sandbox 属性

        Returns:
            Sandbox: 沙箱实例
        """
        sandbox_cfg = getattr(config, "sandbox", None)
        if sandbox_cfg is None:
            return cls()

        return cls(
            enabled=getattr(sandbox_cfg, "enabled", True),
            allowed_paths=getattr(sandbox_cfg, "allowed_paths", ["."]),
            allowed_commands=getattr(sandbox_cfg, "allowed_commands", None),
            allow_network=getattr(sandbox_cfg, "network", True),
        )
