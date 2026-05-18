"""Bot 适配器基类 — 所有平台适配器统一接口."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Self

from .models import ChatMessage, Platform, ReplyMessage


@dataclass
class BotConfig:
    """统一配置结构."""

    platform: Platform
    name: str = ""
    enabled: bool = True
    mode: str = "webhook"  # webhook | stream | polling
    # 通用凭证
    webhook_url: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    bot_token: str | None = None
    # 可选
    tenant_access_token: str | None = None
    encrypt_key: str | None = None
    # 群聊行为
    require_mention: bool = True
    # 原始字典（透传平台特有字段）
    raw: dict[str, Any] = None  # type: ignore[assignment]


class BotAdapter(ABC):
    """所有 IM 平台适配器的抽象基类."""

    platform: Platform
    config: BotConfig
    on_message: Callable[[ChatMessage], Any] | None = None

    def __init__(self) -> None:
        self.config = BotConfig(platform=self.platform)  # type: ignore[arg-type]
        self._running = False
        self._shutdown_event: asyncio.Event | None = None

    @classmethod
    def load_all(cls) -> dict[str, "BotAdapter"]:
        """加载 ~/.kimix/bots/*.yaml 所有配置."""
        config_dir = Path.home() / ".kimix" / "bots"
        result: dict[str, "BotAdapter"] = {}
        for yaml_file in sorted(config_dir.glob("*.yaml")):
            platform_name = yaml_file.stem
            try:
                adapter = cls._create_by_name(platform_name)
                if adapter.load(yaml_file):
                    result[platform_name] = adapter
            except Exception as exc:
                print(f"[bots] 加载 {yaml_file.name} 失败: {exc}")
        return result

    @classmethod
    def _create_by_name(cls, name: str) -> "BotAdapter":
        """根据平台名创建对应适配器."""
        mapping: dict[str, type[BotAdapter]] = {}
        try:
            from .feishu import FeishuAdapter
            mapping["feishu"] = FeishuAdapter
        except Exception:
            pass
        try:
            from .wecom import WecomAdapter
            mapping["wecom"] = WecomAdapter
        except Exception:
            pass
        try:
            from .slack import SlackAdapter
            mapping["slack"] = SlackAdapter
        except Exception:
            pass
        try:
            from .discord import DiscordAdapter
            mapping["discord"] = DiscordAdapter
        except Exception:
            pass
        try:
            from .telegram import TelegramAdapter
            mapping["telegram"] = TelegramAdapter
        except Exception:
            pass
        try:
            from .dingtalk import DingtalkAdapter
            mapping["dingtalk"] = DingtalkAdapter
        except Exception:
            pass
        if name not in mapping:
            raise ValueError(f"Unknown platform: {name}")
        return mapping[name]()

    def load(self, path: Path) -> bool:
        """从 YAML 加载配置."""
        try:
            import yaml
        except ImportError:
            print("[bots] 需要 PyYAML: pip install pyyaml")
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            print(f"[bots] 读取配置失败 {path}: {exc}")
            return False

        if not data.get("enabled", True):
            return False

        self.config = BotConfig(
            platform=self.platform,
            name=data.get("name", path.stem),
            enabled=data.get("enabled", True),
            mode=data.get("mode", "webhook"),
            webhook_url=data.get("webhook_url"),
            app_id=data.get("app_id"),
            app_secret=data.get("app_secret"),
            bot_token=data.get("bot_token"),
            tenant_access_token=data.get("tenant_access_token"),
            encrypt_key=data.get("encrypt_key"),
            require_mention=data.get("require_mention", True),
            raw=data,
        )
        return self._validate_config()

    def _validate_config(self) -> bool:
        """子类可覆盖以做额外校验."""
        return True

    @abstractmethod
    async def send(self, to: str, message: ReplyMessage) -> bool:
        """向指定用户/群组发送消息."""
        ...

    @abstractmethod
    async def run(self, shutdown_event: asyncio.Event) -> None:
        """启动后台接收循环（Webhook 监听 / Stream 长连接 / Polling 轮询）."""
        ...

    async def stop(self) -> None:
        """优雅停止."""
        self._running = False
        if self._shutdown_event:
            self._shutdown_event.set()

    def _build_chat_message(
        self,
        sender_id: str,
        sender_name: str,
        chat_id: str,
        text: str,
        **kwargs: Any,
    ) -> ChatMessage:
        """辅助方法：构造统一消息."""
        return ChatMessage(
            platform=self.platform,
            raw_message=kwargs.get("raw", {}),
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            text=text,
            bot_mentioned=kwargs.get("bot_mentioned", False),
            is_group=kwargs.get("is_group", False),
            message_id=kwargs.get("message_id"),
            reply_to=kwargs.get("reply_to"),
            raw_content=kwargs.get("raw_content"),
        )

    async def _notify(self, msg: ChatMessage) -> None:
        """把消息交给路由引擎."""
        if self.on_message:
            try:
                if asyncio.iscoroutinefunction(self.on_message):
                    await self.on_message(msg)
                else:
                    self.on_message(msg)
            except Exception as exc:
                print(f"[bots] {self.platform.value} 消息处理失败: {exc}")
