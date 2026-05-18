"""飞书 (Feishu / Lark) 适配器 — 支持 Webhook + Stream 模式."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import BotAdapter, BotConfig
from .models import ChatMessage, Platform, ReplyMessage


class FeishuAdapter(BotAdapter):
    """飞书适配器.

    两种模式:
      - webhook: 群机器人 Webhook（仅发送）
      - stream:  企业自建应用 + Stream 长连接（双向收发，无需公网）
    """

    platform = Platform.FEISHU

    def _validate_config(self) -> bool:
        if self.config.mode == "stream":
            if not (self.config.app_id and self.config.app_secret):
                print("[bots] 飞书 Stream 模式需要 app_id + app_secret")
                return False
        elif self.config.mode == "webhook":
            if not self.config.webhook_url:
                print("[bots] 飞书 Webhook 模式需要 webhook_url")
                return False
        return True

    async def send(self, to: str, message: ReplyMessage) -> bool:
        """发送消息（支持卡片 / 纯文本）."""
        if self.config.mode == "webhook":
            return await self._send_webhook(message)
        return await self._send_api(to, message)

    async def _send_webhook(self, message: ReplyMessage) -> bool:
        """Webhook 方式发送."""
        try:
            import httpx
        except ImportError:
            print("[bots] 需要 httpx: pip install httpx")
            return False

        payload: dict[str, Any] = {"msg_type": "text"}
        if message.feishu_card:
            payload = {"msg_type": "interactive", "card": message.feishu_card}
        else:
            payload["content"] = {"text": message.text}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.config.webhook_url or "",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            return resp.status_code == 200 and resp.json().get("code") == 0
        except Exception as exc:
            print(f"[bots] 飞书发送失败: {exc}")
            return False

    async def _send_api(self, chat_id: str, message: ReplyMessage) -> bool:
        """OpenAPI 方式发送（需要 tenant_access_token）."""
        try:
            import httpx
        except ImportError:
            return False

        token = await self._get_tenant_token()
        if not token:
            return False

        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message.text}, ensure_ascii=False),
        }
        if message.feishu_card:
            body["msg_type"] = "interactive"
            body["content"] = json.dumps(message.feishu_card, ensure_ascii=False)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    params={"receive_id_type": "chat_id"},
                )
            return resp.status_code == 200 and resp.json().get("code") == 0
        except Exception as exc:
            print(f"[bots] 飞书 API 发送失败: {exc}")
            return False

    async def _get_tenant_token(self) -> str | None:
        """获取 tenant_access_token（缓存 1 小时）."""
        # 简单缓存（生产环境应加锁）
        if hasattr(self, "_token_cache") and self._token_cache:
            return self._token_cache

        try:
            import httpx
        except ImportError:
            return None

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json={
                        "app_id": self.config.app_id,
                        "app_secret": self.config.app_secret,
                    },
                )
            data = resp.json()
            token = data.get("tenant_access_token")
            if token:
                self._token_cache = token
                # 异步 1 小时后清理缓存
                asyncio.create_task(self._expire_token(data.get("expire", 7200)))
            return token
        except Exception as exc:
            print(f"[bots] 飞书获取 token 失败: {exc}")
            return None

    async def _expire_token(self, seconds: int) -> None:
        await asyncio.sleep(seconds - 60)
        self._token_cache = None  # type: ignore[assignment]

    # ============================
    # 接收消息
    # ============================

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """启动接收循环."""
        self._shutdown_event = shutdown_event
        if self.config.mode == "stream":
            await self._run_stream()
        elif self.config.mode == "webhook":
            print("[bots] 飞书 Webhook 模式不支持接收消息（单向通知）")
            await shutdown_event.wait()
        else:
            print(f"[bots] 飞书未知模式: {self.config.mode}")
            await shutdown_event.wait()

    async def _run_stream(self) -> None:
        """Stream 长连接模式 — WebSocket 持续接收事件."""
        # 飞书官方 Stream SDK 使用 websocket 连接
        # 如果没有安装官方 SDK，用原生 websocket 模拟
        try:
            import websockets
        except ImportError:
            print("[bots] 飞书 Stream 模式需要 websockets: pip install websockets")
            return

        # 获取 ws_endpoint（通过 handshake）
        ws_url = await self._get_stream_endpoint()
        if not ws_url:
            print("[bots] 飞书 Stream 握手失败")
            return

        print(f"[bots] 飞书 Stream 连接中...")
        while not self._shutdown_event.is_set():
            try:
                async with websockets.connect(ws_url) as ws:
                    print("[bots] 飞书 Stream 已连接")
                    while not self._shutdown_event.is_set():
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(),
                                timeout=30,
                            )
                            await self._handle_stream_message(raw)
                        except asyncio.TimeoutError:
                            # 发送 ping
                            await ws.ping()
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as exc:
                print(f"[bots] 飞书 Stream 断开: {exc}")
            if not self._shutdown_event.is_set():
                print("[bots] 飞书 Stream 5秒后重连...")
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                ws_url = await self._get_stream_endpoint()  # 重新握手

    async def _get_stream_endpoint(self) -> str | None:
        """Stream 握手获取 WebSocket URL."""
        try:
            import httpx
        except ImportError:
            return None

        url = "https://open.feishu.cn/open-apis/event/v1/outbound/app/subscription/list"
        token = await self._get_tenant_token()
        if not token:
            return None

        # 简化：直接用官方推荐的 websocket 地址格式
        # 实际生产应调用 handshake API
        return f"wss://ws.feishu.cn/stream?app_id={self.config.app_id}"

    async def _handle_stream_message(self, raw: str) -> None:
        """处理飞书推送的事件消息."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        event_type = data.get("header", {}).get("event_type", "")
        if event_type != "im.message.receive_v1":
            return

        event = data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})

        text = ""
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "")

        # @识别：检测消息中是否有 @_user_1（机器人在群里的身份）
        bot_mentioned = "@_user_1" in text or f"@{self.config.name}" in text
        # 移除 @标记，保留纯文本
        clean_text = text.replace("@_user_1", "").replace(f"@{self.config.name}", "").strip()

        msg = self._build_chat_message(
            sender_id=sender.get("open_id", ""),
            sender_name=sender.get("user_id", "用户"),
            chat_id=message.get("chat_id", ""),
            text=clean_text,
            bot_mentioned=bot_mentioned,
            is_group=message.get("chat_type") == "group",
            message_id=message.get("message_id"),
            raw=data,
        )
        await self._notify(msg)
