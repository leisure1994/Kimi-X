"""Discord 适配器 — 需要 Bot Token（唯一方式）."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import BotAdapter
from .models import ChatMessage, Platform, ReplyMessage


class DiscordAdapter(BotAdapter):
    """Discord 适配器.

    使用 Discord Gateway WebSocket（无需公网服务器）.
    """

    platform = Platform.DISCORD

    def _validate_config(self) -> bool:
        if not self.config.bot_token:
            print("[bots] Discord 需要 bot_token")
            return False
        return True

    async def send(self, to: str, message: ReplyMessage) -> bool:
        """to = channel_id"""
        try:
            import httpx
        except ImportError:
            return False

        headers = {
            "Authorization": f"Bot {self.config.bot_token}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {"content": message.text}
        if message.discord_embed:
            body["embeds"] = [message.discord_embed]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://discord.com/api/v10/channels/{to}/messages",
                    headers=headers,
                    json=body,
                )
            return resp.status_code in (200, 201)
        except Exception as exc:
            print(f"[bots] Discord 发送失败: {exc}")
            return False

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self._shutdown_event = shutdown_event
        await self._run_gateway()

    async def _run_gateway(self) -> None:
        """Discord Gateway WebSocket."""
        try:
            import httpx
            import websockets
        except ImportError:
            print("[bots] Discord 需要 httpx + websockets")
            return

        # Step 1: 获取 Gateway URL
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://discord.com/api/v10/gateway/bot",
                headers={"Authorization": f"Bot {self.config.bot_token}"},
            )
        data = resp.json()
        gateway_url = data.get("url", "wss://gateway.discord.gg/")
        print("[bots] Discord Gateway 连接中...")

        while not self._shutdown_event.is_set():
            try:
                async with websockets.connect(f"{gateway_url}?v=10&encoding=json") as ws:
                    print("[bots] Discord Gateway 已连接")
                    heartbeat_interval = None
                    seq = None

                    while not self._shutdown_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                            payload = json.loads(raw)
                            op = payload.get("op")
                            seq = payload.get("s") or seq
                            d = payload.get("d", {})

                            if op == 10:  # Hello
                                heartbeat_interval = d["heartbeat_interval"] / 1000
                                # 发送 Identify
                                identify = {
                                    "op": 2,
                                    "d": {
                                        "token": self.config.bot_token,
                                        "intents": 512 + 1024,  # GUILD_MESSAGES + GUILD_MESSAGE_CONTENT
                                        "properties": {
                                            "os": "linux",
                                            "browser": "kimix",
                                            "device": "kimix",
                                        },
                                    },
                                }
                                await ws.send(json.dumps(identify))
                                # 启动心跳
                                asyncio.create_task(self._discord_heartbeat(ws, heartbeat_interval, seq))

                            elif op == 0:  # Dispatch
                                t = payload.get("t")
                                if t in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
                                    await self._handle_discord_message(d)

                            elif op == 1:  # Heartbeat
                                await ws.send(json.dumps({"op": 1, "d": seq}))

                        except asyncio.TimeoutError:
                            pass
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as exc:
                print(f"[bots] Discord Gateway 断开: {exc}")
            if not self._shutdown_event.is_set():
                print("[bots] Discord 5秒后重连...")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    async def _discord_heartbeat(self, ws: Any, interval: float, seq_ref: Any) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(interval)
            try:
                await ws.send(json.dumps({"op": 1, "d": seq_ref}))
            except Exception:
                break

    async def _handle_discord_message(self, d: dict) -> None:
        # 忽略自己发的消息
        if d.get("author", {}).get("bot"):
            return

        text = d.get("content", "")
        bot_id = self.config.raw.get("bot_user_id", "")
        bot_mentioned = f"<@{bot_id}>" in text if bot_id else False
        clean_text = text.replace(f"<@{bot_id}>", "").strip() if bot_id else text

        msg = self._build_chat_message(
            sender_id=d.get("author", {}).get("id", ""),
            sender_name=d.get("author", {}).get("username", "用户"),
            chat_id=d.get("channel_id", ""),
            text=clean_text,
            bot_mentioned=bot_mentioned,
            is_group=d.get("guild_id") is not None,
            message_id=d.get("id"),
            raw=d,
        )
        await self._notify(msg)
