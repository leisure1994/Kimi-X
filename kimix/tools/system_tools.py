"""
系统工具集

提供桌面通知和任务列表管理功能。
"""

from __future__ import annotations

import logging
from typing import Any

from .base import AbstractTool, ApprovalLevel, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局任务列表（内存存储）
# ---------------------------------------------------------------------------

_todo_items: list[dict[str, Any]] = []
_todo_counter: int = 0


# ---------------------------------------------------------------------------
# 1. NotifyTool
# ---------------------------------------------------------------------------


class NotifyTool(AbstractTool):
    """桌面通知工具

    发送桌面通知，提醒用户重要事件或任务完成。
    支持跨平台（Linux/Windows/macOS）。
    """

    name = "notify"
    description = (
        "发送桌面通知。用于提醒用户重要事件、任务完成或需要关注的事项。"
        "支持 Linux (notify-send)、Windows (toast) 和 macOS (osascript)。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "通知标题",
            },
            "message": {
                "type": "string",
                "description": "通知正文内容",
            },
            "urgency": {
                "type": "string",
                "description": "紧急程度: low/normal/critical",
                "enum": ["low", "normal", "critical"],
                "default": "normal",
            },
        },
        "required": ["title", "message"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        title = params["title"]
        message = params["message"]
        urgency = params.get("urgency", "normal")

        if not title.strip() or not message.strip():
            return ToolResult.fail("标题和消息内容不能为空")

        # 尝试各平台的通知方式
        notification_sent = False
        errors: list[str] = []

        # 1. Linux - notify-send
        try:
            import subprocess

            cmd = ["notify-send", title, message]
            if urgency == "critical":
                cmd.extend(["-u", "critical"])
            elif urgency == "low":
                cmd.extend(["-u", "low"])

            subprocess.run(
                cmd,
                capture_output=True,
                timeout=5,
                check=True,
            )
            notification_sent = True
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            errors.append(f"notify-send: {exc}")
        except ImportError:
            pass

        # 2. macOS - osascript
        if not notification_sent:
            try:
                import subprocess

                script = (
                    f'display notification "{message}" '
                    f'with title "{title}"'
                )
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                    check=True,
                )
                notification_sent = True
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                errors.append(f"osascript: {exc}")

        # 3. Windows - win10toast (或 powershell)
        if not notification_sent:
            try:
                from win10toast import ToastNotifier  # type: ignore[import-untyped]

                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=5)
                notification_sent = True
            except ImportError:
                # 尝试 PowerShell
                try:
                    import subprocess

                    ps_script = (
                        f"Add-Type -AssemblyName System.Windows.Forms; "
                        f"[System.Windows.Forms.MessageBox]::Show("
                        f"'{message}', '{title}')"
                    )
                    subprocess.run(
                        ["powershell", "-Command", ps_script],
                        capture_output=True,
                        timeout=5,
                    )
                    notification_sent = True
                except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                    errors.append(f"powershell: {exc}")

        # 4. 回退：使用 plyer（跨平台）
        if not notification_sent:
            try:
                from plyer import notification  # type: ignore[import-untyped]

                notification.notify(
                    title=title,
                    message=message,
                    timeout=5,
                )
                notification_sent = True
            except ImportError:
                pass
            except Exception as exc:
                errors.append(f"plyer: {exc}")

        if notification_sent:
            return ToolResult.ok(
                f"通知已发送: {title}",
                title=title,
                urgency=urgency,
            )
        else:
            # 所有通知方式都失败了，返回文本记录
            logger.info("[通知] %s: %s", title, message)
            return ToolResult.ok(
                f"[通知无法发送到桌面]\n标题: {title}\n内容: {message}\n"
                f"\n提示：安装通知工具以启用桌面通知\n"
                f"  Linux: sudo apt-get install libnotify-bin\n"
                f"  或: pip install plyer\n"
                f"尝试详情: {'; '.join(errors[:2])}",
                title=title,
                urgency=urgency,
                fallback=True,
            )


# ---------------------------------------------------------------------------
# 2. TodoTool
# ---------------------------------------------------------------------------


class TodoTool(AbstractTool):
    """任务列表管理工具

    管理待办事项列表，支持添加、列出、完成和删除操作。
    任务列表存储在内存中，当前会话有效。
    """

    name = "todo"
    description = (
        "管理任务列表（TODO）。支持添加、列出、标记完成和删除任务。"
        "任务列表在当前会话中有效。"
    )
    approval_required = ApprovalLevel.NONE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": ["add", "list", "done", "remove", "clear"],
            },
            "content": {
                "type": "string",
                "description": "任务内容（add 时必填）",
                "default": "",
            },
            "task_id": {
                "type": "integer",
                "description": "任务 ID（done/remove 时必填）",
                "default": 0,
            },
        },
        "required": ["action"],
    }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        action = params["action"]
        content = params.get("content", "")
        task_id = params.get("task_id", 0)

        global _todo_counter, _todo_items

        if action == "add":
            if not content.strip():
                return ToolResult.fail("任务内容不能为空")

            _todo_counter += 1
            task = {
                "id": _todo_counter,
                "content": content.strip(),
                "done": False,
            }
            _todo_items.append(task)

            return ToolResult.ok(
                f"已添加任务 #{task['id']}: {task['content']}",
                task_id=task["id"],
                total_tasks=len(_todo_items),
            )

        elif action == "list":
            if not _todo_items:
                return ToolResult.ok("任务列表为空")

            lines = ["# 任务列表", "=" * 40]
            pending = 0
            done = 0

            for task in _todo_items:
                status = "[x]" if task["done"] else "[ ]"
                if task["done"]:
                    done += 1
                else:
                    pending += 1
                lines.append(f"{status} #{task['id']}: {task['content']}")

            lines.append("")
            lines.append(f"总计: {len(_todo_items)} | 待办: {pending} | 已完成: {done}")

            return ToolResult.ok(
                "\n".join(lines),
                total=len(_todo_items),
                pending=pending,
                done=done,
            )

        elif action == "done":
            if task_id <= 0:
                return ToolResult.fail("请提供有效的任务 ID")

            for task in _todo_items:
                if task["id"] == task_id:
                    task["done"] = True
                    return ToolResult.ok(
                        f"任务 #{task_id} 已完成: {task['content']}",
                        task_id=task_id,
                    )

            return ToolResult.fail(f"任务 #{task_id} 不存在")

        elif action == "remove":
            if task_id <= 0:
                return ToolResult.fail("请提供有效的任务 ID")

            for i, task in enumerate(_todo_items):
                if task["id"] == task_id:
                    removed = _todo_items.pop(i)
                    return ToolResult.ok(
                        f"已删除任务 #{task_id}: {removed['content']}",
                        task_id=task_id,
                    )

            return ToolResult.fail(f"任务 #{task_id} 不存在")

        elif action == "clear":
            count = len(_todo_items)
            _todo_items.clear()
            return ToolResult.ok(
                f"已清空任务列表（{count} 个任务）",
                cleared_count=count,
            )

        else:
            return ToolResult.fail(f"未知操作: {action}")
