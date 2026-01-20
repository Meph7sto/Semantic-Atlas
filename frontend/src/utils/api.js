import axios from 'axios'

// 约定：
// - 开发环境通过 Vite 代理 /api 到业务后端 (5001)
// - 生产环境由 Nginx 反代 /api 到后端
const api = axios.create({
    baseURL: '/api',
    timeout: 1800000, // 30分钟超时，批量分析需要较长时间
    headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
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

export default api
