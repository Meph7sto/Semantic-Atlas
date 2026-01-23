import axios from 'axios'

// 约定：
// - 开发环境通过 Vite 代理 /api 到业务后端 (5001)
// - 生产环境由 Nginx 反代 /api 到后端
const api = axios.create({
    baseURL: '/api',
    timeout: 1800000, // 30分钟超时，批量分析需要较长时间
    headers: { 'Content-Type': 'application/json' },
})

const inferenceAxios = axios.create({
    baseURL: '/inference',
    timeout: 1800000, // 30分钟超时，模型推理可能需要较长时间
    headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
    (resp) => resp,
    (err) => Promise.reject(err)
)

inferenceAxios.interceptors.response.use(
    (resp) => resp,
    (err) => Promise.reject(err)
)

// 需求追溯 API 封装
export const traceabilityApi = {
    async health() {
        const resp = await api.get('/health')
        return resp.data
    },

    async analyzeRelation(highLevelReq, lowLevelReq, maxNewTokens = 800) {
        const resp = await api.post('/trace-relation', {
            high_level_requirement: highLevelReq,
            low_level_requirement: lowLevelReq,
            max_new_tokens: maxNewTokens,
            save_to_db: false,
        })
        return resp.data?.data ?? resp.data
    },

    async batchAnalyzeRelation(highLevelReqs, lowLevelReqs, maxNewTokens = 1200) {
        const resp = await api.post('/batch-trace-relation', {
            high_level_requirements: highLevelReqs,
            low_level_requirements: lowLevelReqs,
            max_new_tokens: maxNewTokens,
            save_to_db: false,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '批量分析失败')
        }
        return resp.data?.data ?? resp.data
    },
}

// 冲突检测 API
export const conflictApi = {
    async check(requirementA, requirementB) {
        const resp = await api.post('/conflict/check', {
            requirement_a: requirementA,
            requirement_b: requirementB,
        })
        return resp.data
    },

    // 流式检测，直接连接推理服务
    async streamCheck(requirementA, requirementB, useThinking = false) {
        const response = await fetch('/inference/conflict/stream_check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                requirement_a: requirementA,
                requirement_b: requirementB,
                use_thinking_mode: useThinking,
            }),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return response.body;
    },
}

// 通用问答 API
export const chatApi = {
    async streamAsk(prompt, useThinking = false, maxNewTokens = 800, systemPrompt = '') {
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
            }),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response.body
    },
}

// Phase 2 (Context Building) / Phase 1 spans查询
export const analysisApi = {
    async listContextRuns(sessionId = '') {
        const resp = await api.get('/analysis/context_runs', {
            params: sessionId ? { session_id: sessionId } : undefined,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载 context_runs 失败')
        }
        return resp.data?.data ?? resp.data
    },

    async getSpans(sessionId) {
        const resp = await api.get(`/analysis/spans/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载 spans 失败')
        }
        return resp.data?.data ?? resp.data
    },

    async getSpanLinks(contextRunId) {
        const resp = await api.get(`/analysis/span_links/${encodeURIComponent(contextRunId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载 span_links 失败')
        }
        return resp.data?.data ?? resp.data
    },
}

// Phase 3 (L1-L3) 需求抽取
export const requirementsL123Api = {
    async extract(payload) {
        const resp = await api.post('/requirements/extract_l123', payload)
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async listBySession(sessionId, { level = null, page = 1, perPage = 50 } = {}) {
        const params = {
            page,
            per_page: perPage,
        }
        if (level) params.level = level

        const resp = await api.get(`/requirements/session/${encodeURIComponent(sessionId)}`, { params })
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async stats(sessionId = null) {
        const resp = await api.get('/requirements/stats', {
            params: sessionId ? { session_id: sessionId } : undefined,
        })
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async delete(reqId) {
        const resp = await api.delete(`/requirements/${encodeURIComponent(reqId)}`)
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },
}

// 需求分类 API
export const classifyTexts = (payload) => api.post('/classification/predict-texts', payload)

export const classifyCsv = (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/classification/predict-csv', formData, {
        responseType: 'blob',
        headers: { 'Content-Type': 'multipart/form-data' },
    })
}

// Phase 4 (L4) 软件需求生成与校验
export const l4Api = {
    async generate(requirements, config = {}, model = null) {
        const payload = {
            requirements,
            config,
        }
        if (model) {
            payload.model = model
        }
        const resp = await inferenceAxios.post('/l4/generate', payload)
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async validate(l4Requirements, { expectedTopIds = null, openQuestionsByTopId = null, allowedEvidenceIds = null, confidenceThreshold = null } = {}) {
        const resp = await inferenceAxios.post('/l4/validate', {
            l4_requirements: l4Requirements,
            expected_top_ids: expectedTopIds,
            open_questions_by_top_id: openQuestionsByTopId,
            allowed_evidence_ids: allowedEvidenceIds,
            confidence_threshold: confidenceThreshold,
        })
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async searchKb(query, kbType = 'all', topK = 5, filters = null) {
        const resp = await inferenceAxios.post('/kb/search', {
            query,
            kb_type: kbType,
            top_k: topK,
            filters,
        })
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async getKbStatus() {
        const resp = await inferenceAxios.get('/kb/status')
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    },

    async rebuildKb() {
        const resp = await inferenceAxios.post('/kb/rebuild')
        if (resp.data?.error) {
            throw new Error(resp.data.error)
        }
        return resp.data
    }
}

export default api
