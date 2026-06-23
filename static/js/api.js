/**
 * API client for the ZXF Dialogue Agent backend.
 */
class ApiClient {
    constructor() {
        this.baseUrl = '';
    }

    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) {
            opts.body = JSON.stringify(body);
        }
        const res = await fetch(`${this.baseUrl}${path}`, opts);
        if (!res.ok) {
            let detail = `HTTP ${res.status}`;
            try {
                const err = await res.json();
                detail = err.detail || detail;
            } catch {}
            throw new Error(detail);
        }
        if (res.status === 204) return null;
        return res.json();
    }

    // ── Auth ──
    async login(name) {
        return this.request('POST', '/api/auth/login', { name });
    }

    // ── Conversations ──
    async listConversations(userId) {
        return this.request('GET', `/api/conversations?user_id=${userId}`);
    }

    async createConversation(userId, modelId = null) {
        const body = {};
        if (modelId) body.model_id = modelId;
        return this.request('POST', `/api/conversations?user_id=${userId}`, body);
    }

    async getConversation(conversationId) {
        return this.request('GET', `/api/conversations/${conversationId}`);
    }

    async getMessages(conversationId) {
        return this.request('GET', `/api/conversations/${conversationId}/messages`);
    }

    async sendMessage(conversationId, userId, content) {
        return this.request('POST', `/api/conversations/${conversationId}/chat?user_id=${userId}`, { content });
    }

    /**
     * 流式发送消息，返回 fetch Response 对象。
     * 调用方通过 response.body.getReader() 读取 SSE data 行。
     */
    sendMessageStream(conversationId, userId, content) {
        return fetch(`${this.baseUrl}/api/conversations/${conversationId}/chat/stream?user_id=${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
        });
    }

    async setConversationModel(conversationId, modelId) {
        return this.request('PUT', `/api/conversations/${conversationId}/model`, { model_id: modelId });
    }

    // ── Models ──
    async listModels() {
        return this.request('GET', '/api/models');
    }

    // ── Memories ──
    async listFacts(userId) {
        return this.request('GET', `/api/memories/facts?user_id=${userId}&limit=50`);
    }

    async getSummary(userId) {
        return this.request('GET', `/api/memories/summary?user_id=${userId}`);
    }

    async deleteFact(factId) {
        return this.request('DELETE', `/api/memories/facts/${factId}`);
    }
}
