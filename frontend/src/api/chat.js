import { api } from './request'

// 通用问答 API
export const chatApi = {
    async streamAsk(
        prompt,
        useThinking = false,
        useAsyncClient = false,
        maxNewTokens = 800,
        systemPrompt = ''
    ) {
        const response = await fetch('/inference/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt,
                system_prompt: systemPrompt,
                max_new_tokens: maxNewTokens,
                use_thinking_mode: useThinking,
                use_async_client: useAsyncClient,
            }),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response.body
    },
}

// 移动端对话桥接 API
export const mobileChatApi = {
    async listSessions({ userId = null, limit = 200 } = {}) {
        const params = { limit }
        if (userId) params.user_id = userId
        const resp = await api.get('/mobile/sessions', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话列表失败')
        }
        return resp.data.sessions
    },

    async listMessages({ userId = null, sessionId, limit = 100, since = null } = {}) {
        const params = { session_id: sessionId, limit }
        if (userId) params.user_id = userId
        if (since) params.since = since
        const resp = await api.get('/mobile/messages', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取移动端消息失败')
        }
        return resp.data.messages
    },

    async sendMessage({ userId = null, sessionId, sender, content, metadata = null }) {
        const payload = {
            session_id: sessionId,
            sender,
            content,
        }
        if (userId) payload.user_id = userId
        if (metadata) payload.metadata = metadata
        const resp = await api.post('/mobile/messages', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '发送移动端消息失败')
        }
        return resp.data.data
    },

    createSSEConnection(sessionId, userId = null) {
        const params = new URLSearchParams({
            session_id: sessionId,
        })
        if (userId) params.set('user_id', userId)
        return new EventSource(`/api/mobile/stream?${params.toString()}`)
    },
}

// AI 聊天 API
export const aiChatApi = {
    // ========================
    // Session Management
    // ========================
    async listSessions({ projectId = null, limit = 50 } = {}) {
        const params = { limit }
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/sessions', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话列表失败')
        }
        return resp.data.sessions
    },

    async createSession({ projectId = null, title = null } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (title) payload.title = title
        const resp = await api.post('/ai-chat/sessions', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建会话失败')
        }
        return resp.data.data
    },

    async getCurrentSession({ projectId = null } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/sessions/current', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取当前会话失败')
        }
        return resp.data.data
    },

    async getSession(sessionId) {
        const resp = await api.get(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话失败')
        }
        return resp.data.data
    },

    async updateSession(sessionId, { title }) {
        const resp = await api.patch(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`, { title })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新会话失败')
        }
        return resp.data.data
    },

    async deleteSession(sessionId) {
        const resp = await api.delete(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '删除会话失败')
        }
        return resp.data
    },

    // ========================
    // Message Management
    // ========================
    async listMessages({ sessionId, limit = 50, before = null } = {}) {
        const params = { limit }
        if (before) params.before = before
        const resp = await api.get(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages`, { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取消息列表失败')
        }
        return resp.data.messages
    },

    async sendMessage({ sessionId, content, systemPrompt = null, useThinking = false }) {
        const payload = { content }
        if (systemPrompt) payload.system_prompt = systemPrompt
        if (useThinking) payload.use_thinking = useThinking
        const resp = await api.post(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages`, payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '发送消息失败')
        }
        return resp.data.data
    },

    /**
     * 流式发送消息
     * @returns {Promise<Response>} Fetch Response for SSE streaming
     */
    async sendMessageStream({ sessionId, content, systemPrompt = null, useThinking = false }) {
        const payload = { content }
        if (systemPrompt) payload.system_prompt = systemPrompt
        if (useThinking) payload.use_thinking = useThinking

        const response = await fetch(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Actor': localStorage.getItem('actor') || '',
                'X-Role': localStorage.getItem('role') || '',
            },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response
    },

    /**
     * Agent 流式发送消息（支持工具调用）
     * 返回的 SSE 事件包含：user_message, thinking, token, tool_call, tool_result, task_created, assistant_message, finish, error, done
     * @returns {Promise<Response>} Fetch Response for SSE streaming
     */
    async sendAgentMessageStream({ sessionId, content, projectId = null, agentId = null, useThinking = false }) {
        const payload = { content }
        if (projectId) payload.project_id = projectId
        if (agentId) payload.agent_id = agentId
        if (useThinking) payload.use_thinking = useThinking

        const response = await fetch(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages/agent/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Actor': localStorage.getItem('actor') || '',
                'X-Role': localStorage.getItem('role') || '',
            },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response
    },

    async markRead(sessionId) {
        const resp = await api.post(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/read`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '标记已读失败')
        }
        return resp.data.marked_count
    },

    // ========================
    // Notification Counts
    // ========================
    async getUnreadCount({ projectId = null } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/unread-count', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取未读数失败')
        }
        return resp.data.count
    },

    // ========================
    // SSE Real-time Updates
    // ========================
    createSSEConnection(sessionId) {
        return new EventSource(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/stream`)
    },
}
