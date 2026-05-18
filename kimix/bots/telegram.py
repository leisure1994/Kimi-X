"""Telegram 适配器 — 使用 Polling（无需公网）."""

from __future__ import annotations

import asyncio
from typing import Any

from .base import BotAdapter
from .models import ChatMessage, Platform, ReplyMessage


class TelegramAdapter(BotAdapter):
    """Telegram 适配器.

    模式:
      - polling: 长轮询（默认，无需公网）
      - webhook: 需要公网服务器（可选）
    """

    platform = Platform.TELEGRAM

    def _validate_config(self) -> bool:
        if not self.config.bot_token:
            print("[bots] Telegram 需要 bot_token")
            return False
        return True

    async def send(self, to: str, message: ReplyMessage) -> bool:
        """to = chat_id"""
        try:
            import httpx
        except ImportError:
            return False

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        body = {"chat_id": to, "text": message.text}
        if message.markdown:
            body["parse_mode"] = "MarkdownV2"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=body)
            return resp.status_code == 200 and resp.json().get("ok")
        except Exception as exc:
            print(f"[bots] Telegram 发送失败: {exc}")
            return False

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self._shutdown_event = shutdown_event
        await self._run_polling()

    async def _run_polling(self) -> None:
        """长轮询接收消息."""
        try:
            import httpx
        except ImportError:
            print("[bots] Telegram 需要 httpx")
            return

        url = f"https://api.telegram.org/bot{self.config.bot_token}/getUpdates"
        offset = None
        print("[bots] Telegram Polling 启动...")

        while not self._shutdown_event.is_set():
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(url, params=params)
                data = resp.json()

                if not data.get("ok"):
                    print(f"[bots] Telegram API 错误: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await self._handle_update(update)

            except Exception as exc:
                print(f"[bots] Telegram Polling 错误: {exc}")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return

        text = msg.get("text", "")
        chat = msg.get("chat", {})
        from_ = msg.get("from", {})
        bot_id = self.config.raw.get("bot_user_id", "")
        bot_username = self.config.raw.get("bot_username", "")

        # @识别
        entities = msg.get("entities", [])
        bot_mentioned = False
        for entity in entities:
            if entity.get("type") == "mention":
                mention_text = text[entity["offset"]:entity["offset"]+entity["length"]]
                if bot_username and mention_text == f"@{bot_username}":
                    bot_mentioned = True
                    text = text.replace(f"@{bot_username}", "").strip()

        # 私聊 always reply
        if chat.get("type") == "private":
            bot_mentioned = True

        msg_obj = self._build_chat_message(
            sender_id=str(from_.get("id", "")),
            sender_name=from_.get("username") or from_.get("first_name", "用户"),
            chat_id=str(chat.get("id", "")),
            text=text,
            bot_mentioned=bot_mentioned,
            is_group=chat.get("type") in ("group", "supergroup"),
            message_id=str(msg.get("message_id", "")),
            raw=update,
        )
        await self._notify(msg_obj)
