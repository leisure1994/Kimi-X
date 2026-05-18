#!/usr/bin/env python3
"""
性能基准测试脚本 — 加载时间 + 内存 + 响应延迟

运行: python3 scripts/benchmark.py
"""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent


class PerformanceBenchmark:
    """性能基准测试器"""

    @classmethod
    def run_all(cls) -> dict[str, Any]:
        """运行完整性能基准测试"""
        return {
            "import_time": cls.benchmark_import(),
            "memory_usage": cls.benchmark_memory(),
            "module_load": cls.benchmark_module_load(),
            "tool_registry": cls.benchmark_tool_registry(),
            "sandbox_validation": cls.benchmark_sandbox(),
        }

    @classmethod
    def benchmark_import(cls) -> dict:
        """基准导入时间"""
        times = []
        for _ in range(3):
            start = time.perf_counter()
            # 模拟核心模块导入
            import sys
            sys.path.insert(0, str(PROJECT_ROOT))
            from kimix.version import get_version_string
            get_version_string()
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        avg_time = sum(times) / len(times)
        return {
            "metric": "import_time",
            "unit": "seconds",
            "avg": round(avg_time, 4),
            "min": round(min(times), 4),
            "max": round(max(times), 4),
            "threshold": 2.0,
            "pass": avg_time < 2.0,
            "score": max(0, min(100, int((2.0 - avg_time) / 2.0 * 100))),
        }

    @classmethod
    def benchmark_memory(cls) -> dict:
        """基准内存占用"""
        tracemalloc.start()
        
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from kimix.tools.clawtip import ClawTipPayment
        payment = ClawTipPayment(sandbox=True)
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        current_mb = current / 1024 / 1024
        peak_mb = peak / 1024 / 1024
        
        return {
            "metric": "memory_usage",
            "unit": "MB",
            "current": round(current_mb, 2),
            "peak": round(peak_mb, 2),
            "threshold": 50,
            "pass": peak_mb < 50,
            "score": max(0, min(100, int((50 - peak_mb) / 50 * 100))),
        }

    @classmethod
    def benchmark_module_load(cls) -> dict:
        """基准模块加载时间"""
        modules = [
            "kimix.core.core_rules",
            "kimix.core.agent_economy",
            "kimix.tools.clawtip",
            "kimix.tools.registry",
            "kimix.memory.manager",
        ]
        
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        
        results = []
        for mod_name in modules:
            start = time.perf_counter()
            try:
                __import__(mod_name)
                elapsed = time.perf_counter() - start
                results.append({"module": mod_name, "time": round(elapsed, 4), "loaded": True})
            except Exception as e:
                results.append({"module": mod_name, "time": 0, "loaded": False, "error": str(e)})
        
        avg_time = sum(r["time"] for r in results if r["loaded"]) / max(1, sum(1 for r in results if r["loaded"]))
        
        return {
            "metric": "module_load",
            "unit": "seconds",
            "modules": results,
            "avg_time": round(avg_time, 4),
            "all_loaded": all(r["loaded"] for r in results),
            "threshold": 1.0,
            "pass": avg_time < 1.0,
            "score": max(0, min(100, int((1.0 - avg_time) / 1.0 * 100))),
        }

    @classmethod
    def benchmark_tool_registry(cls) -> dict:
        """基准工具注册表性能"""
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        
        start = time.perf_counter()
        from kimix.tools.registry import ToolRegistry
        registry = ToolRegistry()
        elapsed = time.perf_counter() - start
        
        return {
            "metric": "tool_registry_init",
            "unit": "seconds",
            "time": round(elapsed, 4),
            "threshold": 0.5,
            "pass": elapsed < 0.5,
            "score": max(0, min(100, int((0.5 - elapsed) / 0.5 * 100))),
        }

    @classmethod
    def benchmark_sandbox(cls) -> dict:
        """基准沙盒验证性能"""
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from kimix.core.agent_economy import SandboxValidator
        
        test_cases = [
            'print("hello")',
            'import os',
            'eval("1+1")',
            'def foo(): pass',
        ]
        
        start = time.perf_counter()
        for code in test_cases:
            SandboxValidator.validate_code(code)
        elapsed = time.perf_counter() - start
        
        return {
            "metric": "sandbox_validation",
            "unit": "seconds",
            "cases": len(test_cases),
            "total_time": round(elapsed, 4),
            "avg_per_case": round(elapsed / len(test_cases), 4),
            "threshold": 0.1,
            "pass": elapsed < 0.1,
            "score": max(0, min(100, int((0.1 - elapsed) / 0.1 * 100))),
        }

    @classmethod
    def get_summary(cls) -> dict:
        """性能基准摘要"""
        all_benchmarks = cls.run_all()
        total_score = 0
        max_score = 0
        all_pass = True
        
        for name, result in all_benchmarks.items():
            score = result.get("score", 0)
            total_score += score
            max_score += 100
            if not result.get("pass", False):
                all_pass = False
        
        overall = total_score / max_score * 100 if max_score > 0 else 0
        
        return {
            "overall_score": round(overall, 1),
            "all_pass": all_pass,
            "grade": "A" if overall >= 90 else "B" if overall >= 80 else "C",
            "benchmarks": all_benchmarks,
        }


def main() -> None:
    print("=" * 50)
    print("  Kimi-Agent 性能基准测试")
    print("=" * 50)
    
    summary = PerformanceBenchmark.get_summary()
    
    print(f"\n综合性能评分: {summary['overall_score']:.1f}/100")
    print(f"评级: {summary['grade']}")
    print(f"全部通过: {'是' if summary['all_pass'] else '否'}")
    
    for name, result in summary["benchmarks"].items():
        metric = result.get("metric", name)
        score = result.get("score", "N/A")
        passed = "✅" if result.get("pass", False) else "❌"
        print(f"\n  {passed} {metric}: {result.get('avg', result.get('time', 'N/A'))} (score={score})")
    
    print(f"\n{'='*50}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
