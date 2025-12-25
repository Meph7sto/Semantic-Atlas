// Axios 封装 (BaseURL 配置为 /api) 占位符
import axios from 'axios'

// 约定：
// - 开发环境通过 vue.config.js 把 /api 代理到 http://localhost:8000
// - 生产环境由 Nginx 反代 /api 到后端
const api = axios.create({
  baseURL: '/api',
  timeout: 600000, // 批量分析可能需要更长时间，设置为10分钟
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.response.use(
  resp => resp,
  err => Promise.reject(err)
)

export const traceabilityApi = {
  async health() {
    const resp = await api.get('/health')
    return resp.data
  },

  async analyzeRelation(highLevelReq, lowLevelReq, maxNewTokens = 800) {
    // 走业务后端兼容接口：/api/trace-relation
    const resp = await api.post('/trace-relation', {
      high_level_requirement: highLevelReq,
      low_level_requirement: lowLevelReq,
      max_new_tokens: maxNewTokens,
      save_to_db: false
    })
    // 业务后端返回 {success, data, record_id}
    return resp.data?.data ?? resp.data
  },

  async batchAnalyzeRelation(highLevelReqs, lowLevelReqs, maxNewTokens = 1200) {
    // 走业务后端兼容接口：/api/batch-trace-relation
    try {
      const resp = await api.post('/batch-trace-relation', {
        high_level_requirements: highLevelReqs,
        low_level_requirements: lowLevelReqs,
        max_new_tokens: maxNewTokens,
        save_to_db: false
      })
      console.log('批量分析 API 响应:', resp.data)
      // 业务后端返回 {success, data, record_id}
      if (resp.data?.success === false) {
        throw new Error(resp.data?.error || '批量分析失败')
      }
      return resp.data?.data ?? resp.data
    } catch (error) {
      console.error('批量分析 API 错误:', error)
      throw error
    }
  }
}

export const conflictApi = {
  async check(requirementA, requirementB) {
    const resp = await api.post('/conflict/check', {
      requirement_a: requirementA,
      requirement_b: requirementB
    })
    return resp.data
  }
}

export default api
