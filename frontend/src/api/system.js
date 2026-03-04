import { api } from './request'

// 消息推送 API
export const pushApi = {
    async listMessages({ messageType = null, pushed = null, page = 1, perPage = 20 } = {}) {
        const params = { page, per_page: perPage }
        if (messageType) params.message_type = messageType
        if (pushed !== null) params.pushed = pushed
        const resp = await api.get('/push/messages', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取消息列表失败')
        }
        return resp.data
    },

    async createMessage(payload) {
        const resp = await api.post('/push/messages', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建消息失败')
        }
        return resp.data
    },

    async getMessage(messageId) {
        const resp = await api.get(`/push/messages/${encodeURIComponent(messageId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取消息失败')
        }
        return resp.data.data
    },

    async pushMessage(messageId) {
        const resp = await api.post(`/push/messages/${encodeURIComponent(messageId)}/push`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '推送消息失败')
        }
        return resp.data
    },

    async markRead(messageId) {
        const resp = await api.post(`/push/messages/${encodeURIComponent(messageId)}/read`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '标记已读失败')
        }
        return resp.data
    },

    async deleteMessage(messageId) {
        const resp = await api.delete(`/push/messages/${encodeURIComponent(messageId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '删除消息失败')
        }
        return resp.data
    },

    async getPendingMessages({ messageType = null, since = null } = {}) {
        const params = {}
        if (messageType) params.message_type = messageType
        if (since) params.since = since
        const resp = await api.get('/push/messages/pending', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取待处理消息失败')
        }
        return resp.data.messages
    },

    /**
     * 创建 SSE 连接
     * @returns {EventSource}
     */
    createSSEConnection() {
        return new EventSource('/api/v2/push/stream')
    },
}

// 文件上传 API（移动端文件接收）
export const fileApi = {
    async list() {
        const resp = await api.get('/uploads')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to list files')
        }
        return resp.data
    },

    download(filename) {
        // 直接打开下载链接
        window.open(`/api/v2/uploads/${encodeURIComponent(filename)}?download=true`, '_blank')
    },

    async delete(filename) {
        const resp = await api.delete(`/uploads/${encodeURIComponent(filename)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to delete file')
        }
        return resp.data
    },

    getPreviewUrl(filename) {
        return `/api/v2/uploads/${encodeURIComponent(filename)}`
    },
}
