"""默认配置常量模块.

定义 Kimi-Agent 所有配置项的默认值，包括:
- API 连接参数
- 模型参数
- 工作模式设置
- 内存系统参数
- 子 Agent 编排参数
- 工具系统参数
- 沙箱安全参数
- 成本控制参数
- UI 显示参数

所有常量均使用大写命名规范，便于识别和统一管理。
"""

from __future__ import annotations

# ========================
# 认证相关默认值
# ========================

DEFAULT_API_BASE_URL: str = "https://api.kimi.com/coding/v1"
"""Kimi API 默认基础 URL."""

DEFAULT_MODEL: str = "kimi-for-coding"
"""默认使用的 Kimi 模型名称."""

DEFAULT_MAX_TOKENS: int = 16384
"""默认最大生成 Token 数."""

DEFAULT_TEMPERATURE: float = 0.7
"""默认采样温度，控制输出的随机性."""

# ========================
# 工作模式默认值
# ========================

DEFAULT_MODE: str = "agent"
"""默认工作模式，可选: explore, plan, agent, auto, yolo."""

YOLO_CONFIRM: bool = False
"""YOLO 模式下是否要求确认."""

AUTO_APPROVAL_THRESHOLD: float = 0.8
"""自动审批门控阈值 (0.0 ~ 1.0)."""

# ========================
# 记忆系统默认值
# ========================

MEMORY_ENABLED: bool = True
"""是否启用记忆系统."""

DEFAULT_DB_NAME: str = "memory.db"
"""默认 SQLite 数据库文件名."""

MAX_WORKING_CACHE_MB: int = 100
"""工作记忆最大缓存大小（MB）."""

SEMANTIC_INDEX_ENABLED: bool = True
"""是否启用语义索引."""

# ========================
# 子 Agent 编排默认值
# ========================

DEFAULT_MAX_CONCURRENT: int = 32
"""默认最大并发子 Agent 数量."""

MAX_CONCURRENT_LIMIT: int = 64
"""最大允许的并发子 Agent 数量上限."""

SUBAGENT_TIMEOUT: int = 300
"""子 Agent 默认超时时间（秒）."""

AUTO_CANCEL_ON_ERROR: bool = False
"""子 Agent 出错时是否自动取消其他任务."""

# ========================
# 工具系统默认值
# ========================

DEFAULT_ENABLED_TOOLS: list[str] = [
    "file_read",
    "file_write",
    "file_edit",
    "shell",
    "git",
    "web_search",
    "web_fetch",
    "subagent",
]
"""默认启用的工具列表."""

# ========================
# 沙箱安全默认值
# ========================

SANDBOX_ENABLED: bool = True
"""是否启用沙箱隔离."""

DEFAULT_ALLOWED_PATHS: list[str] = ["."]
"""默认允许访问的路径列表."""

DEFAULT_BLOCKED_COMMANDS: list[str] = [
    # 系统破坏性命令
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "> /dev/sda",
    "mkfs.",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # Fork 炸弹
    "while true; do",
    
    # 权限提升命令
    "chmod -R 777 /",
    "chown -R root",
    
    # 网络攻击命令
    "nc -l -p",
    "ncat -l",
    
    # 系统修改命令
    "init 0",
    "init 6",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "systemctl poweroff",
    "systemctl reboot",
    
    # 管道到危险目标
    "> /etc/passwd",
    "> /etc/shadow",
    "> /etc/hosts",
]
"""默认禁止的危险命令列表."""

DEFAULT_BLOCKED_PATTERNS: list[str] = [
    # 路径遍历
    "..",
    "~/.ssh",
    "~/.gnupg",
    "/etc/passwd",
    "/etc/shadow",
    "/etc/hosts",
    "/proc/",
    "/sys/",
]
"""默认禁止访问的路径模式."""

# ========================
# 成本控制默认值
# ========================

BUDGET_LIMIT: float = 0.0
"""预算上限（美元），0 表示无限制."""

WARNING_THRESHOLD: float = 10.0
"""成本警告阈值（美元）."""

CACHE_OPTIMIZATION: bool = True
"""是否启用缓存优化."""

SHOW_REALTIME_COST: bool = True
"""是否实时显示成本."""

# ========================
# UI 显示默认值
# ========================

DEFAULT_THEME: str = "auto"
"""默认主题，可选: auto, dark, light."""

DEFAULT_LANGUAGE: str = "zh"
"""默认界面语言，可选: zh, en."""

DEFAULT_STREAMING_SPEED: str = "fast"
"""默认流式输出速度，可选: fast, normal, slow."""

SHOW_THINKING: bool = True
"""是否显示思考过程."""

SHOW_COST: bool = True
"""是否显示成本信息."""

# ========================
# 目录和文件路径
# ========================

CONFIG_DIR_NAME: str = ".kimix"
"""配置目录名称."""

CONFIG_FILE_NAME: str = "config.yaml"
"""配置文件名称."""

LOGS_DIR_NAME: str = "logs"
"""日志目录名称."""

MAX_LOG_FILE_SIZE_MB: int = 10
"""单个日志文件最大大小（MB）."""

MAX_LOG_BACKUP_COUNT: int = 5
"""日志文件最大备份数量."""

# ========================
# 网络相关默认值
# ========================

DEFAULT_REQUEST_TIMEOUT: int = 120
"""默认 HTTP 请求超时时间（秒）."""

DEFAULT_MAX_RETRIES: int = 3
"""默认最大重试次数."""

DEFAULT_RETRY_DELAY: float = 1.0
"""默认重试间隔（秒）."""

# ========================
# 流式输出默认值
# ========================

STREAMING_SPEED_MAP: dict[str, float] = {
    "fast": 0.01,
    "normal": 0.03,
    "slow": 0.08,
}
"""流式输出速度映射（字符间隔，秒）."""

# ========================
# 健康检查默认值
# ========================

HEALTH_CHECK_TIMEOUT: int = 10
"""健康检查超时时间（秒）."""

# ========================
# 自学习系统默认值
# ========================

LEARNING_ENABLED: bool = True
"""是否启用自学习系统."""

LEARNING_MAX_EXPERIENCES: int = 1000
"""最大存储经验条数."""

LEARNING_REFLECTION_THRESHOLD: float = 0.6
"""经验反射触发阈值（任务成功率低于此值时强制反射）."""

LEARNING_MAX_INJECTED_TOKENS: int = 500
"""每轮注入的最大经验 tokens."""

LEARNING_SIMILARITY_THRESHOLD: float = 0.3
"""经验检索的 Jaccard 相似度阈值."""

LEARNING_EMA_ALPHA: float = 0.3
"""策略优化 EMA 平滑系数."""

LEARNING_EVOLUTION_MIN_SAMPLES: int = 10
"""Prompt 演化所需最少样本数."""

LEARNING_EVOLUTION_IMPROVEMENT_THRESHOLD: float = 0.05
"""Prompt 演化改进阈值（低于此值回滚）."""
