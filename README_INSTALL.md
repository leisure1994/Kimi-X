# Kimi-Agent 安装指南 — Windows 完整版

> 完全不懂代码也能跟着装完。如果卡住，直接发截图问我。

---

## 准备清单

装之前确认你有：
- [ ] 一台 Windows 电脑（Win10/Win11 都行）
- [ ] 网络能打开网页
- [ ] 10 分钟时间

---

## 第 1 步：下载代码（不用 GitHub，直接下 ZIP）

### 方法 A：GitHub 下载
1. 打开 https://github.com/leisure1994/Kimi-X
2. 点击绿色按钮 `<> Code` → `Download ZIP`
3. 下载完成后，**右键 ZIP → 全部解压缩** → 选一个文件夹（比如桌面）

### 方法 B：飞书下载（推荐，GitHub 被墙时用）
1. 在飞书聊天记录里找到我发的 `kimix-agent-v0.90.zip`
2. 点击下载
3. 下载完成后，**右键 ZIP → 全部解压缩**

解压缩后你会看到一个 `Kimi-X-master` 或 `kimix-agent-v0.90` 文件夹，这就是你的代码。

---

## 第 2 步：安装 Python

Kimi-Agent 是用 Python 写的，你需要先装 Python 这个运行环境。

1. 打开 https://www.python.org/downloads/
2. 找到 **Python 3.12.x**（最大的那个下载按钮）
3. 下载 `Windows installer (64-bit)`
4. 双击安装

**⚠️ 关键步骤：安装时务必勾选 "Add Python to PATH"**

![Add Python to PATH](docs/python_install.png)

（如果没有这个图，记住：安装第一页最下面有个小勾，一定要勾上，然后点 "Install Now"）

5. 等进度条跑完，点 Close

**验证 Python 装好了没：**
1. 按 `Win + R`，输入 `cmd`，回车
2. 黑色窗口里输入：`python --version`
3. 如果显示 `Python 3.12.x`，就是成功了
4. 如果显示 "不是内部命令"，说明没勾 PATH，重装

---

## 第 3 步：安装 Kimi-Agent

1. 打开黑色窗口（`Win + R` → `cmd` → 回车）
2. 进入你解压的文件夹。假设你解压到桌面：
   ```
   cd Desktop\Kimi-X-master
   ```
   （如果你改名了或者放别的地方，就改成对应的路径）

3. 安装依赖：
   ```
   pip install -e ".[dev]"
   ```
   按回车，等它自动下载。可能会等 3-5 分钟，取决于网速。

4. 看到 `Successfully installed kimix` 就是装好了。

**如果报错 "pip 不是内部命令"：**
- Python 没装好，回到第 2 步重装，记得勾 PATH。

**如果报错网络问题（红色字很多）：**
- 这是国内下载国外包的问题，输入下面这个换国内源：
  ```
  pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```

---

## 第 4 步：配置 Kimi API Key

Kimi-Agent 需要调用 Kimi 大模型，你需要一个 API Key。

### 获取 Key
1. 打开 https://platform.moonshot.cn/
2. 用手机号或微信登录
3. 右上角 → "API Key 管理"
4. 点 "新建" → 起一个名字（比如"我的Agent"）→ 创建
5. 复制那串 `sk-` 开头的字符（这就是你的 Key）

### 保存 Key
在黑色窗口里依次输入下面两行（**把 sk-xxx 换成你刚才复制的真实 Key**）：

```
mkdir %USERPROFILE%\.kimix
```

```
echo {"api_key": "sk-你的真实密钥"} > %USERPROFILE%\.kimix\config.json
```

**怎么确认保存成功了？**

输入：
```
type %USERPROFILE%\.kimix\config.json
```

如果显示 `{"api_key": "sk-..."}`，就是成功了。

---

## 第 5 步：启动 Kimi-Agent！

在黑色窗口里输入：

```
python -m kimix
```

或者输入：

```
kimix
```

按回车，你应该会看到 Kimi-Agent 的欢迎界面。

**成功标志：**
- 看到类似 `Kimi-Agent v0.90` 的字样
- 底部有个输入框在闪，等你打字

---

## 第 6 步：测试机器人功能（可选）

如果你不需要让 Kimi-Agent 在飞书/钉钉/Discord 里自动回复，这一步可以跳过。

### 绑定飞书机器人
1. 在黑色窗口输入：
   ```
   kimix bots setup feishu
   ```
2. 按提示一步步输入：
   - 选模式 `2`（Stream 模式，双向收发）
   - 输入你的飞书 App ID
   - 输入你的飞书 App Secret
3. 绑定完成后，启动机器人：
   ```
   kimix bots run
   ```
4. 在飞书群里 @机器人，它就会回复你

其他平台（钉钉/Discord/Slack/Telegram/企业微信）也是同样的命令，只是把 `feishu` 换成对应名字。

---

## 常见问题排查

### "python 不是内部命令"
**原因：** Python 安装时没勾选 "Add Python to PATH"  
**解决：** 重装 Python，记得勾那个勾。

### "pip install" 时一堆红色报错
**原因：** 国内网络下载国外包失败  
**解决：** 用清华源：
```
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### "API Key not found"
**原因：** 密钥没保存对位置  
**解决：** 重新执行第 4 步的两行命令，确认 `config.json` 内容正确。

### 启动后界面很乱 / 字重叠
**原因：** Windows CMD 字体和尺寸不够  
**解决：**
1. 用 Windows Terminal 代替 CMD（微软商店免费下载）
2. 或者右键 CMD 标题栏 → 属性 → 字体大小改成 16
3. 窗口尺寸改成宽 120、高 40

### GitHub 打不开 / ZIP 下载失败
**原因：** 国内网络连不上 GitHub  
**解决：** 用飞书聊天记录里我发的 ZIP 文件，内容完全一样。

### 想更新到新版怎么办？
**方法 1（有 Git）：**
```
cd Kimi-X-master
git pull
```

**方法 2（没有 Git）：**
1. 删掉旧文件夹
2. 重新下载最新 ZIP
3. 重复第 3 步（pip install）

---

## 联系我

装不上？截图发给我，我帮你看。

飞书：直接回复这条消息  
GitHub Issues：https://github.com/leisure1994/Kimi-X/issues

---

**当前版本：0.90**
