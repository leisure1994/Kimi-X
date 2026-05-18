"""钉钉 (DingTalk) 适配器 — 支持 Webhook + Stream 模式."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .base import BotAdapter
from .models import ChatMessage, Platform, ReplyMessage


class DingtalkAdapter(BotAdapter):
    """钉钉适配器.

    模式:
      - webhook: 群机器人 Webhook（单向）
      - stream:  Stream 长连接（双向，无需公网回调）
    """

    platform = Platform.DINGTALK

    def _validate_config(self) -> bool:
        if self.config.mode == "stream":
            if not (self.config.app_id and self.config.app_secret):
                print("[bots] 钉钉 Stream 模式需要 app_id + app_secret")
                return False
        elif self.config.mode == "webhook":
            if not self.config.webhook_url:
                print("[bots] 钉钉 Webhook 需要 webhook_url")
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

        timestamp = str(int(time.time() * 1000))
        secret = self.config.raw.get("webhook_secret", "")
        if secret:
            string_to_sign = f"{timestamp}\n{secret}"
            sign = base64.b64encode(
                hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
            ).decode()
        else:
            sign = ""

        payload: dict[str, Any] = {"msgtype": "text", "text": {"content": message.text}}
        if message.feishu_card:  # 钉钉支持类似卡片，但格式不同，这里简化
            payload = {"msgtype": "markdown", "markdown": {"title": "消息", "text": message.text}}

        url = self.config.webhook_url or ""
        if "?" in url:
            url += f"&timestamp={timestamp}&sign={sign}"
        else:
            url += f"?timestamp={timestamp}&sign={sign}"

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            return resp.status_code == 200 and resp.json().get("errcode") == 0
        except Exception as exc:
            print(f"[bots] 钉钉发送失败: {exc}")
            return False

    async def _send_api(self, chat_id: str, message: ReplyMessage) -> bool:
        """钉钉 OpenAPI 发送（需要 access_token）."""
        try:
            import httpx
        except ImportError:
            return False

        token = await self._get_access_token()
        if not token:
            return False

        url = "https://oapi.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        body = {
            "robotCode": self.config.app_id,
            "userIds": [chat_id],
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": message.text}, ensure_ascii=False),
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={"x-acs-dingtalk-access-token": token},
                )
            return resp.status_code == 200
        except Exception as exc:
            print(f"[bots] 钉钉 API 发送失败: {exc}")
            return False

    async def _get_access_token(self) -> str | None:
        if hasattr(self, "_token_cache") and self._token_cache:
            return self._token_cache  # type: ignore[return-value]

        try:
            import httpx
        except ImportError:
            return None

        url = "https://oapi.dingtalk.com/v1.0/oauth2/accessToken"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json={
                        "appKey": self.config.app_id,
                        "appSecret": self.config.app_secret,
                    },
                )
            data = resp.json()
            token = data.get("accessToken")
            if token:
                self._token_cache = token
                asyncio.create_task(self._expire_token(data.get("expireIn", 7200)))
            return token
        except Exception as exc:
            print(f"[bots] 钉钉获取 token 失败: {exc}")
            return None

    async def _expire_token(self, seconds: int) -> None:
        await asyncio.sleep(seconds - 60)
        self._token_cache = None  # type: ignore[assignment]

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self._shutdown_event = shutdown_event
        if self.config.mode == "stream":
            await self._run_stream()
        else:
            print("[bots] 钉钉 Webhook 模式不支持接收消息")
            await shutdown_event.wait()

    async def _run_stream(self) -> None:
        """钉钉 Stream 模式 — WebSocket 长连接."""
        try:
            import websockets
        except ImportError:
            print("[bots] 钉钉 Stream 需要 websockets: pip install websockets")
            return

        # 钉钉 Stream 需要先用 handshake 获取 endpoint
        ws_url = await self._get_stream_endpoint()
        if not ws_url:
            return

        print("[bots] 钉钉 Stream 连接中...")
        while not self._shutdown_event.is_set():
            try:
                async with websockets.connect(ws_url) as ws:
                    print("[bots] 钉钉 Stream 已连接")
                    while not self._shutdown_event.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=60)
                            await self._handle_stream_message(raw)
                        except asyncio.TimeoutError:
                            await ws.ping()
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as exc:
                print(f"[bots] 钉钉 Stream 断开: {exc}")
            if not self._shutdown_event.is_set():
                print("[bots] 钉钉 Stream 5秒后重连...")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                ws_url = await self._get_stream_endpoint()

    async def _get_stream_endpoint(self) -> str | None:
        """获取钉钉 Stream WebSocket 地址."""
        try:
            import httpx
        except ImportError:
            return None

        token = await self._get_access_token()
        if not token:
            return None

        # 钉钉 Stream 的 endpoint 需要通过 gateway API 获取
        # 简化实现：直接使用标准格式
        return f"wss://comet.dingtalk.com/comet_server?token={token}"

    async def _handle_stream_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # 钉钉 Stream 消息格式
        msg_type = data.get("msgtype", "")
        if msg_type != "text":
            return

        text = data.get("text", {}).get("content", "")
        sender = data.get("senderStaffId", "")
        chat = data.get("conversationId", "")
        is_group = data.get("conversationType") == "2"

        # 钉钉 @识别
        bot_mentioned = "@" in text and self.config.name in text
        clean_text = text
        if bot_mentioned:
            clean_text = text.replace(f"@{self.config.name}", "").strip()

        msg = self._build_chat_message(
            sender_id=sender,
            sender_name=sender,
            chat_id=chat,
            text=clean_text,
            bot_mentioned=bot_mentioned,
            is_group=is_group,
            raw=data,
        )
        await self._notify(msg)
