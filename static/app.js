// API 基础路径
const API_BASE = '';

// 页面加载时检查登录状态
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
});

// 检查登录状态
async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/api/check-auth`, {
            credentials: 'include'
        });
        const data = await res.json();
        
        if (data.authenticated) {
            showMainContent();
            loadFiles();
        } else {
            showLoginBox();
        }
    } catch (err) {
        showLoginBox();
    }
}

// 显示登录框
function showLoginBox() {
    document.getElementById('loginBox').style.display = 'block';
    document.getElementById('mainContent').style.display = 'none';
}

// 显示主内容
function showMainContent() {
    document.getElementById('loginBox').style.display = 'none';
    document.getElementById('mainContent').style.display = 'block';
}

// 登录
async function login() {
    const password = document.getElementById('passwordInput').value.trim();
    const errorEl = document.getElementById('loginError');
    
    if (!password) {
        errorEl.textContent = '请输入密码';
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ password })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showMainContent();
            loadFiles();
            document.getElementById('passwordInput').value = '';
            errorEl.textContent = '';
        } else {
            errorEl.textContent = data.error || '密码错误';
        }
    } catch (err) {
        errorEl.textContent = '登录失败，请重试';
    }
}

// 退出登录
async function logout() {
    try {
        await fetch(`${API_BASE}/api/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        // 忽略错误
    }
    showLoginBox();
}

// 显示状态消息
function showStatus(msg, type) {
    const statusEl = document.getElementById('statusMsg');
    statusEl.textContent = msg;
    statusEl.className = 'status-msg ' + type;
}

// 开始下载
async function startDownload() {
    const urlInput = document.getElementById('urlInput');
    const downloadBtn = document.getElementById('downloadBtn');
    const url = urlInput.value.trim();
    
    if (!url) {
        showStatus('请输入下载链接', 'error');
        return;
    }
    
    // 验证 URL
    try {
        new URL(url);
    } catch {
        showStatus('请输入有效的 URL', 'error');
        return;
    }
    
    // 设置加载状态
    downloadBtn.disabled = true;
    showStatus('下载中，请稍候...', 'loading');
    
    try {
        const res = await fetch(`${API_BASE}/api/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ url })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showStatus(`下载完成: ${data.original_name}`, 'success');
            urlInput.value = '';
            loadFiles();
        } else {
            showStatus(data.error || '下载失败', 'error');
        }
    } catch (err) {
        showStatus('下载失败: ' + err.message, 'error');
    } finally {
        downloadBtn.disabled = false;
    }
}

// 加载文件列表
async function loadFiles() {
    try {
        const res = await fetch(`${API_BASE}/api/files`, {
            credentials: 'include'
        });
        
        const data = await res.json();
        renderFiles(data.files || []);
    } catch (err) {
        console.error('加载文件列表失败:', err);
    }
}

// 格式化文件大小
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 格式化时间
function formatTime(isoTime) {
    const date = new Date(isoTime);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 渲染文件列表
function renderFiles(files) {
    const container = document.getElementById('filesList');
    
    if (files.length === 0) {
        container.innerHTML = '<div class="empty-msg">暂无文件</div>';
        return;
    }
    
    let html = `
        <table>
            <thead>
                <tr>
                    <th>文件名</th>
                    <th>大小</th>
                    <th>下载时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    for (const file of files) {
        html += `
            <tr>
                <td class="file-name" title="${file.filename}">${file.filename}</td>
                <td class="file-size">${formatSize(file.size)}</td>
                <td class="file-time">${formatTime(file.created_at)}</td>
                <td class="actions">
                    <a href="${API_BASE}/api/download/${encodeURIComponent(file.filename)}" 
                       class="btn-download" target="_blank">下载</a>
                    <button class="btn-delete" onclick="deleteFile('${file.filename}')">删除</button>
                </td>
            </tr>
        `;
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

// 删除文件
async function deleteFile(filename) {
    if (!confirm(`确定要删除 ${filename} 吗？`)) {
        return;
    }
    
    try {
        const res = await fetch(`${API_BASE}/api/files/${encodeURIComponent(filename)}`, {
            method: 'DELETE',
            credentials: 'include'
        });
        
        const data = await res.json();
        
        if (data.success) {
            loadFiles();
        } else {
            alert(data.error || '删除失败');
        }
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

// 定时刷新文件列表（每 30 秒）
setInterval(() => {
    if (document.getElementById('mainContent').style.display !== 'none') {
        loadFiles();
    }
}, 30000);
