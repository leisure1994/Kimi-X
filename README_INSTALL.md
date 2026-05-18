# Kimi-Agent 安装指南 — 完全零基础版

> 完全不懂代码也能跟着装完。每一步都有说明，卡住就发截图给我。

---

## 📋 准备清单

装之前确认你有：
- [ ] 一台 Windows 电脑（Win10 或 Win11）
- [ ] 能打开网页的网
- [ ] 大约 15 分钟时间

不需要买任何东西，全部免费。

---

## 🎯 总体步骤（先了解全貌，再往下看详细步骤）

1. 下载 Kimi-Agent 代码（ZIP 文件）
2. 安装 Python（运行环境）
3. 打开黑色窗口，安装 Kimi-Agent
4. 去 Kimi 官网拿一个 API Key（密钥）
5. 把密钥保存到电脑里
6. 启动 Kimi-Agent，开始使用

---

## 第 1 步：下载代码

### 方法 A：从我发的 ZIP 下载（推荐，最简单）

1. 在飞书聊天记录里找到我发的 `kimix-agent-v0.91.zip`
2. 点击下载按钮
3. 下载完成后，在"下载"文件夹里找到这个 ZIP 文件
4. **右键 ZIP 文件 → "全部解压缩"**（Win11）或 **"解压到当前文件夹"**（Win10）
5. 解压后你会看到一个叫 `kimix-agent-v0.91` 的文件夹

> 💡 **记住这个文件夹在哪里**，后面要用。建议把它**拖到桌面**，方便找。

### 方法 B：从 GitHub 下载（GitHub 没被墙时可以用）

1. 打开 https://github.com/leisure1994/Kimi-X
2. 点击绿色按钮 `<> Code` → `Download ZIP`
3. 下载完成后右键解压

---

## 第 2 步：安装 Python

Python 是 Kimi-Agent 的运行环境，就像游戏需要安装游戏引擎一样。

### 2.1 下载 Python

1. 打开浏览器，输入 https://www.python.org/downloads/
2. 页面往下滚动，找到 **Python 3.12.x**
3. 点击 `Download Python 3.12.x`（最大的那个按钮）
4. 下载的是 `python-3.12.x-amd64.exe`，大约 30MB

### 2.2 安装 Python（关键步骤！）

1. 双击下载好的 `python-3.12.x-amd64.exe`
2. 弹出一个安装窗口
3. **⚠️ 第一步最重要：勾上 "Add Python to PATH"**
   - 窗口下方有个小字，前面有个小方框
   - 点一下，让它打勾 ✅
   - 如果没勾，后面全部会失败
4. 点击 **"Install Now"**（立即安装）
5. 等进度条跑完（大概 1-2 分钟）
6. 显示 "Setup was successful" → 点 **Close**

### 2.3 验证 Python 装好了没

1. 按键盘上的 `Win + R`（Windows 键 + R 键）
2. 弹出一个"运行"小窗口
3. 输入 `cmd`，按回车（或点确定）
4. 出现一个**黑色窗口**（这叫"命令提示符"）
5. 在黑色窗口里输入：`python --version`
6. 按回车

**如果显示 `Python 3.12.x`：** ✅ 装好了，继续下一步

**如果显示 `'python' 不是内部或外部命令`：** ❌ 说明第 2.2 步没勾 "Add Python to PATH"，卸载 Python 重新装一遍。

> 怎么卸载：开始菜单 → 设置 → 应用 → 找到 Python → 卸载

---

## 第 3 步：安装 Kimi-Agent

### 3.1 打开黑色窗口

1. 按 `Win + R`
2. 输入 `cmd`
3. 按回车

### 3.2 进入代码文件夹

假设你把 `kimix-agent-v0.91` 文件夹放在了**桌面**：

在黑色窗口里输入：
```
cd Desktop\kimix-agent-v0.91
```
按回车。

**如果不在桌面**，你需要找到文件夹的位置。比如放在 D 盘的"我的文件"里：
```
cd D:\我的文件\kimix-agent-v0.91
```

> 💡 **小技巧**：不会写路径？打开文件夹，点地址栏，复制路径，粘贴到黑色窗口。

### 3.3 执行安装命令

在黑色窗口里输入下面这行（**注意标点符号都要打对**）：
```
pip install -e ".[dev]"
```
按回车。

你会看到一堆文字在滚动，这是正常的，它在下载需要的文件。

**要等多久？**
- 网速快：2-3 分钟
- 网速慢：5-10 分钟

**最后你会看到：**
```
Successfully installed kimix-0.91 ...
```
这说明装好了。

### 3.4 如果安装失败（常见问题）

**问题 A：红色报错，说网络连不上**

这是国内网络连不上国外服务器。换国内源：
```
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**问题 B：提示 "pip 不是内部命令"**

Python 没装好，回到第 2 步重装。

**问题 C：提示 "No module named setuptools"**
```
pip install setuptools
```
然后再执行 `pip install -e ".[dev]"`

---

## 第 4 步：获取 Kimi API Key

Kimi-Agent 需要调用 Kimi 大模型，需要一个密钥。

### 4.1 注册 Kimi 开放平台

1. 打开浏览器，输入 https://platform.moonshot.cn/
2. 点击右上角"登录"
3. 用手机号登录（收个验证码）
4. 登录成功后进入控制台

### 4.2 创建 API Key

1. 页面右上角，点你的头像 → "API Key 管理"
2. 点按钮 **"新建"**
3. 起一个名字（比如"我的 Agent"）
4. 点 **"创建"**
5. 你会看到一串字符，格式是 `sk-xxxxxxxxxxxxxxxx`
6. **点旁边的复制按钮**，把这串字符复制下来

> ⚠️ **重要**：这串字符只显示一次，关掉页面就没了。先复制到一个安全的地方（比如记事本）。

---

## 第 5 步：保存密钥到电脑

### 5.1 创建配置文件

在**黑色窗口**里（还在 `kimix-agent-v0.91` 文件夹下），输入下面两行，**一行一行执行**：

第一行：
```
mkdir %USERPROFILE%\.kimix
```
按回车。

第二行（**把 `sk-你的密钥` 换成你刚才复制的真实密钥**）：
```
echo {"api_key": "sk-你的密钥"} > %USERPROFILE%\.kimix\config.json
```
按回车。

> 示例：如果你的密钥是 `sk-abcd1234`，那就输入：
> ```
> echo {"api_key": "sk-abcd1234"} > %USERPROFILE%\.kimix\config.json
> ```

### 5.2 验证保存成功

在黑色窗口输入：
```
type %USERPROFILE%\.kimix\config.json
```
按回车。

如果显示 `{"api_key": "sk-..."}`，就是成功了。

---

## 第 6 步：启动 Kimi-Agent！

在黑色窗口里输入：
```
python -m kimix
```
按回车。

如果看到类似下面的画面：
```
🤖 Kimi-Agent 0.91 | 模式: agent
输入 /help 查看帮助，/exit 退出。
>
```
**恭喜你，装好了！**

现在在 `>` 后面打字，按回车，Agent 就会回复你。

---

## 🔄 下次开机后怎么重新启动？

这是很多人问的问题。**你不需要重新安装**，只需要重新打开。

### 方法：三步重新启动

1. 按 `Win + R`，输入 `cmd`，回车 → 打开黑色窗口
2. 输入：`cd Desktop\kimix-agent-v0.91`（进入文件夹）
3. 输入：`python -m kimix`（启动）

**只要这三步，不需要重新装 Python，不需要重新配密钥。**

### 更快的启动方式（创建快捷方式）

如果你想双击图标就启动，可以做一个批处理文件：

1. 在桌面右键 → 新建 → 文本文档
2. 打开文本文档，输入下面内容：
   ```
   @echo off
   cd /d C:\Users\你的用户名\Desktop\kimix-agent-v0.91
   python -m kimix
   pause
   ```
   （把 `C:\Users\你的用户名\Desktop` 换成你实际的桌面路径）
3. 文件 → 另存为
4. 文件名改为 `启动 Kimi-Agent.bat`（注意后缀是 .bat，不是 .txt）
5. 保存类型选"所有文件"
6. 保存后，双击这个 `.bat` 文件就能启动

> 💡 怎么找你的用户名？打开 CMD，输入 `echo %USERNAME%`，显示的就是。

---

## 🆘 常见问题

### "python 不是内部命令"
**原因**：Python 没装好，或者没勾 PATH  
**解决**：回到第 2 步，重装 Python，务必勾选 "Add Python to PATH"

### "pip install" 时一堆红色报错
**原因**：国内网络下载国外包失败  
**解决**：用清华源：
```
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### "API Key not found"
**原因**：密钥没保存对  
**解决**：回到第 5 步，重新执行那两行命令

### 启动后提示 "引擎未初始化"
**原因**：API Key 没配或配错了  
**解决**：检查 `config.json` 内容，重新保存密钥

### 提示 "找不到 kimix-agent-v0.91 文件夹"
**原因**：`cd` 的路径不对  
**解决**：确认文件夹在哪里。可以先把文件夹拖到桌面，然后输入 `cd Desktop\kimix-agent-v0.91`

---

## 📦 想更新到新版本怎么办？

当我发布 v0.92、v0.93 等新版本时，你只需要：

1. 下载新的 ZIP
2. 解压，**覆盖旧文件夹**（直接拖进去替换）
3. 重新执行 `pip install -e ".[dev]"`
4. 密钥和配置都在，不需要重新配

---

## 📞 还是装不上？

直接截图发给我，我帮你看。截图要包含：
- 黑色窗口里显示的文字
- 报错信息（红色字）

飞书直接回复这条消息就行。

---

**当前版本：0.91**
