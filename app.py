import os
import uuid
import zipfile
import mimetypes
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# 配置
DOWNLOAD_DIR = Path('downloads')
DOWNLOAD_DIR.mkdir(exist_ok=True)
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'admin')
CHUNK_SIZE = 8192  # 8KB


def require_auth(f):
    """装饰器：检查用户是否已登录"""
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


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


@app.route('/api/download', methods=['POST'])
@require_auth
def download_file():
    """从 URL 下载文件并压缩为 zip"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # 验证 URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return jsonify({'error': 'Invalid URL'}), 400
    
    try:
        # 生成唯一文件名
        file_id = str(uuid.uuid4())[:8]
        
        # 获取原始文件名
        original_filename = os.path.basename(parsed.path) or 'download'
        original_filename = secure_filename(original_filename)
        if not original_filename or original_filename == 'download':
            original_filename = f"file_{file_id}"
        
        # 下载文件
        temp_path = DOWNLOAD_DIR / f"{file_id}_temp"
        
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        
        # 检查文件类型
        content_type = response.headers.get('Content-Type', '')
        is_zip = (
            original_filename.lower().endswith('.zip') or
            content_type == 'application/zip' or
            zipfile.is_zipfile(temp_path)
        )
        
        if is_zip:
            # 如果已经是 zip，直接重命名
            final_filename = f"{file_id}_{original_filename}"
            if not final_filename.lower().endswith('.zip'):
                final_filename += '.zip'
            final_path = DOWNLOAD_DIR / final_filename
            temp_path.rename(final_path)
        else:
            # 压缩为 zip
            final_filename = f"{file_id}_{original_filename}.zip"
            final_path = DOWNLOAD_DIR / final_filename
            
            with zipfile.ZipFile(final_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(temp_path, original_filename)
            
            # 删除临时文件
            temp_path.unlink()
        
        return jsonify({
            'success': True,
            'filename': final_filename,
            'original_name': original_filename,
            'size': final_path.stat().st_size
        })
        
    except requests.RequestException as e:
        # 清理临时文件
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        return jsonify({'error': f'Download failed: {str(e)}'}), 500
    except Exception as e:
        # 清理临时文件
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        return jsonify({'error': f'Error: {str(e)}'}), 500


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
    
    # 按创建时间倒序
    files.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({'files': files})


@app.route('/api/download/<filename>', methods=['GET'])
@require_auth
def serve_file(filename):
    """下载指定文件"""
    # 安全检查
    filename = secure_filename(filename)
    filepath = DOWNLOAD_DIR / filename
    
    # 确保文件在下载目录内
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
    # 安全检查
    filename = secure_filename(filename)
    filepath = DOWNLOAD_DIR / filename
    
    # 确保文件在下载目录内
    try:
        filepath.resolve().relative_to(DOWNLOAD_DIR.resolve())
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400
    
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404
    
    filepath.unlink()
    return jsonify({'success': True})


@app.route('/')
def index():
    """主页"""
    return send_file('static/index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
