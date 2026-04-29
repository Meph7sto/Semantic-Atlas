import { api } from './request'

export const requirementGraphApi = {
    async getGraph({
        projectId,
        sessionId,
        limit = 600,
        infer = false,
        relationMode = '',
        inferenceLimit = 48,
        model = 'deepseek-v4-pro',
        useThinkingMode = true,
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
            params.use_thinking_mode = useThinkingMode
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

    async deleteAllRelations({
        projectId,
        sessionId,
        relationMode = '',
    } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (sessionId) payload.session_id = sessionId
        if (relationMode) payload.relation_mode = relationMode
        const resp = await api.delete('/requirement-graph/relations', { data: payload })
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
        model = 'deepseek-v4-pro',
        useThinkingMode = true,
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
        payload.use_thinking_mode = useThinkingMode
        if (Array.isArray(reviewEdges) && reviewEdges.length) payload.review_edges = reviewEdges
        const resp = await api.post('/requirement-graph/infer', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async streamGraph({
        projectId,
        sessionId,
        limit = 900,
        inferenceLimit = 48,
        packageSize = 6,
        reviewConcurrency = 3,
        model = 'deepseek-v4-pro',
        useThinkingMode = true,
        signal,
        onEvent,
    } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (sessionId) payload.session_id = sessionId
        payload.limit = limit
        payload.inference_limit = inferenceLimit
        payload.package_size = packageSize
        payload.review_concurrency = reviewConcurrency
        payload.model = model
        payload.use_thinking_mode = useThinkingMode

        const headers = { 'Content-Type': 'application/json' }
        const token = localStorage.getItem('token')
        if (token) headers.Authorization = `Bearer ${token}`
        const actor = localStorage.getItem('actor') || ''
        const role = localStorage.getItem('role') || ''
        if (actor) headers['X-Actor'] = actor
        if (role) headers['X-Role'] = role

        const response = await fetch('/api/v2/requirement-graph/stream', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
            signal,
        })
        if (!response.ok) {
            let message = `需求图谱流式生成失败：${response.status}`
            try {
                const body = await response.json()
                message = body?.detail || body?.error || message
            } catch (_) {
                // ignore non-JSON error body
            }
            throw new Error(message)
        }
        if (!response.body) throw new Error('当前浏览器不支持流式读取')

        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const chunks = buffer.split(/\n\n/)
            buffer = chunks.pop() || ''
            chunks.forEach(chunk => {
                const parsed = parseSseChunk(chunk)
                if (parsed && typeof onEvent === 'function') onEvent(parsed)
            })
        }
        buffer += decoder.decode()
        const parsed = parseSseChunk(buffer)
        if (parsed && typeof onEvent === 'function') onEvent(parsed)
    },

    async streamDiscoverGraph({
        projectId,
        sessionId,
        limit = 900,
        reviewConcurrency = 3,
        model = 'deepseek-v4-pro',
        useThinkingMode = true,
        signal,
        onEvent,
    } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (sessionId) payload.session_id = sessionId
        payload.limit = limit
        payload.review_concurrency = reviewConcurrency
        payload.model = model
        payload.use_thinking_mode = useThinkingMode

        const headers = { 'Content-Type': 'application/json' }
        const token = localStorage.getItem('token')
        if (token) headers.Authorization = `Bearer ${token}`
        const actor = localStorage.getItem('actor') || ''
        const role = localStorage.getItem('role') || ''
        if (actor) headers['X-Actor'] = actor
        if (role) headers['X-Role'] = role

        const response = await fetch('/api/v2/requirement-graph/discover/stream', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
            signal,
        })
        if (!response.ok) {
            let message = `DeepSeek 发现关系失败：${response.status}`
            try {
                const body = await response.json()
                message = body?.detail || body?.error || message
            } catch (_) {
                // ignore non-JSON error body
            }
            throw new Error(message)
        }
        if (!response.body) throw new Error('当前浏览器不支持流式读取')

        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const chunks = buffer.split(/\n\n/)
            buffer = chunks.pop() || ''
            chunks.forEach(chunk => {
                const parsed = parseSseChunk(chunk)
                if (parsed && typeof onEvent === 'function') onEvent(parsed)
            })
        }
        buffer += decoder.decode()
        const parsed = parseSseChunk(buffer)
        if (parsed && typeof onEvent === 'function') onEvent(parsed)
    },
}

function parseSseChunk(chunk) {
    const lines = String(chunk || '').split(/\r?\n/)
    let event = 'message'
    const dataLines = []
    lines.forEach(line => {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    })
    if (!dataLines.length) return null
    try {
        return { event, data: JSON.parse(dataLines.join('\n')) }
    } catch (_) {
        return { event, data: dataLines.join('\n') }
    }
}
