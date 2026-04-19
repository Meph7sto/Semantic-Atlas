import { api } from './request'

export const requirementGraphApi = {
    async getGraph({ projectId, sessionId, limit = 600 } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        if (sessionId) params.session_id = sessionId
        if (limit) params.limit = limit
        const resp = await api.get('/requirement-graph', { params })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
