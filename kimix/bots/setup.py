"""Bot 交互式绑定向导 — 引导用户完成平台配置."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

console = Console()

PLATFORM_MAP: dict[str, str] = {
    "feishu": "📘 飞书 (Feishu / Lark)",
    "wecom": "💼 企业微信 (WeCom)",
    "slack": "💬 Slack",
    "discord": "🎮 Discord",
    "telegram": "✈️ Telegram",
    "dingtalk": "🔔 钉钉",
}


def list_platforms() -> dict[str, str]:
    """返回所有支持的机器人平台."""
    return PLATFORM_MAP.copy()


async def run_setup(platform_name: str | None = None) -> None:
    """交互式绑定向导."""
    console.print()
    console.print(Rule("[bold blue]Kimi-Agent IM 机器人绑定向导[/bold blue]"))
    console.print()

    if platform_name is None:
        for key, name in PLATFORM_MAP.items():
            console.print(f"  {key:>10} → {name}")
        console.print()
        platform_name = Prompt.ask("选择平台", choices=list(PLATFORM_MAP.keys()))
    else:
        platform_name = platform_name.lower()

    if platform_name not in PLATFORM_MAP:
        console.print(f"[red]不支持的平台: {platform_name}[/red]")
        return

    console.print(Panel(f"[bold]{PLATFORM_MAP[platform_name]}[/bold]", border_style="blue"))

    if platform_name == "feishu":
        await _setup_feishu()
    elif platform_name == "wecom":
        await _setup_wecom()
    elif platform_name == "slack":
        await _setup_slack()
    elif platform_name == "discord":
        await _setup_discord()
    elif platform_name == "telegram":
        await _setup_telegram()
    elif platform_name == "dingtalk":
        await _setup_dingtalk()

    console.print()
    console.print("[green]✅ 绑定完成！[/green]")
    console.print("[dim]配置保存在: ~/.kimix/bots/{platform}.yaml[/dim]")
    console.print("[dim]启动机器人: kimix bots run[/dim]")
    console.print()


# ============================
# 各平台向导
# ============================

async def _setup_feishu() -> None:
    console.print("\n[bold cyan]飞书支持两种接入方式:[/bold cyan]\n")
    console.print("  [1] [bold]Webhook[/bold] — 群机器人，仅发送消息（最简单）")
    console.print("  [2] [bold]Stream[/bold]   — 企业自建应用，双向收发，无需公网服务器")
    console.print()
    mode = Prompt.ask("选择模式", choices=["1", "2"], default="2")

    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    cfg: dict[str, Any] = {"platform": "feishu", "name": name, "enabled": True}

    if mode == "1":
        cfg["mode"] = "webhook"
        console.print("\n[yellow]Step 1:[/yellow] 在飞书群 → 设置 → 添加机器人 → 自定义机器人")
        cfg["webhook_url"] = Prompt.ask("Webhook 地址", password=False)
    else:
        cfg["mode"] = "stream"
        console.print("\n[yellow]Step 1:[/yellow] 飞书开放平台 → 创建企业自建应用")
        console.print("  https://open.feishu.cn/app")
        cfg["app_id"] = Prompt.ask("App ID")
        cfg["app_secret"] = Prompt.ask("App Secret", password=True)
        console.print("[yellow]Step 2:[/yellow] 权限管理 → 开通 im:chat:readonly, im:message:send")
        console.print("[yellow]Step 3:[/yellow] 事件订阅 → 使用长连接接收事件（Stream 模式）")

    _save_config("feishu", cfg)
    await _test_send("feishu", cfg)


async def _setup_wecom() -> None:
    console.print("\n[bold cyan]企业微信支持两种接入方式:[/bold cyan]\n")
    console.print("  [1] [bold]Webhook[/bold] — 群机器人，仅发送")
    console.print("  [2] [bold]API[/bold]     — 自建应用，需要 corpid + secret")
    console.print()
    mode = Prompt.ask("选择模式", choices=["1", "2"], default="1")

    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    cfg: dict[str, Any] = {"platform": "wecom", "name": name, "enabled": True}

    if mode == "1":
        cfg["mode"] = "webhook"
        console.print("\n[yellow]Step 1:[/yellow] 企微群 → 添加机器人 → 复制 Webhook")
        cfg["webhook_url"] = Prompt.ask("Webhook 地址", password=False)
    else:
        cfg["mode"] = "api"
        console.print("\n[yellow]Step 1:[/yellow] 企微管理后台 → 应用管理 → 创建应用")
        cfg["app_id"] = Prompt.ask("企业 ID (corpid)")
        cfg["app_secret"] = Prompt.ask("应用 Secret", password=True)
        cfg["agentid"] = Prompt.ask("应用 AgentID")

    _save_config("wecom", cfg)
    await _test_send("wecom", cfg)


async def _setup_slack() -> None:
    console.print("\n[bold cyan]Slack 支持两种接入方式:[/bold cyan]\n")
    console.print("  [1] [bold]Webhook[/bold] — Incoming Webhook，仅发送")
    console.print("  [2] [bold]Socket[/bold]  — Socket Mode，双向收发，无需公网")
    console.print()
    mode = Prompt.ask("选择模式", choices=["1", "2"], default="2")

    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    cfg: dict[str, Any] = {"platform": "slack", "name": name, "enabled": True}

    if mode == "1":
        cfg["mode"] = "webhook"
        console.print("\n[yellow]Step 1:[/yellow] Slack App → Incoming Webhooks → 激活")
        cfg["webhook_url"] = Prompt.ask("Webhook URL", password=False)
    else:
        cfg["mode"] = "socket"
        console.print("\n[yellow]Step 1:[/yellow] api.slack.com/apps → Create New App → From scratch")
        console.print("[yellow]Step 2:[/yellow] OAuth & Permissions → Bot Token Scopes → chat:write")
        cfg["bot_token"] = Prompt.ask("Bot User OAuth Token (xoxb-...)", password=True)
        console.print("[yellow]Step 3:[/yellow] Basic Information → App-Level Token → Generate (xapp-...)")
        cfg["app_token"] = Prompt.ask("App-Level Token (xapp-...)", password=True)
        console.print("[yellow]Step 4:[/yellow] Socket Mode → 开启")

    _save_config("slack", cfg)
    await _test_send("slack", cfg)


async def _setup_discord() -> None:
    console.print("\n[bold cyan]Discord 仅支持 Bot Token 模式:[/bold cyan]\n")
    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    console.print("\n[yellow]Step 1:[/yellow] discord.com/developers/applications → New Application")
    console.print("[yellow]Step 2:[/yellow] Bot → Add Bot → Copy Token")
    console.print("[yellow]Step 3:[/yellow] OAuth2 → URL Generator → bot → Send Messages, Read Message History")
    console.print("[yellow]Step 4:[/yellow] 用生成的 URL 邀请机器人加入服务器")

    cfg: dict[str, Any] = {"platform": "discord", "name": name, "enabled": True}
    cfg["bot_token"] = Prompt.ask("Bot Token", password=True)

    _save_config("discord", cfg)
    await _test_send("discord", cfg)


async def _setup_telegram() -> None:
    console.print("\n[bold cyan]Telegram 使用 Bot Token（Polling 模式，无需公网）:[/bold cyan]\n")
    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    console.print("\n[yellow]Step 1:[/yellow] @BotFather → /newbot → 获取 Token")

    cfg: dict[str, Any] = {"platform": "telegram", "name": name, "enabled": True, "mode": "polling"}
    cfg["bot_token"] = Prompt.ask("Bot Token", password=True)
    console.print("[yellow]Step 2:[/yellow] 给你的机器人发一条消息，确认它已启动")

    _save_config("telegram", cfg)
    await _test_send("telegram", cfg)


async def _setup_dingtalk() -> None:
    console.print("\n[bold cyan]钉钉支持两种接入方式:[/bold cyan]\n")
    console.print("  [1] [bold]Webhook[/bold] — 群机器人，仅发送")
    console.print("  [2] [bold]Stream[/bold]  — 自建应用，双向收发，无需公网")
    console.print()
    mode = Prompt.ask("选择模式", choices=["1", "2"], default="2")

    name = Prompt.ask("机器人名称", default="Kimi-Agent")
    cfg: dict[str, Any] = {"platform": "dingtalk", "name": name, "enabled": True}

    if mode == "1":
        cfg["mode"] = "webhook"
        console.print("\n[yellow]Step 1:[/yellow] 钉钉群 → 智能群助手 → 添加机器人 → 自定义")
        cfg["webhook_url"] = Prompt.ask("Webhook 地址")
        secret = Prompt.ask("Webhook Secret（加签密钥，可选）", password=True)
        if secret:
            cfg["webhook_secret"] = secret
    else:
        cfg["mode"] = "stream"
        console.print("\n[yellow]Step 1:[/yellow] 钉钉开放平台 → 创建应用 → 机器人")
        cfg["app_id"] = Prompt.ask("AppKey")
        cfg["app_secret"] = Prompt.ask("AppSecret", password=True)
        console.print("[yellow]Step 2:[/yellow] 权限管理 → 开通机器人相关权限")
        console.print("[yellow]Step 3:[/yellow] 事件订阅 → Stream 模式")

    _save_config("dingtalk", cfg)
    await _test_send("dingtalk", cfg)


# ============================
# 保存 & 测试
# ============================

def _save_config(platform: str, cfg: dict[str, Any]) -> None:
    """保存配置到 YAML."""
    try:
        import yaml
    except ImportError:
        console.print("[red]需要 PyYAML: pip install pyyaml[/red]")
        return

    config_dir = Path.home() / ".kimix" / "bots"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"{platform}.yaml"

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

    console.print(f"[dim]配置已保存: {path}[/dim]")


async def _test_send(platform: str, cfg: dict[str, Any]) -> None:
    """发送测试消息验证连接."""
    console.print()
    test = Prompt.ask("是否发送测试消息验证连接", choices=["y", "n"], default="y")
    if test != "y":
        return

    try:
        from .base import BotAdapter
        from .models import ReplyMessage
        adapter = BotAdapter._create_by_name(platform)
        config_dir = Path.home() / ".kimix" / "bots"
        adapter.load(config_dir / f"{platform}.yaml")
        ok = await adapter.send("test", ReplyMessage.from_text("🤖 Kimi-Agent 测试消息 — 连接成功！"))
        if ok:
            console.print("[green]✅ 测试消息发送成功！[/green]")
        else:
            console.print("[yellow]⚠️ 测试消息发送失败，请检查配置[/yellow]")
    except Exception as exc:
        console.print(f"[yellow]⚠️ 测试失败: {exc}[/yellow]")


async def send_to_all(text: str) -> dict[str, bool]:
    """向所有已绑定平台发送消息."""
    from .base import BotAdapter
    from .models import ReplyMessage

    adapters = BotAdapter.load_all()
    results: dict[str, bool] = {}
    for key, adapter in adapters.items():
        try:
            ok = await adapter.send("broadcast", ReplyMessage.from_text(text))
            results[key] = ok
        except Exception:
            results[key] = False
    return results
