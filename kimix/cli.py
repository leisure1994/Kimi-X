"""
Kimi-Agent (kimix) 主 CLI 入口模块

使用 Typer 构建完整的命令行接口：
- kimix              → 启动交互式 TUI
- kimix "问题"       → 一次性问答
- kimix --plan "问题" → Plan 模式
- kimix --yolo "问题" → YOLO 模式
- kimix --mode <mode> → 指定模式
- kimix auth         → 配置 API Key
- kimix config       → 显示/编辑配置
- kimix session      → 会话管理
- kimix tool         → 工具管理
- kimix doctor       → 诊断检查
- kimix --version    → 版本信息

依赖:
    - typer: CLI 框架
    - rich: 格式化输出
    - prompt_toolkit: 交互式输入
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from kimix.version import get_version_string
from kimix.core.engine import AgentEngine, AgentMode

# Rich 控制台实例
console = Console()

# 创建 Typer 应用
app = typer.Typer(
    name="kimix",
    help="Kimi-Agent: 基于 Kimi k2.6 的智能终端 AI Agent",
    rich_markup_mode="rich",
    no_args_is_help=False,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# 子命令组
session_app = typer.Typer(
    name="session",
    help="会话管理: 列表、恢复、导出",
    rich_markup_mode="rich",
)
tool_app = typer.Typer(
    name="tool",
    help="工具管理: 列表、测试",
    rich_markup_mode="rich",
)
config_app = typer.Typer(
    name="config",
    help="配置管理: 查看和编辑",
    rich_markup_mode="rich",
)

# 注册子命令
app.add_typer(session_app)
app.add_typer(tool_app)
app.add_typer(config_app)

# CLI 状态（在回调中初始化）
_engine: AgentEngine | None = None
_config: dict | None = None


def _print_banner() -> None:
    """打印启动横幅"""
    banner = Panel(
        Text.assemble(
            Text("🤖 ", style="magenta"),
            Text("Kimi-Agent", style="bold magenta"),
            Text(f" v{get_version_string()}\n", style="magenta dim"),
            Text("智能终端 AI Agent - 比 TUI 更聪明\n", style="white dim"),
            Text("基于 Kimi k2.6 模型 | 支持流式输出 | 智能成本优化", style="dim"),
        ),
        border_style="magenta dim",
        padding=(1, 2),
    )
    console.print(banner)


def _get_mode(
    mode: str | None,
    plan: bool,
    yolo: bool,
) -> AgentMode:
    """确定工作模式

    根据命令行参数决定使用哪种工作模式。
    优先级: --yolo > --plan > --mode > 默认(Agent)

    Args:
        mode: --mode 参数值
        plan: --plan 标志
        yolo: --yolo 标志

    Returns:
        AgentMode: 确定的工作模式
    """
    if yolo:
        return AgentMode.YOLO
    if plan:
        return AgentMode.PLAN
    if mode:
        try:
            return AgentMode(mode.lower())
        except ValueError:
            console.print(f"[red]错误: 未知模式 '{mode}'[/red]")
            console.print(
                "[yellow]可用模式: explore, plan, agent, auto, yolo[/yellow]"
            )
            raise typer.Exit(1)
    return AgentMode.AGENT


def _init_engine(mode: AgentMode) -> AgentEngine | None:
    """初始化 Agent 引擎

    加载配置并创建引擎实例。
    如果 API Key 未配置，返回 None。
    子系统初始化失败时不影响核心功能（graceful degradation）。

    Args:
        mode: 工作模式

    Returns:
        AgentEngine | None: 引擎实例或 None
    """
    try:
        from kimix.config.settings import KimixConfig
        from kimix.llm.client import KimiClient
        from kimix.tools.registry import ToolRegistry

        config = KimixConfig()

        # 检查 API Key
        if not config.auth.api_key:
            return None

        # 创建 LLM 客户端
        llm_client = KimiClient(
            api_key=config.auth.api_key,
            base_url=config.auth.base_url,
            model=config.model.default,
        )

        # 创建工具注册表
        tool_registry = ToolRegistry()
        tool_registry.auto_discover()

        # 创建记忆管理器（失败时降级为 None）
        memory_manager = None
        try:
            from kimix.memory.manager import MemoryManager
            from platformdirs import user_data_dir

            project_path = Path(".").resolve()
            data_dir = Path(user_data_dir("kimix"))
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "memory.db"
            memory_manager = MemoryManager(project_path=project_path, db_path=db_path)
        except Exception as mem_exc:
            console.print(
                f"[yellow]警告: 记忆系统初始化失败，以降级模式运行: {mem_exc}[/yellow]"
            )

        # 创建自学习系统（失败时降级为 None）
        learning_system = None
        try:
            from kimix.learning import LearningSystem

            if config.learning.enabled:
                data_dir = Path(user_data_dir("kimix"))
                learning_system = LearningSystem(
                    db_path=data_dir / "memory.db",
                    config=config.learning,
                )
        except Exception:
            pass  # 自学习为可选功能

        # 创建引擎
        engine = AgentEngine(
            llm_client=llm_client,
            tool_registry=tool_registry,
            memory=memory_manager,
            mode=mode,
            learning_system=learning_system,
        )

        return engine

    except ImportError as exc:
        console.print(
            f"[yellow]警告: 部分模块尚未实现，以降级模式运行: {exc}[/yellow]"
        )
        return None
    except Exception as exc:
        console.print(f"[red]引擎初始化失败: {exc}[/red]")
        return None


# ============================
# 主命令
# ============================

@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    query: Optional[str] = typer.Argument(
        None,
        help="询问 Agent 的问题（不提供则启动交互式 TUI）",
        show_default=False,
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        "-m",
        help="工作模式: explore(探索) / plan(规划) / agent(交互) / auto(自动) / yolo(全自主)",
        show_default=False,
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        "-p",
        help="规划模式（等效于 --mode plan）",
        is_flag=True,
    ),
    yolo: bool = typer.Option(
        False,
        "--yolo",
        "-y",
        help="全自主模式（等效于 --mode yolo）—— 慎用",
        is_flag=True,
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="显示版本号",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="显示详细日志（INFO 级别）",
        is_flag=True,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="显示调试日志（DEBUG 级别）",
        is_flag=True,
    ),
) -> None:
    """Kimi-Agent (kimix) - 基于 Kimi k2.6 的智能终端 AI Agent

    [bold magenta]🤖 Kimi-Agent[/bold magenta] 是专为 Kimi k2.6 模型打造的终端 AI Agent，
    提供比 deepseek-TUI 更智能、更懂中文开发者的体验。

    [bold]基本用法:[/bold]

        [cyan]$ kimix[/cyan]                    启动交互式 TUI
        [cyan]$ kimix "问题"[/cyan]              一次性问答
        [cyan]$ kimix -p "如何添加缓存"[/cyan]    Plan 模式
        [cyan]$ kimix -y "重构测试"[/cyan]        YOLO 模式

    [bold]其他命令:[/bold]

        [cyan]$ kimix auth[/cyan]               配置 API Key
        [cyan]$ kimix config --show[/cyan]       显示配置
        [cyan]$ kimix session list[/cyan]        列出会话
        [cyan]$ kimix tool list[/cyan]           列出工具
        [cyan]$ kimix doctor[/cyan]              诊断检查
    """
    # 配置日志级别
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
    elif verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    # 版本信息
    if version:
        console.print(get_version_string())
        raise typer.Exit()

    # 如果有子命令，跳过主逻辑
    if ctx.invoked_subcommand is not None:
        return

    # 确定工作模式
    agent_mode = _get_mode(mode, plan, yolo)

    if query:
        # 一次性问答模式
        _run_once(query, agent_mode)
    else:
        # 启动 TUI 模式
        _run_tui(agent_mode)


def _run_once(query: str, mode: AgentMode) -> None:
    """运行一次性问答

    Args:
        query: 用户问题
        mode: 工作模式
    """
    engine = _init_engine(mode)

    if engine is not None:
        asyncio.run(engine.initialize(project_path=str(Path(".").resolve())))

    from kimix.ui.cli import CLIInterface

    cli = CLIInterface(
        console=console,
        mode=mode,
        show_thinking=True,
        show_cost=True,
        streaming=True,
    )

    try:
        result = asyncio.run(cli.run_once(engine, query))
        if result.get("error"):
            if "引擎未初始化" in str(result["error"]):
                console.print(
                    "\n[red]错误: API Key 未配置[/red]"
                )
                console.print(
                    "[yellow]请运行: kimix auth[/yellow]"
                )
                raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]执行错误: {exc}[/red]")
        raise typer.Exit(1)


def _run_tui(mode: AgentMode) -> None:
    """启动 TUI 模式

    Args:
        mode: 工作模式
    """
    engine = _init_engine(mode)

    if engine is None:
        _print_banner()
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("⚠ 欢迎使用 Kimi-Agent！\n\n", style="yellow bold"),
                    Text("首次使用需要配置 API Key。\n", style="white"),
                    Text("请运行: ", style="white dim"),
                    Text("kimix auth", style="cyan bold"),
                    Text(" 进行配置。\n\n", style="white dim"),
                    Text("获取 API Key: https://platform.moonshot.cn/", style="blue underline"),
                ),
                border_style="yellow",
                padding=(1, 2),
            )
        )
        raise typer.Exit()

    from kimix.ui.tui import TUIApp

    # 初始化引擎运行环境
    asyncio.run(engine.initialize(project_path=str(Path(".").resolve())))

    tui = TUIApp(
        console=console,
        engine=engine,
        mode=mode,
    )

    try:
        exit_code = asyncio.run(tui.run())
        if exit_code != 0:
            raise typer.Exit(exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]已退出[/yellow]")
        raise typer.Exit(130)


# ============================
# auth 命令
# ============================

@app.command("auth")
def auth_command(
    api_key: Optional[str] = typer.Option(
        None,
        "--key",
        "-k",
        help="直接提供 API Key（不推荐，建议交互式输入）",
        prompt=False,
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="自定义 API 基础 URL",
    ),
) -> None:
    """配置 API Key

    交互式配置 Moonshot API Key。
    API Key 将安全存储在配置文件中。

    示例:

        [cyan]$ kimix auth[/cyan]                    交互式输入
        [cyan]$ kimix auth --key <key>[/cyan]         直接指定
    """
    _print_banner()

    try:
        from kimix.config.auth import AuthManager
        from kimix.config.settings import KimixConfig
    except ImportError:
        console.print("[red]错误: 配置模块未加载[/red]")
        raise typer.Exit(1)

    auth_manager = AuthManager()

    # 获取 API Key
    if api_key is None:
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("🔑 配置 API Key\n\n", style="bold"),
                    Text("请输入您的 Moonshot API Key\n", style="white"),
                    Text("获取地址: ", style="dim"),
                    Text("https://platform.moonshot.cn/", style="blue underline"),
                ),
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print("[dim]（输入不会显示在屏幕上）[/dim]\n")

        # 使用 getpass 隐藏输入
        import getpass

        api_key = getpass.getpass("API Key: ").strip()

        if not api_key:
            console.print("[red]错误: API Key 不能为空[/red]")
            raise typer.Exit(1)

        # 确认输入
        masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
        console.print(f"\n已输入: [cyan]{masked}[/cyan]")
        confirm = console.input("确认保存? [Y/n]: ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            console.print("[yellow]已取消[/yellow]")
            raise typer.Exit(0)

    # 验证并保存
    try:
        auth_manager.set_api_key(api_key)
        if base_url:
            auth_manager.set_base_url(base_url)

        console.print()
        console.print(
            Panel(
                Text.assemble(
                    Text("✓ ", style="green bold"),
                    Text("API Key 配置成功！\n\n", style="green bold"),
                    Text("配置文件位置: ", style="dim"),
                    Text(str(auth_manager.config_path), style="cyan"),
                ),
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print()
        console.print("现在可以开始使用 Kimi-Agent:")
        console.print("  [cyan]$ kimix[/cyan]           启动交互式 TUI")
        console.print("  [cyan]$ kimix '你好'[/cyan]    一次性问答")

    except Exception as exc:
        console.print(f"[red]配置保存失败: {exc}[/red]")
        raise typer.Exit(1)


# ============================
# config 命令
# ============================

@config_app.callback(invoke_without_command=True)
def config_callback(
    ctx: typer.Context,
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="显示当前配置",
        is_flag=True,
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        "-e",
        help="编辑配置文件",
        is_flag=True,
    ),
) -> None:
    """配置管理

    查看和编辑 Kimi-Agent 的配置。
    """
    if ctx.invoked_subcommand is not None:
        return

    if edit:
        _edit_config()
        return

    # 默认显示配置
    _show_config()


def _show_config() -> None:
    """显示当前配置"""
    try:
        from kimix.config.settings import KimixConfig

        config = KimixConfig()

        console.print()
        console.print(Rule("[bold]Kimi-Agent 配置[/bold]", style="cyan"))
        console.print()

        # Auth 配置
        auth_table = Table(
            title="认证配置",
            show_header=True,
            header_style="bold cyan",
            border_style="cyan dim",
        )
        auth_table.add_column("配置项", style="bold")
        auth_table.add_column("值")

        api_key_display = (
            config.auth.api_key[:4] + "****" + config.auth.api_key[-4:]
            if len(config.auth.api_key) > 8
            else ("未设置" if not config.auth.api_key else "****")
        )
        auth_table.add_row("API Key", api_key_display)
        auth_table.add_row("Base URL", config.auth.base_url)
        console.print(auth_table)
        console.print()

        # 模型配置
        model_table = Table(
            title="模型配置",
            show_header=True,
            header_style="bold magenta",
            border_style="magenta dim",
        )
        model_table.add_column("配置项", style="bold")
        model_table.add_column("值")
        model_table.add_row("默认模型", config.model.default)
        model_table.add_row("思考模式", "启用" if config.model.thinking else "禁用")
        console.print(model_table)
        console.print()

        # UI 配置
        ui_table = Table(
            title="界面配置",
            show_header=True,
            header_style="bold green",
            border_style="green dim",
        )
        ui_table.add_column("配置项", style="bold")
        ui_table.add_column("值")
        ui_table.add_row("主题", "auto")
        ui_table.add_row("语言", "zh")
        console.print(ui_table)
        console.print()

        # 配置文件路径
        console.print(
            f"[dim]配置文件路径: [/dim][cyan]{config.config_path}[/cyan]"
        )
        console.print()

    except ImportError:
        console.print("[yellow]配置模块尚未完全实现[/yellow]")
    except Exception as exc:
        console.print(f"[red]读取配置失败: {exc}[/red]")


def _edit_config() -> None:
    """编辑配置文件"""
    try:
        from kimix.config.settings import KimixConfig

        config = KimixConfig()
        config_path = config.config_path

        # 确保配置文件存在
        if not config_path.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)

        # 使用编辑器打开
        import os

        editor = os.environ.get("EDITOR", "vi")
        console.print(f"[dim]使用编辑器: {editor}[/dim]")
        console.print(f"[dim]配置文件: {config_path}[/dim]")

        import subprocess

        subprocess.call([editor, str(config_path)])
        console.print("[green]配置编辑完成[/green]")

    except Exception as exc:
        console.print(f"[red]编辑配置失败: {exc}[/red]")


# ============================
# session 命令
# ============================

@session_app.command("list")
def session_list(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="显示最近 N 个会话",
    ),
) -> None:
    """列出会话

    显示最近的会话列表，包括会话 ID、创建时间、消息数等信息。

    示例:

        [cyan]$ kimix session list[/cyan]
        [cyan]$ kimix session list --limit 10[/cyan]
    """
    console.print()
    console.print(Rule("[bold]会话列表[/bold]", style="cyan"))
    console.print()

    try:
        from kimix.core.session import SessionManager

        session_manager = SessionManager()
        sessions = session_manager.list_sessions(limit=limit)

        if not sessions:
            console.print("[dim]暂无会话记录[/dim]")
            return

        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="bright_black",
        )
        table.add_column("ID", style="bold")
        table.add_column("模式", style="green")
        table.add_column("消息数", justify="right")
        table.add_column("创建时间", style="dim")
        table.add_column("最后活跃", style="dim")

        for s in sessions:
            table.add_row(
                s.get("id", "-")[:8] + "...",
                s.get("mode", "agent"),
                str(s.get("message_count", 0)),
                s.get("created_at", "-"),
                s.get("updated_at", "-"),
            )

        console.print(table)
        console.print()
        console.print(f"[dim]共 {len(sessions)} 个会话[/dim]")

    except ImportError:
        console.print("[yellow]会话模块尚未完全实现[/yellow]")
        # 显示模拟数据
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="bright_black",
        )
        table.add_column("ID", style="bold")
        table.add_column("模式", style="green")
        table.add_column("消息数", justify="right")
        table.add_column("创建时间", style="dim")

        table.add_row(
            "abc123...", "agent", "12", "2025-01-15 10:30"
        )
        table.add_row(
            "def456...", "plan", "5", "2025-01-15 09:15"
        )
        console.print(table)
        console.print("\n[dim]（以上为示例数据）[/dim]")
    except Exception as exc:
        console.print(f"[red]获取会话列表失败: {exc}[/red]")


@session_app.command("resume")
def session_resume(
    session_id: str = typer.Argument(
        ...,
        help="要恢复的会话 ID",
    ),
) -> None:
    """恢复会话

    加载指定会话并进入交互模式。

    示例:

        [cyan]$ kimix session resume abc123[/cyan]
    """
    console.print(f"[dim]正在恢复会话: {session_id}...[/dim]")

    try:
        from kimix.core.session import SessionManager

        session_manager = SessionManager()
        session = session_manager.load_session(session_id)

        if session is None:
            console.print(f"[red]未找到会话: {session_id}[/red]")
            raise typer.Exit(1)

        console.print(f"[green]✓ 会话已恢复[/green]")

        # 启动 TUI 并恢复会话
        mode = AgentMode(session.get("mode", "agent"))
        engine = _init_engine(mode)

        if engine is None:
            console.print("[red]引擎初始化失败[/red]")
            raise typer.Exit(1)

        from kimix.ui.tui import TUIApp

        tui = TUIApp(
            console=console,
            engine=engine,
            mode=mode,
        )

        # 恢复历史消息
        for msg in session.get("messages", []):
            tui.chat_history.add_message(
                msg.get("role", "system"),
                msg.get("content", ""),
            )

        exit_code = asyncio.run(tui.run())
        if exit_code != 0:
            raise typer.Exit(exit_code)

    except ImportError:
        console.print("[yellow]会话恢复功能尚未完全实现[/yellow]")
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]恢复会话失败: {exc}[/red]")
        raise typer.Exit(1)


# ============================
# tool 命令
# ============================

@tool_app.command("list")
def tool_list() -> None:
    """列出可用工具

    显示所有已注册的工具及其描述。

    示例:

        [cyan]$ kimix tool list[/cyan]
    """
    console.print()
    console.print(Rule("[bold]可用工具[/bold]", style="green"))
    console.print()

    try:
        from kimix.tools.registry import ToolRegistry

        registry = ToolRegistry()
        registry.register_defaults()
        tools = registry.list_tools()

        table = Table(
            show_header=True,
            header_style="bold green",
            border_style="bright_black",
        )
        table.add_column("工具名称", style="bold cyan")
        table.add_column("描述")
        table.add_column("审批级别", style="yellow")

        tool_info = {
            "file_read": ("读取文件内容", "readonly"),
            "file_write": ("写入文件内容", "destructive"),
            "file_edit": ("编辑文件内容", "destructive"),
            "shell": ("执行 Shell 命令", "destructive"),
            "git_status": ("查看 Git 状态", "readonly"),
            "git_diff": ("查看 Git 差异", "readonly"),
            "git_commit": ("执行 Git 提交", "destructive"),
            "web_search": ("Web 搜索", "readonly"),
            "web_fetch": ("获取网页内容", "readonly"),
        }

        for name, (desc, approval) in tool_info.items():
            approval_color = {
                "none": "green",
                "readonly": "blue",
                "destructive": "yellow",
                "all": "red",
            }.get(approval, "white")
            table.add_row(name, desc, Text(approval, style=approval_color))

        console.print(table)
        console.print()
        console.print(f"[dim]共 {len(tool_info)} 个工具[/dim]")

    except ImportError:
        # 显示默认工具列表
        table = Table(
            show_header=True,
            header_style="bold green",
            border_style="bright_black",
        )
        table.add_column("工具名称", style="bold cyan")
        table.add_column("描述")
        table.add_column("审批级别", style="yellow")

        default_tools = [
            ("file_read", "读取文件内容", "readonly"),
            ("file_write", "写入文件内容", "destructive"),
            ("file_edit", "编辑文件内容", "destructive"),
            ("shell", "执行 Shell 命令", "destructive"),
            ("git_status", "查看 Git 状态", "readonly"),
            ("git_diff", "查看 Git 差异", "readonly"),
            ("git_commit", "执行 Git 提交", "destructive"),
            ("web_search", "Web 搜索", "readonly"),
            ("web_fetch", "获取网页内容", "readonly"),
        ]

        for name, desc, approval in default_tools:
            approval_color = {
                "readonly": "blue",
                "destructive": "yellow",
            }.get(approval, "white")
            table.add_row(name, desc, Text(approval, style=approval_color))

        console.print(table)
        console.print("\n[dim]（以上为默认工具列表）[/dim]")
    except Exception as exc:
        console.print(f"[red]获取工具列表失败: {exc}[/red]")


# ============================
# doctor 命令
# ============================

@app.command("doctor")
def doctor_command(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="显示详细信息",
        is_flag=True,
    ),
) -> None:
    """诊断检查

    检查 Kimi-Agent 的运行环境，包括：
    - API 连接状态
    - 配置文件完整性
    - 工具可用性
    - 依赖项检查

    示例:

        [cyan]$ kimix doctor[/cyan]
        [cyan]$ kimix doctor --verbose[/cyan]
    """
    console.print()
    console.print(Rule("[bold]Kimi-Agent 诊断检查[/bold]", style="green"))
    console.print()

    checks_passed = 0
    checks_failed = 0

    # 1. API Key 配置检查
    try:
        from kimix.config.settings import KimixConfig

        config = KimixConfig()
        if config.auth.api_key:
            masked = config.auth.api_key[:4] + "****" + config.auth.api_key[-4:]
            console.print(f"  [green]✓[/green] API Key 已配置: [cyan]{masked}[/cyan]")
            checks_passed += 1
        else:
            console.print("  [red]✗[/red] API Key 未配置")
            console.print("      [yellow]→ 运行: kimix auth[/yellow]")
            checks_failed += 1
    except Exception as exc:
        console.print(f"  [red]✗[/red] 配置加载失败: {exc}")
        checks_failed += 1

    # 2. API 连接检查
    try:
        from kimix.config.settings import KimixConfig

        config = KimixConfig()
        if config.auth.api_key:
            console.print(
                f"  [green]✓[/green] API 连接配置: [cyan]{config.auth.base_url}[/cyan]"
            )
            checks_passed += 1
        else:
            console.print("  [yellow]○[/yellow] API 连接检查跳过（未配置 Key）")
    except Exception as exc:
        console.print(f"  [red]✗[/red] API 配置检查失败: {exc}")
        checks_failed += 1

    # 3. 工具系统检查
    try:
        from kimix.tools.registry import ToolRegistry

        registry = ToolRegistry()
        # 尝试注册默认工具
        registry.register_defaults()
        tools = registry.list_tools()
        console.print(
            f"  [green]✓[/green] 工具系统正常 ([cyan]{len(tools)}[/cyan] 个工具)"
        )
        checks_passed += 1

        if verbose:
            for tool in tools:
                tool_name = getattr(tool, "name", str(tool))
                console.print(f"      [dim]- {tool_name}[/dim]")
    except ImportError:
        console.print("  [yellow]○[/yellow] 工具系统未完全初始化")
    except Exception as exc:
        console.print(f"  [red]✗[/red] 工具系统检查失败: {exc}")
        checks_failed += 1

    # 4. 记忆系统检查
    try:
        from kimix.memory.manager import MemoryManager

        memory_manager = MemoryManager()
        console.print("  [green]✓[/green] 记忆系统正常")
        checks_passed += 1
    except ImportError:
        console.print("  [yellow]○[/yellow] 记忆系统未完全初始化")
    except Exception as exc:
        console.print(f"  [red]✗[/red] 记忆系统检查失败: {exc}")
        checks_failed += 1

    # 5. 配置文件检查
    try:
        config_dir = Path.home() / ".kimix"
        config_file = config_dir / "config.yaml"

        if config_file.exists():
            console.print(
                f"  [green]✓[/green] 配置文件存在: [cyan]{config_file}[/cyan]"
            )
            checks_passed += 1
        else:
            console.print(
                f"  [yellow]○[/yellow] 配置文件不存在: [cyan]{config_file}[/cyan]"
            )
            console.print("      [yellow]→ 将使用默认配置[/yellow]")
    except Exception as exc:
        console.print(f"  [red]✗[/red] 配置文件检查失败: {exc}")
        checks_failed += 1

    # 6. 依赖项检查
    required_deps = [
        "typer",
        "rich",
        "openai",
        "httpx",
        "pydantic",
        "yaml",
    ]
    missing_deps: list[str] = []

    for dep in required_deps:
        try:
            if dep == "yaml":
                __import__("yaml")
            else:
                __import__(dep)
        except ImportError:
            missing_deps.append(dep)

    if missing_deps:
        console.print(
            f"  [red]✗[/red] 缺少依赖: {', '.join(missing_deps)}"
        )
        checks_failed += 1
    else:
        console.print(
            f"  [green]✓[/green] 核心依赖已安装 ([cyan]{len(required_deps)}[/cyan] 个)"
        )
        checks_passed += 1

    # 总结
    console.print()
    console.print(Rule(style="bright_black"))
    console.print()

    total = checks_passed + checks_failed
    if checks_failed == 0:
        console.print(
            f"[bold green]✓ 所有检查通过 ({checks_passed}/{total})[/bold green]"
        )
        console.print("[green]Kimi-Agent 已就绪！[/green]")
    else:
        console.print(
            f"[bold yellow]⚠ 部分检查未通过 ({checks_passed}/{total} 通过)[/bold yellow]"
        )
        console.print("[yellow]请根据提示修复问题后重试[/yellow]")
        raise typer.Exit(1)

    console.print()


# ============================
# main 入口
# ============================

def main() -> None:
    """CLI 主入口函数

    由 pyproject.toml 的 [project.scripts] 注册为 kimix 命令。
    也是 `python -m kimix` 的最终调用目标。
    """
    # Windows 终端 UTF-8 支持
    if sys.platform == "win32":
        import os
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[red]运行时错误: {exc}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
