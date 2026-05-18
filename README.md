# Kimi-Agent (kimix)

<div align="center">

**为 Kimi K2.6 打造的终端 AI Agent**

[🚀 立即安装](#安装) · [📖 功能说明](#功能) · [💬 问题反馈](https://github.com/leisure1994/Kimi-X/issues)

</div>

---

## 📦 安装（推荐：下载 ZIP）

不需要懂代码，不需要配置网络，三步完成。

> ⚠️ **重要**：以下命令中的路径只是**示例**，你要换成自己电脑上的**实际路径**。
> 比如你解压到了 `D:\KIMI X\Kimi-X-master`，就写这个路径。

### 第一步：下载代码

**用 CMD 或 PowerShell 下载并解压**（不需要浏览器，不需要右键）：

> 下面命令会自动下载、解压，你只需要复制粘贴执行。

### 第二步：安装运行环境

需要两个免费软件：

| 软件 | 作用 | 下载地址 |
|:---|:---|:---|
| **Python** | 运行 Agent 的程序 | [python.org/downloads](https://www.python.org/downloads/) |
| **Git** | 可选，更新代码用 | [git-scm.com](https://git-scm.com/download/win) |

**Python 安装时注意：**
1. 下载 Python 3.12（Windows Installer 64-bit）
2. 安装时**勾选 "Add Python to PATH"**（重要！）
3. 一直点"下一步"直到完成

### 第三步：安装 Kimi-Agent

**Windows 用户注意**：
> Windows 有两种命令行窗口，**命令不一样**：
> - **CMD（黑底白字，标题栏写 "cmd"）**
> - **PowerShell（蓝底白字，标题栏写 "PowerShell"）**
>
> 下面分别写了两种窗口的命令，**用你打开的那种**。

**CMD（黑色窗口）:**
```cmd
:: 第1步：下载代码到桌面（或任意位置）
cd /d %USERPROFILE%\Desktop
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/archive/refs/heads/master.zip

:: 第2步：解压（Win10/11 都自带 tar）
tar -xf kimix.zip

:: 第3步：进入解压后的文件夹（文件夹名固定为 Kimi-X-master）
cd Kimi-X-master

:: 第4步：创建虚拟环境
python -m venv venv

:: 第5步：激活虚拟环境
venv\Scripts\activate.bat

:: 第6步：安装依赖（CMD里要去掉引号）
pip install -e .[dev]

:: 装完会显示 Successfully installed ...
```

**PowerShell（蓝色窗口）:**
```powershell
# 第1步：下载代码到桌面（或任意位置）
cd $env:USERPROFILE\Desktop
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/archive/refs/heads/master.zip

# 第2步：解压
Expand-Archive kimix.zip -DestinationPath .

# 第3步：进入解压后的文件夹（文件夹名固定为 Kimi-X-master）
cd Kimi-X-master

# 第4步：创建虚拟环境
python -m venv venv

# 第5步：激活虚拟环境
venv\Scripts\activate

# 第6步：安装依赖
pip install -e ".[dev]"

# 装完会显示 Successfully installed ...
```

**如果报错？看这里：**

| 错误 | 解决 |
|:---|:---|
| `tar 不是内部命令` | 换用 PowerShell 的 `Expand-Archive` |
| `No module named venv` | Python 没装好，重装并勾选 "Add to PATH" |
| `activate 不是内部命令` | PowerShell 需要管理员权限运行 `Set-ExecutionPolicy RemoteSigned` |
| `No module named pydantic_settings` | 运行 `pip install pydantic-settings>=2.0` 后再装 |
| 安装很慢 | 换国内镜像：`pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple` |

### 第四步：配置 Kimi API Key

1. 打开 https://platform.moonshot.cn/
2. 登录 → 右上角"API Key 管理" → 创建新 Key
3. 复制你的 Key（格式类似 `sk-xxxxx`）
4. 配置到 Agent：

**CMD:**
```cmd
kimix auth
:: 然后按提示粘贴你的 Key
```

**或者直接写配置文件（CMD）:**
```cmd
mkdir %USERPROFILE%\.kimix
echo {"api_key": "sk-你的密钥"} > %USERPROFILE%\.kimix\config.json
```
（把 `sk-你的密钥` 换成你复制的那串字符）

### 第五步：启动！

```cmd
kimix
```

看到 Kimi-Agent 界面出现就是成功了。

**如果提示 `kimix 不是内部命令`：**
```cmd
venv\Scripts\kimix
```

---

## 🔄 重启电脑后怎么重新打开

> 下面的路径假设你解压到了**桌面**。如果你解压到了其他位置（比如 `D:\KIMI X`），把路径换成你自己的。

**CMD:**
```cmd
cd /d %USERPROFILE%\Desktop\Kimi-X-master
venv\Scripts\activate.bat
kimix
```

**PowerShell:**
```powershell
cd $env:USERPROFILE\Desktop\Kimi-X-master
venv\Scripts\activate
kimix
```

**懒得每次输？创建快捷方式：**
1. 桌面右键 → 新建 → 文本文档
2. 改名为 `启动Kimix.bat`（注意：要显示文件扩展名）
3. 右键编辑，粘贴：
   ```batch
   @echo off
   cd /d %USERPROFILE%\Desktop\Kimi-X-master
   call venv\Scripts\activate.bat
   kimix
   pause
   ```
4. 保存，以后双击这个文件就能启动

> 如果你把 Kimi-X-master 解压到了其他位置（比如 `D:\KIMI X\Kimi-X-master`），把上面路径中的 `%USERPROFILE%\Desktop` 换成你自己的。

---

## 🛠️ 功能

- **四层内存** — 工作记忆 + 语义记忆 + 情景记忆 + 层级记忆，越用越懂你
- **Agent 经济** — 闲时兼职、赏金任务、客观评分
- **ClawTip 支付** — 京东背书，SM4 国密加密
- **多模式运行** — Agent / Plan / Explore / Auto / YOLO
- **安全沙盒** — 代码三层检测
- **IM 机器人** — 飞书/企业微信/Slack/Discord/Telegram/钉钉自动回复
- **完整测试** — 27 个测试文件覆盖各种场景

---

## 📂 项目结构

```
Kimi-X/
├── kimix/          # 核心源码
│   ├── core/       # 引擎 + 经济系统
│   ├── llm/        # Kimi 客户端
│   ├── memory/     # 四层内存
│   ├── tools/      # 20+ 工具
│   ├── modes/      # 5 种运行模式
│   ├── ui/         # 界面
│   └── bots/       # IM 机器人（飞书/钉钉/Discord...）
├── tests/          # 测试文件
├── config/         # 配置文件
├── docs/           # 技术文档
├── scripts/        # 安装验证脚本
└── README.md       # 你正在看的文件
```

---

## 🆘 常见问题

**Q：pip install 时报错 "No module named pip"？**
A：Python 安装时没勾选 "Add Python to PATH"，重装 Python 并勾选。

**Q：启动后提示 API Key 未配置？**
A：检查 `%USERPROFILE%\.kimix\config.json` 是否存在，里面要有 `"api_key": "sk-..."`。

**Q：Windows CMD 里字显示不全/界面乱？**
A：用 Windows Terminal 代替 CMD（微软商店下载），字体设为 Consolas。

**Q：GitHub 下载不了 ZIP？**
A：用 CMD 命令直接下载（Windows 10/11 都自带）：
```cmd
curl -L -o kimix.zip https://github.com/leisure1994/Kimi-X/archive/refs/heads/master.zip
```
如果 curl 也不可用，用 PowerShell：
```powershell
Invoke-WebRequest -Uri "https://github.com/leisure1994/Kimi-X/archive/refs/heads/master.zip" -OutFile "kimix.zip"
```

**Q：命令报错 `Expand-Archive` 找不到？**
A：你在 CMD 里运行了 PowerShell 的命令。换成 `tar -xf kimix.zip`。

---

## 📜 许可证

MIT License — 详见 [LICENSE](LICENSE)

**当前版本：0.91** · [完整安装文档](README_INSTALL.md) · [更新日志](CHANGELOG.md)

## 文曲星 writer-blue 修复经验汇总（2026-05-19 凌晨）

### 问题 1：工作台显示"请先选择项目"
**根因链：**
1. `auth.py` token 有效期只有 7 天（`60*24*7`）→ 用户 token 过期
2. 前端点击项目时 API 返回 401 → `localStorage` 中无 `current_project_id`
3. 工作台组件读 `localStorage.getItem("current_project_id")` → null → 显示"请先选择项目"

**修复：**
1. `auth.py`：`ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*7` → `60*24*365*10`（10年）
2. `preload-fix.js`：页面加载时自动注入新 token + 获取项目列表写入 localStorage

### 问题 2：记忆宫殿/故事河流空白
**根因链：**
1. React Router 各页面读取项目 ID 方式不一致：工作台读 localStorage，记忆宫殿/故事河流读 URL 参数 `?project=xxx`
2. 点击导航栏"记忆宫殿"时，URL 只有 `/#/memory-palace`，没有 `?project=`
3. 记忆宫殿组件用 `useSearchParams`（混淆后为 `Nj()`）读取 → 空值 → 无法加载数据

**修复：**
`preload-fix.js` v14 监听导航链接 click 事件 + hashchange 事件，自动附加 `?project=xxx`：
```javascript
// 点击时拦截，修正 href
document.addEventListener('click', function(e) {
  const a = e.target.closest('a[href^="#/"]');
  if (a && !a.href.includes('project=')) {
    a.setAttribute('href', href + '?project=' + pid);
  }
});
// hash 变化后自动修正
window.addEventListener('hashchange', () => fixCurrentHash());
```

### 问题 3：CSS 样式丢失
**根因：** `index.html` 引用 `./assets/index-D9sp7l5L.css`，但该文件不存在（实际为 `index-C_bjNTUP.css`）

**修复：** 修正 CSS `<link>` 指向

### 问题 4：API 404（数据库 UUID 格式不匹配）
**根因：** SQLite 中项目 ID 存储为无连字符格式 `fb81c9fe2a95427098682ad7fb0147af`，但 FastAPI Pydantic 序列化后返回带连字符 `fb81c9fe-2a95-4270-9868-2ad7fb0147af`。前端用带连字符的 ID 请求后端 → 后端 SQL `WHERE id='xxx'` → 格式不匹配 → 404

**修复：** `models.py` 中 `UUIDString.process_bind_param()` 统一去掉连字符：
```python
def process_bind_param(self, value, dialect):
    s = str(value)
    return s.replace('-', '')
```

### 缓存陷阱
浏览器缓存了有 bug 的旧脚本（v1-v9 会循环刷新），即使部署 v10+，浏览器仍加载缓存版本。必须同时处理：
1. nginx 添加 `Cache-Control: no-cache`
2. HTML 中 JS/CSS 加 `?v=版本号`
3. 强制刷新 `Ctrl + Shift + R`

### 教训
- **token 有效期**：文学创作项目周期数月，7 天太短
- **前端 bundle 压缩后不可直接修改**：只能通过外部 `<script>` 注入修复
- **React hash router + query string**：`/#/page?param=val`，`useSearchParams` 只读 hash 内 query
- **不要把任务推给用户**：不应让用户执行 console 代码或创建书签，全部在服务器端解决
- **数据库 UUID 格式一致性**：SQLite TEXT 存储 UUID 时，bind_param 和 result_value 的格式转换必须一致
