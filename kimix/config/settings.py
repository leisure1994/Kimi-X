"""配置加载管理模块.

提供统一的配置管理入口，支持以下配置来源（按优先级从高到低）:
1. 环境变量（如 KIMIX_AUTH__API_KEY）
2. YAML 配置文件（~/.kimix/config.yaml）
3. 代码默认值

使用 Pydantic v2 Settings 进行数据验证和类型转换，
确保配置值始终符合预期类型和约束。

示例:
    >>> from kimix.config import KimixConfig
    >>> config = KimixConfig()
    >>> print(config.auth.api_key)
    >>> print(config.model.default)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from kimix.config import defaults


# ========================
# 子配置模型
# ========================


class AuthConfig(BaseSettings):
    """API 认证配置.

    Attributes:
        api_key: Moonshot API Key，用于访问 Kimi API
        base_url: API 基础 URL，默认为官方地址
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_AUTH__",
        env_file=".env",
        extra="ignore",
    )

    api_key: str = Field(
        default="",
        description="Moonshot API Key",
    )
    base_url: str = Field(
        default=defaults.DEFAULT_API_BASE_URL,
        description="API 基础 URL",
    )


class ModelConfig(BaseSettings):
    """模型参数配置.

    Attributes:
        default: 默认使用的模型名称
        thinking: 是否启用思考模式
        max_tokens: 最大生成 Token 数
        temperature: 采样温度
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_MODEL__",
        extra="ignore",
    )

    default: str = Field(
        default=defaults.DEFAULT_MODEL,
        description="默认模型名称",
    )
    thinking: bool = Field(
        default=True,
        description="是否启用思考模式",
    )
    max_tokens: int = Field(
        default=defaults.DEFAULT_MAX_TOKENS,
        ge=1,
        le=65536,
        description="最大生成 Token 数",
    )
    temperature: float = Field(
        default=defaults.DEFAULT_TEMPERATURE,
        ge=0.0,
        le=2.0,
        description="采样温度",
    )


class ModesConfig(BaseSettings):
    """工作模式配置.

    Attributes:
        default: 默认工作模式
        yolo_confirm: YOLO 模式下是否要求确认
        auto_approval_threshold: 自动审批门控阈值
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_MODES__",
        extra="ignore",
    )

    default: str = Field(
        default=defaults.DEFAULT_MODE,
        description="默认工作模式",
    )
    yolo_confirm: bool = Field(
        default=defaults.YOLO_CONFIRM,
        description="YOLO 模式确认开关",
    )
    auto_approval_threshold: float = Field(
        default=defaults.AUTO_APPROVAL_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="自动审批阈值",
    )

    @field_validator("default")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """验证工作模式值."""
        allowed = {"explore", "plan", "agent", "auto", "yolo"}
        if v not in allowed:
            raise ValueError(f"无效的工作模式: {v!r}，可选: {allowed}")
        return v


class MemoryConfig(BaseSettings):
    """记忆系统配置.

    Attributes:
        enabled: 是否启用记忆系统
        db_path: SQLite 数据库路径
        max_working_cache: 工作记忆最大缓存（MB）
        semantic_index: 是否启用语义索引
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_MEMORY__",
        extra="ignore",
    )

    enabled: bool = Field(
        default=defaults.MEMORY_ENABLED,
        description="记忆系统开关",
    )
    db_path: str = Field(
        default=f"~/{defaults.CONFIG_DIR_NAME}/{defaults.DEFAULT_DB_NAME}",
        description="数据库路径",
    )
    max_working_cache: int = Field(
        default=defaults.MAX_WORKING_CACHE_MB,
        ge=10,
        le=1000,
        description="工作记忆缓存上限（MB）",
    )
    semantic_index: bool = Field(
        default=defaults.SEMANTIC_INDEX_ENABLED,
        description="语义索引开关",
    )


class SubagentsConfig(BaseSettings):
    """子 Agent 编排配置.

    Attributes:
        max_concurrent: 最大并发子 Agent 数量
        timeout: 子 Agent 超时时间（秒）
        auto_cancel_on_error: 出错时是否自动取消其他任务
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_SUBAGENTS__",
        extra="ignore",
    )

    max_concurrent: int = Field(
        default=defaults.DEFAULT_MAX_CONCURRENT,
        ge=1,
        le=defaults.MAX_CONCURRENT_LIMIT,
        description="最大并发数",
    )
    timeout: int = Field(
        default=defaults.SUBAGENT_TIMEOUT,
        ge=30,
        le=3600,
        description="超时时间（秒）",
    )
    auto_cancel_on_error: bool = Field(
        default=defaults.AUTO_CANCEL_ON_ERROR,
        description="错误时自动取消开关",
    )


class ToolsConfig(BaseSettings):
    """工具系统配置.

    Attributes:
        enabled: 启用的工具列表
        disabled: 禁用的工具列表
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_TOOLS__",
        extra="ignore",
    )

    enabled: list[str] = Field(
        default_factory=list,
        description="启用的工具列表",
    )
    disabled: list[str] = Field(
        default_factory=list,
        description="禁用的工具列表",
    )

    @field_validator("enabled", mode="before")
    @classmethod
    def set_default_enabled(cls, v: list[str] | None) -> list[str]:
        """如果未指定，使用默认工具列表."""
        if not v:
            return defaults.DEFAULT_ENABLED_TOOLS.copy()
        return v


class SandboxConfig(BaseSettings):
    """沙箱安全配置.

    Attributes:
        enabled: 是否启用沙箱
        allowed_paths: 允许访问的路径列表
        blocked_commands: 禁止执行的命令列表
        network: 是否允许网络访问
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_SANDBOX__",
        extra="ignore",
    )

    enabled: bool = Field(
        default=defaults.SANDBOX_ENABLED,
        description="沙箱开关",
    )
    allowed_paths: list[str] = Field(
        default_factory=lambda: defaults.DEFAULT_ALLOWED_PATHS.copy(),
        description="允许访问的路径",
    )
    blocked_commands: list[str] = Field(
        default_factory=lambda: defaults.DEFAULT_BLOCKED_COMMANDS.copy(),
        description="禁止的命令",
    )
    network: bool = Field(
        default=True,
        description="网络访问开关",
    )


class CostConfig(BaseSettings):
    """成本控制配置.

    Attributes:
        budget_limit: 预算上限（美元），0 表示无限制
        warning_threshold: 成本警告阈值（美元）
        cache_optimization: 是否启用缓存优化
        show_realtime: 是否实时显示成本
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_COST__",
        extra="ignore",
    )

    budget_limit: float = Field(
        default=defaults.BUDGET_LIMIT,
        ge=0.0,
        description="预算上限（美元）",
    )
    warning_threshold: float = Field(
        default=defaults.WARNING_THRESHOLD,
        ge=0.0,
        description="警告阈值（美元）",
    )
    cache_optimization: bool = Field(
        default=defaults.CACHE_OPTIMIZATION,
        description="缓存优化开关",
    )
    show_realtime: bool = Field(
        default=defaults.SHOW_REALTIME_COST,
        description="实时成本显示开关",
    )


class LearningConfig(BaseSettings):
    """自学习系统配置.

    Attributes:
        enabled: 是否启用自学习系统
        max_experiences: 最大存储经验条数
        reflection_threshold: 反射触发阈值
        max_injected_tokens: 每轮注入的最大经验 tokens
        similarity_threshold: 经验检索相似度阈值
        ema_alpha: 策略优化 EMA 平滑系数
        evolution_min_samples: Prompt 演化所需最少样本数
        evolution_improvement_threshold: Prompt 演化改进阈值
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_LEARNING__",
        extra="ignore",
    )

    enabled: bool = Field(
        default=defaults.LEARNING_ENABLED,
        description="自学习系统开关",
    )
    max_experiences: int = Field(
        default=defaults.LEARNING_MAX_EXPERIENCES,
        ge=100,
        le=10000,
        description="最大存储经验条数",
    )
    reflection_threshold: float = Field(
        default=defaults.LEARNING_REFLECTION_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="反射触发阈值",
    )
    max_injected_tokens: int = Field(
        default=defaults.LEARNING_MAX_INJECTED_TOKENS,
        ge=50,
        le=2000,
        description="每轮注入最大经验 tokens",
    )
    similarity_threshold: float = Field(
        default=defaults.LEARNING_SIMILARITY_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="经验检索相似度阈值",
    )
    ema_alpha: float = Field(
        default=defaults.LEARNING_EMA_ALPHA,
        ge=0.0,
        le=1.0,
        description="EMA 平滑系数",
    )
    evolution_min_samples: int = Field(
        default=defaults.LEARNING_EVOLUTION_MIN_SAMPLES,
        ge=5,
        le=100,
        description="演化所需最少样本数",
    )
    evolution_improvement_threshold: float = Field(
        default=defaults.LEARNING_EVOLUTION_IMPROVEMENT_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="演化改进阈值",
    )


class UIConfig(BaseSettings):
    """UI 显示配置.

    Attributes:
        theme: 主题设置
        language: 界面语言
        streaming_speed: 流式输出速度
        show_thinking: 是否显示思考过程
        show_cost: 是否显示成本
    """

    model_config = SettingsConfigDict(
        env_prefix="KIMIX_UI__",
        extra="ignore",
    )

    theme: str = Field(
        default=defaults.DEFAULT_THEME,
        description="主题",
    )
    language: str = Field(
        default=defaults.DEFAULT_LANGUAGE,
        description="界面语言",
    )
    streaming_speed: str = Field(
        default=defaults.DEFAULT_STREAMING_SPEED,
        description="流式输出速度",
    )
    show_thinking: bool = Field(
        default=defaults.SHOW_THINKING,
        description="思考过程显示开关",
    )
    show_cost: bool = Field(
        default=defaults.SHOW_COST,
        description="成本显示开关",
    )

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """验证主题值."""
        allowed = {"auto", "dark", "light"}
        if v not in allowed:
            raise ValueError(f"无效的主题: {v!r}，可选: {allowed}")
        return v

    @field_validator("streaming_speed")
    @classmethod
    def validate_speed(cls, v: str) -> str:
        """验证流式速度值."""
        allowed = {"fast", "normal", "slow"}
        if v not in allowed:
            raise ValueError(f"无效的速度: {v!r}，可选: {allowed}")
        return v


# ========================
# 主配置类
# ========================


class KimixConfig(BaseSettings):
    """Kimi-Agent 全局配置管理类.

    统一的配置入口，整合所有子配置模块。配置加载优先级:
    1. 环境变量（格式: KIMIX_<SECTION>__<KEY>）
    2. YAML 配置文件（~/.kimix/config.yaml）
    3. 代码默认值

    Attributes:
        auth: API 认证配置
        model: 模型参数配置
        modes: 工作模式配置
        memory: 记忆系统配置
        subagents: 子 Agent 编排配置
        tools: 工具系统配置
        sandbox: 沙箱安全配置
        cost: 成本控制配置
        ui: UI 显示配置

    示例:
        >>> config = KimixConfig()
        >>> print(config.auth.api_key)
        >>> print(config.model.default)
        >>> print(config.sandbox.enabled)
    """

    model_config = SettingsConfigDict(
        # 环境变量前缀
        env_prefix="KIMIX_",
        # 忽略未知字段
        extra="ignore",
        # 大小写敏感
        case_sensitive=False,
    )

    auth: AuthConfig = Field(default_factory=AuthConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    modes: ModesConfig = Field(default_factory=ModesConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    subagents: SubagentsConfig = Field(default_factory=SubagentsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    def __init__(self, **kwargs: Any) -> None:
        """初始化配置，从 YAML 文件加载后与环境变量合并.

        Args:
            **kwargs: 直接传入的配置值，优先级最高
        """
        # 从 YAML 文件加载配置
        yaml_data = self._load_yaml_config()

        # 合并 YAML 数据和传入的参数（传入的参数优先级更高）
        merged = {**yaml_data, **kwargs}

        # 调用父类初始化
        super().__init__(**merged)

    @staticmethod
    def _get_config_path() -> Path:
        """获取配置文件路径.

        配置文件位于用户主目录下的 ~/.kimix/config.yaml

        Returns:
            Path: 配置文件绝对路径
        """
        home = Path.home()
        config_dir = home / defaults.CONFIG_DIR_NAME
        return config_dir / defaults.CONFIG_FILE_NAME

    @classmethod
    def _load_yaml_config(cls) -> dict[str, Any]:
        """从 YAML 配置文件加载配置.

        解析 YAML 文件并处理环境变量引用（格式: ${VAR_NAME}）

        Returns:
            dict: 解析后的配置字典，文件不存在或解析失败时返回空字典
        """
        config_path = cls._get_config_path()

        if not config_path.exists():
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 处理环境变量引用: ${VAR_NAME}
            import re

            def replace_env_var(match: re.Match) -> str:
                """替换环境变量引用为实际值."""
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))

            content = re.sub(r"\$\{([^}]+)\}", replace_env_var, content)

            data = yaml.safe_load(content) or {}
            return data if isinstance(data, dict) else {}

        except yaml.YAMLError as exc:
            print(f"警告: YAML 配置文件解析失败: {exc}")
            return {}
        except OSError as exc:
            print(f"警告: 无法读取配置文件: {exc}")
            return {}

    @property
    def config_dir(self) -> Path:
        """获取配置目录路径.

        Returns:
            Path: 配置目录绝对路径 (~/.kimix)
        """
        return Path.home() / defaults.CONFIG_DIR_NAME

    @property
    def logs_dir(self) -> Path:
        """获取日志目录路径.

        Returns:
            Path: 日志目录绝对路径 (~/.kimix/logs)
        """
        return self.config_dir / defaults.LOGS_DIR_NAME

    def ensure_directories(self) -> None:
        """确保配置目录和日志目录存在.

        在启动时调用，自动创建必要的目录结构
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
        """将配置导出为字典.

        Returns:
            dict: 包含所有配置项的字典
        """
        return self.model_dump()

    def dump_yaml(self) -> str:
        """将配置导出为 YAML 字符串.

        Returns:
            str: YAML 格式的配置字符串
        """
        return yaml.safe_dump(
            self.to_dict(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def save_to_file(self, path: Path | None = None) -> None:
        """将配置保存到 YAML 文件.

        Args:
            path: 目标文件路径，默认使用 ~/.kimix/config.yaml
        """
        target = path or self._get_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.dump_yaml())
