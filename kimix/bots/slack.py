"""Slack 适配器 — 支持 Webhook + Bot Token (Socket Mode)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import BotAdapter
from .models import ChatMessage, Platform, ReplyMessage


class SlackAdapter(BotAdapter):
    """Slack 适配器.

    模式:
      - webhook: Incoming Webhook（仅发送）
      - socket:  Socket Mode（双向，WebSocket 长连接，无需公网）
    """

    platform = Platform.SLACK

    def _validate_config(self) -> bool:
        if self.config.mode == "socket":
            if not self.config.bot_token:
                print("[bots] Slack Socket 模式需要 bot_token")
                return False
        elif self.config.mode == "webhook":
            if not self.config.webhook_url:
                print("[bots] Slack Webhook 需要 webhook_url")
                return False
        return True

    async def send(self, to: str, message: ReplyMessage) -> bool:
        if self.config.mode == "webhook":
            return await self._send_webhook(message)
        return await self._send_api(to, message)

    async def _send_webhook(self, message: ReplyMessage) -> bool:
        try:
            import httpx
        except ImportError:
            return False

        payload: dict[str, Any] = {"text": message.text}
        if message.slack_blocks:
            payload["blocks"] = message.slack_blocks

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.config.webhook_url or "",
                    json=payload,
                )
            return resp.status_code == 200
        except Exception as exc:
            print(f"[bots] Slack 发送失败: {exc}")
            return False

    async def _send_api(self, channel: str, message: ReplyMessage) -> bool:
        try:
            import httpx
        except ImportError:
            return False

        headers = {"Authorization": f"Bearer {self.config.bot_token}", "Content-Type": "application/json"}
        body: dict[str, Any] = {"channel": channel, "text": message.text}
        if message.slack_blocks:
            body["blocks"] = message.slack_blocks

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json=body,
                )
            data = resp.json()
            return data.get("ok", False)
        except Exception as exc:
            print(f"[bots] Slack API 发送失败: {exc}")
            return False

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self._shutdown_event = shutdown_event
        if self.config.mode == "socket":
            await self._run_socket_mode()
        else:
            print("[bots] Slack Webhook 模式不支持接收消息")
            await shutdown_event.wait()

    async def _run_socket_mode(self) -> None:
        """Socket Mode — WebSocket 长连接接收消息."""
        try:
            import httpx
            import websockets
        except ImportError:
            print("[bots] Slack Socket 模式需要 httpx + websockets")
            return

        # Step 1: 获取 wss URL
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://slack.com/api/apps.connections.open",
                headers={"Authorization": f"Bearer {self.config.bot_token}"},
            )
        data = resp.json()
        if not data.get("ok"):
            print(f"[bots] Slack Socket 握手失败: {data}")
            return

        wss_url = data["url"]
        print("[bots] Slack Socket 连接中...")

        while not self._shutdown_event.is_set():
            try:
                async with websockets.connect(wss_url) as ws:
                    print("[bots] Slack Socket 已连接")
                    while not self._shutdown_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                            await self._handle_socket_message(raw, ws)
                        except asyncio.TimeoutError:
                            await ws.ping()
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as exc:
                print(f"[bots] Slack Socket 断开: {exc}")
            if not self._shutdown_event.is_set():
                print("[bots] Slack Socket 5秒后重连...")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                # 重新获取 wss URL
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://slack.com/api/apps.connections.open",
                        headers={"Authorization": f"Bearer {self.config.bot_token}"},
                    )
                data = resp.json()
                if data.get("ok"):
                    wss_url = data["url"]

    async def _handle_socket_message(self, raw: str, ws: Any) -> None:
        """处理 Slack Socket 消息."""
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            return

        # 应答 ack
        if envelope.get("envelope_id"):
            ack = {"envelope_id": envelope["envelope_id"]}
            await ws.send(json.dumps(ack))

        payload = envelope.get("payload", {})
        event = payload.get("event", {})
        if event.get("type") != "message" or event.get("subtype"):
            return

        text = event.get("text", "")
        bot_id = self.config.raw.get("bot_user_id", "")
        bot_mentioned = f"<@{bot_id}>" in text if bot_id else False
        clean_text = text.replace(f"<@{bot_id}>", "").strip() if bot_id else text

        # 忽略自己发的消息
        if event.get("user") == bot_id:
            return

        msg = self._build_chat_message(
            sender_id=event.get("user", ""),
            sender_name=event.get("user", "用户"),
            chat_id=event.get("channel", ""),
            text=clean_text,
            bot_mentioned=bot_mentioned,
            is_group=event.get("channel_type") == "channel",
            message_id=event.get("ts"),
            raw=envelope,
        )
        await self._notify(msg)
