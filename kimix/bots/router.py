"""消息路由引擎 — 把平台消息送进 Kimi-Agent 处理并返回回复."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .models import ChatMessage, Platform, ReplyMessage


class MessageRouter:
    """统一消息路由器.

    所有平台的 ChatMessage 都经过这里，调用 Agent 引擎生成回复，
    再把 ReplyMessage 送回对应平台。
    """

    def __init__(self) -> None:
        # 回调：当需要回复时，调用平台适配器的 send_message
        self._send_callbacks: dict[str, Callable[[str, ReplyMessage], Any]] = {}
        # 简单的内存对话上下文（可用 memory 模块替代）
        self._contexts: dict[str, list[dict]] = {}
        # 并发锁，防止同个会话多消息竞争
        self._locks: dict[str, asyncio.Lock] = {}

    def register_sender(
        self,
        chat_key: str,
        send_fn: Callable[[str, ReplyMessage], Any],
    ) -> None:
        """注册发送回调。

        chat_key 格式: "platform:chat_id"
        """
        self._send_callbacks[chat_key] = send_fn

    async def route(self, msg: ChatMessage) -> None:
        """处理一条平台消息."""
        # 判断是否值得回复（私聊总是回复，群聊需 @）
        if not msg.should_reply(require_mention_in_group=True):
            return

        chat_key = f"{msg.platform.value}:{msg.chat_id}"
        lock = self._locks.setdefault(chat_key, asyncio.Lock())

        async with lock:
            try:
                reply = await self._process(msg)
            except Exception as exc:
                reply = ReplyMessage.from_text(
                    f"⚠️ 处理出错: {type(exc).__name__}: {exc}"
                )

            send_fn = self._send_callbacks.get(chat_key) or self._send_callbacks.get(msg.platform.value)
            if send_fn:
                try:
                    await send_fn(msg.sender_id, reply)
                except Exception as exc:
                    print(f"[router] 发送失败 {chat_key}: {exc}")
            else:
                print(f"[router] 警告: 未找到发送回调 {chat_key}")

    async def _process(self, msg: ChatMessage) -> ReplyMessage:
        """核心处理逻辑 — 调用 Agent 引擎."""
        # 这里接入 Kimi-Agent 核心引擎
        # 为保持解耦，先用 engine 接口（如果可用）
        try:
            from kimix.core.engine import AgentEngine
            from kimix.config.settings import get_settings

            settings = get_settings()
            engine = AgentEngine(settings)

            # 构建 prompt（保留上下文）
            ctx = self._contexts.setdefault(
                f"{msg.platform.value}:{msg.chat_id}", []
            )
            if len(ctx) > 10:
                ctx = ctx[-10:]

            user_prompt = msg.text
            if msg.images:
                user_prompt += f"\n[附 {len(msg.images)} 张图片]"

            # 调用引擎（同步接口包一层 async）
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: engine.run(user_prompt, context=ctx),
            )

            # 更新上下文
            ctx.append({"role": "user", "content": msg.text})
            if isinstance(result, dict) and "response" in result:
                ctx.append({"role": "assistant", "content": result["response"]})
                return ReplyMessage.from_text(result["response"])
            elif isinstance(result, str):
                ctx.append({"role": "assistant", "content": result})
                return ReplyMessage.from_text(result)
            else:
                return ReplyMessage.from_text(str(result))

        except Exception as exc:
            # 引擎不可用时的优雅降级
            print(f"[router] Agent 引擎调用失败: {exc}")
            return ReplyMessage.from_text(
                f"你好！我是 Kimi-Agent 🤖\n\n"
                f"收到你的消息: {msg.text[:100]}\n\n"
                f"当前 Agent 引擎未完全初始化，但机器人连接已就绪。\n"
                f"请检查 API Key 配置或稍后重试。"
            )

    def _get_context(self, chat_key: str) -> list[dict]:
        """获取对话上下文."""
        return self._contexts.get(chat_key, [])
