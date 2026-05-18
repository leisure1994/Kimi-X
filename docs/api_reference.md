# API 参考文档

## 核心模块

### `kimix.core.engine.AgentEngine`

Agent 核心引擎，负责任务调度、模式切换和上下文管理。

```python
from kimix.core.engine import AgentEngine

engine = AgentEngine(
    llm_client=None,      # LLM 客户端
    memory_manager=None,   # 内存管理器
    mode="agent",         # 运行模式
)
response = engine.run("用户输入")
```

### `kimix.core.agent_economy.CloudPlatform`

Agent 云端平台，提供赏金发布、兼职注册、评分结算功能。

```python
from kimix.core.agent_economy import CloudPlatform

platform = CloudPlatform()
bounty = platform.publish_bounty(
    publisher_id="agent_alpha",
    title="实现文件加密工具",
    description="...",
    total_reward=5000,
    currency="CNY",
    stages=[{"description": "实现核心加密", "reward_pct": 60}],
)
```

### `kimix.tools.clawtip.ClawTipPayment`

ClawTip 支付模块，支持京东 Agent 支付系统。

```python
from kimix.tools.clawtip import ClawTipPayment

payment = ClawTipPayment(sandbox=True)  # 沙箱模式
order = payment.create_order(
    amount=100,
    description="测试订单",
    question="测试问题",
)
payment.process_payment(order["order_no"], order["indicator"])
```

### `kimix.memory.manager.MemoryManager`

四层内存管理器。

```python
from kimix.memory.manager import MemoryManager

memory = MemoryManager()
memory.add_working("用户要求写代码")
memory.add_semantic("用户偏好 Python")
memory.add_episodic("上次成功完成了 xxx 任务")
```

## 工具模块

| 模块 | 功能 |
|:---|:---|
| `kimix.tools.shell_tools` | Shell 命令执行 |
| `kimix.tools.file_tools` | 文件读写操作 |
| `kimix.tools.web_tools` | HTTP 请求 |
| `kimix.tools.web_search` | 网页搜索 |
| `kimix.tools.git_tools` | Git 操作 |
| `kimix.tools.sandbox` | 沙盒隔离 |
| `kimix.tools.document_converter` | 文档转换 |

## 运行模式

| 模式 | 说明 |
|:---|:---|
| `agent` | 标准 Agent 模式 |
| `auto` | 自动模式 |
| `plan` | 规划模式 |
| `explore` | 探索模式 |
| `yolo` | YOLO 模式 |

## 常量

```python
from kimix.version import __version__
print(__version__)  # "0.85.0"
```
