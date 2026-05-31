import {
  api,
  extractErrorMessageFromPayload,
  handleUnauthorized,
  readErrorPayload,
} from './request'

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

export const agentChatApi = {
  async listSessions(projectId, limit = 100) {
    const resp = await api.get('/agent-chat/sessions', {
      params: {
        project_id: projectId || undefined,
        limit
      }
    })
    return resp.data?.sessions || []
  },

  async createOrGetSession(projectId) {
    const resp = await api.post('/agent-chat/sessions', {
      project_id: projectId || null
    })
    return resp.data
  },

  async createSession(projectId, title) {
    const resp = await api.post('/agent-chat/sessions/new', {
      project_id: projectId || null,
      title: title || null
    })
    return resp.data
  },

  async deleteSession(sessionId) {
    const resp = await api.delete(`/agent-chat/sessions/${encodeURIComponent(sessionId)}`)
    return resp.data
  },

  async listMessages(sessionId, limit = 100) {
    const resp = await api.get(`/agent-chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
      params: { limit }
    })
    return resp.data?.messages || []
  },

  async getSessionGraphChain(sessionId) {
    const resp = await api.get(`/agent-chat/sessions/${encodeURIComponent(sessionId)}/graph-chain`)
    return resp.data
  },

  async getGraphDetail(graphId) {
    const resp = await api.get(`/agent-chat/graphs/${encodeURIComponent(graphId)}/detail`)
    return resp.data
  },

  async streamMessage({
    sessionId,
    projectId,
    requirementId,
    message,
    model = 'deepseek-v4-pro',
    useThinkingMode = true
  }) {
    const response = await fetch(`/api/v2/agent-chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
      method: 'POST',
      headers: buildAuthHeaders(),
      body: JSON.stringify({
        project_id: projectId,
        requirement_id: requirementId || null,
        message,
        model,
        use_thinking_mode: useThinkingMode,
        execution_mode: 'graph'
      })
    })

    if (!response.ok) {
      const errorPayload = await readErrorPayload(response)

      if (response.status === 401) {
        handleUnauthorized()
      }

      throw new Error(
        extractErrorMessageFromPayload(errorPayload) ||
          `HTTP error! status: ${response.status}`,
      )
    }

    return response.body
  }
}
