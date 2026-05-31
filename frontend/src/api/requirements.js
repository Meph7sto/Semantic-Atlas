import { api, inferenceAxios } from './request'

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

    async batchAnalyzeRelation(highLevelReqs, lowLevelReqs, maxNewTokens = 800, saveToDb = false, sessionId = null) {
        const payload = {
            high_level_requirements: highLevelReqs,
            low_level_requirements: lowLevelReqs,
            max_new_tokens: maxNewTokens,
            save_to_db: saveToDb,
        }
        if (sessionId) {
            payload.session_id = sessionId
        }
        const resp = await api.post('/batch-trace-relation', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '批量分析失败')
        }
        return resp.data?.data ?? resp.data
    },

    /**
     * 基于数据库映射关系的追溯分析
     * 只分析有映射关系的顶层-底层需求对，而非全量笛卡尔积
     */
    async traceByMapping(sessionId, saveToDb = true, maxNewTokens = 800) {
        const payload = {
            session_id: sessionId,
            save_to_db: saveToDb,
            max_new_tokens: maxNewTokens,
        }
        const resp = await api.post('/trace-by-mapping', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '基于映射的追溯分析失败')
        }
        return resp.data
    },
}

// 冲突检测 API
export const conflictApi = {
    async check(requirementA, requirementB, saveToDb = false, sessionId = null) {
        const payload = {
            requirement_a: requirementA,
            requirement_b: requirementB,
            save_to_db: saveToDb,
        }
        if (sessionId) {
            payload.session_id = sessionId
        }
        const resp = await api.post('/conflict/check', payload)
        return resp.data
    },

    async checkBatch(pairs, saveToDb = false, sessionId = null) {
        const payload = {
            pairs: pairs,
            save_to_db: saveToDb,
        }
        if (sessionId) {
            payload.session_id = sessionId
        }
        const resp = await api.post('/conflict/check/batch', payload)
        return resp.data
    },

    async analyze(requirements, {
        saveToDb = false,
        sessionId = null,
        conflictConcurrency = 3,
        maxCandidatesPerBucket = 20,
        model = 'deepseek-v4-pro',
        useThinkingMode = true,
    } = {}) {
        const payload = {
            requirements,
            save_to_db: saveToDb,
            conflict_concurrency: conflictConcurrency,
            max_candidates_per_bucket: maxCandidatesPerBucket,
            model,
            use_thinking_mode: useThinkingMode,
        }
        if (sessionId) {
            payload.session_id = sessionId
        }
        const resp = await api.post('/conflict/analyze', payload)
        return resp.data
    },

    async getLatest(sessionId) {
        const resp = await api.get('/conflict/latest', {
            params: { session_id: sessionId },
        })
        return resp.data
    },

    // 冲突检测（统一走业务后端 FastAPI，不再前端直连 inference）
    async streamCheck(requirementA, requirementB, model = 'deepseek-v4-pro', useThinking = true) {
        const response = await fetch('/api/v2/conflict/stream_check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                requirement_a: requirementA,
                requirement_b: requirementB,
                model,
                use_thinking_mode: useThinking,
            }),
        })

        if (!response.ok) {
            let detail = ''
            try {
                const text = await response.text()
                if (text) {
                    detail = text
                }
            } catch (_) {
                // ignore
            }
            if (detail) {
                throw new Error(detail)
            }
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

    async getLatestTrace(sessionId) {
        const resp = await api.get('/trace/latest', {
            params: { session_id: sessionId },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载追溯缓存失败')
        }
        return resp.data?.data ?? resp.data
    },

    async saveRun(payload) {
        const resp = await api.post('/analysis/runs', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '保存分析记录失败')
        }
        return resp.data?.data ?? resp.data
    },

    async listRuns(sessionId, limit = 20) {
        const resp = await api.get('/analysis/runs', {
            params: { session_id: sessionId, limit },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载分析记录失败')
        }
        return resp.data?.data ?? resp.data
    },

    async getLatestRun(sessionId) {
        const resp = await api.get('/analysis/runs/latest', {
            params: { session_id: sessionId },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载最新分析记录失败')
        }
        return resp.data?.data ?? resp.data
    },

    async getRun(analysisRunId) {
        const resp = await api.get(`/analysis/runs/${encodeURIComponent(analysisRunId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载分析记录详情失败')
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

    /**
     * 流式需求抽取（支持并发处理）
     * @param {Object} payload - 抽取参数
     * @param {Function} onEvent - 事件回调 (eventName, eventData) => void
     * @returns {Promise<void>}
     */
    async extractStream(payload, onEvent) {
        const response = await fetch('/api/v2/requirements/extract_l123/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            const text = await response.text()
            throw new Error(`HTTP ${response.status}: ${text}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            let currentEvent = 'message'
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim()
                } else if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6))
                        if (onEvent) {
                            await onEvent(currentEvent, data)
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line, e)
                    }
                }
            }
        }
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

// L4 底层需求 API
export const l4RequirementsApi = {
    /**
     * 获取指定 session 的 L4 底层需求
     */
    async getBySession(sessionId, { page = 1, perPage = 100 } = {}) {
        const resp = await api.get(`/requirements/l4/${encodeURIComponent(sessionId)}`, {
            params: { page, per_page: perPage },
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '加载 L4 需求失败')
        }
        return resp.data
    },

    /**
     * 检查指定 session 是否有 L4 底层需求缓存
     */
    async checkExists(sessionId) {
        const resp = await api.get(`/requirements/l4/${encodeURIComponent(sessionId)}/exists`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '检查 L4 缓存失败')
        }
        return resp.data.exists
    },

    async clearBySession(sessionId) {
        const resp = await api.delete(`/requirements/l4/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '清空 L4 历史失败')
        }
        return resp.data
    },

    /**
     * 生成 L4 底层需求
     * 如有缓存直接返回，否则调用推理后端生成
     */
    async generate(sessionId, requirements, { config = {}, model = null, useThinkingMode = true, forceRegenerate = false } = {}) {
        const payload = {
            session_id: sessionId,
            requirements,
            config,
            use_thinking_mode: useThinkingMode,
            force_regenerate: forceRegenerate,
        }
        if (model) {
            payload.model = model
        }

        const resp = await api.post('/requirements/l4/generate', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || 'L4 需求生成失败')
        }
        return resp.data
    },

    async generateStream(sessionId, requirements, onEvent, { config = {}, model = null, useThinkingMode = true, forceRegenerate = false } = {}) {
        const payload = {
            session_id: sessionId,
            requirements,
            config,
            use_thinking_mode: useThinkingMode,
            force_regenerate: forceRegenerate,
        }
        if (model) {
            payload.model = model
        }

        const response = await fetch('/api/v2/requirements/l4/generate/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            const text = await response.text()
            throw new Error(`HTTP ${response.status}: ${text}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            let currentEvent = 'message'
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim()
                } else if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6))
                        if (onEvent) {
                            await onEvent(currentEvent, data)
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line, e)
                    }
                }
            }
        }
    },
}

// 需求分类 API
export const classifyTexts = (payload, saveToDb = false, sessionId = null) => {
    const finalPayload = {
        ...payload,
        save_to_db: saveToDb,
    }
    if (sessionId) {
        finalPayload.session_id = sessionId
    }
    return api.post('/classification/predict-texts', finalPayload)
}

export const getLatestClassification = async (sessionId) => {
    const resp = await api.get('/classification/latest', {
        params: { session_id: sessionId },
    })
    return resp.data?.data ?? resp.data
}

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
    async generate(requirements, config = {}, model = null, useThinkingMode = true) {
        const payload = {
            requirements,
            config,
            use_thinking_mode: useThinkingMode,
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
    },
}
