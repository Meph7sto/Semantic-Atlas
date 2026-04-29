/**
 * useSessionAssistant — 会话总控小助手核心逻辑
 *
 * 从 alpha SessionControllerAgentChat.vue 提取的纯状态/业务逻辑 composable。
 * 会话隔离由后端 token + user_id 自动保证，前端无需额外处理。
 *
 * 用法：
 *   const { projects, sessions, messages, sendMessage, ... } = useSessionAssistant()
 */

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { manageApi } from '@/api/project'
import { sessionControllerChatApi } from '@/api/sessionControllerChat'
import { createEmptyGraphDetail, buildMergedSessionGraphDetail } from '@/utils/sessionGraphLayout'

// ---- SSE 解析工具 ----

function parseEventBlock(block) {
  const lines = block.split('\n')
  let eventName = 'message'
  const dataLines = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (!dataLines.length) return null

  let payload = dataLines.join('\n')
  try {
    payload = JSON.parse(payload)
  } catch (_err) {
    // keep raw
  }

  return { eventName, payload }
}

// ---- Composable ----

export function useSessionAssistant() {
  // ---- 状态 ----
  const projects = ref([])
  const sessions = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const sessionId = ref('')
  const messages = ref([])
  const inputMessage = ref('')
  const selectedModel = ref('deepseek-v4-pro')
  const useThinkingMode = ref(true)
  const isSending = ref(false)
  const isLoadingProjects = ref(false)
  const isLoadingSessions = ref(false)
  const isCreatingSession = ref(false)
  const errorMessage = ref('')
  const activeGraphId = ref('')
  const sessionGraphChain = ref([])
  const graphDetail = ref(createEmptyGraphDetail())
  const stageTimeline = ref([])
  const selectedCanvasId = ref(null)
  const draftAssistantId = ref(null)
  const lastDispatchedAgents = ref([])
  const autoCreatingProjectIds = new Set()
  const isSyncingProjectFromEvent = ref(false)

  // ---- 派生状态 ----

  const currentSession = computed(() =>
    sessions.value.find((item) => item.session_id === sessionId.value) || null,
  )

  const latestGraphStatus = computed(() =>
    graphDetail.value.graph?.status || 'idle',
  )

  const sessionGraphSummaries = computed(() =>
    sessionGraphChain.value.map((detail, index) => {
      const graph = detail?.graph || {}
      return {
        graphId: graph.graph_id || '',
        index: index + 1,
        status: graph.status || 'idle',
        prevGraphId: graph.meta_json?.prev_graph_id || '',
        active: graph.graph_id === activeGraphId.value,
      }
    }),
  )

  // ---- 工具函数 ----

  const formatTime = (value) => {
    if (!value) return '刚刚创建'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const sessionTitle = (session, index = 0) =>
    session?.title || `会话 ${index + 1}`

  const generateSessionTitle = () => {
    const now = new Date()
    const stamp = now
      .toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
      .replace(/\//g, '-')
    return `会话总控 ${stamp}`
  }

  // ---- 内部辅助 ----

  const resetSessionView = () => {
    messages.value = []
    inputMessage.value = ''
    activeGraphId.value = ''
    sessionGraphChain.value = []
    graphDetail.value = createEmptyGraphDetail()
    stageTimeline.value = []
    selectedCanvasId.value = null
    draftAssistantId.value = null
    lastDispatchedAgents.value = []
  }

  const appendTimeline = (event, data) => {
    stageTimeline.value = [
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        event,
        data,
      },
      ...stageTimeline.value,
    ].slice(0, 50)
  }

  const upsertMessage = (message) => {
    if (!message?.message_id) return
    const index = messages.value.findIndex(
      (item) => item.message_id === message.message_id,
    )
    if (index >= 0) {
      messages.value = messages.value.map((item, i) =>
        i === index ? message : item,
      )
      return
    }
    messages.value = [...messages.value, message]
  }

  const upsertSessionPatch = (targetSessionId, patch) => {
    const index = sessions.value.findIndex(
      (item) => item.session_id === targetSessionId,
    )
    if (index < 0) return
    sessions.value = sessions.value.map((item, i) =>
      i === index ? { ...item, ...patch } : item,
    )
  }

  const ensureDraftAssistant = () => {
    if (draftAssistantId.value) {
      const existing = messages.value.find(
        (item) => item.message_id === draftAssistantId.value,
      )
      if (existing) return existing
    }
    const draft = {
      message_id: `draft-${Date.now()}`,
      role: 'assistant',
      content: '',
      metadata: { draft: true },
      created_at: new Date().toISOString(),
    }
    draftAssistantId.value = draft.message_id
    messages.value = [...messages.value, draft]
    return draft
  }

  // ---- 执行图链 ----

  const refreshSessionGraphChain = async (
    targetSessionId = sessionId.value,
  ) => {
    if (!targetSessionId) {
      sessionGraphChain.value = []
      graphDetail.value = createEmptyGraphDetail()
      selectedCanvasId.value = null
      return
    }
    try {
      const chainPayload =
        await sessionControllerChatApi.getSessionGraphChain(targetSessionId)
      sessionGraphChain.value = chainPayload?.graphs || []
      activeGraphId.value =
        chainPayload?.active_graph_id || activeGraphId.value || ''
      graphDetail.value = buildMergedSessionGraphDetail(chainPayload)
    } catch (err) {
      console.error('加载会话执行图链失败', err)
      sessionGraphChain.value = []
      graphDetail.value = createEmptyGraphDetail()
    }
  }

  // ---- 数据加载 ----

  const loadProjects = async () => {
    isLoadingProjects.value = true
    errorMessage.value = ''
    try {
      const data = await manageApi.listProjects()
      projects.value = data.projects || []
      if (!projects.value.length) {
        selectedProjectId.value = ''
        return
      }

      const hasSelectedProject = projects.value.some(
        (project) => project.project_id === selectedProjectId.value,
      )
      if (!hasSelectedProject) {
        selectedProjectId.value = projects.value[0].project_id
      }
    } catch (err) {
      errorMessage.value = err?.message || '加载项目失败'
    } finally {
      isLoadingProjects.value = false
    }
  }

  const loadSessionContent = async (session) => {
    if (!session?.session_id) {
      sessionId.value = ''
      resetSessionView()
      return
    }

    sessionId.value = session.session_id
    errorMessage.value = ''
    resetSessionView()

    try {
      messages.value = await sessionControllerChatApi.listMessages(
        session.session_id,
      )
      activeGraphId.value = session.active_graph_id || ''
      await refreshSessionGraphChain(session.session_id)
    } catch (err) {
      errorMessage.value = err?.message || '加载会话失败'
    }
  }

  const loadSessions = async ({
    preferredSessionId = sessionId.value,
  } = {}) => {
    if (!selectedProjectId.value) {
      sessions.value = []
      sessionId.value = ''
      resetSessionView()
      return
    }

    isLoadingSessions.value = true
    try {
      const data = await sessionControllerChatApi.listSessions(
        selectedProjectId.value,
      )
      sessions.value = data || []

      if (!sessions.value.length) {
        sessionId.value = ''
        resetSessionView()
        await ensureSessionForProject(selectedProjectId.value)
        return
      }

      const nextSession =
        sessions.value.find(
          (item) => item.session_id === preferredSessionId,
        ) || sessions.value[0]
      if (
        nextSession?.session_id !== sessionId.value ||
        activeGraphId.value !== (nextSession?.active_graph_id || '')
      ) {
        await loadSessionContent(nextSession)
      }
    } catch (err) {
      errorMessage.value = err?.message || '加载会话列表失败'
    } finally {
      isLoadingSessions.value = false
    }
  }

  const refreshWorkspace = async () => {
    await loadProjects()
    if (!selectedProjectId.value) return
    await loadSessions({ preferredSessionId: sessionId.value })
  }

  // ---- 会话 CRUD ----

  const createSessionForProject = async (projectId, title = null) => {
    if (!projectId) return null
    isCreatingSession.value = true
    errorMessage.value = ''
    try {
      const session = await sessionControllerChatApi.createSession(
        projectId,
        title || generateSessionTitle(),
      )
      sessions.value = [
        session,
        ...sessions.value.filter(
          (item) => item.session_id !== session.session_id,
        ),
      ]
      await loadSessionContent(session)
      return session
    } catch (err) {
      errorMessage.value = err?.message || '新建会话失败'
      return null
    } finally {
      isCreatingSession.value = false
    }
  }

  const ensureSessionForProject = async (projectId) => {
    if (!projectId || autoCreatingProjectIds.has(projectId)) return null
    autoCreatingProjectIds.add(projectId)
    try {
      return await createSessionForProject(projectId)
    } finally {
      autoCreatingProjectIds.delete(projectId)
    }
  }

  const createSession = async () =>
    createSessionForProject(selectedProjectId.value)

  const handleSelectSession = async (session) => {
    if (!session?.session_id) return
    await loadSessionContent(session)
  }

  const handleDeleteSession = async (session) => {
    if (!session?.session_id || isSending.value) return
    const confirmed = window.confirm(
      `删除会话"${sessionTitle(session)}"？对应执行图也会一起删除。`,
    )
    if (!confirmed) return

    errorMessage.value = ''
    try {
      await sessionControllerChatApi.deleteSession(session.session_id)
      const remaining = sessions.value.filter(
        (item) => item.session_id !== session.session_id,
      )
      sessions.value = remaining

      if (sessionId.value === session.session_id) {
        if (remaining.length > 0) {
          await loadSessionContent(remaining[0])
        } else {
          sessionId.value = ''
          resetSessionView()
        }
      }
    } catch (err) {
      errorMessage.value = err?.message || '删除会话失败'
    }
  }

  // ---- SSE 流式处理 ----

  const consumeSSEStream = async (stream) => {
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        const parsed = parseEventBlock(chunk.trim())
        if (!parsed) continue
        const { eventName, payload } = parsed
        appendTimeline(eventName, payload)

        if (eventName === 'user_message') {
          upsertMessage(payload)
        } else if (eventName === 'graph') {
          activeGraphId.value = payload.graph_id || ''
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id || '',
            updated_at: new Date().toISOString(),
          })
          await refreshSessionGraphChain(sessionId.value)
        } else if (eventName === 'token') {
          const draft = ensureDraftAssistant()
          draft.content += payload.content || ''
        } else if (eventName === 'assistant_message') {
          if (draftAssistantId.value) {
            messages.value = messages.value.filter(
              (item) => item.message_id !== draftAssistantId.value,
            )
            draftAssistantId.value = null
          }
          upsertMessage(payload)
        } else if (eventName === 'result') {
          if (payload.dispatched_agents) {
            lastDispatchedAgents.value = payload.dispatched_agents
          }
          if (payload.graph_id) {
            activeGraphId.value = payload.graph_id
            upsertSessionPatch(sessionId.value, {
              active_graph_id: payload.graph_id,
              updated_at: new Date().toISOString(),
            })
            await refreshSessionGraphChain(sessionId.value)
          }
        } else if (
          eventName === 'stage' ||
          eventName === 'tool_call' ||
          eventName === 'tool_result'
        ) {
          if (payload.graph_id) {
            activeGraphId.value = payload.graph_id
            upsertSessionPatch(sessionId.value, {
              active_graph_id: payload.graph_id,
              updated_at: new Date().toISOString(),
            })
            await refreshSessionGraphChain(sessionId.value)
          }
        } else if (eventName === 'error') {
          errorMessage.value = payload.error || '处理失败'
          if (payload.graph_id) {
            activeGraphId.value = payload.graph_id
            upsertSessionPatch(sessionId.value, {
              active_graph_id: payload.graph_id,
              updated_at: new Date().toISOString(),
            })
            await refreshSessionGraphChain(sessionId.value)
          }
        }
      }
    }
  }

  const sendMessage = async () => {
    if (
      !inputMessage.value.trim() ||
      !selectedProjectId.value ||
      !sessionId.value
    )
      return

    isSending.value = true
    errorMessage.value = ''
    stageTimeline.value = []
    lastDispatchedAgents.value = []
    if (draftAssistantId.value) {
      messages.value = messages.value.filter(
        (item) => item.message_id !== draftAssistantId.value,
      )
      draftAssistantId.value = null
    }

    try {
      const message = inputMessage.value.trim()
      const stream = await sessionControllerChatApi.streamMessage({
        sessionId: sessionId.value,
        projectId: selectedProjectId.value,
        message,
        model: selectedModel.value,
        useThinkingMode: useThinkingMode.value,
      })
      inputMessage.value = ''
      appendTimeline('submit', { message })
      upsertSessionPatch(sessionId.value, {
        updated_at: new Date().toISOString(),
      })
      await consumeSSEStream(stream)
      await loadSessions({ preferredSessionId: sessionId.value })
    } catch (err) {
      errorMessage.value = err?.message || '发送消息失败'
    } finally {
      isSending.value = false
    }
  }

  // ---- 生命周期 ----

  const syncProjectFromStorage = () => {
    const nextProjectId = localStorage.getItem('lastProjectId') || ''
    if (nextProjectId === selectedProjectId.value) return
    isSyncingProjectFromEvent.value = true
    selectedProjectId.value = nextProjectId
  }

  const handleProjectChanged = (event) => {
    const nextProjectId = String(
      event?.detail?.projectId ?? localStorage.getItem('lastProjectId') ?? '',
    ).trim()
    if (nextProjectId === selectedProjectId.value) return
    isSyncingProjectFromEvent.value = true
    selectedProjectId.value = nextProjectId
  }

  watch(selectedProjectId, async (projectId) => {
    const shouldBroadcast = !isSyncingProjectFromEvent.value
    isSyncingProjectFromEvent.value = false

    if (projectId) {
      localStorage.setItem('lastProjectId', projectId)
    } else {
      localStorage.removeItem('lastProjectId')
    }

    if (shouldBroadcast) {
      window.dispatchEvent(
        new CustomEvent('project-changed', { detail: { projectId } }),
      )
    }

    sessionId.value = ''
    sessions.value = []
    resetSessionView()
    if (!projectId) return
    await loadSessions()
  })

  onMounted(async () => {
    syncProjectFromStorage()
    window.addEventListener('project-changed', handleProjectChanged)
    await loadProjects()
    if (selectedProjectId.value && !sessionId.value && !isLoadingSessions.value) {
      await loadSessions()
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('project-changed', handleProjectChanged)
  })

  // ---- 返回 ----

  return {
    // 状态
    projects,
    sessions,
    selectedProjectId,
    sessionId,
    messages,
    inputMessage,
    selectedModel,
    useThinkingMode,
    isSending,
    isLoadingProjects,
    isLoadingSessions,
    isCreatingSession,
    errorMessage,
    activeGraphId,
    sessionGraphChain,
    graphDetail,
    stageTimeline,
    selectedCanvasId,
    lastDispatchedAgents,

    // 派生
    currentSession,
    latestGraphStatus,
    sessionGraphSummaries,

    // 工具
    formatTime,
    sessionTitle,

    // 操作
    loadProjects,
    loadSessions,
    refreshWorkspace,
    createSession,
    handleSelectSession,
    handleDeleteSession,
    sendMessage,
    refreshSessionGraphChain,
  }
}
