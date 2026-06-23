/**
 * ZXF Dialogue Agent — Main Application
 */
const api = new ApiClient();

// ── Markdown 渲染 ──
function renderMarkdown(text) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
        // 降级：库未加载时显示纯文本
        return escapeHtml(text);
    }
    const raw = marked.parse(text, { breaks: true, gfm: true });
    return DOMPurify.sanitize(raw);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
let state = {
    user: null,
    userId: null,
    token: null,
    conversations: [],
    currentConvId: null,
    models: [],
    loading: false,
};

// ── DOM references ──
const $ = (id) => document.getElementById(id);
const loginScreen = $('login-screen');
const chatScreen = $('chat-screen');
const nameInput = $('name-input');
const loginBtn = $('login-btn');
const userDisplay = $('user-display');
const logoutBtn = $('logout-btn');
const newChatBtn = $('new-chat-btn');
const convList = $('conversation-list');
const messageList = $('message-list');
const emptyState = $('empty-state');
const messageInput = $('message-input');
const sendBtn = $('send-btn');
const modelSelect = $('model-select');
const menuToggle = $('menu-toggle');
const sidebar = $('sidebar');

// ── Storage ──
function saveSession(user, token) {
    localStorage.setItem('zxf_user', JSON.stringify(user));
    localStorage.setItem('zxf_token', token);
}

function loadSession() {
    const user = localStorage.getItem('zxf_user');
    const token = localStorage.getItem('zxf_token');
    if (user && token) {
        try {
            state.user = JSON.parse(user);
            state.token = token;
            state.userId = state.user.id;
            return true;
        } catch { return false; }
    }
    return false;
}

function clearSession() {
    localStorage.removeItem('zxf_user');
    localStorage.removeItem('zxf_token');
}

// ── Login ──
async function handleLogin() {
    const name = nameInput.value.trim();
    if (!name) return;

    loginBtn.disabled = true;
    loginBtn.textContent = '登录中...';

    try {
        const result = await api.login(name);
        state.user = result.user;
        state.token = result.token;
        state.userId = result.user.id;
        saveSession(state.user, state.token);

        if (result.is_new) {
            showToast('欢迎！账号已创建');
        }

        enterChat();
    } catch (err) {
        showToast('登录失败: ' + err.message);
    } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = '进入';
    }
}

// ── Enter Chat ──
async function enterChat() {
    loginScreen.classList.add('hidden');
    chatScreen.classList.remove('hidden');
    userDisplay.textContent = state.user.display_name || state.user.name;

    await Promise.all([loadModels(), loadConversations()]);
    updateModelSelector();

    // If no conversations, create one
    if (state.conversations.length === 0) {
        await createNewConversation();
    } else {
        selectConversation(state.conversations[0].id);
    }
}

// ── Load Models ──
async function loadModels() {
    try {
        state.models = await api.listModels();
    } catch (err) {
        console.error('Failed to load models:', err);
        state.models = [];
    }
}

function updateModelSelector() {
    modelSelect.innerHTML = '';
    if (state.models.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '无可用模型';
        modelSelect.appendChild(opt);
        return;
    }
    for (const model of state.models) {
        const opt = document.createElement('option');
        opt.value = model.id;
        opt.textContent = model.display_name || model.model_name;
        if (model.provider) {
            opt.textContent += ` (${model.provider.name})`;
        }
        modelSelect.appendChild(opt);
    }
}

// ── Conversations ──
async function loadConversations() {
    try {
        state.conversations = await api.listConversations(state.userId);
    } catch (err) {
        console.error('Failed to load conversations:', err);
        state.conversations = [];
    }
    renderConversationList();
}

function renderConversationList() {
    convList.innerHTML = '';
    if (state.conversations.length === 0) {
        const item = document.createElement('div');
        item.className = 'conversation-item';
        item.textContent = '暂无对话';
        item.style.opacity = '0.5';
        convList.appendChild(item);
        return;
    }

    for (const conv of state.conversations) {
        const item = document.createElement('div');
        item.className = 'conversation-item';
        if (conv.id === state.currentConvId) {
            item.classList.add('active');
        }
        item.textContent = conv.title || '新对话';
        item.dataset.id = conv.id;
        item.addEventListener('click', () => selectConversation(conv.id));
        convList.appendChild(item);
    }
}

async function createNewConversation() {
    const defaultModelId = state.models.length > 0 ? state.models[0].id : null;
    try {
        const conv = await api.createConversation(state.userId, defaultModelId);
        state.conversations.unshift(conv);
        renderConversationList();
        selectConversation(conv.id);
        closeSidebar();
    } catch (err) {
        showToast('创建对话失败: ' + err.message);
    }
}

async function selectConversation(convId) {
    state.currentConvId = convId;
    renderConversationList();
    updateModelSelectorForConv(convId);

    // Load messages
    messageList.innerHTML = '';
    emptyState.classList.remove('hidden');

    try {
        const messages = await api.getMessages(convId);
        emptyState.classList.add('hidden');
        renderMessages(messages);
    } catch (err) {
        console.error('Failed to load messages:', err);
    }

    messageInput.disabled = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

function updateModelSelectorForConv(convId) {
    const conv = state.conversations.find(c => c.id === convId);
    if (conv && conv.model && state.models.length > 0) {
        modelSelect.value = conv.model.id;
    } else if (state.models.length > 0) {
        modelSelect.value = state.models[0].id;
    }
}

// ── Render Messages ──
function renderMessages(messages) {
    messageList.innerHTML = '';
    for (const msg of messages) {
        appendMessage(msg.role, msg.content, msg.created_at);
    }
    scrollToBottom();
}

function appendMessage(role, content, timestamp) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = role === 'assistant' ? renderMarkdown(content) : escapeHtml(content);
    div.appendChild(contentDiv);

    if (timestamp) {
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = formatTime(timestamp);
        div.appendChild(timeDiv);
    }

    messageList.appendChild(div);
    scrollToBottom();
}

function showLoading() {
    const div = document.createElement('div');
    div.className = 'message assistant loading';
    div.id = 'loading-indicator';
    const dots = document.createElement('div');
    dots.className = 'loading-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';
    div.appendChild(dots);
    messageList.appendChild(div);
    scrollToBottom();
}

function removeLoading() {
    const el = document.getElementById('loading-indicator');
    if (el) el.remove();
}

function scrollToBottom() {
    setTimeout(() => {
        messageList.scrollTop = messageList.scrollHeight;
    }, 10);
}

// ── Send Message (Streaming) ──
async function handleSend() {
    const content = messageInput.value.trim();
    if (!content || state.loading || !state.currentConvId) return;

    state.loading = true;
    sendBtn.disabled = true;
    messageInput.disabled = true;

    // 立即显示用户消息
    appendMessage('user', content);
    messageInput.value = '';
    emptyState.classList.add('hidden');

    // 创建 assistant 消息占位
    const assistantDiv = document.createElement('div');
    assistantDiv.className = 'message assistant';
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    assistantDiv.appendChild(contentDiv);
    messageList.appendChild(assistantDiv);
    scrollToBottom();

    let rawText = '';  // 累积原始文本，用于 markdown 渲染

    try {
        const response = await api.sendMessageStream(state.currentConvId, state.userId, content);
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try { const err = await response.json(); detail = err.detail || detail; } catch {}
            throw new Error(detail);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';  // 保留未完成的行

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const event = JSON.parse(line.slice(6));
                    const type = event.type;
                    const data = event.content;

                    if (type === 'token') {
                        rawText += data;
                        contentDiv.innerHTML = renderMarkdown(rawText);
                        scrollToBottom();
                    } else if (type === 'title') {
                        // 会话标题已生成，下次刷新列表时更新
                    } else if (type === 'error') {
                        contentDiv.textContent = '⚠️ ' + data;
                        contentDiv.style.color = '#dc2626';
                    } else if (type === 'done') {
                        console.log('Stream done, memories_updated:', data.memories_updated);
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
        }

        // 流结束后刷新会话列表（标题可能已更新）
        await loadConversations();
    } catch (err) {
        contentDiv.textContent = '⚠️ 请求失败: ' + err.message;
        contentDiv.style.color = '#dc2626';
    } finally {
        state.loading = false;
        sendBtn.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
    }
}

// ── Model Switching ──
async function handleModelChange() {
    const modelId = parseInt(modelSelect.value);
    if (!modelId || !state.currentConvId) return;

    try {
        await api.setConversationModel(state.currentConvId, modelId);
        showToast('模型已切换');
        // Refresh to get updated model info
        await loadConversations();
    } catch (err) {
        showToast('切换模型失败: ' + err.message);
    }
}

// ── UI Helpers ──
function formatTime(ts) {
    try {
        const d = new Date(ts);
        return d.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch { return ''; }
}

function showToast(msg) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%)',
        background: '#1e293b',
        color: 'white',
        padding: '10px 24px',
        borderRadius: '8px',
        fontSize: '14px',
        zIndex: '200',
        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
        transition: 'opacity 0.3s',
    });
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
}

function toggleSidebar() {
    sidebar.classList.toggle('open');
}

function closeSidebar() {
    sidebar.classList.remove('open');
}

// ── Logout ──
function handleLogout() {
    clearSession();
    state = { user: null, userId: null, token: null, conversations: [], currentConvId: null, models: [], loading: false };
    chatScreen.classList.add('hidden');
    loginScreen.classList.remove('hidden');
    nameInput.value = '';
    messageInput.disabled = true;
    sendBtn.disabled = true;
    sidebar.classList.remove('open');
}

// ── Event Listeners ──
loginBtn.addEventListener('click', handleLogin);
nameInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleLogin(); });

sendBtn.addEventListener('click', handleSend);
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});

modelSelect.addEventListener('change', handleModelChange);

newChatBtn.addEventListener('click', createNewConversation);
logoutBtn.addEventListener('click', handleLogout);
menuToggle.addEventListener('click', toggleSidebar);

// Click outside sidebar to close (mobile)
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && sidebar.classList.contains('open')) {
        if (!sidebar.contains(e.target) && e.target !== menuToggle) {
            closeSidebar();
        }
    }
});

// ── Keyboard shortcut ──
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
});

// ── Init ──
if (loadSession()) {
    enterChat();
} else {
    nameInput.focus();
}
