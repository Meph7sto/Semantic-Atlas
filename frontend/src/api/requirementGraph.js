import { api } from './request'

export const requirementGraphApi = {
    async getGraph({
        projectId,
        sessionId,
        limit = 600,
        infer = false,
        relationMode = '',
        inferenceLimit = 48,
        model = 'deepseek-reasoner',
    } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        if (sessionId) params.session_id = sessionId
        if (limit) params.limit = limit
        params.infer = infer
        if (relationMode) params.relation_mode = relationMode
        if (infer) {
            params.inference_limit = inferenceLimit
            params.model = model
        }
        const resp = await api.get('/requirement-graph', { params })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getLatestSnapshot({
        projectId,
        sessionId,
        relationMode = '',
        limit = 600,
    } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        if (sessionId) params.session_id = sessionId
        if (relationMode) params.relation_mode = relationMode
        if (limit) params.limit = limit
        const resp = await api.get('/requirement-graph/latest', { params })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listSnapshotHistory({
        projectId,
        sessionId,
        relationMode = '',
        limit = 20,
    } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        if (sessionId) params.session_id = sessionId
        if (relationMode) params.relation_mode = relationMode
        if (limit) params.limit = limit
        const resp = await api.get('/requirement-graph/history', { params })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getSnapshot(snapshotId, { limit = 600 } = {}) {
        const resp = await api.get(`/requirement-graph/snapshots/${encodeURIComponent(snapshotId)}`, {
            params: { limit },
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async inferGraph({
        projectId,
        sessionId,
        limit = 80,
        relationMode = 'llm',
        inferenceLimit = 48,
        reviewConcurrency = 3,
        model = 'deepseek-reasoner',
        reviewEdges = [],
    } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (sessionId) payload.session_id = sessionId
        payload.limit = limit
        payload.relation_mode = relationMode
        payload.inference_limit = inferenceLimit
        payload.review_concurrency = reviewConcurrency
        payload.model = model
        if (Array.isArray(reviewEdges) && reviewEdges.length) payload.review_edges = reviewEdges
        const resp = await api.post('/requirement-graph/infer', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },
}
