# Kimi-Agent (kimix) — 安装指南

> 专为 Kimi K2.6 模型打造的终端 AI Agent。目前需要手动安装，没有一键安装脚本。

## 前置要求

- **Python 3.10+**（3.12 推荐）
- **pip**（Python 包管理器）
- **Git**（可选，用于克隆仓库）

如果不确定 Python 版本：
```bash
python3 --version   # macOS/Linux
python --version     # Windows
```

---

## 安装方式一：pip 安装（推荐）

```bash
pip install kimix-agent
```

如果包名不可用，使用方式二。

---

## 安装方式二：源码安装

### Step 1: 获取源码

```bash
git clone https://github.com/yourname/kimix.git
cd kimix
```

或直接下载 ZIP 并解压。

### Step 2: 安装依赖

```bash
# 进入项目目录后
pip install -e ".[all]"
```

如果报错缺少某些依赖（如 `rich`、`httpx`、`typer`），单独安装：
```bash
pip install rich httpx typer prompt-toolkit
```

### Step 3: 验证安装

```bash
python3 -m kimix --version
# 预期输出: 0.85.1
```

---

## 配置 API Key

Kimi-Agent 需要 LLM API Key 才能工作。

### 获取 Key
1. 访问 https://platform.moonshot.cn/
2. 注册/登录 → 创建 API Key
3. 复制以 `sk-` 开头的密钥

### 配置方式

**方式 A：环境变量（推荐，临时）**
```bash
# macOS/Linux
export MOONSHOT_API_KEY="sk-xxxxxx"

# Windows CMD
set MOONSHOT_API_KEY=sk-xxxxxx

# Windows PowerShell
$env:MOONSHOT_API_KEY="sk-xxxxxx"
```

**方式 B：配置文件（持久化）**
```bash
mkdir -p ~/.kimix
```
创建 `~/.kimix/config.yaml`，写入：
```yaml
llm:
  default_provider: "kimi"
  api_key: "sk-xxxxxx"
```

---

## 启动

```bash
# 交互式 TUI 模式
python3 -m kimix

# 一次性问答
python3 -m kimix "你好"

# 指定模式
python3 -m kimix --mode agent
python3 -m kimix --mode plan "写一个Python脚本"

# 查看帮助
python3 -m kimix --help
```

---

## 5 种工作模式

| 模式 | 特点 | 适合场景 |
|:---|:---|:---|
| `explore` | 只读，thinking 开启 | 代码理解、信息收集 |
| `plan` | 只读+计划生成 | 方案设计、架构规划 |
| `agent` | 交互执行，智能审批 | 日常开发（默认） |
| `auto` | 自适应 thinking+审批门 | 平衡效率和安全 |
| `yolo` | 全自主，自动审批 | 最高效率（慎用） |

---

## Docker 运行（可选）

```bash
docker build -t kimix-agent .
docker run -it --rm -e MOONSHOT_API_KEY=sk-xxxxxx kimix-agent
```

---

## 常见问题

### Q: 启动时提示 "引擎未初始化"
A: 没有配置 API Key。参考上面的配置方式。

### Q: Windows CMD 下界面抖动
A: 已修复。如果仍抖动，尝试增大 CMD 窗口或使用 Windows Terminal。

### Q: 依赖安装失败
A: 使用国内 pip 源：
```bash
pip install -e ".[all]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 目录结构

```
kimix/
├── kimix/          # 核心源码
│   ├── core/       # 引擎、经济系统
│   ├── llm/        # LLM 客户端
│   ├── memory/     # 四层内存
│   ├── tools/      # 工具系统
│   ├── modes/      # 运行模式
│   └── ui/         # TUI/CLI 界面
├── tests/          # 测试
├── config/         # 环境配置 (dev/test/prod)
├── docs/           # 文档
├── scripts/        # 辅助脚本
├── CHANGELOG.md    # 版本变更
└── README.md       # 项目主页
```

---

License: MIT
