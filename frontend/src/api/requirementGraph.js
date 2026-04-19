import { api } from './request'

export const requirementGraphApi = {
    async getGraph({
        projectId,
        sessionId,
        limit = 600,
        infer = true,
        inferenceLimit = 48,
        model = 'deepseek-reasoner',
    } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        if (sessionId) params.session_id = sessionId
        if (limit) params.limit = limit
        params.infer = infer
        if (infer) {
            params.inference_limit = inferenceLimit
            params.model = model
        }
        const resp = await api.get('/requirement-graph', { params })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async inferGraph({ projectId, sessionId, limit = 80, inferenceLimit = 48, model = 'deepseek-reasoner' } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (sessionId) payload.session_id = sessionId
        payload.limit = limit
        payload.inference_limit = inferenceLimit
        payload.model = model
        const resp = await api.post('/requirement-graph/infer', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
