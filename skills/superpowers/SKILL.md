---
name: "superpowers"
description: >
  Superpowers 工程流程 Skill — 让 Agent 从"冲动型程序员"变为"有流程意识的工程师"。
  标准6步工作流：澄清需求 → 设计方案 → 拆解计划 → 编写测试 → 运行验证 → 请求审查。
metadata:
  author: "community"
  category: "workflow"
  capabilities:
    - "workflow.enforce"
    - "quality.gate"
  permissions:
    - "project.read"
---

# Superpowers — 工程流程规范化

## 📌 技能概述

Superpowers 解决 Agent "怎么干活"的问题。

**核心转变：**
- **未装 Superpowers**：冲动型程序员 — 一上来就开写
- **装了 Superpowers**：有流程意识的工程师 — 按标准流程执行

**6步标准工作流：**
1. **澄清需求** (Clarify requirements)
2. **设计方案** (Design solution)
3. **拆解计划** (Break down plan)
4. **编写测试** (Write tests)
5. **跑验证** (Run validation)
6. **请求代码审查** (Request code review)

---

## 🔄 6步工作流

### Step 1: 澄清需求
**目标**：确保理解用户真正要什么，而不是你以为的。

**动作**：
- 重述需求，确认理解正确
- 提出澄清问题（边界情况、异常处理、性能要求）
- 确认验收标准

**输出**：`requirements.md` — 确认后的需求文档

### Step 2: 设计方案
**目标**：想清楚再动手，避免返工。

**动作**：
- 确定技术选型（Why this？）
- 设计架构/接口/数据流
- 识别风险和依赖

**输出**：`design.md` — 设计方案文档

### Step 3: 拆解计划
**目标**：把大任务拆成可执行的小步骤。

**动作**：
- 列出所有任务项
- 估算工时
- 标记依赖关系
- 确定优先级

**输出**：`plan.md` — 执行计划

### Step 4: 编写测试
**目标**：先定义"完成"的标准。

**动作**：
- 编写单元测试（覆盖核心逻辑）
- 编写集成测试（覆盖交互场景）
- 确认测试失败（红）→ 实现（绿）→ 重构

**输出**：`tests/` — 测试代码

### Step 5: 跑验证
**目标**：确保实现符合预期。

**动作**：
- 运行所有测试
- 代码审查（self-review）
- 性能/安全扫描
- 文档更新

**输出**：验证报告

### Step 6: 请求代码审查
**目标**：引入外部视角，防止盲区。

**动作**：
- 准备 PR 描述（What/Why/How）
- 标注重点审查区域
- 回应审查意见

**输出**：PR / Review 记录

---

## 🛡️ 质量门禁

**硬性规则（永不跳过）：**
- [ ] 没有测试的代码不能合并
- [ ] 没有文档的接口不能发布
- [ ] 没有审查的变更不能上线

**软性建议（灵活调整）：**
- 小改动（<10行）可跳过 Step 2-3
- 紧急修复可跳过 Step 4，但需补测试
- 探索性代码可跳过 Step 6，但需标记为 WIP

---

## 📂 触发条件

**何时激活 Superpowers：**
- 用户要求"写代码"、"实现功能"、"修复 bug"
- 任务涉及代码变更（>5 行）
- 用户明确要求"按流程来"

**何时跳过：**
- 纯问答（不涉及代码）
- 已有明确方案的微小调整
- 用户明确说"直接写"

---

## 💡 使用示例

```
用户: "帮我实现一个用户登录功能"

Agent (Superpowers 激活):
  Step 1: "确认需求 — 需要支持哪些登录方式？密码策略？第三方登录？"
  Step 2: "设计方案 — JWT + bcrypt，接口 /api/login，返回 token"
  Step 3: "拆解计划 — 1)模型 2)接口 3)测试 4)文档"
  Step 4: "编写测试 — 测试成功登录、失败登录、token刷新"
  Step 5: "跑验证 — 全部测试通过，覆盖率 90%"
  Step 6: "请求审查 — 已准备好，请审查 /api/login 接口设计"
```

---

## 🔧 集成到 Kimi-Agent

```python
from kimix.skills import SkillRegistry

# 注册 Superpowers
registry = SkillRegistry()
registry.load_skill("superpowers")

# 在执行代码任务前自动检查
if task_type == "coding" and registry.has_skill("superpowers"):
    workflow = registry.get_skill("superpowers")
    if not workflow.is_compliant(current_state):
        workflow.enforce(current_state)
```

---

## 📊 效果

| 指标 | 无 Superpowers | 有 Superpowers |
|:---|:---|:---|
| 返工率 | 30% | <10% |
| Bug 逃逸率 | 25% | <5% |
| 需求理解偏差 | 常见 | 极少 |
| 代码可维护性 | 中 | 高 |

---

**一句话：Superpowers 让 Agent 从「写代码」升级到「做工程」。**
