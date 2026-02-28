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

    async getLatest(sessionId) {
        const resp = await api.get('/conflict/latest', {
            params: { session_id: sessionId },
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

    /**
     * 生成 L4 底层需求
     * 如有缓存直接返回，否则调用推理后端生成
     */
    async generate(sessionId, requirements, { config = {}, model = null, forceRegenerate = false } = {}) {
        const payload = {
            session_id: sessionId,
            requirements,
            config,
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
}

// 需求管理监控 API
export const manageApi = {
    async createProject(payload) {
        const resp = await api.post('/manage/projects', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listProjects() {
        const resp = await api.get('/manage/projects')
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listRequirements(projectId, { tree = false } = {}) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/requirements`, {
            params: tree ? { tree: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createRequirement(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/requirements`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateRequirement(reqId, payload) {
        const resp = await api.patch(`/manage/requirements/${encodeURIComponent(reqId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async bulkUpdateRequirementStatus(payload) {
        const resp = await api.post('/manage/requirements/bulk-status', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async moveRequirement(reqId, payload) {
        const resp = await api.post(`/manage/requirements/${encodeURIComponent(reqId)}/move`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async deleteRequirement(reqId, { cascade = false } = {}) {
        const resp = await api.delete(`/manage/requirements/${encodeURIComponent(reqId)}`, {
            params: cascade ? { cascade: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async importFromL123(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/requirements/import`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createMilestone(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/milestones`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestones(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/milestones`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getMilestone(milestoneId) {
        const resp = await api.get(`/manage/milestones/${encodeURIComponent(milestoneId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async setBaseline(milestoneId) {
        const resp = await api.post(`/manage/milestones/${encodeURIComponent(milestoneId)}/baseline`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async compareMilestones(payload) {
        const resp = await api.post('/manage/milestones/compare', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestoneGraph(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/milestone-graph`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createBranch(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/branches`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async mergeBranches(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/branches/merge`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listBranches(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/branches`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async addChangeSet(branchId, payload) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/changes`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listChangeSets(branchId) {
        const resp = await api.get(`/manage/branches/${encodeURIComponent(branchId)}/changes`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createImpactReport(branchId) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/impact`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createMergeRequest(branchId, payload) {
        const resp = await api.post(`/manage/branches/${encodeURIComponent(branchId)}/merge`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listAudits(projectId, limit = 100) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}/audits`, {
            params: { limit },
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
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
        return new EventSource('/api/push/stream')
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
        window.open(`/api/uploads/${encodeURIComponent(filename)}?download=true`, '_blank')
    },

    async delete(filename) {
        const resp = await api.delete(`/uploads/${encodeURIComponent(filename)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.message || 'Failed to delete file')
        }
        return resp.data
    },

    getPreviewUrl(filename) {
        return `/api/uploads/${encodeURIComponent(filename)}`
    },
}

// 移动端对话桥接 API
export const mobileChatApi = {
    async listSessions({ limit = 200 } = {}) {
        const resp = await api.get('/mobile/sessions', { params: { limit } })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话列表失败')
        }
        return resp.data.sessions
    },

    async listMessages({ sessionId, limit = 100, since = null } = {}) {
        const params = { session_id: sessionId, limit }
        if (since) params.since = since
        const resp = await api.get('/mobile/messages', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取移动端消息失败')
        }
        return resp.data.messages
    },

    async sendMessage({ sessionId, sender, content, metadata = null }) {
        const payload = {
            session_id: sessionId,
            sender,
            content,
        }
        if (metadata) payload.metadata = metadata
        const resp = await api.post('/mobile/messages', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '发送移动端消息失败')
        }
        return resp.data.data
    },

    createSSEConnection(sessionId) {
        return new EventSource(`/api/mobile/stream?session_id=${encodeURIComponent(sessionId)}`)
    },
}

export default api
