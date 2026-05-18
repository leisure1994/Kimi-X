#!/usr/bin/env python3
"""
i18n 国际化模块 — 中英文切换框架

用法:
    from kimix.i18n import get_text
    print(get_text("welcome"))  # 根据配置返回中文或英文
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# 默认语言
DEFAULT_LANG = os.environ.get("KIMIX_LANG", "zh")

# 翻译字典
TRANSLATIONS = {
    "zh": {
        "welcome": "欢迎使用 Kimi-Agent",
        "idle_prompt_freelance": "你已闲置 {idle_time}，是否开启闲时兼职模式？",
        "idle_prompt_bounty": "当前任务复杂度为日常的 {ratio} 倍，是否开启赏金模式？",
        "clawtip_setup_required": "需要先开通 ClawTip 支付才能开启经济模式。",
        "task_accepted": "任务已接受",
        "task_rejected": "任务已拒绝",
        "payment_success": "支付成功",
        "payment_failed": "支付失败",
        "sandbox_safe": "代码安全检查通过",
        "sandbox_dangerous": "代码包含危险操作",
        "quality_excellent": "代码质量优秀",
        "quality_poor": "代码质量较差",
        "version": "版本",
        "loading": "加载中...",
        "done": "完成",
        "error": "错误",
        "warning": "警告",
        "info": "信息",
    },
    "en": {
        "welcome": "Welcome to Kimi-Agent",
        "idle_prompt_freelance": "You've been idle for {idle_time}. Enable freelance mode?",
        "idle_prompt_bounty": "Task complexity is {ratio}x daily average. Enable bounty mode?",
        "clawtip_setup_required": "ClawTip payment setup required to enable economy mode.",
        "task_accepted": "Task accepted",
        "task_rejected": "Task rejected",
        "payment_success": "Payment successful",
        "payment_failed": "Payment failed",
        "sandbox_safe": "Code security check passed",
        "sandbox_dangerous": "Code contains dangerous operations",
        "quality_excellent": "Excellent code quality",
        "quality_poor": "Poor code quality",
        "version": "Version",
        "loading": "Loading...",
        "done": "Done",
        "error": "Error",
        "warning": "Warning",
        "info": "Info",
    },
}


def get_text(key: str, lang: str | None = None, **kwargs) -> str:
    """获取指定语言的文本。

    Args:
        key: 文本键名
        lang: 语言代码 (zh/en)，默认从环境变量获取
        **kwargs: 格式化参数

    Returns:
        str: 翻译后的文本
    """
    target_lang = lang or DEFAULT_LANG
    text = TRANSLATIONS.get(target_lang, TRANSLATIONS["en"]).get(
        key, f"[{key}]"
    )
    if kwargs:
        text = text.format(**kwargs)
    return text


def set_language(lang: str) -> None:
    """设置全局语言。

    Args:
        lang: 语言代码 (zh/en)
    """
    global DEFAULT_LANG
    DEFAULT_LANG = lang
    os.environ["KIMIX_LANG"] = lang


def list_languages() -> list[str]:
    """返回支持的语言列表。"""
    return list(TRANSLATIONS.keys())


def get_all_texts(lang: str | None = None) -> dict[str, str]:
    """获取指定语言的所有文本。

    Args:
        lang: 语言代码

    Returns:
        dict: 所有文本键值对
    """
    target_lang = lang or DEFAULT_LANG
    return TRANSLATIONS.get(target_lang, TRANSLATIONS["zh"]).copy()


def export_translations(path: str | Path, lang: str | None = None) -> None:
    """导出翻译到 JSON 文件。

    Args:
        path: 输出文件路径
        lang: 语言代码，None 则导出所有语言
    """
    target = Path(path)
    if lang:
        data = {lang: TRANSLATIONS.get(lang, {})}
    else:
        data = TRANSLATIONS
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_translations(path: str | Path) -> None:
    """从 JSON 文件加载翻译。

    Args:
        path: JSON 文件路径
    """
    global TRANSLATIONS
    target = Path(path)
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        TRANSLATIONS.update(data)
