FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY app.py .
COPY static/ ./static/

# 创建下载目录和临时目录
RUN mkdir -p downloads temp

# 暴露端口
EXPOSE 5000

# 使用 gunicorn 运行（单 worker 模式以支持 WebSocket）
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "1", "--threads", "8", "--timeout", "300", "app:app"]
