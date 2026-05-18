"""
Pytest 配置和共享 Fixtures

提供测试所需的共享资源:
- event_loop: asyncio 事件循环
- temp_dir: 临时目录
- mock_llm_client: Mock LLM 客户端
- mock_tool_registry: Mock 工具注册表
- sample_config: 示例配置
- sample_session: 示例会话
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from kimix.config import KimixConfig
from kimix.core.session import Session
from kimix.tools.base import ToolContext


# ---------------------------------------------------------------------------
# Pytest 配置
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    """Pytest 全局配置"""
    config.addinivalue_line("markers", "unit: 单元测试标记")
    config.addinivalue_line("markers", "integration: 集成测试标记")
    config.addinivalue_line("markers", "asyncio: 异步测试标记")


# ---------------------------------------------------------------------------
# 事件循环 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """提供会话级的事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 临时目录 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir() -> Path:
    """提供临时目录，测试结束后自动清理"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def temp_git_repo(temp_dir: Path) -> Path:
    """提供临时 Git 仓库目录"""
    import subprocess
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_dir, capture_output=True, check=True,
    )
    (temp_dir / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=temp_dir, capture_output=True, check=True,
    )
    return temp_dir


# ---------------------------------------------------------------------------
# Mock LLM 客户端 Fixture
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Mock LLM 客户端 - 模拟 KimiClient 的行为"""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or []
        self.call_history: list[list[dict[str, Any]]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """模拟流式聊天响应"""
        self.call_history.append(messages)
        for resp in self.responses:
            yield resp

    async def chat_with_thinking(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
    ) -> tuple[str, str]:
        """模拟非流式聊天响应"""
        self.call_history.append(messages)
        return "thinking content", "response content"


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """提供 Mock LLM 客户端"""
    return MockLLMClient()


@pytest.fixture
def mock_llm_factory():
    """提供 Mock LLM 客户端工厂函数"""
    def _factory(responses: list[dict[str, Any]] | None = None) -> MockLLMClient:
        return MockLLMClient(responses=responses)
    return _factory


# ---------------------------------------------------------------------------
# Mock 工具注册表 Fixture
# ---------------------------------------------------------------------------

class MockToolRegistry:
    """Mock 工具注册表"""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        self._tools = tools or {}
        self.call_log: list[str] = []

    def get(self, tool_name: str) -> Any:
        """获取工具"""
        self.call_log.append(f"get:{tool_name}")
        if tool_name not in self._tools:
            raise KeyError(f"工具未注册: {tool_name}")
        return self._tools[tool_name]

    def list_tools(self) -> list[Any]:
        """列出所有工具"""
        return list(self._tools.values())

    def register(self, tool: Any) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def has(self, tool_name: str) -> bool:
        """检查工具是否存在"""
        return tool_name in self._tools


@pytest.fixture
def mock_tool_registry() -> MockToolRegistry:
    """提供 Mock 工具注册表"""
    return MockToolRegistry()


# ---------------------------------------------------------------------------
# 示例配置 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config() -> KimixConfig:
    """提供示例配置"""
    return KimixConfig(
        model={"default": "kimi-k2.6", "max_tokens": 4096},
        auth={"api_key": "test-key"},
        tools={"file_max_size": 1048576},
    )


# ---------------------------------------------------------------------------
# 示例会话 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_session() -> Session:
    """提供示例会话"""
    return Session(
        id="sess-test001",
        name="测试会话",
        project_path="/tmp/test-project",
    )


# ---------------------------------------------------------------------------
# 工具上下文 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def tool_context(temp_dir: Path) -> ToolContext:
    """提供工具执行上下文"""
    return ToolContext(
        work_dir=str(temp_dir),
        session_id="test-session",
    )


# ---------------------------------------------------------------------------
# Mock 记忆管理器 Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """提供 Mock 记忆管理器"""
    memory = MagicMock()
    memory.recall = AsyncMock(return_value=[])
    memory.store = AsyncMock(return_value=None)
    memory.consolidate = AsyncMock(return_value={
        "cached_files": 0,
        "variables": 0,
        "tool_cache_cleared": True,
    })
    return memory
