# 部署指南

## 方式一: pip 安装 (推荐)

```bash
pip install kimix-agent
kimix --version
```

## 方式二: 源码安装

```bash
git clone https://github.com/kimi-agent/kimix.git
cd kimix
pip install -e ".[all]"
```

## 方式三: Docker 部署

```bash
docker build -t kimix-agent .
docker run -it --rm kimix-agent
```

## 环境配置

### 开发环境

```bash
cp config/dev.yaml ~/.kimix/config.yaml
export KIMIX_ENV=dev
```

### 生产环境

```bash
cp config/prod.yaml ~/.kimix/config.yaml
export KIMIX_ENV=prod
```

## 必要配置

1. **API Keys** — 配置 LLM 提供商 API key
2. **ClawTip** — 配置收款服务（如需支付功能）
3. **内存目录** — `~/.kimix/` 会自动创建

## 启动

```bash
# CLI 模式
kimix

# 特定模式
kimix --mode agent
kimix --mode auto

# 查看帮助
kimix --help
```

## 健康检查

```bash
python3 scripts/verify_install.py
python3 scripts/security_audit.py
python3 scripts/benchmark.py
```
