"""企业微信 (WeCom) 适配器 — 支持 Webhook + 自建应用."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import BotAdapter, BotConfig
from .models import ChatMessage, Platform, ReplyMessage


class WecomAdapter(BotAdapter):
    """企业微信适配器.

    模式:
      - webhook: 群机器人 Webhook（仅发送）
      - api:     自建应用 + Access Token（双向，需要公网回调或企业微信消息推送）
    """

    platform = Platform.WECOM

    def _validate_config(self) -> bool:
        if self.config.mode == "api":
            if not (self.config.app_id and self.config.app_secret):
                print("[bots] 企微 API 模式需要 corpid + corpsecret (对应 app_id / app_secret)")
                return False
        elif self.config.mode == "webhook":
            if not self.config.webhook_url:
                print("[bots] 企微 Webhook 需要 webhook_url")
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

        payload: dict[str, Any] = {"msgtype": "text", "text": {"content": message.text}}
        if message.markdown:
            payload = {"msgtype": "markdown", "markdown": {"content": message.text}}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.config.webhook_url or "",
                    json=payload,
                )
            return resp.status_code == 200 and resp.json().get("errcode") == 0
        except Exception as exc:
            print(f"[bots] 企微发送失败: {exc}")
            return False

    async def _send_api(self, user_id: str, message: ReplyMessage) -> bool:
        try:
            import httpx
        except ImportError:
            return False

        token = await self._get_access_token()
        if not token:
            return False

        url = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        body = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.config.raw.get("agentid"),
            "text": {"content": message.text},
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    json=body,
                    params={"access_token": token},
                )
            return resp.status_code == 200 and resp.json().get("errcode") == 0
        except Exception as exc:
            print(f"[bots] 企微 API 发送失败: {exc}")
            return False

    async def _get_access_token(self) -> str | None:
        if hasattr(self, "_token_cache") and self._token_cache:
            return self._token_cache  # type: ignore[return-value]

        try:
            import httpx
        except ImportError:
            return None

        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    url,
                    params={
                        "corpid": self.config.app_id,
                        "corpsecret": self.config.app_secret,
                    },
                )
            data = resp.json()
            token = data.get("access_token")
            if token:
                self._token_cache = token
                asyncio.create_task(self._expire_token(data.get("expires_in", 7200)))
            return token
        except Exception as exc:
            print(f"[bots] 企微获取 token 失败: {exc}")
            return None

    async def _expire_token(self, seconds: int) -> None:
        await asyncio.sleep(seconds - 60)
        self._token_cache = None  # type: ignore[assignment]

    async def run(self, shutdown_event: asyncio.Event) -> None:
        self._shutdown_event = shutdown_event
        if self.config.mode == "webhook":
            print("[bots] 企微 Webhook 模式不支持接收消息")
            await shutdown_event.wait()
        else:
            print("[bots] 企微 API 接收需要配置公网回调或消息推送，当前未实现")
            await shutdown_event.wait()

    async def stop(self) -> None:
        self._running = False
        if self._shutdown_event:
            self._shutdown_event.set()
