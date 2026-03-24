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

    async listAll() {
        const resp = await api.get('/admin/uploads')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to list all files')
        }
        return resp.data
    },

    async listTree() {
        const resp = await api.get('/admin/uploads/tree')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to list file tree')
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

    downloadAdmin(userId, relativePath) {
        const params = new URLSearchParams({
            user_id: userId,
            path: relativePath,
            download: 'true',
        })
        window.open(`/api/v2/admin/uploads/content?${params.toString()}`, '_blank')
    },

    async deleteAdmin(userId, relativePath) {
        const resp = await api.delete('/admin/uploads/content', {
            params: {
                user_id: userId,
                path: relativePath,
            },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to delete file')
        }
        return resp.data
    },

    getAdminPreviewUrl(userId, relativePath) {
        const params = new URLSearchParams({
            user_id: userId,
            path: relativePath,
        })
        return `/api/v2/admin/uploads/content?${params.toString()}`
    },

    async listMyTree() {
        const resp = await api.get('/uploads/tree')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to list file tree')
        }
        return resp.data
    },

    downloadMy(relativePath) {
        const params = new URLSearchParams({ path: relativePath, download: 'true' })
        window.open(`/api/v2/uploads/content?${params.toString()}`, '_blank')
    },

    getMyPreviewUrl(relativePath) {
        const params = new URLSearchParams({ path: relativePath })
        return `/api/v2/uploads/content?${params.toString()}`
    },
}
