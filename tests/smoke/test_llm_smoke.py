"""
LLM 冒烟测试

使用真实 API Key 测试 LLM 调用链路完整性。
仅在配置了 MOONSHOT_API_KEY 时运行。

运行方式:
    MOONSHOT_API_KEY=sk-xxxxx pytest tests/smoke/test_llm_smoke.py -v
"""

from __future__ import annotations

import os

import pytest

from kimix.llm.client import KimiClient
from kimix.llm.models import Message

pytestmark = pytest.mark.smoke

SKIP_REASON = "未配置 MOONSHOT_API_KEY 环境变量，跳过真实 LLM 冒烟测试"


@pytest.mark.skipif(
    not os.environ.get("MOONSHOT_API_KEY"),
    reason=SKIP_REASON,
)
@pytest.mark.asyncio
@pytest.mark.timeout(30)
class TestLLMSmoke:
    """LLM 真实调用冒烟测试"""

    @pytest.fixture
    def client(self) -> KimiClient:
        """创建真实 LLM 客户端"""
        api_key = os.environ["MOONSHOT_API_KEY"]
        return KimiClient(
            api_key=api_key,
            thinking=False,  # 冒烟测试不需要 thinking，减少 token 消耗
        )

    @pytest.mark.timeout(60)
    def test_basic_chat_completion(self, client: KimiClient) -> None:
        """测试基础聊天补全"""
        messages = [Message.system("你是一个助手"), Message.user("你好，请回复'测试通过'")]
        response = client.chat(messages)
        assert response is not None
        assert len(response.content) > 0
        print(f"响应: {response.content[:100]}")

    @pytest.mark.timeout(60)
    def test_streaming_response(self, client: KimiClient) -> None:
        """测试流式响应"""
        messages = [Message.user("列举3种水果，只回复水果名称")]
        chunks = list(client.chat(messages, stream=True))
        assert len(chunks) > 0
        full_text = "".join(c.content for c in chunks)
        assert len(full_text) > 0
        print(f"流式响应: {full_text[:100]}")

    @pytest.mark.timeout(60)
    def test_token_counting(self, client: KimiClient) -> None:
        """测试 token 计数"""
        messages = [Message.user("Hello world")]
        response = client.chat(messages)
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
        print(f"Token 使用: input={response.usage.input_tokens}, output={response.usage.output_tokens}")

    @pytest.mark.timeout(60)
    def test_multi_turn_conversation(self, client: KimiClient) -> None:
        """测试多轮对话"""
        history = []
        for i in range(3):
            history.append(Message.user(f"这是第{i+1}轮对话，请回复'收到{i+1}'"))
            response = client.chat(history)
            history.append(Message.assistant(response.content))
            assert "收到" in response.content
        assert len(history) == 6

    @pytest.mark.timeout(60)
    def test_long_context(self, client: KimiClient) -> None:
        """测试长上下文处理能力"""
        long_text = "Python是一种编程语言。" * 1000
        messages = [Message.user(f"请总结以下文本（限制20字内）：\n\n{long_text}")]
        response = client.chat(messages)
        assert len(response.content) <= 50
        print(f"长上下文摘要: {response.content[:50]}")

    @pytest.mark.timeout(60)
    def test_tool_calling_capability(self, client: KimiClient) -> None:
        """测试工具调用能力（如果模型支持）"""
        messages = [Message.user("使用计算器工具计算 123 * 456")]
        # 这里只是验证 API 能正常响应，不验证具体工具调用结果
        response = client.chat(messages)
        assert response is not None
        print(f"工具调用测试响应: {response.content[:100]}")
