"""
工作模式基类模块

定义所有工作模式的抽象基类和通用类型。
每个具体模式继承 BaseMode，实现 process 方法定义自己的行为逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from kimix.core.events import EngineEvent


class ApprovalLevel(Enum):
    """审批级别枚举
    
    定义工具执行前需要的审批严格程度：
    
    - NONE: 无需审批，直接执行
    - READONLY: 只读操作无需审批，写入需审批
    - DESTRUCTIVE: 只有破坏性操作需审批
    - ALL: 所有操作都需要审批
    """
    NONE = "none"
    READONLY = "readonly"
    DESTRUCTIVE = "destructive"
    ALL = "all"


# 引擎协议（避免循环导入）
@runtime_checkable
class EngineLike(Protocol):
    """引擎协议，模式实现中使用的引擎接口"""
    @property
    def mode(self) -> Any: ...

    async def run(self, user_input: str) -> AsyncIterator[EngineEvent]: ...

    async def execute_tools(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def cognitive_analysis(self, user_input: str) -> dict[str, Any]: ...


class BaseMode(ABC):
    """工作模式抽象基类
    
    所有工作模式的基类，定义了模式的基本属性和行为接口。
    
    Attributes:
        name: 模式名称（英文标识）
        description: 模式描述（中文说明）
        approval_level: 审批级别
        supports_thinking: 是否支持 thinking 模式
    
    Examples:
        >>> class MyMode(BaseMode):
        ...     name = "my_mode"
        ...     description = "我的自定义模式"
        ...     approval_level = ApprovalLevel.DESTRUCTIVE
        ...     supports_thinking = True
        ...
        ...     async def process(self, engine, user_input):
        ...         yield create_content_event("处理中...")
    """

    # 模式元数据（子类必须覆盖）
    name: str = ""
    description: str = ""
    approval_level: ApprovalLevel = ApprovalLevel.DESTRUCTIVE
    supports_thinking: bool = True

    @abstractmethod
    async def process(
        self,
        engine: EngineLike,
        user_input: str,
    ) -> AsyncIterator[EngineEvent]:
        """处理用户输入
        
        模式的核心方法，定义该模式下如何处理用户请求。
        通过 AsyncIterator 产生事件流。
        
        Args:
            engine: Agent 引擎实例
            user_input: 用户输入文本
        
        Yields:
            EngineEvent 事件流
        
        Examples:
            >>> async for event in mode.process(engine, "帮我分析代码"):
            ...     print(event["type"])
        """
        ...

    def should_approve(self, tool_name: str, tool_params: dict[str, Any] | None = None) -> bool:
        """判断指定工具是否需要审批
        
        根据当前模式的审批级别和工具特性决定是否需用户确认。
        
        Args:
            tool_name: 工具名称
            tool_params: 工具参数（用于更精细的判断）
        
        Returns:
            True 如果需要审批，False 如果可直接执行
        
        Examples:
            >>> mode.should_approve("file_read")
            False  # Explore 模式下只读操作无需审批
            >>> mode.should_approve("file_write")
            True   # 写入操作需要审批
        """
        # 只读工具列表
        read_only_tools = {
            "file_read", "file_list", "file_search",
            "git_status", "git_log", "git_diff", "git_show",
            "web_search", "web_fetch",
        }

        # 破坏性工具列表
        destructive_tools = {
            "file_delete", "shell", "git_reset", "git_checkout_force",
        }

        level = self.approval_level

        if level == ApprovalLevel.NONE:
            # 所有操作都无需审批
            return False

        elif level == ApprovalLevel.ALL:
            # 所有操作都需审批
            return True

        elif level == ApprovalLevel.READONLY:
            # 只读操作无需审批，其他需审批
            return tool_name not in read_only_tools

        elif level == ApprovalLevel.DESTRUCTIVE:
            # 只有破坏性操作需审批
            if tool_name in destructive_tools:
                return True
            # 写入操作也需审批（覆盖文件风险）
            write_tools = {"file_write", "file_edit", "file_create"}
            if tool_name in write_tools:
                return True
            return False

        # 默认保守策略
        return True

    def is_readonly_tool(self, tool_name: str) -> bool:
        """判断工具是否为只读工具
        
        Args:
            tool_name: 工具名称
        
        Returns:
            True 如果是只读工具
        """
        read_only_tools = {
            "file_read", "file_list", "file_search",
            "git_status", "git_log", "git_diff", "git_show",
            "web_search", "web_fetch",
        }
        return tool_name in read_only_tools

    def is_destructive_tool(self, tool_name: str, params: dict[str, Any] | None = None) -> bool:
        """判断工具是否为破坏性工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
        
        Returns:
            True 如果是破坏性工具/操作
        """
        destructive_tools = {
            "file_delete", "shell", "git_reset", "git_checkout_force",
            "git_clean", "git_revert",
        }
        if tool_name in destructive_tools:
            return True

        # 检查参数中的危险性
        if params and tool_name == "shell":
            command = str(params.get("command", "")).lower()
            dangerous = ["rm -rf", "> /dev", "mkfs", "dd if=", ":(){:|:&};:"]
            if any(d in command for d in dangerous):
                return True

        return False

    def get_mode_info(self) -> dict[str, Any]:
        """获取模式信息
        
        Returns:
            模式元数据字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "approval_level": self.approval_level.value,
            "supports_thinking": self.supports_thinking,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"

    def __str__(self) -> str:
        return f"[{self.name.upper()}] {self.description}"
