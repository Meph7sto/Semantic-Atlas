import axios from 'axios'

// 创建axios实例
const api = axios.create({
  baseURL: process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:5000/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    console.log('API请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  error => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    console.log('API响应:', response.status, response.config.url)
    return response
  },
  error => {
    console.error('响应错误:', error.response?.status, error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// API方法
export const requirementApi = {
  // 健康检查
  async healthCheck() {
    const response = await api.get('/health')
    return response.data
  },


  // 分析需求关系
  async analyzeRequirementRelation(highLevelReq, lowLevelReq, saveToDb = false) {
    const response = await api.post('/trace-relation', {
      high_level_requirement: highLevelReq,
      low_level_requirement: lowLevelReq,
      save_to_db: saveToDb
    })
    return response.data
  },

  // 批量分析需求关系
  async batchAnalyzeRequirementRelations(highLevelReqs, lowLevelReqs, saveToDb = false) {
    const response = await api.post('/batch-trace-relation', {
      high_level_requirements: highLevelReqs,
      low_level_requirements: lowLevelReqs,
      save_to_db: saveToDb
    })
    return response.data
  },

  // 获取需求列表
  async getRequirements(page = 1, perPage = 10) {
    const response = await api.get('/requirements', {
      params: { page, per_page: perPage }
    })
    return response.data
  },

  // 获取需求详情
  async getRequirementDetail(id) {
    const response = await api.get(`/requirements/${id}`)
    return response.data
  },

  // 删除需求
  async deleteRequirement(id) {
    const response = await api.delete(`/requirements/${id}`)
    return response.data
  },

  // 获取统计数据
  async getStatistics() {
    const response = await api.get('/statistics')
    return response.data
  },

  // 获取模型状态
  async getModelStatus() {
    const response = await api.get('/model/status')
    return response.data
  },

  // 重新连接模型
  async reconnectModel() {
    const response = await api.post('/model/reconnect')
    return response.data
  }
}

export default api
