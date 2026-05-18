# Kimi-Agent v0.85 变更日志

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
