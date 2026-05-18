"""
多模型客户端 — 支持 fallback 切换

当主模型（Kimi）不可用时，自动降级到备用模型：
- 主模型: Kimi K2.6
- 备用 1: DeepSeek V4
- 备用 2: Doubao Pro
- 备用 3: Qwen Max

自动切换策略：
1. API 错误（5xx/超时）→ 立即切换
2. Rate limit (429) → 指数退避后重试，仍失败切换
3. 内容审核拒绝 → 切换模型重试
4. 全部失败 → 返回错误

配置方式:
    client = MultiModelClient(
        primary="kimi",
        fallback_order=["deepseek", "doubao", "qwen"],
    )
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from kimix.llm.models import Message


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    api_key_env: str
    base_url: str | None = None
    model_id: str | None = None


# 内置模型配置
BUILT_IN_MODELS: dict[str, ModelConfig] = {
    "kimi": ModelConfig(
        name="kimi",
        api_key_env="MOONSHOT_API_KEY",
        base_url="https://api.kimi.com/v1",
        model_id="kimi-k2-6",
    ),
    "deepseek": ModelConfig(
        name="deepseek",
        api_key_env="DEEPSEEK_V4_API_KEY",
        base_url="https://api.deepseek.com/v1",
        model_id="deepseek-v4-pro",
    ),
    "doubao": ModelConfig(
        name="doubao",
        api_key_env="DOUBAO_API_KEY_2",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model_id="doubao-pro-128k",
    ),
    "qwen": ModelConfig(
        name="qwen",
        api_key_env="QWEN_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_id="qwen-max",
    ),
}


class MultiModelClient:
    """多模型客户端（带 fallback）

    用法:
        client = MultiModelClient()
        messages = [Message.user("你好")]

        # 同步风格（自动 fallback）
        async for event in client.chat(messages):
            print(event)

        # 查看当前使用的模型
        print(f"实际使用: {client.last_used_model}")
    """

    def __init__(
        self,
        primary: str = "kimi",
        fallback_order: list[str] | None = None,
        models: dict[str, ModelConfig] | None = None,
    ) -> None:
        """初始化多模型客户端

        Args:
            primary: 主模型名称
            fallback_order: 备用模型顺序
            models: 自定义模型配置
        """
        self.primary = primary
        self.fallback_order = fallback_order or ["deepseek", "doubao", "qwen"]
        self.models = models or BUILT_IN_MODELS

        self.last_used_model: str | None = None
        self._clients: dict[str, Any] = {}

    def _get_client(self, model_name: str) -> Any | None:
        """获取指定模型的客户端（懒加载）"""
        if model_name in self._clients:
            return self._clients[model_name]

        cfg = self.models.get(model_name)
        if not cfg:
            return None

        api_key = os.environ.get(cfg.api_key_env)
        if not api_key:
            return None

        # 根据模型类型创建对应客户端
        try:
            if model_name == "kimi":
                from kimix.llm.client import KimiClient
                client = KimiClient(api_key=api_key)
            else:
                # 通用 OpenAI-compatible 客户端
                from kimix.llm.client import KimiClient  # 复用相同接口
                client = KimiClient(
                    api_key=api_key,
                    base_url=cfg.base_url,
                    default_model=cfg.model_id or model_name,
                )
            self._clients[model_name] = client
            return client
        except Exception:
            return None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = True,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """聊天（自动 fallback）

        依次尝试主模型 → 备用模型，直到成功。
        """
        errors: list[str] = []
        models_to_try = [self.primary] + self.fallback_order

        for model_name in models_to_try:
            client = self._get_client(model_name)
            if not client:
                errors.append(f"{model_name}: 未配置 API key")
                continue

            try:
                self.last_used_model = model_name
                async for event in client.chat(
                    messages=messages,
                    stream=stream,
                    temperature=temperature,
                    **kwargs,
                ):
                    # 标记来源模型
                    if isinstance(event, dict):
                        event["_model"] = model_name
                    yield event
                return  # 成功完成

            except Exception as e:
                error_msg = str(e)
                errors.append(f"{model_name}: {error_msg}")

                # 判断是否需要切换
                if self._should_fallback(error_msg):
                    continue  # 尝试下一个模型
                else:
                    # 不可恢复错误，直接抛出
                    break

        # 全部失败
        yield {
            "type": "error",
            "data": {
                "message": f"所有模型均失败: {'; '.join(errors)}",
                "code": "ALL_MODELS_FAILED",
                "recoverable": False,
            },
        }

    def _should_fallback(self, error: str) -> bool:
        """判断错误是否应该触发 fallback"""
        fallback_signals = [
            "timeout",
            "connection",
            "rate limit",
            "429",
            "503",
            "500",
            "overload",
            "content moderation",  # 内容审核，换模型可能通过
            "invalid api key",  # 也可能是配置问题
        ]
        error_lower = error.lower()
        return any(sig in error_lower for sig in fallback_signals)

    def get_available_models(self) -> list[str]:
        """获取当前可用的模型列表"""
        available = []
        for name, cfg in self.models.items():
            if os.environ.get(cfg.api_key_env):
                available.append(name)
        return available

    def get_status(self) -> dict[str, Any]:
        """获取客户端状态"""
        return {
            "primary": self.primary,
            "fallback_order": self.fallback_order,
            "available_models": self.get_available_models(),
            "last_used": self.last_used_model,
        }


class ModelRouter:
    """智能模型路由 — 根据任务类型选择最优模型"""

    # 任务类型 → 推荐模型
    TASK_MODEL_MAP: dict[str, str] = {
        "code": "kimi",           # 代码生成用 Kimi
        "math": "deepseek",       # 数学推理用 DeepSeek
        "chat": "doubao",         # 对话用 Doubao
        "analysis": "qwen",       # 分析用 Qwen
        "translation": "kimi",    # 翻译用 Kimi（中文优势）
    }

    def __init__(self, multi_client: MultiModelClient | None = None) -> None:
        self.client = multi_client or MultiModelClient()

    def route(self, task_type: str, user_input: str) -> str:
        """根据任务类型选择模型"""
        # 1. 按任务类型映射
        preferred = self.TASK_MODEL_MAP.get(task_type, "kimi")

        # 2. 检查可用性
        available = self.client.get_available_models()
        if preferred in available:
            return preferred

        # 3. 降级到第一个可用
        for fallback in self.client.fallback_order:
            if fallback in available:
                return fallback

        # 4. 全部不可用，返回主模型（会失败，但给出明确错误）
        return self.client.primary
