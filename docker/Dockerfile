# 使用Python 3.11作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

ENV http_proxy=http://192.168.0.123:7890
ENV https_proxy=http://192.168.0.123:7890

# 安装FFmpeg，使用代理
RUN apt-get update \
    && apt-get install -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 先复制 requirements.txt 并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再复制主程序
COPY ./*.py /app/
COPY ./data/config.yaml /app/data/
COPY ./README.md /app/

# 暴露端口
EXPOSE 8080

# 设置环境变量
ENV PYTHONPATH=/app

# 启动应用
CMD ["python", "app.py"]