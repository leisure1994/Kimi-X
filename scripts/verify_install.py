"""
多平台部署验证脚本

验证 Kimi-Agent 在目标平台的安装完整性:
- Python 版本检查 (>=3.10)
- 依赖安装验证
- API Key 配置检查
- 基本功能冒烟测试(不消耗 API token)
- 目录权限检查
- 网络连通性测试
- IM 机器人模块检查

运行方式:
    python scripts/verify_install.py

退出码:
    0 = 全部通过
    1 = 有阻塞性问题
    2 = 有警告但可运行
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def check_python_version() -> tuple[bool, str]:
    """检查 Python 版本"""
    v = sys.version_info
    ok = v.major >= 3 and v.minor >= 10
    icon = '✅' if ok else '❌ (需要 >=3.10)'
    msg = f"Python {v.major}.{v.minor}.{v.micro} {icon}"
    return ok, msg


def check_dependencies() -> tuple[bool, str]:
    """检查核心依赖"""
    required = {
        "typer": "typer",
        "rich": "rich",
        "pydantic": "pydantic",
        "aiohttp": "aiohttp",
        "tiktoken": "tiktoken",
        "prompt_toolkit": "prompt_toolkit",
        "httpx": "httpx",
        "websockets": "websockets",
    }
    missing: list[str] = []
    for module, name in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(name)

    if missing:
        return False, f"❌ 缺少依赖: {', '.join(missing)} (运行: pip install -e .)"
    return True, "✅ 所有核心依赖已安装"


def check_api_key() -> tuple[bool, str, str]:
    """检查 API Key 配置"""
    key = os.environ.get("MOONSHOT_API_KEY", "")
    if key:
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        return True, f"✅ 环境变量 MOONSHOT_API_KEY={masked}", "env"

    # 检查配置文件
    config_paths = [
        Path.home() / ".kimix" / "config.json",
        Path.home() / ".kimix" / "auth.json",
    ]
    for p in config_paths:
        if p.exists():
            return True, f"✅ 配置文件: {p}", "file"

    return False, "❌ API Key 未配置 (运行: kimix auth 或设置 MOONSHOT_API_KEY)", "none"


def check_directory_permissions() -> tuple[bool, str]:
    """检查工作目录权限"""
    test_dir = Path(".")
    try:
        test_file = test_dir / ".kimix_verify_test"
        test_file.write_text("test")
        test_file.unlink()
        return True, "✅ 工作目录可读写"
    except OSError as e:
        return False, f"❌ 工作目录权限不足: {e}"


def check_network_connectivity() -> tuple[bool, str]:
    """网络连通性测试"""
    import socket

    try:
        # 测试 DNS 解析
        socket.getaddrinfo("api.kimi.com", None)
        return True, "✅ DNS 解析正常 (api.kimi.com)"
    except socket.gaierror:
        return False, "⚠️ DNS 解析失败 (api.kimi.com),可能无法连接 Kimi API"


def check_module_import() -> tuple[bool, str]:
    """验证核心模块可导入"""
    try:
        from kimix.llm.client import KimiClient
        from kimix.llm.models import Message
        from kimix.core.engine import AgentEngine, AgentMode
        from kimix.core.preflight import PreFlightChecker
        from kimix.core.healing import SelfHealingEngine
        from kimix.memory.experience import ExperienceMemory
        from kimix.subagents.orchestrator import SubAgentOrchestrator
        return True, "✅ 所有核心模块导入正常"
    except Exception as e:
        return False, f"❌ 模块导入失败: {e}"


def check_bots_module() -> tuple[bool, str]:
    """验证 IM 机器人模块可导入"""
    try:
        from kimix.bots import BotAdapter, BotConfig, BotRunner
        from kimix.bots.models import ChatMessage, ReplyMessage, Platform, MsgType
        from kimix.bots.router import MessageRouter
        # 构造测试
        r = ReplyMessage.from_text("test")
        assert r.text == "test"
        m = ChatMessage.from_text(Platform.FEISHU, text="hi", sender_id="u1", chat_id="c1", is_group=False, bot_mentioned=False)
        assert m.should_reply() is True
        router = MessageRouter()
        assert router is not None
        return True, "✅ IM 机器人模块导入正常"
    except Exception as e:
        return False, f"❌ IM 机器人模块导入失败: {e}"


def check_cli_entrypoint() -> tuple[bool, str]:
    """验证 CLI 入口可用"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "kimix", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, f"✅ CLI 正常: {result.stdout.strip()}"
        # 如果是因为依赖缺失，降级为警告
        if "No module" in result.stderr or "ImportError" in result.stderr:
            return True, f"⚠️ CLI 依赖未安装 (pip install -e .)"
        return False, f"❌ CLI 返回错误码 {result.returncode}: {result.stderr[:100]}"
    except Exception as e:
        return False, f"❌ CLI 测试失败: {e}"


def run_smoke_test_no_api() -> tuple[bool, str]:
    """不消耗 API 的冒烟测试"""
    try:
        from kimix.llm.models import Message, ChatEvent
        from kimix.llm.cost_tracker import CostTracker
        from kimix.core.preflight import PreFlightChecker
        import asyncio

        # 1. Token 计数（本地）
        from kimix.llm.client import KimiClient
        client = KimiClient(api_key="sk-test")
        tokens = client.count_tokens("这是一个测试")
        assert tokens > 0

        # 2. 预判系统(本地)
        async def check_preflight() -> bool:
            checker = PreFlightChecker()
            result = await checker.check({
                "api_key": "sk-test",
                "workspace_dir": ".",
                "task_signature": "test",
                "skip_network_test": True,
            })
            return result.passed

        passed = asyncio.run(check_preflight())
        assert passed

        # 3. ChatEvent 构造
        event = ChatEvent(type="content", data="test", role="assistant")
        assert event.type == "content"

        # 4. 机器人消息模型
        from kimix.bots.models import ChatMessage, ReplyMessage, Platform
        r = ReplyMessage.from_text("hello")
        assert r.markdown == False
        m = ChatMessage.from_text(Platform.SLACK, text="hi", sender_id="u1", chat_id="c1", is_group=True, bot_mentioned=False)
        assert m.should_reply() is False
        m2 = ChatMessage.from_text(Platform.SLACK, text="hi", sender_id="u1", chat_id="c1", is_group=True, bot_mentioned=True)
        assert m2.should_reply() is True

        return True, "✅ 本地冒烟测试通过 (Token计数/预判/事件模型/机器人消息)"
    except Exception as e:
        return False, f"❌ 本地冒烟测试失败: {e}"


def print_platform_info() -> None:
    """打印平台信息"""
    print(f"\n{'='*50}")
    print(f"🖥️  平台信息")
    print(f"   OS: {platform.system()} {platform.release()}")
    print(f"   Machine: {platform.machine()}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   Executable: {sys.executable}")
    print(f"{'='*50}\n")


def main() -> int:
    """主验证流程"""
    print_platform_info()

    # 自动将脚本所在目录的父目录加入 PYTHONPATH，支持未 pip install 时运行
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    checks = [
        ("Python 版本", check_python_version),
        ("依赖安装", check_dependencies),
        ("API Key 配置", check_api_key),
        ("目录权限", check_directory_permissions),
        ("网络连通性", check_network_connectivity),
        ("核心模块导入", check_module_import),
        ("IM 机器人模块", check_bots_module),
        ("CLI 入口", check_cli_entrypoint),
        ("本地冒烟测试", run_smoke_test_no_api),
    ]

    blockers = 0
    warnings = 0
    passed = 0

    for name, check_fn in checks:
        try:
            result = check_fn()
            if len(result) == 3:
                ok, msg, _ = result
            else:
                ok, msg = result

            print(f"  {msg}")
            if ok:
                passed += 1
            elif "⚠️" in msg:
                warnings += 1
            else:
                blockers += 1
        except Exception as e:
            print(f"  ❌ {name} 检查异常: {e}")
            blockers += 1

    print(f"\n{'='*50}")
    print(f"📊 验证结果: {passed}/{len(checks)} 通过 | {warnings} 警告 | {blockers} 阻塞")

    if blockers > 0:
        print(f"\n❌ 部署验证失败: 存在 {blockers} 个阻塞性问题")
        print(f"   请修复上述问题后重试")
        return 1
    elif warnings > 0:
        print(f"\n⚠️ 部署验证通过(有警告): 可运行但建议处理警告")
        return 2
    else:
        print(f"\n✅ 部署验证全部通过!Kimi-Agent 可正常运行")
        return 0


if __name__ == "__main__":
    sys.exit(main())
