// ── Admin SPA ──

const API_BASE = '/api/admin';

let currentUserId = null;
let currentConvId = null;

// ── Navigation ──

function showView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(viewId).classList.add('active');
}

function showUserDetail(userId) {
    currentUserId = userId;
    showView('view-user-conversations');
    loadUserConversations(userId);
    document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
}

// ── API helpers ──

async function apiFetch(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return res.json();
}

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
    });
}

// ── Dashboard ──

async function loadDashboard() {
    try {
        const [stats, users] = await Promise.all([
            apiFetch('/stats'),
            apiFetch('/users'),
        ]);

        document.getElementById('stat-users').textContent = stats.user_count;
        document.getElementById('stat-conversations').textContent = stats.conversation_count;
        document.getElementById('stat-messages').textContent = stats.message_count;
        document.getElementById('stat-memories').textContent = stats.memory_fact_count;

        const tbody = document.getElementById('user-table-body');
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无用户</td></tr>';
        } else {
            tbody.innerHTML = users.map(u => `
                <tr>
                    <td>${u.id}</td>
                    <td><strong>${escapeHtml(u.name)}</strong></td>
                    <td>${escapeHtml(u.display_name || '—')}</td>
                    <td>${u.conversation_count}</td>
                    <td>${u.memory_fact_count}</td>
                    <td>${formatTime(u.created_at)}</td>
                    <td class="action-cell">
                        <button class="btn btn-small btn-primary" onclick="showUserDetail(${u.id})">查看对话</button>
                        <button class="btn btn-small btn-secondary" onclick="showUserMemories(${u.id}, '${escapeHtml(u.name)}')">查看记忆</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (err) {
        document.getElementById('stats-grid').innerHTML = `<div class="error-card">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

// ── Sidebar user list ──

async function loadSidebarUsers() {
    try {
        const users = await apiFetch('/users');
        const list = document.getElementById('user-list');
        if (users.length === 0) {
            list.innerHTML = '<div class="loading-text">暂无用户</div>';
            return;
        }
        list.innerHTML = users.map(u => `
            <div class="user-list-item" onclick="showUserDetail(${u.id})" data-user-id="${u.id}">
                <span class="user-list-name">${escapeHtml(u.name)}</span>
                <span class="user-list-count">${u.conversation_count} 对话</span>
            </div>
        `).join('');
        // Highlight currently selected user if any
        if (currentUserId) {
            const item = list.querySelector(`[data-user-id="${currentUserId}"]`);
            if (item) item.style.background = 'var(--sidebar-active)';
        }
    } catch (err) {
        document.getElementById('user-list').innerHTML = '<div class="loading-text">加载失败</div>';
    }
}

// ── Delete Conversation ──

async function deleteConversation(convId, userId) {
    if (!confirm('确定要删除此对话吗？此操作不可恢复。')) return;

    try {
        const res = await fetch(`${API_BASE}/conversations/${convId}`, { method: 'DELETE' });
        if (!res.ok) {
            const text = await res.text();
            alert('删除失败：' + text);
            return;
        }
        // Refresh conversation list and dashboard
        loadUserConversations(userId);
        loadDashboard();
        loadSidebarUsers();
    } catch (err) {
        alert('删除失败：' + err.message);
    }
}

// ── User Conversations ──

async function loadUserConversations(userId) {
    try {
        const users = await apiFetch('/users');
        const user = users.find(u => u.id === userId);
        document.getElementById('user-conv-title').textContent =
            `${escapeHtml(user ? user.name : '用户')} 的对话`;

        const convs = await apiFetch(`/users/${userId}/conversations`);
        const tbody = document.getElementById('conv-table-body');
        if (convs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">暂无对话</td></tr>';
        } else {
            tbody.innerHTML = convs.map(c => `
                <tr>
                    <td>${c.id}</td>
                    <td>${escapeHtml(c.title || '（无标题）')}</td>
                    <td>${escapeHtml(c.model_name || '—')}</td>
                    <td>${c.message_count}</td>
                    <td>${formatTime(c.created_at)}</td>
                    <td>${formatTime(c.updated_at)}</td>
                    <td class="action-cell">
                        <button class="btn btn-small btn-primary" onclick="showMessages(${c.id}, ${userId})">查看消息</button>
                        <button class="btn btn-small btn-danger" onclick="deleteConversation(${c.id}, ${userId})">删除</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (err) {
        document.getElementById('conv-table-body').innerHTML =
            `<tr><td colspan="7" class="empty-cell error-text">加载失败：${escapeHtml(err.message)}</td></tr>`;
    }
}

// ── User Memories ──

window.showUserMemories = async function (userId, userName) {
    currentUserId = userId;
    document.getElementById('user-mem-title').textContent =
        `${escapeHtml(userName || '用户')} 的记忆`;

    try {
        const facts = await apiFetch(`/users/${userId}/memories`);
        const tbody = document.getElementById('mem-table-body');
        if (facts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">暂无记忆</td></tr>';
        } else {
            tbody.innerHTML = facts.map(f => `
                <tr>
                    <td>${f.id}</td>
                    <td class="content-cell">${escapeHtml(f.content)}</td>
                    <td>${escapeHtml(f.category || '—')}</td>
                    <td>${(f.confidence * 100).toFixed(0)}%</td>
                    <td>${formatTime(f.created_at)}</td>
                </tr>
            `).join('');
        }
        showView('view-user-memories');
        document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
    } catch (err) {
        document.getElementById('mem-table-body').innerHTML =
            `<tr><td colspan="5" class="empty-cell error-text">加载失败：${escapeHtml(err.message)}</td></tr>`;
    }
};

// ── Clear Memories ──

document.getElementById('clear-memories-btn').addEventListener('click', async () => {
    if (!currentUserId) return;
    if (!confirm('确定要清除该用户的所有记忆吗？此操作不可恢复。')) return;

    try {
        const res = await fetch(`${API_BASE}/users/${currentUserId}/memories`, { method: 'DELETE' });
        if (!res.ok) {
            const text = await res.text();
            alert('清除失败：' + text);
            return;
        }
        // Refresh memories view + dashboard stats
        showUserMemories(currentUserId, document.getElementById('user-mem-title').textContent.replace(' 的记忆', ''));
        loadDashboard();
    } catch (err) {
        alert('清除失败：' + err.message);
    }
});

// ── Messages ──

async function showMessages(conversationId, userId) {
    currentConvId = conversationId;
    currentUserId = userId;

    document.getElementById('msg-title').textContent = `对话 #${conversationId} 的消息`;
    showView('view-messages');

    try {
        const msgs = await apiFetch(`/conversations/${conversationId}/messages`);
        const container = document.getElementById('message-list');

        if (msgs.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无消息</div>';
            return;
        }

        container.innerHTML = msgs.map(m => `
            <div class="message ${m.role}">
                <div class="msg-role">${m.role === 'user' ? '👤 用户' : '🤖 助手'}</div>
                <div class="msg-content">${escapeHtml(m.content)}</div>
                <div class="msg-time">${formatTime(m.created_at)}</div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('message-list').innerHTML =
            `<div class="empty-state error-text">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

// ── Back buttons ──

document.getElementById('back-from-user').addEventListener('click', () => {
    showView('view-dashboard');
    document.getElementById('nav-dashboard').classList.add('active');
});

document.getElementById('back-from-memories').addEventListener('click', () => {
    showView('view-dashboard');
    document.getElementById('nav-dashboard').classList.add('active');
});

document.getElementById('back-from-messages').addEventListener('click', () => {
    if (currentUserId) {
        showUserDetail(currentUserId);
    } else {
        showView('view-dashboard');
        document.getElementById('nav-dashboard').classList.add('active');
    }
});

// ── Sidebar nav ──

document.getElementById('nav-dashboard').addEventListener('click', () => {
    document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
    document.getElementById('nav-dashboard').classList.add('active');
    showView('view-dashboard');
});

// ── Init ──

async function init() {
    await Promise.all([loadDashboard(), loadSidebarUsers()]);
}

init();
