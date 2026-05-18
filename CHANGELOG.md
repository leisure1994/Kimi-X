# Kimi-Agent v0.85 变更日志

## [0.91] - 2026-05-18

### 文档
- **重写安装指南** — 拆分到每一步的截图级说明，加入"下次开机怎么重新启动"完整教程
- **加入快捷方式教程** — 教用户创建 `.bat` 批处理文件，双击即可启动
- 更新 README 版本号

## [0.90] - 2026-05-18

### 修复
- **彻底修复 Windows CMD TUI 抖动** — 不再用 Rich Live 的 async 模式，改为简化模式（直接 print + input），自动检测 Windows CMD 并切换
- 修复 `tui.py` 中版本号硬编码为 `1.0.0` 的问题，改为使用 `__version__`

## [0.89] - 2026-05-18

### 文档
- **重写 README** — 面向非程序员用户，删除 git/pip 等术语，改用下载 ZIP + 双击安装的通俗语言
- **重写安装指南** — 按步骤截图式教程，Windows 专用，国内网络环境适配（GitHub 被墙时提供 ZIP 替代方案）

## [0.88] - 2026-05-18

### 重构
- **IM 机器人系统全面重写**（参考 LangBot / AstrBot / OpenClaw / ClawdBot）
  - **统一消息模型** — `ChatMessage` / `ReplyMessage` 跨平台标准化
  - **消息路由引擎** — `MessageRouter` 自动判断 @识别、私聊/群聊行为
  - **后台运行器** — `BotRunner` 支持多平台同时常驻运行
  - **Stream 长连接** — 飞书/钉钉/Slack/Discord WebSocket，无需公网服务器
  - **Polling 轮询** — Telegram 长轮询，无需公网
  - **丰富消息格式** — 飞书卡片、Discord Embed、Slack Block Kit
  - **群聊 @识别** — 只有被 @ 时才回复，避免刷屏
  - **优雅重连** — 所有适配器断线自动重连（5 秒间隔）
  - **Token 缓存** — 飞书/企微/钉钉 tenant_access_token 自动刷新

### CLI
- 新增 `kimix bots run` — 启动机器人后台服务

### 修复
- `ReplyMessage` 补充 `markdown` 字段（wecom/telegram 兼容）
- `router.py` sender callback 增加 platform fallback
- `runner.py` 注册 sender callback 到 router
- `pyproject.toml` 补充 `websockets` 依赖
- `verify_install.py` 补充 bots 模块与依赖检查

## [0.86] - 2026-05-18

### 新增
- **IM 机器人绑定系统** — 支持飞书/企业微信/Slack/Discord/Telegram/钉钉
  - `kimix bots setup` — 交互式绑定向导，分步引导 + 凭证验证 + 测试消息
  - `kimix bots list` — 列出已绑定平台
  - `kimix bots send` — 向所有已绑定平台广播消息
  - 每个平台两种接入方式（Webhook 快速模式 + 自建应用完整模式）
  - 配置持久化到 `~/.kimix/bots/{platform}.yaml`

### 修复
- **Windows CMD 抖动** — TUI 刷新率 10→4，关闭全屏模式
- **删除虚假启动脚本** — `install.bat` / `start.bat`
- **README 重写** — 删除虚假宣传，改为真实手动安装指南

### 版本号规范
- 每次修复 +0.01（用户指定）

## [0.85.1] - 2026-05-18

### 修复
- **Windows CMD 抖动** — TUI `refresh_per_second` 10→4，`screen=True`→`False`，减少多余 `refresh()` 调用
- **删除虚假启动脚本** — `install.bat` / `start.bat` 无法真实工作，已移除
- **README 重写** — 删除一键安装虚假宣传，改为手动安装指南

## [0.85.0] - 2026-05-18

### 新增
- **四层内存系统** — 工作记忆 + 语义记忆 + 情景记忆 + 层级记忆 + Hindsight机制
- **Agent经济系统** — 完整三阶段握手协议、智能匹配引擎、客观评分、任务生命周期管理
- **自动经济模式提示** — 闲置3小时提示闲时兼职、复杂任务提示赏金模式
- **ClawTip支付集成** — 京东背书Agent支付系统，SM4国密加密
- **纯本地Mock测试** — core_rules / progress_whip / clawtip / sandbox / quality / auto_economy 全部可验证
- **安全审计脚本** — 依赖扫描 + 密钥检测 + 代码安全 + 配置安全 + 沙盒策略
- **性能基准脚本** — 导入时间 + 内存占用 + 模块加载 + 工具注册 + 沙盒验证
- **多环境配置** — dev / test / prod 环境分离
- **国际化框架** — 中英文切换就绪
- **Docker一键运行** — Dockerfile + .dockerignore 完整
- **CI/CD配置** — GitHub Actions 自动 lint + 编译 + 测试
- **覆盖率配置** — .coveragerc 目标 80%

### 改进
- 类型注解全覆盖 — 96% 文件覆盖率
- 文档字符串全覆盖 — 100% 文件覆盖率
- 语法零错误 — Python 3.12 编译通过
- 代码规范 — 遵循 PEP8
- 测试标记 — 22个测试文件 + 7类 pytestmark
- 端到端演示 — Agent Alpha ↔ 云端平台 ↔ Agent Beta 全流程模拟

### 安全
- 收款信息零硬编码 — 全部从外部加载
- 沙盒三层策略 — dangerous / suspicious / network 分级检测
- 代码质量评估 — 五维量化评分

## [0.84.0] - 2026-05-18
- 初始完整版本
- 核心引擎 + 工具系统 + 内存系统 + CLI + TUI
- 22个测试文件 (smoke/benchmark/stress/chaos/unit/integration)
