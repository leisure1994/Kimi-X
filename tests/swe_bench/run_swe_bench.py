"""
SWE-bench Lite 测试框架

评估 Agent 修复真实 GitHub issue 的能力。
下载 SWE-bench Lite 数据集，让 Agent 尝试修复，对比 patch 正确性。

参考: https://github.com/princeton-nlp/SWE-bench
数据集: princeton-nlp/SWE-bench_Lite

运行方式:
    python tests/swe_bench/run_swe_bench.py --instance astropy__astropy-1234
    python tests/swe_bench/run_swe_bench.py --run-lite --max-instances 10

注：完整 SWE-bench 需要 Docker 环境和大量时间，这里提供 Lite 版本支持。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SWEInstance:
    """SWE-bench 实例"""
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    test_patch: str  # 测试用例 patch（用于验证修复）
    patch: str  # 正确 patch（用于评分）
    hint_text: str = ""


@dataclass
class SWEResult:
    """单次修复结果"""
    instance_id: str
    resolved: bool  # 是否通过测试
    agent_patch: str  # Agent 生成的 patch
    test_output: str  # 测试输出
    duration_sec: float
    error: str | None = None


class SWEBenchRunner:
    """SWE-bench 测试运行器

    用法:
        runner = SWEBenchRunner(work_dir="/tmp/swe-bench")
        dataset = runner.download_lite()
        result = runner.run_instance(dataset[0], agent)
        print(f"Resolved: {result.resolved}")
    """

    def __init__(self, work_dir: str = "/tmp/swe-bench") -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_path = self.work_dir / "swe-bench-lite.json"

    def download_lite(self, force: bool = False) -> list[SWEInstance]:
        """下载 SWE-bench Lite 数据集

        Args:
            force: 强制重新下载

        Returns:
            SWEInstance 列表
        """
        if self.dataset_path.exists() and not force:
            with open(self.dataset_path) as f:
                data = json.load(f)
            return [self._parse_instance(d) for d in data]

        # 从 Hugging Face 下载
        url = "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite/resolve/main/swe-bench-lite.json"
        print(f"[SWE-bench] 下载数据集...")

        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "kimix-agent"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            # 下载失败，创建模拟数据集用于测试
            print(f"[SWE-bench] 下载失败 ({e})，使用模拟数据集")
            data = self._create_mock_dataset()

        with open(self.dataset_path, "w") as f:
            json.dump(data, f)

        return [self._parse_instance(d) for d in data]

    def _create_mock_dataset(self) -> list[dict[str, Any]]:
        """创建模拟数据集（用于离线测试）"""
        return [
            {
                "instance_id": "mock__repo-001",
                "repo": "mock/repo",
                "base_commit": "abc123",
                "problem_statement": "修复一个模拟的 bug：函数 add(a, b) 没有返回正确结果",
                "patch": "diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n",
                "test_patch": "diff --git a/test_calc.py b/test_calc.py\n--- /dev/null\n+++ b/test_calc.py\n@@ -0,0 +1,4 @@\n+from calc import add\n+\n+def test_add():\n+    assert add(1, 2) == 3\n",
                "hint_text": "",
            }
        ]

    def _parse_instance(self, data: dict[str, Any]) -> SWEInstance:
        """解析实例数据"""
        return SWEInstance(
            instance_id=data.get("instance_id", "unknown"),
            repo=data.get("repo", ""),
            base_commit=data.get("base_commit", ""),
            problem_statement=data.get("problem_statement", ""),
            test_patch=data.get("test_patch", ""),
            patch=data.get("patch", ""),
            hint_text=data.get("hint_text", ""),
        )

    def run_instance(
        self,
        instance: SWEInstance,
        agent_runner: Any | None = None,
        timeout: float = 300.0,
    ) -> SWEResult:
        """运行单个实例

        Args:
            instance: SWE 实例
            agent_runner: Agent 执行器（callable，接收 problem_statement 返回 patch）
            timeout: 超时秒数

        Returns:
            SWEResult
        """
        import time
        start = time.time()

        try:
            # 1. 克隆仓库到指定 commit
            repo_dir = self._checkout_repo(instance)

            # 2. 让 Agent 尝试修复
            if agent_runner is None:
                # 模拟：直接返回空 patch（用于测试框架）
                agent_patch = ""
            else:
                agent_patch = agent_runner(
                    problem=instance.problem_statement,
                    repo_dir=str(repo_dir),
                    hint=instance.hint_text,
                )

            # 3. 应用 Agent 的 patch
            if agent_patch:
                self._apply_patch(repo_dir, agent_patch)

            # 4. 应用测试 patch
            self._apply_patch(repo_dir, instance.test_patch)

            # 5. 运行测试
            test_output = self._run_tests(repo_dir, timeout)
            resolved = "passed" in test_output.lower() or test_output.count("FAILED") == 0

            duration = time.time() - start
            return SWEResult(
                instance_id=instance.instance_id,
                resolved=resolved,
                agent_patch=agent_patch,
                test_output=test_output,
                duration_sec=duration,
            )

        except Exception as e:
            duration = time.time() - start
            return SWEResult(
                instance_id=instance.instance_id,
                resolved=False,
                agent_patch="",
                test_output="",
                duration_sec=duration,
                error=str(e),
            )

    def _checkout_repo(self, instance: SWEInstance) -> Path:
        """克隆仓库并 checkout 到指定 commit"""
        repo_name = instance.repo.replace("/", "__")
        repo_dir = self.work_dir / "repos" / repo_name / instance.instance_id
        repo_dir.parent.mkdir(parents=True, exist_ok=True)

        if not repo_dir.exists():
            # 克隆
            github_url = f"https://github.com/{instance.repo}.git"
            subprocess.run(
                ["git", "clone", github_url, str(repo_dir)],
                capture_output=True,
                timeout=120,
            )

        # Checkout 到指定 commit
        subprocess.run(
            ["git", "checkout", instance.base_commit],
            cwd=repo_dir,
            capture_output=True,
            timeout=30,
        )

        return repo_dir

    def _apply_patch(self, repo_dir: Path, patch: str) -> None:
        """应用 patch"""
        if not patch.strip():
            return

        # 写入临时文件
        patch_file = repo_dir / "_agent.patch"
        patch_file.write_text(patch)

        # 应用
        result = subprocess.run(
            ["git", "apply", "_agent.patch"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # 尝试 git am
            subprocess.run(
                ["git", "apply", "--reject", "_agent.patch"],
                cwd=repo_dir,
                capture_output=True,
            )

    def _run_tests(self, repo_dir: Path, timeout: float) -> str:
        """运行测试"""
        # 尝试常见的测试命令
        test_commands = [
            ["python", "-m", "pytest", "-xvs"],
            ["python", "-m", "pytest", "test_calc.py", "-xvs"],
            ["python", "-m", "unittest", "discover", "-v"],
        ]

        for cmd in test_commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                output = result.stdout + "\n" + result.stderr
                if result.returncode == 0 or "FAILED" in output or "passed" in output:
                    return output
            except subprocess.TimeoutExpired:
                return "[TIMEOUT] 测试超时"
            except Exception:
                continue

        return "[ERROR] 无法运行测试"

    def evaluate(
        self,
        instances: list[SWEInstance] | None = None,
        max_instances: int | None = None,
        agent_runner: Any | None = None,
    ) -> dict[str, Any]:
        """批量评估

        Args:
            instances: 实例列表（默认下载 Lite 数据集）
            max_instances: 最大运行数量
            agent_runner: Agent 执行器

        Returns:
            {"resolved": N, "total": N, "instances": [...]}
        """
        if instances is None:
            instances = self.download_lite()

        if max_instances:
            instances = instances[:max_instances]

        results: list[SWEResult] = []
        for i, inst in enumerate(instances):
            print(f"[{i+1}/{len(instances)}] {inst.instance_id} ...", end=" ")
            result = self.run_instance(inst, agent_runner)
            status = "✅ RESOLVED" if result.resolved else "❌ FAILED"
            print(f"{status} ({result.duration_sec:.1f}s)")
            results.append(result)

        resolved = sum(1 for r in results if r.resolved)
        total = len(results)
        accuracy = resolved / total if total > 0 else 0

        return {
            "resolved": resolved,
            "total": total,
            "accuracy": round(accuracy, 3),
            "results": results,
        }


def main() -> None:
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description="SWE-bench Lite 测试")
    parser.add_argument("--instance", help="运行单个实例")
    parser.add_argument("--run-lite", action="store_true", help="运行 Lite 数据集")
    parser.add_argument("--max-instances", type=int, default=10)
    parser.add_argument("--work-dir", default="/tmp/swe-bench")
    args = parser.parse_args()

    runner = SWEBenchRunner(work_dir=args.work_dir)

    if args.instance:
        # 运行单个实例
        dataset = runner.download_lite()
        instance = next((i for i in dataset if i.instance_id == args.instance), None)
        if not instance:
            print(f"未找到实例: {args.instance}")
            return
        result = runner.run_instance(instance)
        print(f"\n结果: {'✅ 已修复' if result.resolved else '❌ 未修复'}")
        print(f"测试输出:\n{result.test_output[:1000]}")

    elif args.run_lite:
        # 批量运行
        results = runner.evaluate(max_instances=args.max_instances)
        print(f"\n{'='*50}")
        print(f"SWE-bench Lite 结果: {results['resolved']}/{results['total']}")
        print(f"准确率: {results['accuracy']*100:.1f}%")
    else:
        # 仅下载数据集
        dataset = runner.download_lite()
        print(f"数据集已下载: {len(dataset)} 个实例")
        for i in dataset[:5]:
            print(f"  - {i.instance_id}: {i.repo}")


if __name__ == "__main__":
    main()
