"""
安全沙箱执行器（Docker 隔离）

替代直接 subprocess.run()，所有 shell 命令在隔离容器中执行：
- 文件系统只读挂载（工作目录可写）
- 网络可控（可禁用）
- CPU/内存限制
- 超时强制终止
- 执行后自动清理

依赖: Docker 已安装且 daemon 运行
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    container_id: str | None = None
    killed: bool = False  # 是否因超时被强制终止


class DockerSandbox:
    """Docker 沙箱执行环境

    用法:
        sandbox = DockerSandbox(project_dir="/path/to/project")
        result = await sandbox.run("python -m pytest", timeout=60)
        if result.returncode != 0:
            print(f"失败: {result.stderr}")
    """

    def __init__(
        self,
        project_dir: str | Path,
        image: str = "python:3.12-slim",
        network: bool = False,
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
        read_only: bool = True,
    ) -> None:
        """初始化沙箱

        Args:
            project_dir: 项目目录（挂载到 /workspace）
            image: Docker 镜像
            network: 是否允许网络访问
            memory_limit: 内存限制（如 "512m", "1g"）
            cpu_limit: CPU 限制（如 "1.0", "2.0"）
            read_only: 是否只读（工作目录可写，系统只读）
        """
        self.project_dir = Path(project_dir).resolve()
        self.image = image
        self.network = network
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.read_only = read_only

    def _check_docker(self) -> bool:
        """检查 Docker 是否可用"""
        try:
            subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def run(
        self,
        command: str,
        timeout: float = 60.0,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """在沙箱中执行命令

        Args:
            command: 要执行的 shell 命令
            timeout: 超时秒数
            env: 额外环境变量

        Returns:
            SandboxResult 包含 stdout/stderr/returncode
        """
        if not self._check_docker():
            # Docker 不可用，降级为本地执行（带警告）
            return self._fallback_local(command, timeout, env)

        container_name = f"kimix-{uuid.uuid4().hex[:12]}"
        work_mount = f"{self.project_dir}:/workspace"

        # 构建 docker run 参数
        args = [
            "docker", "run",
            "--rm",  # 执行后自动删除
            "--name", container_name,
            "-v", work_mount,
            "-w", "/workspace",
            "--memory", self.memory_limit,
            "--cpus", self.cpu_limit,
        ]

        if not self.network:
            args.append("--network=none")

        if self.read_only:
            args.append("--read-only")
            # 只读模式下，需要可写临时目录
            args.extend(["--tmpfs", "/tmp:noexec,nosuid,size=100m"])

        # 环境变量
        if env:
            for k, v in env.items():
                args.extend(["-e", f"{k}={v}"])

        # 默认传递 API Key（如果配置）
        for key_name in ["MOONSHOT_API_KEY", "OPENAI_API_KEY"]:
            if os.environ.get(key_name):
                args.extend(["-e", f"{key_name}={os.environ[key_name]}"])

        args.append(self.image)
        args.extend(["sh", "-c", command])

        # 执行
        start = __import__("time").time()
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = (__import__("time").time() - start) * 1000
            return SandboxResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_ms=duration,
                container_id=container_name,
                killed=False,
            )
        except subprocess.TimeoutExpired as e:
            # 超时，强制终止容器
            self._kill_container(container_name)
            duration = (__import__("time").time() - start) * 1000
            return SandboxResult(
                command=command,
                returncode=-9,
                stdout=e.stdout or "",
                stderr=e.stderr or "",
                duration_ms=duration,
                container_id=container_name,
                killed=True,
            )

    def _kill_container(self, container_name: str) -> None:
        """强制终止容器"""
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

    def _fallback_local(
        self,
        command: str,
        timeout: float,
        env: dict[str, str] | None,
    ) -> SandboxResult:
        """Docker 不可用时的降级执行（本地，有警告）"""
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)

        start = __import__("time").time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.project_dir,
                env=merged_env,
            )
            duration = (__import__("time").time() - start) * 1000
            stderr_warn = "[WARN] Docker 不可用，命令在宿主环境执行，无隔离\n" + proc.stderr
            return SandboxResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=stderr_warn,
                duration_ms=duration,
                container_id=None,
                killed=False,
            )
        except subprocess.TimeoutExpired as e:
            duration = (__import__("time").time() - start) * 1000
            return SandboxResult(
                command=command,
                returncode=-9,
                stdout=e.stdout or "",
                stderr="[TIMEOUT] 命令执行超时\n" + (e.stderr or ""),
                duration_ms=duration,
                container_id=None,
                killed=True,
            )


class SandboxTool:
    """工具层封装：将沙箱作为 Agent 可调用工具

    注册到工具注册表后，Agent 执行 shell 命令自动进入沙箱。
    """

    def __init__(self, sandbox: DockerSandbox) -> None:
        self.sandbox = sandbox

    def execute(self, command: str, timeout: int = 60) -> dict[str, Any]:
        """工具接口：执行命令

        Args:
            command: 命令字符串
            timeout: 超时秒数

        Returns:
            {"success": bool, "stdout": str, "stderr": str, "returncode": int}
        """
        result = self.sandbox.run(command, timeout=float(timeout))
        return {
            "success": result.returncode == 0 and not result.killed,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "duration_ms": round(result.duration_ms, 1),
            "sandbox": result.container_id is not None,
            "killed": result.killed,
        }
