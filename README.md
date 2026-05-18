# Kimi-Agent (kimix)

<div align="center">

**为 Kimi K2.6 打造的终端 AI Agent**

[安装指南](#安装) · [文档](docs/) · [CHANGELOG](CHANGELOG.md)

</div>

## 特性

- **四层内存** — 工作记忆 + 语义记忆 + 情景记忆 + 层级记忆 + Hindsight 复盘
- **Agent 经济** — 闲时兼职、赏金任务、客观评分、平台仲裁
- **ClawTip 支付** — 京东背书 Agent 支付系统，SM4 国密加密
- **多模式运行** — Agent / Plan / Explore / Auto / YOLO
- **安全沙盒** — 代码三层检测（dangerous / suspicious / network）
- **完整测试** — 27 个测试文件覆盖 smoke/benchmark/stress/chaos/unit/integration

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/yourname/kimix.git
cd kimix

# 安装
pip install -e ".[all]"

# 配置 API Key
export MOONSHOT_API_KEY="sk-xxxxxx"

# 启动
python3 -m kimix
```

详见 [README_INSTALL.md](README_INSTALL.md)。

## 版本

当前: **0.88** — IM 机器人系统重写（Stream 长连接/统一消息路由/@识别）

历史: [CHANGELOG.md](CHANGELOG.md)

## 项目结构

```
kimix/
├── kimix/          # 核心源码
│   ├── core/       # 引擎 + 经济系统 + 进度鞭子
│   ├── llm/        # LLM 客户端 + 成本追踪
│   ├── memory/     # 四层内存 + Hindsight
│   ├── tools/      # 20+ 工具（shell/web/git/文件...）
│   ├── modes/      # 5 种运行模式
│   ├── ui/         # TUI (Rich) + CLI (Typer)
│   └── i18n.py     # 国际化框架
├── tests/          # 27 个测试文件
├── config/         # dev / test / prod 环境
├── docs/           # API 文档 + 部署指南 + 架构设计
├── scripts/        # 安全审计 + 性能基准 + 安装验证
└── Dockerfile      # Docker 一键运行
```

## 安全

- 收款信息零硬编码，全部从环境变量/配置文件加载
- 沙盒三层策略检测危险代码
- 五维代码质量评估系统

## 许可证

MIT License — 详见 [LICENSE](LICENSE)
