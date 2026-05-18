"""
Kimi-Agent 工具系统

提供完整的工具注册、发现和执行机制，包含以下工具类别：
- 文件操作工具（读、写、编辑、补丁、目录列表、搜索等）
- Shell 执行工具（带沙箱保护）
- Git 操作工具（状态、差异、日志、分支）
- Web 工具（搜索、URL 获取）
- 子 Agent 工具（预留接口）
- 系统工具（通知、任务列表）

Usage:
    from kimix.tools import ToolRegistry, Tool, ToolResult

    # 创建注册表并自动发现所有工具
    registry = ToolRegistry()
    registry.auto_discover()

    # 获取 OpenAI 格式的工具模式
    schema = registry.to_openai_schema()

    # 执行工具
    tool = registry.get("file_read")
    result = await tool.execute({"file_path": "README.md"}, ToolContext())
"""

from __future__ import annotations

from .base import (
    AbstractTool,
    ApprovalLevel,
    Tool,
    ToolCall,
    ToolCallResult,
    ToolContext,
    ToolResult,
)
from .registry import ToolRegistry

# 导出文件工具
from .file_tools import (
    ApplyPatchTool,
    EditFileTool,
    FileSearchTool,
    GetFileInfoTool,
    GrepFilesTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)

# 导出 Shell 工具
from .shell_tools import ShellTool

# 导出 Git 工具
from .git_tools import (
    GitBranchTool,
    GitDiffTool,
    GitLogTool,
    GitStatusTool,
)

# 导出 Web 工具
from .web_tools import FetchUrlTool, WebSearchTool

# 导出子 Agent 工具
from .agent_tools import (
    AgentCloseTool,
    AgentEvalTool,
    AgentOpenTool,
)

# 导出系统工具
from .system_tools import NotifyTool, TodoTool

__all__ = [
    # 基类与核心模型
    "AbstractTool",
    "Tool",
    "ToolContext",
    "ToolResult",
    "ToolCall",
    "ToolCallResult",
    "ApprovalLevel",
    # 注册表
    "ToolRegistry",
    # 文件工具
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ApplyPatchTool",
    "ListDirTool",
    "GrepFilesTool",
    "FileSearchTool",
    "GetFileInfoTool",
    # Shell 工具
    "ShellTool",
    # Git 工具
    "GitStatusTool",
    "GitDiffTool",
    "GitLogTool",
    "GitBranchTool",
    # Web 工具
    "WebSearchTool",
    "FetchUrlTool",
    # 子 Agent 工具
    "AgentOpenTool",
    "AgentEvalTool",
    "AgentCloseTool",
    # 系统工具
    "NotifyTool",
    "TodoTool",
]

# 工具系统版本
TOOL_SYSTEM_VERSION = "1.0.0"
