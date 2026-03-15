import { api } from './request'

export const asrApi = {
  async health() {
    const { data } = await api.get('/asr/health')
    return data
  },

  async createSession(file) {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post('/asr/sessions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async listSessions(params = {}) {
    const { data } = await api.get('/asr/sessions', { params })
    return data
  },

  async getSession(sessionId) {
    const { data } = await api.get(`/asr/sessions/${encodeURIComponent(sessionId)}`)
    return data
  },

  async retrySession(sessionId) {
    const { data } = await api.post(`/asr/sessions/${encodeURIComponent(sessionId)}/retry`)
    return data
  },

  exportUrl(sessionId, format = 'txt') {
    return `/api/v2/asr/sessions/${encodeURIComponent(sessionId)}/export?format=${encodeURIComponent(format)}`
  },
}

