"""统一消息模型 — 所有平台消息转为统一格式."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Self


class Platform(str, enum.Enum):
    """支持的消息平台."""

    FEISHU = "feishu"
    WECOM = "wecom"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    DINGTALK = "dingtalk"


class MsgType(str, enum.Enum):
    """消息类型."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    CARD = "card"          # 交互式卡片
    RICH = "rich"          # 富文本
    EVENT = "event"        # 平台事件（加群、退群等）


@dataclass
class ChatMessage:
    """跨平台统一消息格式.

    所有平台的原始消息都转成这个结构，然后送入 Agent 引擎处理。
    """

    # 来源
    platform: Platform
    raw_message: dict[str, Any] = field(repr=False)

    # 身份
    sender_id: str                    # 用户唯一 ID
    sender_name: str                  # 用户显示名
    chat_id: str                      # 聊天室/群组 ID
    chat_name: str | None = None
    is_group: bool = False
    bot_id: str | None = None         # 本 bot 在该平台的 ID
    bot_mentioned: bool = False       # 是否被 @提及

    # 内容
    msg_type: MsgType = MsgType.TEXT
    text: str = ""                    # 纯文本内容（已脱敏处理 @ 标记）
    images: list[str] = field(default_factory=list)   # 图片 URL 列表
    files: list[dict] = field(default_factory=list)   # 文件信息
    raw_content: Any = None           # 平台原始格式（用于回复时透传）

    # 元信息
    message_id: str | None = None
    reply_to: str | None = None       # 回复某条消息
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_text(
        cls,
        platform: Platform,
        text: str,
        sender_id: str,
        chat_id: str,
        **kwargs: Any,
    ) -> Self:
        """快速构造一条文本消息（用于单元测试）."""
        return cls(
            platform=platform,
            raw_message={},
            sender_id=sender_id,
            sender_name=kwargs.get("sender_name", sender_id),
            chat_id=chat_id,
            text=text,
            message_id=kwargs.get("message_id"),
            reply_to=kwargs.get("reply_to"),
            is_group=kwargs.get("is_group", False),
            bot_mentioned=kwargs.get("bot_mentioned", False),
            **{k: v for k, v in kwargs.items() if k not in (
                "sender_name", "message_id", "reply_to",
                "is_group", "bot_mentioned",
            )},
        )

    def should_reply(self, require_mention_in_group: bool = True) -> bool:
        """判断这条消息是否需要回复.

        私聊 → 总是回复
        群聊 → 只有被 @ 时才回复（避免刷屏）
        """
        if not self.is_group:
            return True
        if not require_mention_in_group:
            return True
        return self.bot_mentioned


@dataclass
class ReplyMessage:
    """回复消息 — 支持多种格式."""

    text: str = ""
    images: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)

    # 平台特定格式（如果提供，优先使用）
    feishu_card: dict | None = None          # 飞书卡片 JSON
    discord_embed: dict | None = None        # Discord Embed
    slack_blocks: list[dict] | None = None   # Slack Block Kit
    markdown: bool = False                   # 是否支持 Markdown 渲染

    @classmethod
    def from_text(cls, text: str) -> Self:
        return cls(text=text)
