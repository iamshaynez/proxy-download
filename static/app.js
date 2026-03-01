// API 基础路径
const API_BASE = '';
const WS_BASE = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host;

// 全局状态
let ws = null;
let activeTasks = new Map(); // task_id -> { url, element }
let reconnectTimer = null;

// 页面加载时检查登录状态
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
});

// ==================== 认证相关 ====================

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE}/api/check-auth`, {
            credentials: 'include'
        });
        const data = await res.json();
        
        if (data.authenticated) {
            showMainContent();
            connectWebSocket();
            loadFiles();
        } else {
            showLoginBox();
        }
    } catch (err) {
        showLoginBox();
    }
}

function showLoginBox() {
    document.getElementById('loginBox').style.display = 'block';
    document.getElementById('mainContent').style.display = 'none';
    disconnectWebSocket();
}

function showMainContent() {
    document.getElementById('loginBox').style.display = 'none';
    document.getElementById('mainContent').style.display = 'block';
}

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
            connectWebSocket();
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

async function logout() {
    try {
        await fetch(`${API_BASE}/api/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        // 忽略错误
    }
    disconnectWebSocket();
    showLoginBox();
}

// ==================== WebSocket ====================

function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    
    updateConnectionStatus('connecting');
    
    ws = new WebSocket(`${WS_BASE}/ws/download`);
    
    ws.onopen = () => {
        updateConnectionStatus('connected');
        // 重新订阅所有活跃任务
        activeTasks.forEach((task, taskId) => {
            ws.send(JSON.stringify({
                action: 'query',
                task_id: taskId
            }));
        });
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    ws.onclose = () => {
        updateConnectionStatus('disconnected');
        // 3秒后重连
        reconnectTimer = setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = () => {
        updateConnectionStatus('disconnected');
    };
}

function disconnectWebSocket() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (ws) {
        ws.close();
        ws = null;
    }
}

function updateConnectionStatus(status) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    
    dot.className = 'status-dot ' + status;
    
    const statusMap = {
        'connected': '已连接',
        'disconnected': '未连接',
        'connecting': '连接中...'
    };
    text.textContent = statusMap[status] || status;
}

function handleWebSocketMessage(data) {
    if (data.error) {
        console.error('WebSocket error:', data.error);
        return;
    }
    
    if (data.type === 'task_created') {
        // 任务创建成功
        const url = document.getElementById('urlInput').value.trim();
        addTaskToUI(data.task_id, url);
        activeTasks.set(data.task_id, { url });
    } else if (data.type === 'progress' || data.type === 'status') {
        // 更新任务进度
        updateTaskUI(data.task_id, data);
        
        // 如果任务完成或失败，更新文件列表
        if (data.status === 'completed' || data.status === 'failed') {
            if (data.status === 'completed') {
                loadFiles();
            }
        }
    }
}

// ==================== 下载任务管理 ====================

function startDownload() {
    const urlInput = document.getElementById('urlInput');
    const url = urlInput.value.trim();
    
    if (!url) {
        alert('请输入下载链接');
        return;
    }
    
    // 验证 URL
    try {
        new URL(url);
    } catch {
        alert('请输入有效的 URL');
        return;
    }
    
    // 检查 WebSocket 连接
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert('未连接到服务器，请稍后再试');
        return;
    }
    
    // 发送开始下载命令
    ws.send(JSON.stringify({
        action: 'start',
        url: url
    }));
    
    // 清空输入框
    urlInput.value = '';
}

function retryDownload(taskId) {
    const task = activeTasks.get(taskId);
    if (!task) return;
    
    // 检查 WebSocket 连接
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert('未连接到服务器，请稍后再试');
        return;
    }
    
    // 移除旧任务UI
    removeTaskUI(taskId);
    
    // 发送重试命令
    ws.send(JSON.stringify({
        action: 'retry',
        task_id: taskId,
        url: task.url
    }));
}

function cancelDownload(taskId) {
    // 从活跃任务中移除
    activeTasks.delete(taskId);
    removeTaskUI(taskId);
    
    // 发送取消命令（如果需要后端支持）
    // 目前只是前端移除显示
}

// ==================== UI 更新 ====================

function addTaskToUI(taskId, url) {
    const container = document.getElementById('tasksList');
    
    const taskEl = document.createElement('div');
    taskEl.className = 'task-item';
    taskEl.id = `task-${taskId}`;
    taskEl.innerHTML = `
        <div class="task-header">
            <span class="task-url" title="${escapeHtml(url)}">${escapeHtml(url)}</span>
            <div class="task-status">
                <span class="status-badge status-pending">等待中</span>
            </div>
        </div>
        <div class="progress-container">
            <div class="progress-bar">
                <div class="progress-fill indeterminate" style="width: 100%"></div>
            </div>
            <div class="progress-text">
                <span class="progress-status">准备下载...</span>
                <span class="progress-percent">-</span>
            </div>
        </div>
        <div class="task-actions">
            <button class="btn-cancel" onclick="cancelDownload('${taskId}')">取消</button>
        </div>
    `;
    
    container.insertBefore(taskEl, container.firstChild);
}

function updateTaskUI(taskId, data) {
    const taskEl = document.getElementById(`task-${taskId}`);
    if (!taskEl) return;
    
    const statusBadge = taskEl.querySelector('.status-badge');
    const progressFill = taskEl.querySelector('.progress-fill');
    const progressStatus = taskEl.querySelector('.progress-status');
    const progressPercent = taskEl.querySelector('.progress-percent');
    const taskActions = taskEl.querySelector('.task-actions');
    
    // 移除旧的错误信息
    const oldError = taskEl.querySelector('.error-detail');
    if (oldError) oldError.remove();
    
    // 更新状态
    const statusMap = {
        'pending': { text: '等待中', class: 'status-pending' },
        'downloading': { text: '下载中', class: 'status-downloading' },
        'compressing': { text: '处理中', class: 'status-compressing' },
        'completed': { text: '完成', class: 'status-completed' },
        'failed': { text: '失败', class: 'status-failed' }
    };
    
    const status = statusMap[data.status] || { text: data.status, class: '' };
    statusBadge.textContent = status.text;
    statusBadge.className = 'status-badge ' + status.class;
    
    // 更新进度条
    if (data.status === 'downloading' || data.status === 'compressing') {
        if (data.progress >= 0) {
            progressFill.style.width = data.progress + '%';
            progressFill.classList.remove('indeterminate');
            progressPercent.textContent = data.progress + '%';
        } else {
            progressFill.style.width = '100%';
            progressFill.classList.add('indeterminate');
            progressPercent.textContent = '下载中...';
        }
    } else if (data.status === 'completed') {
        progressFill.style.width = '100%';
        progressFill.classList.remove('indeterminate');
        progressPercent.textContent = '100%';
    }
    
    // 更新状态文本
    if (data.message) {
        progressStatus.textContent = data.message;
    }
    
    // 更新按钮
    if (data.status === 'completed') {
        taskActions.innerHTML = `
            <a href="${API_BASE}/api/download/${encodeURIComponent(data.filename)}" 
               class="btn-open" target="_blank">打开文件</a>
            <button class="btn-cancel" onclick="cancelDownload('${taskId}')">隐藏</button>
        `;
        // 5秒后自动隐藏
        setTimeout(() => {
            cancelDownload(taskId);
        }, 5000);
    } else if (data.status === 'failed') {
        let html = `
            <button class="btn-retry" onclick="retryDownload('${taskId}')">重试</button>
            <button class="btn-cancel" onclick="cancelDownload('${taskId}')">隐藏</button>
        `;
        if (data.can_resume) {
            html = `<button class="btn-retry" onclick="retryDownload('${taskId}')">断点续传</button>` + html;
        }
        taskActions.innerHTML = html;
        
        // 显示错误信息
        if (data.error) {
            const errorEl = document.createElement('div');
            errorEl.className = 'error-detail';
            errorEl.textContent = data.error;
            taskEl.appendChild(errorEl);
        }
    }
}

function removeTaskUI(taskId) {
    const taskEl = document.getElementById(`task-${taskId}`);
    if (taskEl) {
        taskEl.remove();
    }
    activeTasks.delete(taskId);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 文件列表 ====================

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

function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

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
                <td class="file-name" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</td>
                <td class="file-size">${formatSize(file.size)}</td>
                <td class="file-time">${formatTime(file.created_at)}</td>
                <td class="actions">
                    <a href="${API_BASE}/api/download/${encodeURIComponent(file.filename)}" 
                       class="btn-download" target="_blank">下载</a>
                    <button class="btn-delete" onclick="deleteFile('${escapeHtml(file.filename)}')">删除</button>
                </td>
            </tr>
        `;
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

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
