---
name: "cron-automation"
description: >
  Cron 自动化 Skill — 让 Agent 能在干净的 session 中执行定时任务。
  核心原则：Cron 是干净 session，prompt 必须自包含（定时任务看不到当前对话上下文）。
metadata:
  author: "community"
  category: "automation"
  capabilities:
    - "cron.schedule"
    - "cron.execute"
  permissions:
    - "system.cron"
---

# Cron 自动化

## 📌 技能概述

Cron 自动化让 Agent 能在预定时间执行指定任务。

**核心原则：** Cron 是 **干净 session**，prompt 必须 **自包含** — 定时任务看不到当前对话上下文。

---

## ❌ BAD 写法（依赖人类记忆）

```bash
# 每日9点运行
0 9 * * * hermes exec \
  'Check on that server issue'
# 结果：回 Which server? Which issue? — 死循环
```

**问题：** `that` 指代不明、目标模糊、缺乏验证标准

---

## ✅ GOOD 写法（自包含 prompt）

```bash
# 每日9点巡检 prod-api-01
0 9 * * * hermes exec \
  'SSH to prod-api-01, run:
    systemctl status api-server,
    tail -n 100 /var/log/api.err.
    如果 status 非 active 或 err log 含 ERROR,
    发 Telegram 并附上最后20行'
# 结果：独立 session 也能跑完整的巡检流程
```

**标准：** 当成对 **从未见过项目的同事的一次性授权** — 缺什么就写什么

---

## 🔄 Kimi-Agent Cron 规范

### 格式

```python
from kimix.tools.cron import CronScheduler

scheduler = CronScheduler()

# 添加定时任务
scheduler.add_job(
    name="daily-health-check",
    schedule="0 9 * * *",  # 每天9点
    prompt="""
自包含任务：每日健康检查

目标服务器：prod-api-01 (192.168.1.100)
检查项：
1. systemctl status api-server
2. df -h /var/log
3. tail -n 50 /var/log/api.err

告警条件：
- api-server 状态不是 active
- 磁盘使用率 > 80%
- 错误日志含 "ERROR" 或 "FATAL"

执行动作：
- 发现问题时发送通知到 admin@example.com
- 附上相关日志片段
""",
)
```

### 自包含检查清单

- [ ] 目标明确（哪个服务器？哪个服务？）
- [ ] 命令完整（路径、参数、环境变量）
- [ ] 判断标准（什么叫"正常"？什么叫"异常"？）
- [ ] 异常处理（发现问题后做什么？）
- [ ] 通知方式（通知谁？通过什么渠道？）

---

## 📂 示例任务

### 1. 每日备份检查
```
0 8 * * * 检查昨日备份是否成功
- 备份路径：/backup/daily/
- 成功标准：存在当天日期的 .tar.gz 文件，大小 > 100MB
- 失败动作：发送告警邮件，附上备份日志
```

### 2. 每周依赖更新
```
0 2 * * 1 检查项目依赖更新
- 项目路径：~/projects/myapp
- 检查命令：npm outdated / pip list --outdated
- 更新策略：minor 版本自动更新，major 版本人工确认
- 执行后：跑测试套件，全部通过才提交
```

### 3. 每月成本报告
```
0 9 1 * * 生成上月成本报告
- 统计项：API 调用量、Token 消耗、存储费用
- 输出格式：Markdown 表格
- 发送给：finance@example.com
- 异常：单服务费用比上月增长 > 50% 时标红
```

---

## 🔧 集成到 Kimi-Agent

```python
from kimix.tools.cron import CronScheduler
from kimix.skills import SkillRegistry

# 注册 Cron Skill
registry = SkillRegistry()
registry.load_skill("cron-automation")

# 创建调度器
scheduler = CronScheduler()

# 用户添加定时任务
scheduler.add_job_from_user_prompt("每天早上9点检查服务器状态")
# Agent 自动转换为自包含 prompt 并保存

# 查看所有任务
scheduler.list_jobs()

# 删除任务
scheduler.remove_job("job-id")
```

---

## ⚠️ 常见错误

| 错误 | 示例 | 修复 |
|:---|:---|:---|
| 指代不明 | "检查那个问题" | "检查 prod-api-01 的内存泄漏问题" |
| 路径依赖 | "运行 ./script.sh" | "运行 /home/user/project/script.sh" |
| 标准模糊 | "看看是否正常" | "CPU < 80%, 内存 < 90%, 响应 < 200ms" |
| 无异常处理 | "监控日志" | "发现 ERROR 时发送邮件给 admin@example.com" |

---

## 💡 最佳实践

1. **一条任务只做一件事** — 复杂任务拆成多个定时任务
2. **输出结构化** — 使用 JSON / Markdown 表格，便于后续处理
3. **失败明确** — 定义"失败"的标准和"失败后的动作"
4. **测试先行** — 先用 `*/5 * * * *`（每5分钟）测试，确认正常再改为低频
5. **日志留存** — 每次执行结果保存到 `~/.kimix/cron/logs/`

---

**一句话：Cron 任务要像给陌生人写的说明书 — 不需要上下文，拿到就能执行。**
