"""
上下文管理模块

管理 Agent 的对话上下文，包括：
- 系统提示词生成（中文优先，适配 Kimi 中文优势）
- 消息列表构建与维护
- 上下文窗口管理（256K tokens，保留安全边距）
- 上下文压缩与修剪策略
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from pathlib import Path

# 上下文窗口限制常量
MAX_CONTEXT_TOKENS = 256_000      # Kimi K2.6 最大上下文
SAFE_CONTEXT_LIMIT = 200_000      # 安全使用上限（保留 ~22% 余量）
SYSTEM_PROMPT_RESERVE = 8_000     # 系统提示词预留
TOOL_DEF_RESERVE = 12_000         # 工具定义预留
# 用户对话可用 = 200000 - 8000 - 12000 = 180000 tokens

# 预估 token 比例（中文字符）
CHARS_PER_TOKEN_ZH = 1.5          # 中文约 1.5 字符/token
CHARS_PER_TOKEN_EN = 4.0          # 英文约 4 字符/token


# 系统提示词模板（中文优先）
DEFAULT_SYSTEM_PROMPT = """你是 Kimi-Agent（简称 Kimix），由 Moonshot AI 的 Kimi K2.6 模型驱动的智能编程助手。

## 核心能力
- 代码编写、阅读、重构和调试
- 项目结构分析和架构设计
- 文件操作（读/写/编辑）和 Shell 命令执行
- Git 操作和版本管理
- Web 搜索和信息检索
- **IM 机器人绑定**：支持飞书、企业微信、微信、Slack、Discord、Telegram、钉钉等平台。运行 `kimix bots setup` 即可交互式绑定，或 `kimix bots setup feishu` 直接绑定飞书。绑定后 Agent 可接收和回复对应平台的消息。

## 工作原则
1. **主动思考**：在执行前先分析任务，制定清晰计划
2. **最小权限**：只执行必要的操作，避免过度修改
3. **代码质量**：遵循最佳实践，保持代码可读性和可维护性
4. **安全第一**：破坏性操作（删除、覆盖）前必须确认
5. **透明沟通**：清晰说明你在做什么、为什么这么做

## 工具使用规范
- 优先使用工具获取信息，而非猜测
- 复杂任务先制定计划，再分步执行
- 工具调用失败时分析原因，尝试替代方案
- 文件操作前检查路径是否存在

## 响应风格
- 用中文回复（除非用户要求英文）
- 代码块使用正确的语法高亮
- 长回复先给摘要，再给详情
- 步骤多时显示进度（如 "第 1/3 步..."）

当前工作目录：{project_path}
当前模式：{mode}
会话ID：{session_id}
"""

# 探索模式系统提示词
EXPLORE_SYSTEM_PROMPT = """你处于 **探索模式 (Explore Mode)**。

此模式下你只能执行**只读操作**：
- 读取文件内容
- 查看目录结构
- 搜索代码
- 查看 Git 历史和状态

**禁止执行任何写入操作**（创建/修改/删除文件、执行写入性 Shell 命令）。

你的任务是帮助用户理解代码库、查找信息、分析项目结构。
所有操作无需审批，可自由执行只读工具。

{base_prompt}
"""

# 规划模式系统提示词
PLAN_SYSTEM_PROMPT = """你处于 **规划模式 (Plan Mode)**。

此模式下你的主要任务是：
1. **分析需求**：深入理解用户目标和约束条件
2. **调研现状**：读取相关文件了解当前状态
3. **制定计划**：生成详细的执行计划（包含步骤、依赖、风险）

你可以执行只读操作来调研项目，但不能直接修改任何文件。
计划输出格式：
- 目标概述
- 现状分析
- 执行步骤（编号、描述、涉及文件）
- 依赖关系
- 风险评估
- 预估工作量

{base_prompt}
"""

# Agent 模式系统提示词
AGENT_SYSTEM_PROMPT = """你处于 **Agent 模式 (Agent Mode)**。

这是默认的交互执行模式。你可以：
- 读写文件、执行 Shell 命令
- 进行代码重构和架构调整
- 交互式地与用户确认关键决策

**审批规则**：
- 只读操作：无需审批
- 文件写入/修改：需用户确认
- 删除操作：需用户确认
- Shell 命令（非破坏性）：无需审批
- 可能影响系统的命令：需用户确认

{base_prompt}
"""

# 自动模式系统提示词
AUTO_SYSTEM_PROMPT = """你处于 **自动模式 (Auto Mode)**。

此模式下你拥有更高的自主权：
- 可以自主决定执行步骤
- 智能判断是否需要用户确认（基于风险评估）
- 自动调整 thinking 模式（简单任务关闭，复杂任务开启）

**审批门控**：
- 低风险操作（读取、安全写入）：自动执行
- 中风险操作（修改现有文件）：记录并执行
- 高风险操作（删除、系统命令）：需确认

{base_prompt}
"""

# YOLO 模式系统提示词
YOLO_SYSTEM_PROMPT = """你处于 **YOLO 模式 (Full Auto Mode)**。

此模式下你拥有完全自主权：
- 所有操作自动审批
- 目标是最高效率完成任务
- Thinking 模式关闭以节省 token

**约束**：
- 仍遵循最小权限原则
- 操作失败时自动重试或调整策略
- 批量操作时保持原子性

{base_prompt}
"""

# 模式提示词映射
MODE_PROMPT_MAP: dict[str, str] = {
    "explore": EXPLORE_SYSTEM_PROMPT,
    "plan": PLAN_SYSTEM_PROMPT,
    "agent": AGENT_SYSTEM_PROMPT,
    "auto": AUTO_SYSTEM_PROMPT,
    "yolo": YOLO_SYSTEM_PROMPT,
}


class MemoryManagerLike(Protocol):
    """MemoryManager 协议类，用于类型提示"""
    async def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


class ContextManager:
    """上下文管理器
    
    负责构建和管理 Agent 的对话上下文，包括系统提示词、
    对话历史和记忆注入。核心功能是确保上下文不超出 token 限制。
    
    Attributes:
        session_id: 当前会话 ID
        project_path: 当前项目路径
        mode: 当前工作模式
        system_prompt: 当前系统提示词
        message_history: 完整消息历史（持久化）
    
    Examples:
        >>> ctx = ContextManager("sess-001", "/home/user/project", "agent")
        >>> messages = ctx.build_messages("帮我读取 README.md")
        >>> messages[0]["role"]
        'system'
    """

    def __init__(
        self,
        session_id: str,
        project_path: str | Path,
        mode: str = "agent",
    ) -> None:
        """初始化上下文管理器
        
        Args:
            session_id: 会话唯一标识
            project_path: 项目根目录路径
            mode: 工作模式名称
        """
        self.session_id = session_id
        self.project_path = Path(project_path)
        self.mode = mode
        self._message_history: list[dict[str, Any]] = []
        self._system_prompt_tokens = 0

    @property
    def messages(self) -> list[dict[str, Any]]:
        """当前消息历史（只读）"""
        return list(self._message_history)

    @property
    def system_prompt(self) -> str:
        """生成当前模式对应的系统提示词"""
        base = DEFAULT_SYSTEM_PROMPT.format(
            project_path=str(self.project_path),
            mode=self.mode,
            session_id=self.session_id,
        )

        mode_template = MODE_PROMPT_MAP.get(self.mode, AGENT_SYSTEM_PROMPT)
        return mode_template.format(base_prompt=base)

    def build_messages(
        self,
        user_input: str,
        relevant_memories: list[dict[str, Any]] | None = None,
        experience_guidance: str = "",
    ) -> list[dict[str, Any]]:
        """构建完整的 LLM 消息列表
        
        构建顺序：
        1. 系统提示词（根据当前模式）
        2. 相关记忆（如有）
        3. 经验指导（自学习系统注入）
        4. 消息历史（经裁剪后）
        5. 用户最新输入
        
        Args:
            user_input: 用户输入文本
            relevant_memories: 从记忆系统检索到的相关记忆
            experience_guidance: 自学习系统生成的经验指导文本
        
        Returns:
            完整的消息列表，可直接传给 LLM
        """
        messages: list[dict[str, Any]] = []

        # 1. 系统提示词
        messages.append({
            "role": "system",
            "content": self.system_prompt,
        })

        # 2. 注入相关记忆（作为 system 补充）
        if relevant_memories:
            memory_text = self._format_memories(relevant_memories)
            if memory_text:
                messages.append({
                    "role": "system",
                    "content": f"【相关记忆】\n{memory_text}",
                })

        # 3. 注入经验指导（自学习系统）
        if experience_guidance:
            messages.append({
                "role": "system",
                "content": f"【历史经验指导】\n{experience_guidance}",
            })

        # 4. 消息历史（裁剪到安全范围内）
        trimmed_history = self.trim_context(self._message_history)
        messages.extend(trimmed_history)

        # 5. 用户最新输入
        messages.append({
            "role": "user",
            "content": user_input,
        })

        return messages

    def add_message(self, role: str, content: str | dict[str, Any], **kwargs: Any) -> None:
        """添加消息到历史记录
        
        Args:
            role: 消息角色（system/user/assistant/tool）
            content: 消息内容
            **kwargs: 额外字段
        """
        msg: dict[str, Any] = {"role": role, "content": content}
        msg.update(kwargs)
        self._message_history.append(msg)

    def add_user_message(self, content: str) -> None:
        """添加用户消息快捷方法"""
        self.add_message("user", content)

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """添加助手消息快捷方法
        
        Args:
            content: 助手响应文本
            tool_calls: 工具调用列表（如有）
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._message_history.append(msg)

    def add_tool_message(
        self,
        tool_call_id: str,
        name: str,
        content: str,
    ) -> None:
        """添加工具结果消息
        
        Args:
            tool_call_id: 对应工具调用的 ID
            name: 工具名称
            content: 工具返回内容
        """
        self._message_history.append({
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
            "name": name,
        })

    def trim_context(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = SAFE_CONTEXT_LIMIT,
    ) -> list[dict[str, Any]]:
        """裁剪上下文到安全 token 范围内
        
        策略：
        1. 预留系统提示词 + 工具定义的空间
        2. 优先保留最近的消息（热数据）
        3. 历史消息优先压缩/丢弃 tool 结果中的长输出
        4. 保留用户和 assistant 的核心对话
        
        Args:
            messages: 原始消息列表
            max_tokens: 最大允许 token 数
        
        Returns:
            裁剪后的消息列表
        """
        if not messages:
            return []

        # 计算可用 token 预算
        available_tokens = max_tokens - SYSTEM_PROMPT_RESERVE - TOOL_DEF_RESERVE

        # 估算当前消息的总 token 数
        total_tokens = sum(self._estimate_msg_tokens(m) for m in messages)

        if total_tokens <= available_tokens:
            return list(messages)

        # 需要裁剪：优先保留最新消息
        # 策略：从旧消息开始丢弃，但保留关键上下文
        trimmed: list[dict[str, Any]] = []
        current_tokens = 0

        # 始终保留最近的用户消息
        # 倒序遍历，优先保留新消息
        for msg in reversed(messages):
            msg_tokens = self._estimate_msg_tokens(msg)

            if current_tokens + msg_tokens <= available_tokens:
                trimmed.insert(0, msg)
                current_tokens += msg_tokens
            else:
                # 尝试压缩这条消息而不是丢弃
                compressed = self._compress_message(msg)
                compressed_tokens = self._estimate_msg_tokens(compressed)
                if current_tokens + compressed_tokens <= available_tokens:
                    trimmed.insert(0, compressed)
                    current_tokens += compressed_tokens
                else:
                    # 空间不足，停止添加
                    break

        # 如果裁剪后只剩很少消息，添加一个摘要提示
        if len(trimmed) < len(messages) and len(messages) - len(trimmed) > 2:
            # 找到被裁剪的最早一条消息的索引
            if trimmed:
                first_kept_idx = messages.index(trimmed[0])
                skipped_count = first_kept_idx
                summary_msg = {
                    "role": "system",
                    "content": f"[上下文摘要：已省略前 {skipped_count} 条历史消息以节省空间]",
                }
                # 在保留的消息前插入摘要
                trimmed.insert(0, summary_msg)

        return trimmed

    def update_mode(self, mode: str) -> None:
        """更新工作模式，重新生成系统提示词
        
        Args:
            mode: 新模式名称
        """
        self.mode = mode

    def clear_history(self) -> None:
        """清空消息历史（保留系统提示词）"""
        self._message_history.clear()

    def get_history(self) -> list[dict[str, Any]]:
        """获取当前消息历史副本"""
        return list(self._message_history)

    def _format_memories(self, memories: list[dict[str, Any]]) -> str:
        """将记忆列表格式化为文本
        
        Args:
            memories: 记忆条目列表
        
        Returns:
            格式化后的记忆文本
        """
        if not memories:
            return ""

        parts: list[str] = []
        for i, mem in enumerate(memories, 1):
            content = mem.get("content", str(mem))
            source = mem.get("source", "未知来源")
            parts.append(f"{i}. [{source}] {content}")

        return "\n".join(parts)

    def _estimate_msg_tokens(self, msg: dict[str, Any]) -> int:
        """估算单条消息的 token 数
        
        使用字符数 + 结构化开销进行粗略估算。
        对于中文内容，按 1.5 字符/token 计算；
        对于英文内容，按 4 字符/token 计算。
        
        Args:
            msg: 消息字典
        
        Returns:
            估算的 token 数
        """
        content = msg.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        elif not isinstance(content, str):
            content = str(content)

        # 计算字符组成（粗略区分中英文）
        zh_chars = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
        total_chars = len(content)
        en_chars = total_chars - zh_chars

        # 估算 token
        content_tokens = int(zh_chars / CHARS_PER_TOKEN_ZH + en_chars / CHARS_PER_TOKEN_EN)

        # 结构化开销（role、metadata 等）
        overhead = 4  # role 字段等基础开销

        # tool_calls 的额外开销
        if "tool_calls" in msg:
            tool_calls = msg["tool_calls"]
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    tc_str = json.dumps(tc, ensure_ascii=False)
                    overhead += len(tc_str) // 4

        # tool 结果的消息名开销
        if msg.get("name"):
            overhead += 2

        return max(content_tokens + overhead, 1)

    def _compress_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """压缩单条消息，减少 token 占用
        
        策略：
        - tool 结果：截断长输出，保留前 2000 字符 + 摘要
        - assistant 消息：保留内容不变（通常重要）
        - user 消息：保留内容不变
        
        Args:
            msg: 原始消息
        
        Returns:
            压缩后的消息
        """
        compressed = dict(msg)
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "tool" and isinstance(content, str) and len(content) > 3000:
            # 截断工具输出，保留首尾
            head = content[:1500]
            tail = content[-1000:]
            omitted = len(content) - 2500
            compressed["content"] = (
                f"{head}\n\n"
                f"[... 省略 {omitted} 字符 ...]\n\n"
                f"{tail}"
            )

        elif role == "assistant" and isinstance(content, str) and len(content) > 5000:
            # 压缩助手的长回复（较少见）
            compressed["content"] = content[:4000] + "\n\n[内容已截断]"

        return compressed

    def get_token_estimate(self) -> dict[str, int]:
        """获取当前上下文的 token 估算统计
        
        Returns:
            包含各项 token 估算的字典
        """
        sys_tokens = self._estimate_msg_tokens({"content": self.system_prompt})
        history_tokens = sum(self._estimate_msg_tokens(m) for m in self._message_history)

        return {
            "system_prompt": sys_tokens,
            "message_history": history_tokens,
            "tool_definitions": TOOL_DEF_RESERVE,
            "total": sys_tokens + history_tokens + TOOL_DEF_RESERVE,
            "limit": SAFE_CONTEXT_LIMIT,
            "remaining": max(0, SAFE_CONTEXT_LIMIT - sys_tokens - history_tokens - TOOL_DEF_RESERVE),
        }
