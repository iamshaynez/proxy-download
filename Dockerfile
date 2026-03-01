FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY app.py .
COPY static/ ./static/

# 创建下载目录
RUN mkdir -p downloads

# 暴露端口
EXPOSE 5000

# 使用 gunicorn 运行
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--timeout", "300", "app:app"]
