"""Bot 后台运行管理器 — 支持多平台同时常驻运行."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

from .models import ChatMessage, Platform, ReplyMessage
from .router import MessageRouter


def load_adapter_cls(platform: Platform) -> type:
    """根据平台名加载对应适配器类（延迟导入避免循环依赖）."""
    if platform == Platform.FEISHU:
        from .feishu import FeishuAdapter
        return FeishuAdapter
    elif platform == Platform.WECOM:
        from .wecom import WecomAdapter
        return WecomAdapter
    elif platform == Platform.SLACK:
        from .slack import SlackAdapter
        return SlackAdapter
    elif platform == Platform.DISCORD:
        from .discord import DiscordAdapter
        return DiscordAdapter
    elif platform == Platform.TELEGRAM:
        from .telegram import TelegramAdapter
        return TelegramAdapter
    elif platform == Platform.DINGTALK:
        from .dingtalk import DingtalkAdapter
        return DingtalkAdapter
    raise ValueError(f"Unknown platform: {platform}")


class BotRunner:
    """Bot 运行器 — 启动一个或多个平台适配器，接收消息并路由到 Agent."""

    def __init__(self) -> None:
        self._adapters: dict[Platform, Any] = {}
        self._tasks: set[asyncio.Task] = set()
        self._router = MessageRouter()
        self._shutdown_event = asyncio.Event()

    async def add_platform(self, platform: Platform, config_path: Path | None = None) -> bool:
        """加载一个平台的配置并启动适配器."""
        config_dir = Path.home() / ".kimix" / "bots"
        if config_path is None:
            config_path = config_dir / f"{platform.value}.yaml"

        if not config_path.exists():
            print(f"[bots] {platform.value}: 配置文件不存在 {config_path}")
            return False

        AdapterCls = load_adapter_cls(platform)
        adapter = AdapterCls()
        if not adapter.load(config_path):
            print(f"[bots] {platform.value}: 配置加载失败")
            return False

        self._adapters[platform] = adapter
        # 把适配器消息回调绑定到路由
        adapter.on_message = self._router.route
        print(f"[bots] {platform.value}: 已加载，等待启动...")
        return True

    async def start(self) -> None:
        """启动所有适配器."""
        for platform, adapter in self._adapters.items():
            task = asyncio.create_task(self._run_adapter(platform, adapter))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # 注册信号处理
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                asyncio.get_event_loop().add_signal_handler(sig, self._request_shutdown)
            except (NotImplementedError, ValueError):
                pass  # Windows 不支持

        print("[bots] 所有平台已启动。按 Ctrl+C 停止。")
        await self._shutdown_event.wait()

    async def _run_adapter(self, platform: Platform, adapter: Any) -> None:
        """运行单个适配器（内部重试逻辑）."""
        while not self._shutdown_event.is_set():
            try:
                await adapter.run(self._shutdown_event)
            except Exception as exc:
                print(f"[bots] {platform.value}: 运行异常 {exc}")
            if self._shutdown_event.is_set():
                break
            print(f"[bots] {platform.value}: 5秒后重连...")
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    def _request_shutdown(self) -> None:
        print("\n[bots] 收到关闭信号...")
        self._shutdown_event.set()

    async def stop(self) -> None:
        """优雅停止所有适配器."""
        self._shutdown_event.set()
        for adapter in self._adapters.values():
            try:
                await adapter.stop()
            except Exception:
                pass
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


def _main() -> None:
    """CLI 入口: python -m kimix.bots.runner"""
    runner = BotRunner()

    async def _run() -> None:
        config_dir = Path.home() / ".kimix" / "bots"
        for yaml_file in sorted(config_dir.glob("*.yaml")):
            platform = Platform(yaml_file.stem)
            await runner.add_platform(platform, yaml_file)

        if not runner._adapters:
            print("[bots] 没有已绑定的平台。请先运行: kimix bots setup")
            sys.exit(1)

        try:
            await runner.start()
        finally:
            await runner.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    _main()
