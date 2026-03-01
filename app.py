import os
import json
import uuid
import zipfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from flask_sock import Sock
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app, supports_credentials=True)
sock = Sock(app)

# 配置
DOWNLOAD_DIR = Path('downloads')
DOWNLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR = Path('temp')
TEMP_DIR.mkdir(exist_ok=True)
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'admin')
CHUNK_SIZE = 8192  # 8KB

# 下载任务状态存储
download_tasks = {}
download_tasks_lock = threading.Lock()


def require_auth(f):
    """装饰器：检查用户是否已登录"""
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


# ==================== 认证相关 ====================

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    password = data.get('password', '')
    
    if password == ACCESS_PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    """用户登出"""
    session.pop('authenticated', None)
    return jsonify({'success': True})


@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """检查登录状态"""
    return jsonify({'authenticated': session.get('authenticated', False)})


# ==================== 下载任务管理 ====================

def update_task_status(task_id, status, progress=0, message='', filename=None, error=None):
    """更新下载任务状态"""
    with download_tasks_lock:
        download_tasks[task_id] = {
            'status': status,  # 'pending', 'downloading', 'compressing', 'completed', 'failed', 'paused'
            'progress': progress,
            'message': message,
            'filename': filename,
            'error': error,
            'updated_at': datetime.now().isoformat()
        }


def get_task_status(task_id):
    """获取下载任务状态"""
    with download_tasks_lock:
        return download_tasks.get(task_id, {}).copy()


def delete_task(task_id):
    """删除下载任务"""
    with download_tasks_lock:
        if task_id in download_tasks:
            del download_tasks[task_id]


# ==================== WebSocket 实时进度 ====================

@sock.route('/ws/download')
def download_websocket(ws):
    """WebSocket 连接处理下载任务"""
    while True:
        try:
            # 接收消息
            message = ws.receive()
            if message is None:
                break
            
            data = json.loads(message)
            action = data.get('action')
            task_id = data.get('task_id')
            
            if action == 'start':
                # 开始新下载
                url = data.get('url', '').strip()
                if not url:
                    ws.send(json.dumps({'error': 'URL is required'}))
                    continue
                
                # 验证 URL
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    ws.send(json.dumps({'error': 'Invalid URL'}))
                    continue
                
                # 创建任务
                task_id = str(uuid.uuid4())[:12]
                update_task_status(task_id, 'pending', 0, '准备下载...')
                
                # 启动下载线程
                thread = threading.Thread(
                    target=download_with_progress,
                    args=(task_id, url, ws)
                )
                thread.daemon = True
                thread.start()
                
                ws.send(json.dumps({
                    'type': 'task_created',
                    'task_id': task_id,
                    'status': 'pending'
                }))
                
            elif action == 'retry':
                # 重试下载
                url = data.get('url', '').strip()
                if not url:
                    ws.send(json.dumps({'error': 'URL is required'}))
                    continue
                
                # 删除旧任务
                delete_task(task_id)
                
                # 创建新任务
                new_task_id = str(uuid.uuid4())[:12]
                update_task_status(new_task_id, 'pending', 0, '准备重试...')
                
                # 启动下载线程
                thread = threading.Thread(
                    target=download_with_progress,
                    args=(new_task_id, url, ws)
                )
                thread.daemon = True
                thread.start()
                
                ws.send(json.dumps({
                    'type': 'task_created',
                    'task_id': new_task_id,
                    'status': 'pending'
                }))
                
            elif action == 'query':
                # 查询任务状态
                status = get_task_status(task_id)
                ws.send(json.dumps({
                    'type': 'status',
                    'task_id': task_id,
                    **status
                }))
                
        except json.JSONDecodeError:
            ws.send(json.dumps({'error': 'Invalid JSON'}))
        except Exception as e:
            ws.send(json.dumps({'error': str(e)}))


def download_with_progress(task_id, url, ws):
    """带进度追踪的下载函数"""
    temp_path = None
    final_path = None
    
    try:
        # 获取原始文件名
        parsed = urlparse(url)
        original_filename = os.path.basename(parsed.path) or 'download'
        original_filename = secure_filename(original_filename)
        if not original_filename or original_filename == 'download':
            original_filename = f"file_{task_id[:8]}"
        
        # 临时文件路径
        temp_filename = f"{task_id}_temp"
        temp_path = TEMP_DIR / temp_filename
        
        # 检查是否有未完成的下载（断点续传）
        downloaded_size = 0
        if temp_path.exists():
            downloaded_size = temp_path.stat().st_size
        
        # 准备请求头（支持断点续传）
        headers = {}
        if downloaded_size > 0:
            headers['Range'] = f'bytes={downloaded_size}-'
        
        # 开始下载
        update_task_status(task_id, 'downloading', 0, '连接中...')
        
        response = requests.get(url, stream=True, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 获取文件总大小
        total_size = None
        if 'Content-Length' in response.headers:
            total_size = int(response.headers['Content-Length'])
            if downloaded_size > 0 and response.status_code == 206:
                # 断点续传，总大小是剩余部分
                total_size += downloaded_size
            elif downloaded_size > 0:
                # 服务器不支持断点续传，重新下载
                downloaded_size = 0
                temp_path.unlink() if temp_path.exists() else None
        
        # 如果已经下载完成
        if total_size and downloaded_size >= total_size:
            pass
        else:
            # 写入文件
            mode = 'ab' if downloaded_size > 0 else 'wb'
            with open(temp_path, mode) as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 计算进度
                        if total_size:
                            progress = min(int((downloaded_size / total_size) * 100), 99)
                        else:
                            progress = -1  # 未知大小
                        
                        # 更新状态并发送
                        update_task_status(task_id, 'downloading', progress, '下载中...')
                        
                        try:
                            ws.send(json.dumps({
                                'type': 'progress',
                                'task_id': task_id,
                                'progress': progress,
                                'downloaded': downloaded_size,
                                'total': total_size,
                                'status': 'downloading',
                                'message': '下载中...'
                            }))
                        except:
                            pass  # WebSocket 可能已关闭
        
        # 下载完成，检查文件类型并压缩
        update_task_status(task_id, 'compressing', 99, '处理中...')
        
        try:
            ws.send(json.dumps({
                'type': 'progress',
                'task_id': task_id,
                'progress': 99,
                'status': 'compressing',
                'message': '压缩中...'
            }))
        except:
            pass
        
        # 检查是否是 zip 文件
        content_type = response.headers.get('Content-Type', '')
        is_zip = (
            original_filename.lower().endswith('.zip') or
            content_type == 'application/zip' or
            zipfile.is_zipfile(temp_path)
        )
        
        if is_zip:
            # 如果已经是 zip，直接移动
            final_filename = f"{task_id[:8]}_{original_filename}"
            if not final_filename.lower().endswith('.zip'):
                final_filename += '.zip'
            final_path = DOWNLOAD_DIR / final_filename
            temp_path.rename(final_path)
        else:
            # 压缩为 zip
            final_filename = f"{task_id[:8]}_{original_filename}.zip"
            final_path = DOWNLOAD_DIR / final_filename
            
            with zipfile.ZipFile(final_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(temp_path, original_filename)
            
            # 删除临时文件
            temp_path.unlink()
        
        # 完成
        final_size = final_path.stat().st_size
        update_task_status(task_id, 'completed', 100, '完成', filename=final_filename)
        
        try:
            ws.send(json.dumps({
                'type': 'progress',
                'task_id': task_id,
                'progress': 100,
                'status': 'completed',
                'message': '下载完成',
                'filename': final_filename,
                'size': final_size
            }))
        except:
            pass
        
    except requests.RequestException as e:
        error_msg = f'下载失败: {str(e)}'
        update_task_status(task_id, 'failed', 0, error_msg, error=error_msg)
        
        try:
            ws.send(json.dumps({
                'type': 'progress',
                'task_id': task_id,
                'progress': 0,
                'status': 'failed',
                'message': error_msg,
                'error': error_msg,
                'can_resume': temp_path and temp_path.exists()
            }))
        except:
            pass
        
    except Exception as e:
        error_msg = f'错误: {str(e)}'
        update_task_status(task_id, 'failed', 0, error_msg, error=error_msg)
        
        try:
            ws.send(json.dumps({
                'type': 'progress',
                'task_id': task_id,
                'progress': 0,
                'status': 'failed',
                'message': error_msg,
                'error': error_msg
            }))
        except:
            pass
        
        # 清理
        if temp_path and temp_path.exists():
            temp_path.unlink()


# ==================== HTTP API ====================

@app.route('/api/download', methods=['POST'])
@require_auth
def download_file():
    """创建新的下载任务（HTTP 方式，返回 task_id）"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return jsonify({'error': 'Invalid URL'}), 400
    
    # 创建任务
    task_id = str(uuid.uuid4())[:12]
    update_task_status(task_id, 'pending', 0, '等待连接...')
    
    return jsonify({
        'success': True,
        'task_id': task_id,
        'url': url
    })


@app.route('/api/tasks/<task_id>', methods=['GET'])
@require_auth
def get_task(task_id):
    """获取任务状态"""
    status = get_task_status(task_id)
    if not status:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(status)


@app.route('/api/files', methods=['GET'])
@require_auth
def list_files():
    """列出所有已下载的文件"""
    files = []
    
    for filepath in DOWNLOAD_DIR.glob('*.zip'):
        stat = filepath.stat()
        files.append({
            'filename': filepath.name,
            'size': stat.st_size,
            'created_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    
    files.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify({'files': files})


@app.route('/api/download/<filename>', methods=['GET'])
@require_auth
def serve_file(filename):
    """下载指定文件"""
    filename = secure_filename(filename)
    filepath = DOWNLOAD_DIR / filename
    
    try:
        filepath.resolve().relative_to(DOWNLOAD_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400
    
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(filepath, as_attachment=True)


@app.route('/api/files/<filename>', methods=['DELETE'])
@require_auth
def delete_file(filename):
    """删除指定文件"""
    filename = secure_filename(filename)
    filepath = DOWNLOAD_DIR / filename
    
    try:
        filepath.resolve().relative_to(DOWNLOAD_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400
    
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    filepath.unlink()
    return jsonify({'success': True})


# ==================== 页面 ====================

@app.route('/')
def index():
    return send_file('static/index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
