import { api } from './request'

const buildAuthHeaders = () => {
  const headers = {
    'Content-Type': 'application/json'
  }

  const token = localStorage.getItem('token')
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const actor = localStorage.getItem('actor') || ''
  const role = localStorage.getItem('role') || ''
  if (actor) headers['X-Actor'] = actor
  if (role) headers['X-Role'] = role

  return headers
}

export const sessionControllerChatApi = {
  async getCapabilities() {
    const resp = await api.get('/session-controller/capabilities')
    return resp.data || {}
  },

  async listSessions(projectId, limit = 100) {
    const resp = await api.get('/session-controller/sessions', {
      params: {
        project_id: projectId || undefined,
        limit
      }
    })
    return resp.data?.sessions || []
  },

  async createOrGetSession(projectId) {
    const resp = await api.post('/session-controller/sessions', {
      project_id: projectId || null
    })
    return resp.data
  },

  async createSession(projectId, title) {
    const resp = await api.post('/session-controller/sessions/new', {
      project_id: projectId || null,
      title: title || null
    })
    return resp.data
  },

  async deleteSession(sessionId) {
    const resp = await api.delete(`/session-controller/sessions/${encodeURIComponent(sessionId)}`)
    return resp.data
  },

  async listMessages(sessionId, limit = 100) {
    const resp = await api.get(`/session-controller/sessions/${encodeURIComponent(sessionId)}/messages`, {
      params: { limit }
    })
    return resp.data?.messages || []
  },

  async getSessionGraphChain(sessionId) {
    const resp = await api.get(`/session-controller/sessions/${encodeURIComponent(sessionId)}/graph-chain`)
    return resp.data
  },

  async getGraphDetail(graphId) {
    const resp = await api.get(`/session-controller/graphs/${encodeURIComponent(graphId)}/detail`)
    return resp.data
  },

  async streamMessage({
    sessionId,
    projectId,
    message,
    executionMode,
    useThinkingMode = true,
    delegatedMaxToolCallRounds = 15
  }) {
    const payload = {
      project_id: projectId,
      message,
      use_thinking_mode: useThinkingMode,
      delegated_max_tool_call_rounds: delegatedMaxToolCallRounds,
    }
    if (executionMode) {
      payload.execution_mode = executionMode
    }

    const response = await fetch(`/api/v2/session-controller/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
      method: 'POST',
      headers: buildAuthHeaders(),
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      let detail = ''
      try {
        const errorPayload = await response.json()
        const responseDetail = errorPayload?.detail
        if (typeof responseDetail === 'string') {
          detail = responseDetail
        } else if (Array.isArray(responseDetail) && responseDetail.length) {
          detail = responseDetail.map((item) => item?.msg || JSON.stringify(item)).join('; ')
        }
      } catch (_err) {
        detail = ''
      }
      throw new Error(detail || `HTTP error! status: ${response.status}`)
    }

    return response.body
  }
}
