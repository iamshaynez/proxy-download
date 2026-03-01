# 代理下载服务

一个简单的文件代理下载服务，支持密码保护、自动压缩为 zip、文件管理等功能。

## 功能特点

- 🔒 密码保护访问
- 📥 代理下载任意文件
- 🗜️ 自动压缩为非 zip 文件
- 📁 文件列表管理（下载、删除）
- 🐳 Docker 部署支持

## 快速开始

### 1. 配置环境变量

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，设置密码
ACCESS_PASSWORD=your-secure-password
SECRET_KEY=your-random-secret-key
```

### 2. Docker 部署

```bash
docker-compose up -d
```

### 3. 访问服务

打开浏览器访问 http://localhost:5000

## 本地开发

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
# 设置环境变量（Windows PowerShell）
$env:ACCESS_PASSWORD="your-password"
$env:SECRET_KEY="your-secret"

# 运行
python app.py
```

## 项目结构

```
proxy-download/
├── app.py              # Flask 后端
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 镜像配置
├── docker-compose.yml  # Docker 编排
├── .env                # 环境变量（需自行创建）
├── .env.example        # 环境变量示例
├── static/             # 前端文件
│   ├── index.html
│   └── app.js
└── downloads/          # 下载文件存储目录
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/login | 登录 |
| POST | /api/logout | 登出 |
| GET | /api/check-auth | 检查登录状态 |
| POST | /api/download | 下载文件到服务器 |
| GET | /api/files | 获取文件列表 |
| GET | /api/download/<filename> | 下载指定文件 |
| DELETE | /api/files/<filename> | 删除指定文件 |

## 注意事项

1. 务必修改默认密码
2. 建议修改 SECRET_KEY
3. 下载目录已挂载为 volume，重启容器不会丢失文件
4. 大文件下载可能需要较长时间，请耐心等待
