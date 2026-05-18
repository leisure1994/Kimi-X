# 📦 Kimi-Agent (kimix) v{VERSION} - 完整安装与使用指南

> 🤖 基于 Kimi k2.6 模型的智能终端 AI Agent —— 比 deepseek-TUI 更智能

---

## 目录

1. [快速开始（3分钟上手）](#1-快速开始)
2. [详细安装教程（Windows/Mac/Linux）](#2-详细安装教程)
3. [API Key 获取与绑定](#3-api-key-获取与绑定)
4. [飞书/微信/钉钉/Slack 绑定](#4-im-机器人绑定)
5. [重启电脑后如何重新启动](#5-重启电脑后重新启动)
6. [常见问题与故障排除](#6-常见问题与故障排除)
7. [命令速查表](#7-命令速查表)

---

## 1. 快速开始（3分钟上手）

### 1.1 一键安装（推荐）

**Windows 用户请先看：CMD vs PowerShell**
> Windows 有两种命令行窗口，**命令不一样**：
> - **CMD（黑底白字）** → 用 `tar -xf` 解压
> - **PowerShell（蓝底白字）** → 用 `Expand-Archive` 解压
> 
> **怎么区分？** 看窗口标题栏：
> - 标题含 "cmd" → 是 CMD
> - 标题含 "PowerShell" 或 "Windows PowerShell" → 是 PowerShell
> - **不知道？两个命令都试，哪个不报错用哪个**

**Windows (CMD 黑窗口):**
```cmd
:: 第1步：下载
powershell -Command "curl -L -o kimix.zip https://github.com/kimi-agent/kimix/releases/download/v{VERSION}/kimix-agent-v{VERSION}.zip"

:: 第2步：解压（CMD 用 tar，Win10/Win11 都内置）
tar -xf kimix.zip

:: 如果 tar 报错，用这行替代：
:: powershell -Command "Expand-Archive kimix.zip -DestinationPath ."

:: 第3步：进入目录
cd kimix-agent-v{VERSION}

:: 第4步：创建虚拟环境并安装
python -m venv venv
venv\Scripts\activate.bat
pip install -e ".[dev]"

:: 第5步：配置 API Key
kimix auth
:: 按提示输入从 https://platform.moonshot.cn/ 获取的 Key

:: 第6步：启动！
kimix
```

**Windows (PowerShell 蓝窗口):**
```powershell
# 1. 下载并解压
curl -L -o kimix.zip https://github.com/kimi-agent/kimix/releases/download/v{VERSION}/kimix-agent-v{VERSION}.zip
Expand-Archive kimix.zip -DestinationPath .
cd kimix-agent-v{VERSION}

# 2. 创建虚拟环境并安装
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"

# 3. 配置 API Key
kimix auth
# 按提示输入从 https://platform.moonshot.cn/ 获取的 Key

# 4. 启动！
kimix
```

**Mac / Linux (Bash/Zsh):**
```bash
# 1. 下载并解压
curl -L -o kimix.zip https://github.com/kimi-agent/kimix/releases/download/v{VERSION}/kimix-agent-v{VERSION}.zip
unzip kimix.zip
cd kimix-agent-v{VERSION}

# 2. 创建虚拟环境并安装
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 3. 配置 API Key
kimix auth
# 按提示输入从 https://platform.moonshot.cn/ 获取的 Key

# 4. 启动！
kimix
```

---

## 2. 详细安装教程

### 2.1 前置要求

| 项目 | 最低要求 | 推荐 |
|:---|:---|:---|
| Python | 3.10 | 3.12 |
| pip | 23.0 | 最新版 |
| 操作系统 | Windows 10 / macOS 12 / Linux | 任意现代系统 |
| 网络 | 能访问 `api.moonshot.cn` | 稳定网络 |
| 磁盘空间 | 500MB | 1GB |
| 内存 | 2GB | 4GB+ |

#### 检查 Python 版本
```bash
python --version        # Windows
python3 --version       # Mac/Linux
```
如果显示 `Python 3.10.x` 或更高 → ✅ 继续
如果显示 `command not found` 或版本低于 3.10 → ❌ [先安装 Python](#安装-python)

#### 检查 pip
```bash
pip --version           # Windows
pip3 --version          # Mac/Linux
```
如果显示版本号 → ✅ 继续
如果没有 → `python -m ensurepip`

---

### 2.2 下载 Kimi-Agent

#### 方式 A：从 GitHub 下载（推荐）

**Windows (CMD):**
```cmd
:: 第1步：创建目录（换成你自己的路径，如 D:\KIMI X）
mkdir D:\KIMI X
cd /d D:\KIMI X

:: 第2步：下载
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/releases/latest/download/kimix-agent.zip

:: 第3步：解压（Win10/Win11 都内置 tar）
tar -xf kimix.zip

:: 如果 tar 报错，用这行替代：
:: powershell -Command "Expand-Archive kimix.zip -DestinationPath ."

:: 第4步：进入目录（文件夹名以实际解压出来的为准）
cd Kimi-X-master
```

**Windows (PowerShell):**
```powershell
# 第1步：创建目录（换成你自己的路径）
mkdir D:\KIMI X
cd D:\KIMI X

# 第2步：下载并解压
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/releases/latest/download/kimix-agent.zip
Expand-Archive kimix.zip -DestinationPath .

# 第3步：进入目录（文件夹名以实际解压出来的为准）
cd Kimi-X-master
```

**Mac/Linux:**
```bash
# 创建项目目录
mkdir ~/Kimi-X
cd ~/Kimi-X

# 下载并解压
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/releases/latest/download/kimix-agent.zip
unzip kimix.zip

# 进入目录（文件夹名以实际解压出来的为准）
cd Kimi-X-master
```

#### 方式 B：从飞书/微信接收的 ZIP 文件
1. 下载飞书/微信发给你的 `kimix-agent-v{VERSION}.zip`
2. 解压到任意目录（如 `D:\KIMI X` 或 `~/Kimi-X`）
3. 打开终端，cd 到解压后的 `kimix-agent-v{VERSION}` 目录

---

### 2.3 创建虚拟环境（重要！必须做！）

**为什么必须创建虚拟环境？**
- 避免影响系统 Python 环境
- 防止与其他项目依赖冲突
- 方便后续升级和卸载

**Windows (CMD):**
```cmd
:: 第1步：进入项目目录（换成你自己的实际路径）
cd /d D:\KIMI X\Kimi-X-master

:: 第2步：创建虚拟环境
python -m venv venv

:: 第3步：激活虚拟环境
venv\Scripts\activate.bat

:: 第4步：安装依赖（注意：CMD里去掉引号）
pip install -e .[dev]

:: 第5步：配置 API Key
kimix auth

:: 第6步：启动
kimix
```

**Windows (PowerShell):**
```powershell
# 第1步：进入项目目录（换成你自己的实际路径）
cd D:\KIMI X\Kimi-X-master

# 第2步：创建虚拟环境
python -m venv venv

# 第3步：激活虚拟环境
venv\Scripts\activate

# 第4步：安装依赖
pip install -e ".[dev]"

# 第5步：配置 API Key
kimix auth

# 第6步：启动
kimix
```

**⚠️ 常见错误：**

| 错误信息 | 原因 | 解决方法 |
|:---|:---|:---|
| `No module named venv` | Python 安装不完整 | 重新安装 Python，勾选 "Add to PATH" |
| `Permission denied` | 权限不足 | Mac/Linux: `chmod +x venv/bin/activate` |
| `activate 不是内部命令` | Windows PowerShell 策略 | 以管理员运行 `Set-ExecutionPolicy RemoteSigned` |

---

### 2.4 安装依赖

在虚拟环境激活状态下（看到 `(venv)` 前缀）：

```bash
pip install -e ".[dev]"
```

这会安装所有依赖，包括：
- `openai` — Kimi API 客户端
- `rich` — 终端美化
- `pydantic-settings` — 配置管理（v{VERSION} 新增）
- 等等...

**安装时间**：2-5 分钟（取决于网络速度）

**⚠️ 常见错误：**

| 错误信息 | 原因 | 解决方法 |
|:---|:---|:---|
| `No module named pydantic_settings` | 依赖缺失（旧版本问题） | `pip install pydantic-settings>=2.0` |
| `Connection timeout` | 网络慢/被墙 | 换用国内镜像：`pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `gcc/clang 错误` | 缺少编译器 | Windows: 安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/?q=build+tools)；Mac: `xcode-select --install` |

---

### 2.5 验证安装

```bash
kimix --version
```

**预期输出：**
```
0.91
```

如果出现 `command not found`：
```bash
# Windows
venv\Scripts\kimix --version

# Mac/Linux
venv/bin/kimix --version
```

---

## 3. API Key 获取与绑定

### 3.1 获取 API Key

1. 打开浏览器，访问 **https://platform.moonshot.cn/**
2. 点击右上角 **"注册/登录"**（用手机号或邮箱注册）
3. 登录后，点击左侧菜单 **"API Key 管理"**
4. 点击 **"新建"** 按钮
5. 给 Key 起个名字（如 `kimix-local`）
6. 点击 **"创建"**
7. **⚠️ 立即复制弹出的 Key**（格式：`sk-xxxxxxxx`）
   - **这个 Key 只显示一次，刷新页面就看不到了！**
   - 建议保存到密码管理器或记事本

### 3.2 绑定 API Key（方式一：命令行交互）

```bash
kimix auth
```

按提示输入：
```
? 请输入 Moonshot API Key: sk-xxxxxxxxxxxxxxx
? 自定义 API 基础 URL (回车使用默认): [直接回车]
✅ API Key 已配置！
```

### 3.3 绑定 API Key（方式二：直接写入配置文件）

配置文件路径：`~/.kimix/config.yaml`

**Windows:**
```powershell
notepad $env:USERPROFILE\.kimix\config.yaml
```

**Mac/Linux:**
```bash
mkdir -p ~/.kimix
cat > ~/.kimix/config.yaml << 'EOF'
auth:
  api_key: "sk-你的APIKey"
  base_url: "https://api.moonshot.cn/v1"

model:
  default: "kimi-k2.6"
  thinking: true
  max_tokens: 16384
  temperature: 0.7
EOF
```

### 3.4 验证 API Key 是否有效

```bash
kimix "你好，请用一句话介绍自己" --batch
```

**预期输出：**
```
你好，我是 Kimi，由月之暗面科技有限公司开发的人工智能助手...
```

**如果显示 `API Key 未配置`：**
- 检查 `~/.kimix/config.yaml` 是否存在
- 检查 Key 是否正确复制（不要多复制空格）
- 检查 Key 是否过期（去平台重新创建）

**如果显示 `Invalid Authentication`：**
- Key 已失效/被删除 → 去平台重新创建
- 复制时多了空格 → 重新复制
- 使用了测试环境 Key → 换成正式环境 Key

---

## 4. IM 机器人绑定（飞书/微信/钉钉/Slack/Discord/Telegram）

### 4.1 飞书机器人绑定

```bash
kimix bots feishu
```

按提示输入：
1. **App ID** — 从飞书开放平台获取（https://open.feishu.cn/）
   - 创建企业自建应用 → 凭证与基础信息 → App ID
2. **App Secret** — 同上页面 → App Secret（点击显示）
3. **Encrypt Key** — 事件与回调 → Encrypt Key
4. **Verification Token** — 事件与回调 → Verification Token

**常见问题：**

| 问题 | 解决方法 |
|:---|:---|
| 不知道 App ID 在哪里 | 飞书开放平台 → 你的应用 → 凭证与基础信息 |
| 收不到消息 | 检查事件订阅 URL 是否配置正确，是否已发布应用 |
| 权限不足 | 应用管理后台 → 权限管理 → 添加 `im:chat:readonly`, `im:message`, `im:message:send` |

### 4.2 企业微信机器人绑定

```bash
kimix bots wecom
```

按提示输入：
1. **CorpID** — 企业微信管理后台 → 我的企业 → 企业ID
2. **AgentID** — 应用管理 → 自建应用 → AgentId
3. **Secret** — 同上 → Secret

### 4.3 Slack 机器人绑定

```bash
kimix bots slack
```

1. 访问 https://api.slack.com/apps
2. Create New App → From scratch
3. 复制 `Bot User OAuth Token`（格式：`xoxb-...`）
4. 粘贴到 kimix 提示中

### 4.4 Discord 机器人绑定

```bash
kimix bots discord
```

1. 访问 https://discord.com/developers/applications
2. New Application → Bot → Add Bot
3. 复制 `Token`（格式：长串随机字符）
4. 粘贴到 kimix 提示中

---

## 5. 重启电脑后重新启动

### 5.1 快速启动（记得这3步）

**Windows (CMD):**
```cmd
:: 1. 打开 CMD 窗口
:: 2. 进入项目目录（把路径换成你自己的）
cd D:\KIMI X\Kimi-X-master

:: 3. 激活虚拟环境
venv\Scripts\activate.bat

:: 4. 启动
kimix
```

**Windows (PowerShell):**
```powershell
# 1. 打开 PowerShell 窗口
# 2. 进入项目目录（把路径换成你自己的）
cd D:\KIMI X\Kimi-X-master

# 3. 激活虚拟环境
venv\Scripts\activate

# 4. 启动
kimix
```

**Mac/Linux:**
```bash
# 1. 打开终端
# 2. 进入项目目录
cd ~/Kimi-X-master
# 3. 激活虚拟环境
source venv/bin/activate
# 4. 启动
kimix
```

### 5.2 创建快捷启动脚本（推荐）

**Windows (CMD) — 创建 `start-kimix.bat`：**
1. 右键桌面 → 新建 → 文本文档
2. 改名为 `start-kimix.bat`（注意：要显示文件扩展名，否则改的是 `start-kimix.bat.txt`）
3. 右键编辑，粘贴以下内容（把路径换成你自己的）：
```batch
@echo off
cd /d D:\KIMI X\Kimi-X-master
call venv\Scripts\activate.bat
kimix
pause
```
4. 保存，双击即可启动！

**Windows (PowerShell) — 创建 `start-kimix.ps1`：**
```powershell
# 保存为 start-kimix.ps1，双击或用右键"使用 PowerShell 运行"
cd D:\KIMI X\Kimi-X-master
venv\Scripts\activate
kimix
```

**Mac — 创建 `start-kimix.command`：**
```bash
cd ~/Kimi-X-master
source venv/bin/activate
kimix
```
然后：
```bash
chmod +x start-kimix.command
```
双击即可启动！

**Linux — 创建别名：**
在 `~/.bashrc` 或 `~/.zshrc` 中添加：
```bash
alias kimix-start='cd ~/Kimi-X-master && source venv/bin/activate && kimix'
```
然后 `source ~/.bashrc`，以后输入 `kimix-start` 即可启动！

---

## 6. 常见问题与故障排除

### Q1: 安装时报错 `No module named 'pydantic_settings'`

```bash
pip install pydantic-settings>=2.0
pip install -e ".[dev]"
```

### Q2: 启动后卡在 TUI 界面不动

**原因：** 服务器/无真实终端环境（如 SSH、Docker、CI）不支持 Rich TUI

**解决：** 使用纯文本模式
```bash
kimix --batch           # 一次性问答
kimix --batch           # 交互式纯文本模式
```

### Q3: `kimix: command not found`

**原因 A：** 虚拟环境没激活

**CMD:**
```cmd
venv\Scripts\activate.bat
```

**PowerShell:**
```powershell
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

**原因 B：** 用完整路径

**CMD:**
```cmd
venv\Scripts\kimix
```

**PowerShell/Mac/Linux:**
```powershell
venv\Scripts\kimix          # Windows
venv/bin/kimix               # Mac/Linux
```

### Q4: API 返回 `401 Invalid Authentication`

1. 打开 https://platform.moonshot.cn/
2. 检查 API Key 列表，确认你的 Key 还在
3. 如果 Key 旁边显示 "已删除" 或不存在了 → 新建一个
4. 重新运行 `kimix auth`

### Q5: 网络超时 / 连接失败

```bash
# 测试网络连通性
curl -I https://api.moonshot.cn/v1

# 如果超时，尝试换 DNS 或使用代理
# Windows: 设置 → 网络和 Internet → 代理
# Mac: 系统设置 → 网络 → 代理
```

### Q6: 安装依赖很慢

```bash
# 使用国内镜像加速
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或阿里云镜像
pip install -e ".[dev]" -i https://mirrors.aliyun.com/pypi/simple/
```

### Q7: 如何升级到新版本

```bash
# 1. 备份旧版本
cd ..
cp -r kimix-agent-v{VERSION} kimix-agent-v{VERSION}-backup

# 2. 下载新版
curl -L -o kimix.zip https://github.com/kimi-agent/kimix/releases/download/v0.92/kimix-agent-v0.92.zip

# 3. 解压覆盖
unzip -o kimix.zip

# 4. 重新安装依赖
cd kimix-agent-v0.92
source venv/bin/activate
pip install -e ".[dev]"
```

### Q8: 如何完全卸载

```bash
# 1. 删除项目目录
cd ..
rm -rf kimix-agent-v{VERSION}
```

**删除配置（可选）：**

**Windows (CMD):**
```cmd
rmdir /s /q %USERPROFILE%\.kimix
```

**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force $env:USERPROFILE\.kimix
```

**Mac/Linux:**
```bash
rm -rf ~/.kimix
```

---

## 7. 命令速查表

| 命令 | 功能 | 示例 |
|:---|:---|:---|
| `kimix` | 启动交互式 TUI | `kimix` |
| `kimix --batch` | 启动纯文本交互模式 | `kimix --batch` |
| `kimix "问题"` | 一次性问答 | `kimix "写一个Python函数"` |
| `kimix -p "问题"` | Plan 模式 | `kimix -p "如何优化数据库"` |
| `kimix -y "任务"` | YOLO 全自主模式 | `kimix -y "重构这个项目"` |
| `kimix -m agent` | 指定模式启动 | `kimix -m agent` |
| `kimix auth` | 配置 API Key | `kimix auth` |
| `kimix config` | 查看/编辑配置 | `kimix config --show` |
| `kimix doctor` | 诊断检查 | `kimix doctor` |
| `kimix tool list` | 列出所有工具 | `kimix tool list` |
| `kimix session list` | 列出会话 | `kimix session list` |
| `kimix bots feishu` | 绑定飞书机器人 | `kimix bots feishu` |
| `kimix bots wecom` | 绑定企业微信 | `kimix bots wecom` |
| `kimix bots slack` | 绑定 Slack | `kimix bots slack` |
| `kimix bots discord` | 绑定 Discord | `kimix bots discord` |
| `kimix --version` | 查看版本 | `kimix --version` |
| `kimix --help` | 查看帮助 | `kimix --help` |

---

## 附录：安装 Python

### Windows
1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.12.x
3. 安装时 **务必勾选** "Add Python to PATH"
4. 点击 "Install Now"

### Mac
```bash
brew install python@3.12
```
或下载安装包：https://www.python.org/downloads/macos/

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-pip
```

### Linux (CentOS/RHEL/Fedora)
```bash
sudo dnf install python3.12 python3.12-pip
```

---

**最后更新：2026-05-19**
**版本：v{VERSION}**
**GitHub：https://github.com/kimi-agent/kimix**
