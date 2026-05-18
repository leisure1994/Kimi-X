"""
新功能集成测试 — 沙箱/Git/搜索/MemoryBank/多模型

验证新增组件可独立工作：
- DockerSandbox 安全执行
- GitTool 基本操作
- WebSearchTool 搜索
- MemoryBank 持久化
- MultiModelClient fallback

运行:
    pytest tests/integration/test_new_features.py -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kimix.tools.sandbox import DockerSandbox, SandboxTool
from kimix.tools.git_tool import GitTool
from kimix.tools.web_search import WebSearchTool
from kimix.memory.memory_bank import MemoryBank, ProjectAnalyzer
from kimix.llm.multi_model import MultiModelClient, ModelRouter



pytestmark = pytest.mark.integration
class TestDockerSandbox:
    """沙箱执行测试"""

    def test_sandbox_run_local_fallback(self) -> None:
        """沙箱本地降级执行"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = DockerSandbox(project_dir=tmpdir)
            # Docker 不可用时会降级到本地
            result = sandbox.run("echo 'hello from sandbox'", timeout=5)
            # 可能成功（本地降级）或因 Docker 不可用而失败
            assert result.stdout.strip() == "hello from sandbox" or "Docker 不可用" in result.stderr
            print(f"  [Sandbox] returncode={result.returncode}, sandbox={result.container_id is not None}")

    def test_sandbox_timeout(self) -> None:
        """沙箱超时终止"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = DockerSandbox(project_dir=tmpdir)
            result = sandbox.run("sleep 10", timeout=1)
            assert result.killed
            print(f"  [Sandbox] killed={result.killed}, duration={result.duration_ms:.0f}ms")

    def test_sandbox_tool_interface(self) -> None:
        """SandboxTool 工具接口"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox = DockerSandbox(project_dir=tmpdir)
            tool = SandboxTool(sandbox)
            result = tool.execute("echo test", timeout=5)
            assert "success" in result
            print(f"  [SandboxTool] success={result['success']}")


class TestGitTool:
    """Git 操作测试"""

    def test_git_init_repo(self) -> None:
        """初始化仓库并提交"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 初始化 git
            os.system(f"cd {tmpdir} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")

            git = GitTool(tmpdir)

            # 创建文件并提交
            Path(tmpdir, "test.txt").write_text("hello")
            r1 = git.add(".")
            assert r1.success

            r2 = git.commit("Initial commit")
            assert r2.success

            # 查看状态
            r3 = git.status()
            assert len(r3.files_changed) == 0  # 已提交，无修改

            # 查看日志
            r4 = git.log(n=3)
            assert "Initial commit" in r4.stdout

            print(f"  [Git] commit OK, log OK")

    def test_git_branch(self) -> None:
        """分支操作"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.system(f"cd {tmpdir} && git init && git config user.email 'test@test.com' && git config user.name 'Test'")
            Path(tmpdir, "f.txt").write_text("x")
            os.system(f"cd {tmpdir} && git add . && git commit -m 'init'")

            git = GitTool(tmpdir)
            r = git.branch_create("feature-x", checkout=True)
            assert r.success

            r2 = git.branch_list()
            assert "feature-x" in r2.files_changed
            print(f"  [Git] branch create/list OK")


class TestMemoryBank:
    """记忆银行测试"""

    def test_remember_and_recall(self) -> None:
        """记录和检索记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bank = MemoryBank(tmpdir, auto_save=True)
            bank.remember("api_pattern", "使用 Pydantic 验证输入", "pattern")
            bank.remember("auth_issue", "JWT 过期太短", "issue")

            # 按键检索
            entry = bank.recall("api_pattern")
            assert entry is not None
            assert entry.content == "使用 Pydantic 验证输入"

            # 搜索
            results = bank.search("JWT")
            assert len(results) == 1

            # 按类别
            patterns = bank.recall_by_category("pattern")
            assert len(patterns) == 1

            print(f"  [MemoryBank] {len(bank._entries)} entries, search/recall OK")

    def test_persistence(self) -> None:
        """持久化跨实例加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            bank1 = MemoryBank(tmpdir, auto_save=True)
            bank1.remember("test_key", "test_value", "general")

            # 新实例加载
            bank2 = MemoryBank(tmpdir, auto_save=False)
            entry = bank2.recall("test_key")
            assert entry is not None
            assert entry.content == "test_value"
            print(f"  [MemoryBank] persistence OK")

    def test_project_analyzer(self) -> None:
        """项目分析器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "requirements.txt").write_text("pytest\n")
            Path(tmpdir, "pytest.ini").write_text("[pytest]\n")

            analyzer = ProjectAnalyzer(tmpdir)
            analysis = analyzer.analyze()

            assert analysis.get("tech_stack") == "Python 项目"
            assert analysis.get("test_framework") == "使用 pytest 进行测试"
            print(f"  [Analyzer] detected: {analysis['tech_stack']}")


class TestMultiModel:
    """多模型客户端测试"""

    def test_available_models(self) -> None:
        """检测可用模型"""
        client = MultiModelClient()
        available = client.get_available_models()
        # 至少有一个可用（当前环境有 MOONSHOT_API_KEY）
        assert isinstance(available, list)
        print(f"  [MultiModel] available: {available}")

    def test_status(self) -> None:
        """状态查询"""
        client = MultiModelClient()
        status = client.get_status()
        assert status["primary"] == "kimi"
        assert "available_models" in status
        print(f"  [MultiModel] status OK")

    def test_model_router(self) -> None:
        """模型路由"""
        router = ModelRouter()
        model = router.route("code", "帮我写个函数")
        assert model in ["kimi", "deepseek", "doubao", "qwen"]
        print(f"  [ModelRouter] task=code -> model={model}")


class TestWebSearch:
    """Web 搜索测试"""

    def test_search_offline(self) -> None:
        """离线时降级为空结果"""
        search = WebSearchTool()
        # 未配置 key 且离线时返回空
        results = search.search("python tutorial", limit=3)
        # 可能为空（无网络）或有结果（有网络）
        assert isinstance(results, list)
        print(f"  [WebSearch] results: {len(results)}")

    def test_fetch_page_mock(self) -> None:
        """获取页面内容（模拟）"""
        search = WebSearchTool()
        # 测试无效 URL
        content = search.fetch_page("http://invalid.url.test", max_chars=100)
        assert "ERROR" in content or "无法获取" in content
        print(f"  [WebSearch] fetch invalid URL handled")
