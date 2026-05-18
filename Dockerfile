FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml README.md ./
COPY kimix/ ./kimix/
COPY tests/ ./tests/

# 安装 Python 依赖
RUN pip install --no-cache-dir -e ".[dev]"

# 创建非 root 用户
RUN useradd -m -s /bin/bash kimix
USER kimix

# 默认启动 TUI
ENTRYPOINT ["kimix"]
CMD []
