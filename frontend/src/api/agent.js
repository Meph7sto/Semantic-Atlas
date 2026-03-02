import { api } from './request'

// Agent 协作监控 API
export const agentMonitorApi = {
    async getOverview({ projectId = null, limitMessages = 300, limitTasks = 200, limitEvents = 500 } = {}) {
        const params = {
            limit_messages: limitMessages,
            limit_tasks: limitTasks,
            limit_events: limitEvents,
        }
        if (projectId) params.project_id = projectId
        const resp = await api.get('/agent-monitor/overview', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取 Agent 监控数据失败')
        }
        return resp.data
    },

    async getChannelMessages(channelId, { projectId = null, limit = 200 } = {}) {
        const params = { limit }
        if (projectId) params.project_id = projectId
        const resp = await api.get(`/agent-monitor/channels/${encodeURIComponent(channelId)}/messages`, { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取频道消息失败')
        }
        return resp.data.messages || []
    },
}

// Agent 任务 API
export const agentTaskApi = {
    async listTasks({ projectId = null, status = null, limit = 50 } = {}) {
        const params = { limit }
        if (projectId) params.project_id = projectId
        if (status) params.status = status
        const resp = await api.get('/agent-tasks', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取任务列表失败')
        }
        return resp.data.tasks
    },

    async createTask({ taskType, title, description = null, payload = null, sessionId = null, projectId = null }) {
        const reqPayload = { task_type: taskType, title }
        if (description) reqPayload.description = description
        if (payload) reqPayload.payload = payload
        if (sessionId) reqPayload.session_id = sessionId
        if (projectId) reqPayload.project_id = projectId
        const resp = await api.post('/agent-tasks', reqPayload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建任务失败')
        }
        return resp.data.data
    },

    async getTask(taskId) {
        const resp = await api.get(`/agent-tasks/${encodeURIComponent(taskId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取任务失败')
        }
        return resp.data.data
    },

    async approveTask(taskId) {
        const resp = await api.post(`/agent-tasks/${encodeURIComponent(taskId)}/approve`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '批准任务失败')
        }
        return resp.data.data
    },

    async rejectTask(taskId) {
        const resp = await api.post(`/agent-tasks/${encodeURIComponent(taskId)}/reject`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '拒绝任务失败')
        }
        return resp.data.data
    },

    async getPendingCount({ projectId = null } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        const resp = await api.get('/agent-tasks/pending-count', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取待审数失败')
        }
        return resp.data.count
    },
}
