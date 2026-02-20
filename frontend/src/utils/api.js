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
    (err) => {
        // 处理 401 未授权错误，清除本地存储的认证信息
        if (err.response?.status === 401) {
            // 清除认证信息
            localStorage.removeItem('token')
            localStorage.removeItem('user')
            // 如果不是在登录页面，可以重定向到登录页
            if (window.location.pathname !== '/beta/login' && !window.location.pathname.startsWith('/guide')) {
                window.location.href = '/beta/login'
            }
        }
        return Promise.reject(err)
    }
)

api.interceptors.request.use((config) => {
    try {
        // 优先使用 JWT Token 认证
        const token = localStorage.getItem('token')
        if (token) {
            config.headers = config.headers || {}
            config.headers['Authorization'] = `Bearer ${token}`
        }

        // 兼容旧的 X-Actor / X-Role 头
        const actor = localStorage.getItem('actor') || ''
        const role = localStorage.getItem('role') || ''
        if (actor) {
            config.headers = config.headers || {}
            config.headers['X-Actor'] = actor
        }
        if (role) {
            config.headers = config.headers || {}
            config.headers['X-Role'] = role
        }
    } catch (_) {
        // ignore
    }
    return config
})

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

    /**
     * 流式需求抽取（支持并发处理）
     * @param {Object} payload - 抽取参数
     * @param {Function} onEvent - 事件回调 (eventName, eventData) => void
     * @returns {Promise<void>}
     */
    async extractStream(payload, onEvent) {
        const response = await fetch('/api/requirements/extract_l123/stream', {
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
                            onEvent(currentEvent, data)
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

    async getProject(projectId) {
        const resp = await api.get(`/manage/projects/${encodeURIComponent(projectId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateProject(projectId, payload) {
        const resp = await api.patch(`/manage/projects/${encodeURIComponent(projectId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async setProjectSession(projectId, sessionId) {
        return this.updateProject(projectId, { current_session_id: sessionId })
    },

    async deleteProject(projectId) {
        const resp = await api.delete(`/manage/projects/${encodeURIComponent(projectId)}`)
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

    async importFromSession(projectId, payload) {
        const resp = await api.post(`/manage/projects/${encodeURIComponent(projectId)}/requirements/import`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // Backward-compatible alias (old naming).
    async importFromL123(projectId, payload) {
        return this.importFromSession(projectId, payload)
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

// 产品管理 API
export const productApi = {
    // ----------------------
    // Products CRUD
    // ----------------------
    async createProduct(payload) {
        const resp = await api.post('/product/products', payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listProducts({ includeArchived = false } = {}) {
        const resp = await api.get('/product/products', {
            params: includeArchived ? { include_archived: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async getProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async updateProduct(productId, payload) {
        const resp = await api.patch(`/product/products/${encodeURIComponent(productId)}`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async deleteProduct(productId) {
        const resp = await api.delete(`/product/products/${encodeURIComponent(productId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product Members
    // ----------------------
    async addMember(productId, payload) {
        const resp = await api.post(`/product/products/${encodeURIComponent(productId)}/members`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async removeMember(productId, userId) {
        const resp = await api.delete(`/product/products/${encodeURIComponent(productId)}/members/${encodeURIComponent(userId)}`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMembers(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/members`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product-Project Relations
    // ----------------------
    async listProjectsByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/projects`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async createProjectUnderProduct(productId, payload) {
        const resp = await api.post(`/product/products/${encodeURIComponent(productId)}/projects`, payload)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async bindProjectToProduct(projectId, productId) {
        const resp = await api.post(`/product/projects/${encodeURIComponent(projectId)}/bind`, {
            product_id: productId,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    // ----------------------
    // Product Overview
    // ----------------------
    async getProductOverview(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/overview`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listRequirementsByProduct(productId, { includeDeleted = false } = {}) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/requirements`, {
            params: includeDeleted ? { include_deleted: true } : undefined,
        })
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listMilestonesByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/milestones`)
        if (resp.data?.error) throw new Error(resp.data.error)
        return resp.data
    },

    async listBaselinesByProduct(productId) {
        const resp = await api.get(`/product/products/${encodeURIComponent(productId)}/baselines`)
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

// AI 聊天 API
export const aiChatApi = {
    // ========================
    // Session Management
    // ========================
    async listSessions({ projectId = null, limit = 50 } = {}) {
        const params = { limit }
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/sessions', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话列表失败')
        }
        return resp.data.sessions
    },

    async createSession({ projectId = null, title = null } = {}) {
        const payload = {}
        if (projectId) payload.project_id = projectId
        if (title) payload.title = title
        const resp = await api.post('/ai-chat/sessions', payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建会话失败')
        }
        return resp.data.data
    },

    async getCurrentSession({ projectId = null } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/sessions/current', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取当前会话失败')
        }
        return resp.data.data
    },

    async getSession(sessionId) {
        const resp = await api.get(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取会话失败')
        }
        return resp.data.data
    },

    async updateSession(sessionId, { title }) {
        const resp = await api.patch(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`, { title })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新会话失败')
        }
        return resp.data.data
    },

    async deleteSession(sessionId) {
        const resp = await api.delete(`/ai-chat/sessions/${encodeURIComponent(sessionId)}`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '删除会话失败')
        }
        return resp.data
    },

    // ========================
    // Message Management
    // ========================
    async listMessages({ sessionId, limit = 50, before = null } = {}) {
        const params = { limit }
        if (before) params.before = before
        const resp = await api.get(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages`, { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取消息列表失败')
        }
        return resp.data.messages
    },

    async sendMessage({ sessionId, content, systemPrompt = null, useThinking = false }) {
        const payload = { content }
        if (systemPrompt) payload.system_prompt = systemPrompt
        if (useThinking) payload.use_thinking = useThinking
        const resp = await api.post(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages`, payload)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '发送消息失败')
        }
        return resp.data.data
    },

    /**
     * 流式发送消息
     * @returns {Promise<Response>} Fetch Response for SSE streaming
     */
    async sendMessageStream({ sessionId, content, systemPrompt = null, useThinking = false }) {
        const payload = { content }
        if (systemPrompt) payload.system_prompt = systemPrompt
        if (useThinking) payload.use_thinking = useThinking

        const response = await fetch(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Actor': localStorage.getItem('actor') || '',
                'X-Role': localStorage.getItem('role') || '',
            },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response
    },

    /**
     * Agent 流式发送消息（支持工具调用）
     * 返回的 SSE 事件包含：user_message, thinking, token, tool_call, tool_result, task_created, assistant_message, finish, error, done
     * @returns {Promise<Response>} Fetch Response for SSE streaming
     */
    async sendAgentMessageStream({ sessionId, content, projectId = null, agentId = null, useThinking = false }) {
        const payload = { content }
        if (projectId) payload.project_id = projectId
        if (agentId) payload.agent_id = agentId
        if (useThinking) payload.use_thinking = useThinking

        const response = await fetch(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/messages/agent/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Actor': localStorage.getItem('actor') || '',
                'X-Role': localStorage.getItem('role') || '',
            },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response
    },

    async markRead(sessionId) {
        const resp = await api.post(`/ai-chat/sessions/${encodeURIComponent(sessionId)}/read`)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '标记已读失败')
        }
        return resp.data.marked_count
    },

    // ========================
    // Notification Counts
    // ========================
    async getUnreadCount({ projectId = null } = {}) {
        const params = {}
        if (projectId) params.project_id = projectId
        const resp = await api.get('/ai-chat/unread-count', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取未读数失败')
        }
        return resp.data.count
    },

    // ========================
    // SSE Real-time Updates
    // ========================
    createSSEConnection(sessionId) {
        return new EventSource(`/api/ai-chat/sessions/${encodeURIComponent(sessionId)}/stream`)
    },
}

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

// 认证 API
export const authApi = {
    // 登录
    async login(username, password, role = 'member') {
        const resp = await api.post('/auth/login', {
            username,
            password,
            role
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '登录失败')
        }
        return resp.data.data
    },

    // 注册
    async register(username, password, displayName, role = 'member') {
        const resp = await api.post('/auth/register', {
            username,
            password,
            display_name: displayName,
            role
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '注册失败')
        }
        return resp.data.data
    },

    // 验证 Token
    async verify() {
        const resp = await api.get('/auth/verify')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || 'Token 无效')
        }
        return resp.data.data
    },

    // 获取当前用户信息
    async getCurrentUser() {
        const resp = await api.get('/auth/me')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户信息失败')
        }
        return resp.data.data
    },

    // 登出
    async logout() {
        const resp = await api.post('/auth/logout')
        return resp.data
    },

    // 列出用户（仅管理员）
    async listUsers({ role, limit = 100, offset = 0 } = {}) {
        const params = { limit, offset }
        if (role) params.role = role
        const resp = await api.get('/auth/users', { params })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取用户列表失败')
        }
        return resp.data.data
    },

    // 创建用户（仅管理员）
    async createUser(data) {
        const resp = await api.post('/auth/users', data)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '创建用户失败')
        }
        return resp.data.data
    },

    // 更新用户（仅管理员）
    async updateUser(userId, data) {
        const resp = await api.patch(`/auth/users/${userId}`, data)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新用户失败')
        }
        return resp.data.data
    },

    // 获取当前用户个人资料
    async getProfile() {
        const resp = await api.get('/auth/profile')
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '获取个人资料失败')
        }
        return resp.data.data
    },

    // 更新当前用户个人资料（display_name, avatar_url）
    async updateProfile({ display_name, avatar_url } = {}) {
        const body = {}
        if (display_name !== undefined) body.display_name = display_name
        if (avatar_url !== undefined) body.avatar_url = avatar_url
        const resp = await api.patch('/auth/profile', body)
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '更新个人资料失败')
        }
        return resp.data.data
    },

    // 修改当前用户密码
    async changePassword(oldPassword, newPassword) {
        const resp = await api.post('/auth/profile/change-password', {
            old_password: oldPassword,
            new_password: newPassword,
        })
        if (resp.data?.success === false) {
            throw new Error(resp.data?.error || '修改密码失败')
        }
        return resp.data
    },
}

// ========================
// 权限管理 API
// ========================
export const permissionApi = {
  /**
   * 获取用户在项目中的权限上下文
   */
  async getProjectContext(projectId) {
    const resp = await api.get(`/permission/projects/${encodeURIComponent(projectId)}/context`)
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取权限上下文失败')
    }
    return resp.data.data
  },

  // ========================
  // 项目成员管理
  // ========================

  /**
   * 添加项目成员
   * @param {string} projectId - 项目 ID
   * @param {string} userId - 用户 ID
   * @param {string[]} memberRoles - 角色列表（可选）
   */
  async addProjectMember(projectId, userId, memberRoles = []) {
    const resp = await api.post(`/permission/projects/${encodeURIComponent(projectId)}/members`, {
      user_id: userId,
      member_roles: memberRoles,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '添加项目成员失败')
    }
    return resp.data.data
  },

  /**
   * 列出项目成员
   * @param {string} projectId - 项目 ID
   * @param {boolean} includeRoles - 是否包含角色信息
   */
  async listProjectMembers(projectId, includeRoles = false) {
    const resp = await api.get(`/permission/projects/${encodeURIComponent(projectId)}/members`, {
      params: { include_roles: includeRoles ? 'true' : 'false' },
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取项目成员列表失败')
    }
    return resp.data.data
  },

  /**
   * 移除项目成员
   * @param {string} projectId - 项目 ID
   * @param {string} userId - 用户 ID
   */
  async removeProjectMember(projectId, userId) {
    const resp = await api.delete(`/permission/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`)
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '移除项目成员失败')
    }
    return resp.data.data
  },

  /**
   * 设置用户角色（全量替换）
   * @param {string} projectId - 项目 ID
   * @param {string} userId - 用户 ID
   * @param {string[]} roles - 角色列表
   */
  async setUserRoles(projectId, userId, roles) {
    const resp = await api.put(`/permission/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}/roles`, {
      roles,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '设置用户角色失败')
    }
    return resp.data.data
  },

  // ========================
  // 评审管理
  // ========================

  /**
   * 创建评审指派
   * @param {string} requirementId - 需求 ID
   * @param {string} reviewerId - 评审人 ID
   * @param {number} seq - 序号
   * @param {string} comment - 评审说明
   */
  async createReviewAssignment(requirementId, reviewerId, seq = 1, comment = null) {
    const resp = await api.post(`/permission/requirements/${encodeURIComponent(requirementId)}/reviews`, {
      reviewrer_id: reviewerId,
      seq,
      comment,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '创建评审指派失败')
    }
    return resp.data.data
  },

  /**
   * 列出需求的所有评审
   * @param {string} requirementId - 需求 ID
   * @param {string} status - 状态筛选（可选）
   */
  async listRequirementReviews(requirementId, status = null) {
    const params = {}
    if (status) params.status = status

    const resp = await api.get(`/permission/requirements/${encodeURIComponent(requirementId)}/reviews`, { params })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取评审列表失败')
    }
    return resp.data.data
  },

  /**
   * 通过评审
   * @param {number} assignmentId - 评审指派 ID
   * @param {string} comment - 审批意见
   */
  async approveReview(assignmentId, comment = null) {
    const resp = await api.post(`/permission/reviews/${assignmentId}/approve`, { comment })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '通过评审失败')
    }
    return resp.data.data
  },

  /**
   * 驳回评审
   * @param {number} assignmentId - 评审指派 ID
   * @param {string} comment - 驳回原因
   */
  async rejectReview(assignmentId, comment = null) {
    const resp = await api.post(`/permission/reviews/${assignmentId}/reject`, { comment })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '驳回评审失败')
    }
    return resp.data.data
  },

  /**
   * 撤回评审
   * @param {number} assignmentId - 评审指派 ID
   */
  async withdrawReview(assignmentId) {
    const resp = await api.post(`/permission/reviews/${assignmentId}/withdraw`)
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '撤回评审失败')
    }
    return resp.data.data
  },

  /**
   * 获取当前用户的待处理评审列表
   * @param {string} projectId - 项目 ID（可选）
   */
  async getPendingReviews(projectId = null) {
    const params = {}
    if (projectId) params.project_id = projectId

    const resp = await api.get('/permission/user/pending-reviews', { params })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取待处理评审失败')
    }
    return resp.data.data
  },

  // ========================
  // 基线管理
  // ========================

  /**
   * 创建基线
   * @param {string} projectId - 项目 ID
   * @param {string} version - 版本号
   * @param {boolean} locked - 是否锁定
   */
  async createBaseline(projectId, version, locked = false) {
    const resp = await api.post(`/permission/projects/${encodeURIComponent(projectId)}/baselines`, {
      version,
      locked,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '创建基线失败')
    }
    return resp.data.data
  },

  /**
   * 列出项目的所有基线
   * @param {string} projectId - 项目 ID
   * @param {boolean} includeLocked - 是否包含已锁定的基线
   */
  async listBaselines(projectId, includeLocked = true) {
    const resp = await api.get(`/permission/projects/${encodeURIComponent(projectId)}/baselines`, {
      params: { include_locked: includeLocked ? 'true' : 'false' },
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取基线列表失败')
    }
    return resp.data.data
  },

  /**
   * 锁定基线
   * @param {number} baselineId - 基线 ID
   */
  async lockBaseline(baselineId) {
    const resp = await api.post(`/permission/baselines/${baselineId}/lock`)
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '锁定基线失败')
    }
    return resp.data.data
  },

  /**
   * 解锁基线
   * @param {number} baselineId - 基线 ID
   */
  async unlockBaseline(baselineId) {
    const resp = await api.post(`/permission/baselines/${baselineId}/unlock`)
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '解锁基线失败')
    }
    return resp.data.data
  },

  // ========================
  // 变更请求管理
  // ========================

  /**
   * 创建变更请求
   * @param {string} requirementId - 需求 ID
   * @param {number} baselineId - 基线 ID
   * @param {string} reason - 变更原因
   * @param {string} changeSummary - 变更摘要
   */
  async createChangeRequest(requirementId, baselineId, reason, changeSummary) {
    const resp = await api.post(`/permission/requirements/${encodeURIComponent(requirementId)}/change-requests`, {
      baseline_id: baselineId,
      reason,
      change_summary: changeSummary,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '创建变更请求失败')
    }
    return resp.data.data
  },

  /**
   * 列出需求的所有变更请求
   * @param {string} requirementId - 需求 ID
   * @param {string} status - 状态筛选（可选）
   */
  async listChangeRequests(requirementId, status = null) {
    const params = {}
    if (status) params.status = status

    const resp = await api.get(`/permission/requirements/${encodeURIComponent(requirementId)}/change-requests`, { params })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取变更请求列表失败')
    }
    return resp.data.data
  },

  /**
   * 批准变更请求
   * @param {number} requestId - 变更请求 ID
   * @param {string} reviewComment - 审批意见
   */
  async approveChangeRequest(requestId, reviewComment = null) {
    const resp = await api.post(`/permission/change-requests/${requestId}/approve`, {
      review_comment: reviewComment,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '批准变更请求失败')
    }
    return resp.data.data
  },

  /**
   * 驳回变更请求
   * @param {number} requestId - 变更请求 ID
   * @param {string} reviewComment - 驳回原因
   */
  async rejectChangeRequest(requestId, reviewComment = null) {
    const resp = await api.post(`/permission/change-requests/${requestId}/reject`, {
      review_comment: reviewComment,
    })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '驳回变更请求失败')
    }
    return resp.data.data
  },

  /**
   * 获取待审批的变更请求列表
   * @param {string} projectId - 项目 ID（可选）
   */
  async getPendingChangeRequests(projectId = null) {
    const params = {}
    if (projectId) params.project_id = projectId

    const resp = await api.get('/permission/change-requests/pending', { params })
    if (resp.data?.success === false) {
      throw new Error(resp.data?.error || '获取待审批变更请求失败')
    }
    return resp.data.data
  },
}

export default api
