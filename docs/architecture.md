# Kimi-Agent 架构说明文档

## 1. 整体架构

### 1.1 架构概览

Kimi-Agent (kimix) 采用**分层架构设计**，从上至下依次为：CLI/TUI 界面层、认知-决策引擎层、多维记忆系统层、工具与扩展层、LLM 客户端层。这种分层结构确保了各模块之间的职责清晰，便于独立开发、测试和扩展。

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / TUI Interface                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Rich TUI    │  │  One-shot    │  │  Config/Auth       │  │
│  │  (live mode) │  │  Mode        │  │  Management        │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘  │
└─────────┼─────────────────┼────────────────────┼─────────────┘
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                 Cognition-Decision Engine                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Mode Router │  │  Task Planner│  │  Cost Optimizer    │  │
│  │  (cognitive) │  │  (strategic) │  │  (economic)        │  │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘  │
│         └─────────────────┼────────────────────┘              │
│                           ▼                                   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              Agent Loop (core/engine.py)                │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐  │   │
│  │  │Session │ │ Turn   │ │Context │ │ Tool           │  │   │
│  │  │Manager │ │ Manager│ │Manager │ │ Orchestrator   │  │   │
│  │  └────────┘ └────────┘ └────────┘ └────────────────┘  │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────────────────────┬──────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Multi-Dimensional Memory System                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ Working Mem  │  ┌ Episodic Mem │  │ Semantic Mem       │  │
│  │ (short-term) │  │ (events)     │  │ (knowledge)        │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Tool & Extension Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ ToolRegistry │  │ SubAgent     │  │ MCP Client         │  │
│  │ (20+ tools)  │  │ Orchestrator │  │ (extensible)       │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└────────────────────────────┬──────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM Client Layer                                 │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Kimi API Client (OpenAI-compatible)                  │    │
│  │  - Streaming SSE                                      │    │
│  │  - Tool Calling (128 functions)                       │    │
│  │  - Thinking mode control                              │    │
│  │  - Cost tracking & cache optimization                 │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块 | 路径 | 职责 | 核心文件 |
|------|------|------|----------|
| Core Engine | `kimix/core/` | Agent 循环、会话管理、上下文管理 | `engine.py`, `session.py`, `context.py` |
| Modes | `kimix/modes/` | 工作模式实现 | `plan.py`, `agent.py`, `yolo.py`, `auto_router.py` |
| Tools | `kimix/tools/` | 工具注册表和工具实现 | `registry.py`, `file_tools.py`, `shell_tools.py`, `git_tools.py`, `web_tools.py` |
| Memory | `kimix/memory/` | 多维记忆系统 | `working.py`, `episodic.py`, `semantic.py`, `manager.py` |
| SubAgents | `kimix/subagents/` | 子 Agent 编排 | `orchestrator.py`, `worker.py`, `result_collector.py` |
| UI | `kimix/ui/` | CLI/TUI 界面 | `cli.py`, `tui.py`, `renderers.py` |
| Config | `kimix/config/` | 配置管理 | `settings.py`, `auth.py`, `profiles.py` |
| LLM Client | `kimix/llm/` | LLM API 客户端 | `client.py`, `streaming.py`, `cost_tracker.py` |
| Utils | `kimix/utils/` | 工具函数 | `sandbox.py`, `logger.py`, `file_watcher.py` |

---

## 2. 核心模块详细说明

### 2.1 Agent 引擎 (`core/engine.py`)

Agent 引擎是整个系统的核心协调者，管理 Agent 的完整生命周期。

**类设计：**

```python
class AgentEngine:
    def __init__(
        self,
        llm_client: KimiClient,           # LLM 客户端
        tool_registry: ToolRegistry,       # 工具注册表
        memory_manager: MemoryManager,     # 记忆管理器
        subagent_orchestrator: SubAgentOrchestrator,  # 子 Agent 编排器
        mode: AgentMode = AgentMode.AGENT, # 工作模式
        mode_router: ModeRouter | None = None,  # 模式路由器
    ) -> None
```

**核心职责：**

1. **认知分析** (`cognitive_analysis`) — 基于启发式规则分析用户输入，识别任务类型、复杂度、风险等级。分析维度包括：任务类型识别（10种类型）、复杂度评估（low/medium/high/critical）、风险评估（safe/low/medium/high/critical）。

2. **模式决策** — 支持手动模式切换和 AUTO 模式下的自动路由。AUTO 模式通过 `ModeRouter` 根据任务特征自动选择最适合的子模式。

3. **主运行循环** (`run`) — 异步生成器产生流式事件，完整执行流程包括：认知分析 → 模式决策 → 记忆检索 → 构建消息 → LLM 流式调用 → 工具执行 → 记忆存储 → 完成。

4. **工具执行** (`execute_tools`) — 并发执行所有工具调用，自动解析参数并回传结果。

### 2.2 模式路由器 (`modes/router.py`)

模式路由器实现**认知-决策分离架构**的决策层。

```python
class ModeRouter:
    def analyze_task(self, user_input: str) -> TaskAnalysis
    def suggest_mode(self, analysis: TaskAnalysis) -> AgentMode
    def auto_route(self, analysis: TaskAnalysis) -> AgentMode
```

**决策机制：**

1. **任务分类** — 基于正则模式匹配，将用户输入分类为 10 种任务类型：simple_qa、file_read、file_write、code_refactor、debug、shell_exec、architecture_design、code_review、git_operation、general。

2. **权重矩阵** — 每种任务类型对应一个模式权重字典，结合风险等级限制和复杂度调整因子计算最终得分。

3. **风险限制** — 根据风险等级动态限制可选模式（critical 风险仅允许 explore/plan/agent）。

4. **AUTO 模式保守策略** — 高风险任务自动降级、破坏性操作使用 AGENT 模式、只读任务直接使用 EXPLORE。

### 2.3 LLM 客户端 (`llm/client.py`)

`KimiClient` 提供与 Kimi API（OpenAI 兼容）的完整异步交互。

**核心能力：**

- **流式聊天** (`chat`) — SSE 流式响应，生成 thinking/content/tool_call/usage/done 事件
- **非流式接口** (`chat_with_thinking`, `chat_completion`) — 聚合响应返回完整结果
- **工具调用循环** (`chat_with_tools`) — 自动处理多轮工具调用（最多10轮）
- **Token 计数** (`count_tokens`) — 使用 tiktoken cl100k_base 编码器精确计数
- **成本估算** (`estimate_cost`) — 基于缓存命中率估算 API 调用成本
- **重试机制** — 指数退避 + 抖动，处理限流、网络错误等可重试异常

**错误处理体系：**

```
OpenAIError → LLMError
    ├── AuthenticationError  (401)
    ├── RateLimitError       (429)
    ├── TimeoutError
    ├── NetworkError
    ├── TokenLimitError      (413 / context length)
    └── APIError             (5xx / 其他)
```

### 2.4 会话管理 (`core/session.py`)

会话管理器负责 Agent 会话的生命周期管理。

- **Session** — 表示一次完整的交互会话，包含会话 ID、项目路径、消息历史、元数据
- **SessionManager** — 创建、保存、恢复、列出会话，支持持久化到 SQLite

### 2.5 上下文管理 (`core/context.py`)

上下文管理器维护 LLM 对话的完整上下文。

- 系统提示词动态构建（根据当前模式调整）
- 消息历史管理（支持滑动窗口截断）
- 工具结果回传格式处理
- 相关记忆注入（从记忆系统检索的上下文自动添加到系统消息）

---

## 3. 数据流设计

### 3.1 主循环数据流

```
1. 用户输入 → 2. 记忆检索(相关上下文) → 3. 模式路由 → 4. 构建消息
→ 5. LLM 调用(流式) → 6. 事件分发(思考/内容/工具调用)
→ 7. 如工具调用: 执行工具 → 结果回传 → 回到步骤 5
→ 8. 如文本输出: 流式渲染 → 记忆存储 → 等待下次输入
```

**详细说明：**

1. **用户输入** — 通过 CLI/TUI 接收用户输入文本
2. **记忆检索** — `MemoryManager.recall()` 按优先级分层检索（工作记忆 → 情景记忆 → 语义记忆）
3. **模式路由** — `ModeRouter.analyze_task()` 进行认知分析，`auto_route()` 决定执行模式
4. **构建消息** — `ContextManager.build_messages()` 组装系统提示词 + 历史消息 + 相关记忆 + 用户输入
5. **LLM 流式调用** — `KimiClient.chat()` 发起 SSE 流式请求，产生 thinking/content/tool_call/usage 事件
6. **事件分发** — 引擎将事件通过 `AsyncIterator` 分发给 UI 层实时渲染
7. **工具执行** — 如有 tool_call，`execute_tools()` 并发执行所有工具，结果回传给 LLM 继续处理（循环最多10轮）
8. **记忆存储** — 交互完成后，将对话内容存入情景记忆

### 3.2 子 Agent 数据流

```
1. 父 Agent 决定需要并行任务
→ 2. orchestrator.spawn_batch([task1, task2, ...])
→ 3. 每个子 Agent 获得: 独立上下文 + 工具子集 + 任务描述
→ 4. 子 Agent 后台执行（独立的 engine.run 循环）
→ 5. 进度通过 events 流回父 Agent
→ 6. 完成后 SubAgentResult 包含: summary, evidence, execution_log
→ 7. 父 Agent 通过 handle_read 按需获取详细结果
→ 8. 结果整合进父 Agent 上下文
```

### 3.3 记忆数据流

```
输入 → 工作记忆(立即缓存)
    → 情景记忆(事件记录)
    → 语义记忆(知识提取，异步)

检索 ← 工作记忆(优先，< 100ms)
     ← 情景记忆(最近事件，< 500ms)
     ← 语义记忆(相似性搜索，< 2s)
```

---

## 4. Agent 循环流程

### 4.1 标准执行流程

```python
async for event in engine.run("用户输入"):
    match event["type"]:
        case "thinking":
            # 渲染思考过程（灰色/折叠显示）
            render_thinking(event["data"]["text"])
        case "content":
            # 渲染响应内容（实时流式输出）
            render_content(event["data"]["text"])
        case "tool_call":
            # 显示工具调用信息
            render_tool_call(event["data"])
        case "tool_result":
            # 显示工具执行结果
            render_tool_result(event["data"])
        case "mode_switch":
            # 显示模式切换通知
            render_mode_switch(event["data"])
        case "cost_update":
            # 更新成本显示
            update_cost_display(event["data"])
        case "done":
            # 回合完成
            handle_turn_complete(event["data"])
        case "error":
            # 错误处理
            handle_error(event["data"])
```

### 4.2 工具调用循环

```
用户输入
  │
  ▼
LLM 调用 ←─────────────────────┐
  │                              │
  ├── 文本响应 → 完成 ──────────┘
  │
  └── 工具调用 → 并发执行工具
         │
         ▼
    工具结果回传给 LLM
         │
         └────────────────────────►
```

最大迭代次数：10 轮（防止无限循环）。

---

## 5. 记忆系统设计

### 5.1 三层记忆架构

Kimi-Agent 的记忆系统模拟人脑的多层记忆机制，分为三个层次：

#### 工作记忆 (`memory/working.py`)

**特性：** 短期、高速、易失

- **文件内容缓存** — LRU 淘汰策略，带大小限制（默认100MB）
- **工具执行结果缓存** — 避免重复执行相同工具调用
- **活跃变量空间** — 类 Python dict 接口，支持 `store_variable`/`get_variable`
- **检索延迟** < 100ms

#### 情景记忆 (`memory/episodic.py`)

**特性：** 中期、持久化、事件驱动

- **SQLite 持久化** — 使用 aiosqlite 异步操作
- **FTS5 全文搜索** — 高效检索历史事件
- **事件记录** — 对话历史、文件修改、命令执行、错误记录
- **检索延迟** < 500ms

#### 语义记忆 (`memory/semantic.py`)

**特性：** 长期、结构化、知识驱动

- **项目知识图谱** — 文件关系、模块依赖、API 接口
- **代码模式库** — 常用代码片段、最佳实践
- **用户偏好学习** — 编码风格、命名习惯、常用工具
- **检索延迟** < 2s

### 5.2 记忆管理器 (`memory/manager.py`)

`MemoryManager` 是记忆系统的统一入口，提供：

- **分层检索** (`recall`) — 按优先级同时查询三层记忆，合并后按相关性排序
- **统一存储** (`store`) — 根据 `MemoryType` 自动分发到对应子系统
- **记忆整合** (`consolidate`) — 定期将工作记忆转移到情景记忆

### 5.3 记忆检索优先级

```
┌──────────────────────────────────────────────┐
│               recall(query)                    │
│                                               │
│  第一层: 工作记忆                              │
│  ├── 搜索变量空间（关键词匹配变量名和值）       │
│  ├── 查询文件缓存（路径匹配）                   │
│  └── 检索工具缓存（最近执行记录）               │
│                                               │
│  第二层: 情景记忆                              │
│  ├── FTS5 全文搜索事件内容                      │
│  └── 回退: 获取最近事件                         │
│                                               │
│  第三层: 语义记忆                              │
│  ├── 余弦相似度搜索知识条目                     │
│  └── 项目知识图谱查询                           │
│                                               │
│  合并结果 → 按 relevance_score 排序            │
└──────────────────────────────────────────────┘
```

---

## 6. 子 Agent 编排机制

### 6.1 架构设计

```
┌─────────────────────────────────────────────────────┐
│                  父 Agent (Parent)                   │
│              (AgentEngine 主实例)                     │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │        SubAgentOrchestrator                  │   │
│  │                                             │   │
│  │  ┌─────────┐ ┌─────────┐     ┌─────────┐  │   │
│  │  │ Worker 1│ │ Worker 2│ ... │ Worker N│  │   │
│  │  │(explorer│ │(coder)  │     │(tester) │  │   │
│  │  └────┬────┘ └────┬────┘     └────┬────┘  │   │
│  │       └───────────┴───────────────┘       │   │
│  │              Semaphore (max 32)             │   │
│  │                                             │   │
│  │  ┌─────────────────────────────────────┐   │   │
│  │  │     asyncio.Queue (结果收集)         │   │   │
│  │  └─────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 6.2 核心机制

**并发控制：**

- 使用 `asyncio.Semaphore(32)` 限制最大并发数
- 默认并发上限 32，可配置到 64
- 优先级队列确保高优先级任务优先调度

**Agent 角色 (8种)：**

| 角色 | 职责 | 模型配置 |
|------|------|----------|
| `explorer` | 代码库探索、文件分析 | K2.6 thinking on |
| `planner` | 任务规划、架构设计 | K2.6 thinking on |
| `coder` | 代码编写、重构 | K2.6 (auto) |
| `reviewer` | 代码审查、质量检查 | K2.6 thinking on |
| `tester` | 测试编写、测试执行 | K2.6 (auto) |
| `debugger` | 错误诊断、修复 | K2.6 thinking on |
| `researcher` | 技术调研、文档查询 | K2.6 + web_search |
| `documenter` | 文档生成、注释编写 | K2.6 (auto) |

**任务生命周期：**

```
task_create → agent_spawn → background_execution 
→ progress_streaming → completion_notify → result_integration
```

### 6.3 编排器接口

```python
class SubAgentOrchestrator:
    async def spawn(self, role, task, context, priority) -> SubAgentHandle
    async def spawn_batch(self, tasks) -> list[SubAgentHandle]
    async def wait_all(self, handles, timeout) -> list[SubAgentResult]
    async def wait_any(self, handles, timeout) -> SubAgentResult
    async def cancel(self, handle) -> bool
    async def cancel_all(self) -> int
    def get_stats(self) -> dict
```

---

## 7. 与 deepseek-TUI 的设计差异分析

### 7.1 架构层面

| 维度 | deepseek-TUI | Kimi-Agent (kimix) | 差异说明 |
|------|-------------|-------------------|----------|
| 模式系统 | 3层（Ask/Agent/YOLO） | 5层（Explore/Plan/Agent/Auto/YOLO） | 增加认知层和自适应路由 |
| 记忆系统 | 基础 session persistence | 多维记忆（3层） | 模拟人脑记忆机制 |
| 子Agent并发 | 16个 | 32个（可扩展到64） | 利用 K2.6 更低延迟优势 |
| 成本优化 | prefix cache 感知 | 智能路由+动态模型选择+Token优化 | 全面成本管理体系 |
| 多模态 | 不支持 | 预留架构 | 利用 K2.6 原生多模态能力 |
| 语言支持 | 英文为主 | 中文优先 | 更适合中文开发者 |

### 7.2 设计哲学差异

**deepseek-TUI** 的设计理念是"最小可行 Agent" —— 提供基础的 Agent 能力，保持简洁和轻量。

**Kimi-Agent** 的设计理念是"认知增强 Agent" —— 引入认知科学的概念，让 Agent 具备：

1. **自我认知能力** — 能够分析任务复杂度和风险，做出合理的模式选择
2. **持续学习能力** — 通过多维记忆系统从交互中学习，越用越聪明
3. **协作执行能力** — 通过子 Agent 编排实现复杂任务的并行处理
4. **成本意识** — 内置成本追踪和优化，帮助用户控制开销

### 7.3 技术实现差异

**1. 认知-决策分离**

deepseek-TUI 的模式切换是用户手动或通过简单的规则触发。Kimi-Agent 引入了独立的 `ModeRouter` 组件，通过任务特征分析、权重矩阵、风险限制等多维度决策机制实现智能路由。

**2. 记忆系统深度**

deepseek-TUI 的记忆主要是 session 级别的消息持久化。Kimi-Agent 的工作记忆支持 LRU 缓存淘汰、情景记忆支持 FTS5 全文搜索、语义记忆支持知识图谱构建，三层记忆之间有明确的职责划分和整合机制。

**3. 子 Agent 架构**

deepseek-TUI 的 RLM（Remote Language Model）是简单的并行调用。Kimi-Agent 的 `SubAgentOrchestrator` 提供完整的生命周期管理：优先级队列、信号量并发控制、结果收集队列、取消机制、超时控制、统计监控。

**4. 成本管理**

deepseek-TUI 只有基础的 cache 感知。Kimi-Agent 的 `CostTracker` 提供：实时成本追踪、预算管理、成本估算、缓存命中率分析。

### 7.4 工具系统对比

| 工具类别 | deepseek-TUI | Kimi-Agent |
|----------|-------------|------------|
| 文件操作 | 基础读写 | 8个工具（含补丁、搜索、信息查询） |
| Shell | 基础执行 | 含危险命令过滤、超时控制 |
| Git | 无 | 4个专用工具 |
| Web | 无 | 搜索 + URL获取 |
| 子 Agent | 无 | 3个管理工具 |
| 系统 | 无 | 通知 + 任务列表 |

---

## 8. 安全设计

### 8.1 沙箱系统 (`utils/sandbox.py`)

- **路径限制** — 所有文件操作限制在 `work_dir` 和 `allowed_paths` 内
- **命令黑名单** — 内置危险命令模式拦截（fork bomb、rm -rf /、mkfs 等）
- **敏感命令检测** — rm -rf、sudo、chmod 777 等需要额外审批
- **超时控制** — Shell 命令默认60秒超时
- **输出限制** — 最大1MB输出截断

### 8.2 审批级别 (`tools/base.py`)

```python
class ApprovalLevel(Enum):
    NONE = "none"           # 无需审批（只读操作）
    READONLY = "readonly"   # 只读操作无需审批
    DESTRUCTIVE = "destructive"  # 破坏性操作需审批（写入、Shell）
    ALL = "all"             # 所有操作需审批
```

### 8.3 模式权限矩阵

| 模式 | 读取文件 | 写入文件 | Shell | 审批行为 |
|------|----------|----------|-------|----------|
| Explore | 是 | 否 | 否 | 无需审批 |
| Plan | 是 | 否 | 否 | 无需审批 |
| Agent | 是 | 是 | 是 | 破坏性操作需审批 |
| Auto | 是 | 是 | 是 | 智能审批门 |
| YOLO | 是 | 是 | 是 | 自动审批 |

---

## 9. 配置体系

配置文件位于 `~/.kimix/config.yaml`，支持以下配置项：

```yaml
auth:
  api_key: "${MOONSHOT_API_KEY}"
  base_url: "https://api.moonshot.cn/v1"

model:
  default: "kimi-k2.6"
  thinking: true
  max_tokens: 16384

modes:
  default: "agent"
  yolo_confirm: false
  auto_approval_threshold: 0.8

memory:
  enabled: true
  db_path: "~/.kimix/memory.db"
  max_working_cache: 100

subagents:
  max_concurrent: 32
  timeout: 300

tools:
  enabled: [file_read, file_write, file_edit, shell, git, web_search, web_fetch, subagent]

sandbox:
  enabled: true
  allowed_paths: ["."]
  blocked_commands: ["rm -rf /", ":(){:|:&};:"]

cost:
  budget_limit: 0
  warning_threshold: 10.0
  cache_optimization: true

ui:
  theme: "auto"
  language: "zh"
  show_thinking: true
  show_cost: true
```

**配置优先级**：环境变量 > 配置文件 > 默认值
