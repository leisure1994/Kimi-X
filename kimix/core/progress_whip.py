#!/usr/bin/env python3
"""
进度鞭 (Progress Whip) — Agent 自我鞭策系统

功能：
- 任务开始时注册进度追踪
- 周期性自检（不消耗 LLM Token）
- 长时间无进展时自我提醒/报警
- 任务完成时归档记录

实现方式：纯本地文件记录，零 Token 消耗。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

WHIP_DIR = Path(os.path.expanduser("~/.kimix/progress_whip"))
WHIP_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class TaskProgress:
    """单个任务的进度记录"""
    task_id: str
    description: str
    status: str = "running"   # running | blocked | warning | stalled | completed | failed
    created_at: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)
    last_step: str = "init"
    steps_total: int = 0
    steps_done: int = 0
    eta_seconds: int | None = None
    stall_count: int = 0      # 连续无进展次数
    stall_threshold: int = 3  # 触发 warning 阈值
    whip_message: str = ""    # 鞭策信息
    history: list[dict] = field(default_factory=list)

class ProgressWhip:
    """
    进度鞭 — Agent 的自我鞭策引擎
    """

    def __init__(self, whip_dir: Path | str | None = None) -> None:
        self.whip_dir = Path(whip_dir) if whip_dir else WHIP_DIR
        self.whip_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, TaskProgress] = {}
        self._load_all()

    # ── 任务生命周期 ──

    def register(self, task_id: str, description: str, steps_total: int = 0) -> TaskProgress:
        """注册新任务，开始追踪"""
        t = TaskProgress(
            task_id=task_id,
            description=description,
            steps_total=steps_total,
            last_step="已注册",
        )
        t.history.append({"time": t.created_at, "event": "register", "detail": description})
        self._tasks[task_id] = t
        self._save(t)
        return t

    def step(self, task_id: str, step_name: str, steps_done: int | None = None) -> TaskProgress:
        """记录一个步骤完成"""
        t = self._get(task_id)
        now = time.time()
        t.last_update = now
        t.last_step = step_name
        if steps_done is not None:
            t.steps_done = steps_done
        else:
            t.steps_done += 1
        t.stall_count = 0        # 有进展，重置 stall
        t.status = "running"
        t.history.append({"time": now, "event": "step", "detail": step_name})
        self._save(t)
        return t

    def block(self, task_id: str, reason: str) -> TaskProgress:
        """标记任务阻塞（等待外部输入/依赖）"""
        t = self._get(task_id)
        t.status = "blocked"
        t.history.append({"time": time.time(), "event": "block", "detail": reason})
        self._save(t)
        return t

    def complete(self, task_id: str, result_summary: str = "") -> TaskProgress:
        """标记任务完成"""
        t = self._get(task_id)
        t.status = "completed"
        t.last_update = time.time()
        t.history.append({"time": t.last_update, "event": "complete", "detail": result_summary})
        self._save(t)
        # 归档：移动到 completed 目录
        self._archive(t)
        return t

    def fail(self, task_id: str, reason: str) -> TaskProgress:
        """标记任务失败"""
        t = self._get(task_id)
        t.status = "failed"
        t.last_update = time.time()
        t.history.append({"time": t.last_update, "event": "fail", "detail": reason})
        self._save(t)
        self._archive(t)
        return t

    # ── 自检与鞭策（核心） ──

    def whip_check(self) -> list[str]:
        """
        进度自检（零 Token 消耗）
        返回所有需要鞭策的任务消息列表。
        Agent 应在每次主循环调用此方法。
        """
        alerts: list[str] = []
        now = time.time()
        for t in list(self._tasks.values()):
            if t.status in ("completed", "failed"):
                continue

            idle = now - t.last_update

            # 阻塞状态
            if t.status == "blocked":
                if idle > 300:   # 阻塞超过 5 分钟
                    alerts.append(
                        f"🚨 [进度鞭] 任务「{t.description}」已阻塞 {int(idle)} 秒，"
                        f"原因：{t.last_step}。请立即处理或取消任务。"
                    )
                continue

            # 运行状态 — 检测停滞
            # 规则：
            #   0-10 min: 正常
            #   10-30 min: 轻微提醒
            #   30+ min: 严重警告
            if idle > 1800:   # 30 分钟无进展
                t.stall_count += 1
                t.status = "stalled"
                msg = (
                    f"🔴 [进度鞭] 任务「{t.description}」已停滞 {int(idle/60)} 分钟！"
                    f"最后进展：{t.last_step}。"
                    f"这是第 {t.stall_count} 次停滞警告。"
                    f"请立即汇报阻塞原因，或拆分任务、降低范围。"
                )
                t.whip_message = msg
                t.history.append({"time": now, "event": "whip", "detail": msg})
                alerts.append(msg)
            elif idle > 600:   # 10 分钟无进展
                t.stall_count += 1
                t.status = "warning"
                msg = (
                    f"🟡 [进度鞭] 任务「{t.description}」已 {int(idle/60)} 分钟无进展，"
                    f"最后进展：{t.last_step}。请确认是否仍在推进。"
                )
                t.whip_message = msg
                alerts.append(msg)

            self._save(t)
        return alerts

    def get_stalled_tasks(self) -> list[TaskProgress]:
        """获取所有停滞的任务"""
        return [t for t in self._tasks.values() if t.status in ("warning", "stalled", "blocked")]

    def get_running_tasks(self) -> list[TaskProgress]:
        """获取进行中的任务"""
        return [t for t in self._tasks.values() if t.status == "running"]

    def get_all_tasks(self) -> list[TaskProgress]:
        """获取所有任务"""
        return list(self._tasks.values())

    def is_task_stalled(self, task_id: str, threshold_seconds: float = 600) -> bool:
        """检查指定任务是否停滞"""
        t = self._tasks.get(task_id)
        if not t or t.status in ("completed", "failed"):
            return False
        return (time.time() - t.last_update) > threshold_seconds

    # ── 持久化 ──

    def _task_path(self, task_id: str) -> Path:
        return self.whip_dir / f"{task_id}.json"

    def _archive_path(self, task_id: str) -> Path:
        archive_dir = self.whip_dir / "completed"
        archive_dir.mkdir(exist_ok=True)
        return archive_dir / f"{task_id}_{int(time.time())}.json"

    def _save(self, t: TaskProgress) -> None:
        data = asdict(t)
        data["_saved_at"] = time.time()
        self._task_path(t.task_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self, path: Path) -> TaskProgress | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("_saved_at", None)
            return TaskProgress(**data)
        except Exception:
            return None

    def _load_all(self) -> None:
        for p in self.whip_dir.glob("*.json"):
            t = self._load(p)
            if t:
                self._tasks[t.task_id] = t

    def _get(self, task_id: str) -> TaskProgress:
        if task_id not in self._tasks:
            raise KeyError(f"未知任务: {task_id}")
        return self._tasks[task_id]

    def _archive(self, t: TaskProgress) -> None:
        src = self._task_path(t.task_id)
        dst = self._archive_path(t.task_id)
        if src.exists():
            src.rename(dst)
        self._tasks.pop(t.task_id, None)

    # ── 统计 ──

    def get_stats(self) -> dict[str, Any]:
        all_t = list(self._tasks.values())
        running = [t for t in all_t if t.status == "running"]
        warning = [t for t in all_t if t.status == "warning"]
        stalled = [t for t in all_t if t.status == "stalled"]
        blocked = [t for t in all_t if t.status == "blocked"]
        return {
            "total_active": len(all_t),
            "running": len(running),
            "warning": len(warning),
            "stalled": len(stalled),
            "blocked": len(blocked),
            "avg_idle_seconds": sum(time.time()-t.last_update for t in running)/max(len(running),1),
        }

    def generate_report(self) -> str:
        """生成纯文本进度报告（零 Token）"""
        lines = ["📋 进度鞭报告", "="*40]
        if not self._tasks:
            lines.append("当前无活跃任务。")
            return "\n".join(lines)
        for t in self._tasks.values():
            idle = int(time.time() - t.last_update)
            emoji = {"running":"🟢","blocked":"🟠","warning":"🟡","stalled":"🔴","completed":"✅","failed":"❌"}.get(t.status,"⚪")
            lines.append(f"\n{emoji} [{t.status.upper()}] {t.description}")
            lines.append(f"   任务ID: {t.task_id}")
            lines.append(f"   最后进展: {t.last_step} ({idle}s 前)")
            lines.append(f"   进度: {t.steps_done}/{t.steps_total if t.steps_total else '?'}")
            if t.whip_message:
                lines.append(f"   ⚠️ 鞭策: {t.whip_message}")
        return "\n".join(lines)
