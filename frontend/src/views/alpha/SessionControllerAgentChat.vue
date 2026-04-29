<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Bot,
  Download,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Workflow,
  X
} from 'lucide-vue-next'

import { manageApi } from '@/api/project'
import { sessionControllerChatApi } from '@/api/sessionControllerChat'
import ExperienceSkillPanel from '@/components/alpha/ExperienceSkillPanel.vue'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'
import NodeDetailPanel from '@/components/alpha/NodeDetailPanel.vue'
import SubgraphTracePanel from '@/components/alpha/SubgraphTracePanel.vue'
import { createEmptyGraphDetail, buildMergedSessionGraphDetail } from '@/utils/sessionGraphLayout'
import { buildExecutionGraphExportPayload, downloadExecutionGraphFile } from '@/utils/executionGraphExport'

const GRAPH_EXECUTION_MODE = 'graph'
const SESSION_GRAPH_LAYOUT_OPTIONS = {
  filterDelegatedContainers: true,
  hideSubgraphBoundaryNodes: true,
  stackGraphsByRow: true,
  alignLaneStarts: true
}

const projects = ref([])
const sessions = ref([])
const selectedProjectId = ref('')
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
const isAssistantOpen = ref(false)
const lastDispatchedAgents = ref([])
const detailPanelRef = ref(null)
const delegatedMaxToolCallRounds = ref(15)

const GRAPH_CHAIN_REFRESH_DEBOUNCE_MS = 180
const DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS = 15
const MIN_DELEGATED_MAX_TOOL_CALL_ROUNDS = 1
const MAX_DELEGATED_MAX_TOOL_CALL_ROUNDS = 50

let graphChainRefreshTimer = null
let graphChainRefreshPendingSessionId = ''
let graphChainRefreshInFlight = null

const currentSession = computed(() => {
  return sessions.value.find((item) => item.session_id === sessionId.value) || null
})

const activeGraphDetail = computed(() => {
  if (!sessionGraphChain.value.length) return null
  return sessionGraphChain.value.find((detail) => detail?.graph?.graph_id === activeGraphId.value)
    || sessionGraphChain.value[sessionGraphChain.value.length - 1]
    || null
})

const activeRuntimeGraph = computed(() => activeGraphDetail.value?.graph || null)

const selectedNode = computed(() => {
  return graphDetail.value.nodes.find((node) => node.node_id === selectedCanvasId.value) || null
})

const selectedEdge = computed(() => {
  return graphDetail.value.edges.find((edge) => edge.edge_id === selectedCanvasId.value) || null
})

const latestGraphStatus = computed(() => graphDetail.value.graph?.status || 'idle')

const detailPanelTitle = computed(() => {
  if (selectedNode.value) {
    return `节点详情: ${selectedNode.value.label || selectedNode.value.node_key || selectedNode.value.node_id}`
  }
  if (selectedEdge.value) {
    return `连线详情: ${selectedEdge.value.label || selectedEdge.value.edge_id}`
  }
  return '节点详情'
})

const sessionGraphSummaries = computed(() => {
  return sessionGraphChain.value.map((detail, index) => {
    const graph = detail?.graph || {}
    return {
      graphId: graph.graph_id || '',
      index: index + 1,
      status: graph.status || 'idle',
      prevGraphId: graph.meta_json?.prev_graph_id || '',
      active: graph.graph_id === activeGraphId.value
    }
  })
})

const flattenedToolResults = computed(() => {
  return graphDetail.value.nodes.flatMap((node) => {
    const toolCallResults = node.config_json?.tool_call_results || []
    return toolCallResults.map((entry) => ({
      nodeKey: node.node_key,
      ...entry
    }))
  })
})

const formatJson = (value) => {
  if (!value) return '暂无'
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
}

const formatTime = (value) => {
  if (!value) return '刚刚创建'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const sessionTitle = (session, index = 0) => {
  return session?.title || `会话 ${index + 1}`
}

const generateSessionTitle = () => {
  const now = new Date()
  const stamp = now.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).replace(/\//g, '-')
  return `会话总控 ${stamp}`
}

const normalizeDelegatedMaxToolCallRounds = () => {
  const parsed = Number.parseInt(String(delegatedMaxToolCallRounds.value ?? ''), 10)
  if (Number.isNaN(parsed)) {
    delegatedMaxToolCallRounds.value = DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS
    return delegatedMaxToolCallRounds.value
  }
  delegatedMaxToolCallRounds.value = Math.min(
    MAX_DELEGATED_MAX_TOOL_CALL_ROUNDS,
    Math.max(MIN_DELEGATED_MAX_TOOL_CALL_ROUNDS, parsed)
  )
  return delegatedMaxToolCallRounds.value
}

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
  stageTimeline.value.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    event,
    data
  })
  if (stageTimeline.value.length > 50) {
    stageTimeline.value = stageTimeline.value.slice(0, 50)
  }
}

const upsertMessage = (message) => {
  if (!message?.message_id) return
  const index = messages.value.findIndex((item) => item.message_id === message.message_id)
  if (index >= 0) {
    messages.value[index] = message
    return
  }
  messages.value.push(message)
}

const upsertSessionPatch = (targetSessionId, patch) => {
  const index = sessions.value.findIndex((item) => item.session_id === targetSessionId)
  if (index < 0) return
  sessions.value[index] = {
    ...sessions.value[index],
    ...patch
  }
}

const ensureDraftAssistant = () => {
  if (draftAssistantId.value) {
    const existing = messages.value.find((item) => item.message_id === draftAssistantId.value)
    if (existing) return existing
  }
  const draft = {
    message_id: `draft-${Date.now()}`,
    role: 'assistant',
    content: '',
    metadata: { draft: true },
    created_at: new Date().toISOString()
  }
  draftAssistantId.value = draft.message_id
  messages.value.push(draft)
  return draft
}

const rebuildMergedGraphDetail = () => {
  graphDetail.value = buildMergedSessionGraphDetail({
    session_id: sessionId.value,
    active_graph_id: activeGraphId.value,
    graphs: sessionGraphChain.value
  }, SESSION_GRAPH_LAYOUT_OPTIONS)
}

const upsertById = (items, idKey, nextItem) => {
  if (!nextItem?.[idKey]) return items
  const index = items.findIndex((item) => item?.[idKey] === nextItem[idKey])
  if (index >= 0) {
    const nextItems = [...items]
    nextItems[index] = {
      ...nextItems[index],
      ...nextItem
    }
    return nextItems
  }
  return [...items, nextItem]
}

const applyGraphIncrementalPayload = (payload, graphStatus = null) => {
  const targetGraphId = payload?.graph_id
  if (!targetGraphId) return false

  const index = sessionGraphChain.value.findIndex((detail) => detail?.graph?.graph_id === targetGraphId)
  if (index < 0) return false

  const currentDetail = sessionGraphChain.value[index] || {}
  const nextDetail = {
    ...currentDetail,
    graph: currentDetail.graph ? { ...currentDetail.graph } : null,
    containers: [...(currentDetail.containers || [])],
    subgraphs: [...(currentDetail.subgraphs || [])],
    nodes: [...(currentDetail.nodes || [])],
    edges: [...(currentDetail.edges || [])]
  }

  if (nextDetail.graph) {
    nextDetail.graph = {
      ...nextDetail.graph,
      status: graphStatus || nextDetail.graph.status,
      meta_json: {
        ...(nextDetail.graph.meta_json || {}),
        current_node_key: payload.node_key || nextDetail.graph.meta_json?.current_node_key || null
      }
    }
  }

  if (payload.node) {
    nextDetail.nodes = upsertById(nextDetail.nodes, 'node_id', payload.node)
    nextDetail.nodes.sort((a, b) => {
      const orderDiff = Number(a?.order_index || 0) - Number(b?.order_index || 0)
      if (orderDiff !== 0) return orderDiff
      return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
    })
  }

  if (Array.isArray(payload.edges)) {
    payload.edges.forEach((edge) => {
      nextDetail.edges = upsertById(nextDetail.edges, 'edge_id', edge)
    })
    nextDetail.edges.sort((a, b) => {
      const orderDiff = Number(a?.order_index || 0) - Number(b?.order_index || 0)
      if (orderDiff !== 0) return orderDiff
      return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
    })
  }

  const nextChain = [...sessionGraphChain.value]
  nextChain[index] = nextDetail
  sessionGraphChain.value = nextChain
  rebuildMergedGraphDetail()
  return true
}

const patchSessionGraphMeta = (graphId, metaPatch) => {
  if (!graphId || !metaPatch || typeof metaPatch !== 'object') return false

  const index = sessionGraphChain.value.findIndex((detail) => detail?.graph?.graph_id === graphId)
  if (index < 0) return false

  const currentDetail = sessionGraphChain.value[index] || {}
  const nextDetail = {
    ...currentDetail,
    graph: currentDetail.graph
      ? {
          ...currentDetail.graph,
          meta_json: {
            ...(currentDetail.graph.meta_json || {}),
            ...metaPatch
          }
        }
      : currentDetail.graph
  }

  const nextChain = [...sessionGraphChain.value]
  nextChain[index] = nextDetail
  sessionGraphChain.value = nextChain
  rebuildMergedGraphDetail()
  return true
}

const inferDelegatedAgentsFromEvent = (eventName, payload) => {
  if (eventName === 'intent_judge_completed') {
    return Array.isArray(payload?.selected_container_keys) ? payload.selected_container_keys : []
  }

  if (eventName === 'result') {
    if (Array.isArray(payload?.dispatched_agents) && payload.dispatched_agents.length) {
      return payload.dispatched_agents
    }
    if (payload?.mode === 'delegate_requirement') return ['requirement_agent']
    if (payload?.mode === 'delegate_conflict') return ['conflict_detection']
    if (payload?.mode === 'delegate_classification') return ['requirement_classification_agent']
    return []
  }

  if (eventName !== 'tool_call' && eventName !== 'tool_result') {
    return []
  }

  if (payload?.tool === 'invoke_requirement_agent') return ['requirement_agent']
  if (payload?.tool === 'invoke_conflict_detection') return ['conflict_detection']
  if (payload?.tool === 'invoke_requirement_classification_agent') return ['requirement_classification_agent']
  return []
}

const refreshSessionGraphChain = async (targetSessionId = sessionId.value) => {
  if (!targetSessionId) {
    sessionGraphChain.value = []
    graphDetail.value = createEmptyGraphDetail()
    selectedCanvasId.value = null
    return
  }
  try {
    const chainPayload = await sessionControllerChatApi.getSessionGraphChain(targetSessionId)
    if (targetSessionId !== sessionId.value) {
      return chainPayload
    }
    sessionGraphChain.value = chainPayload?.graphs || []
    activeGraphId.value = chainPayload?.active_graph_id || activeGraphId.value || ''
    graphDetail.value = buildMergedSessionGraphDetail(chainPayload, SESSION_GRAPH_LAYOUT_OPTIONS)
    return chainPayload
  } catch (err) {
    console.error('加载会话执行图链失败', err)
    if (targetSessionId !== sessionId.value) {
      return null
    }
    if (!sessionGraphChain.value.length) {
      sessionGraphChain.value = []
      graphDetail.value = createEmptyGraphDetail()
    }
    return null
  }
}

const clearScheduledGraphChainRefresh = () => {
  if (graphChainRefreshTimer) {
    clearTimeout(graphChainRefreshTimer)
    graphChainRefreshTimer = null
  }
}

const runQueuedGraphChainRefresh = async () => {
  if (graphChainRefreshInFlight) {
    await graphChainRefreshInFlight
    if (!graphChainRefreshPendingSessionId) return
  }

  const targetSessionId = graphChainRefreshPendingSessionId || sessionId.value
  graphChainRefreshPendingSessionId = ''
  if (!targetSessionId) return

  const refreshPromise = refreshSessionGraphChain(targetSessionId)
  graphChainRefreshInFlight = refreshPromise

  try {
    await refreshPromise
  } finally {
    if (graphChainRefreshInFlight === refreshPromise) {
      graphChainRefreshInFlight = null
    }
  }

  if (graphChainRefreshPendingSessionId) {
    await runQueuedGraphChainRefresh()
  }
}

const queueGraphChainRefresh = (targetSessionId = sessionId.value, { immediate = false } = {}) => {
  if (!targetSessionId) return

  graphChainRefreshPendingSessionId = targetSessionId
  clearScheduledGraphChainRefresh()

  if (immediate) {
    void runQueuedGraphChainRefresh()
    return
  }

  graphChainRefreshTimer = setTimeout(() => {
    graphChainRefreshTimer = null
    void runQueuedGraphChainRefresh()
  }, GRAPH_CHAIN_REFRESH_DEBOUNCE_MS)
}

const flushGraphChainRefresh = async (targetSessionId = sessionId.value) => {
  if (!targetSessionId) return

  graphChainRefreshPendingSessionId = targetSessionId
  clearScheduledGraphChainRefresh()
  await runQueuedGraphChainRefresh()
}

const loadProjects = async () => {
  isLoadingProjects.value = true
  errorMessage.value = ''
  try {
    const data = await manageApi.listProjects()
    projects.value = data.projects || []
    if (!selectedProjectId.value && projects.value.length > 0) {
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
    messages.value = await sessionControllerChatApi.listMessages(session.session_id)
    activeGraphId.value = session.active_graph_id || ''
    await refreshSessionGraphChain(session.session_id)
  } catch (err) {
    errorMessage.value = err?.message || '加载会话失败'
  }
}

const loadSessions = async ({ preferredSessionId = sessionId.value } = {}) => {
  if (!selectedProjectId.value) {
    sessions.value = []
    sessionId.value = ''
    resetSessionView()
    return
  }

  isLoadingSessions.value = true
  try {
    const data = await sessionControllerChatApi.listSessions(selectedProjectId.value)
    sessions.value = data || []

    if (!sessions.value.length) {
      sessionId.value = ''
      resetSessionView()
      return
    }

    const nextSession = sessions.value.find((item) => item.session_id === preferredSessionId) || sessions.value[0]
    if (nextSession?.session_id !== sessionId.value || activeGraphId.value !== (nextSession?.active_graph_id || '')) {
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

const createSession = async () => {
  if (!selectedProjectId.value) return
  isCreatingSession.value = true
  errorMessage.value = ''
  try {
    const session = await sessionControllerChatApi.createSession(selectedProjectId.value, generateSessionTitle())
    sessions.value = [session, ...sessions.value.filter((item) => item.session_id !== session.session_id)]
    await loadSessionContent(session)
  } catch (err) {
    errorMessage.value = err?.message || '新建会话失败'
  } finally {
    isCreatingSession.value = false
  }
}

const handleSelectSession = async (session) => {
  if (!session?.session_id) return
  await loadSessionContent(session)
}

const handleDeleteSession = async (session) => {
  if (!session?.session_id || isSending.value) return
  const confirmed = window.confirm(`删除会话"${sessionTitle(session)}"？对应执行图也会一起删除。`)
  if (!confirmed) return

  errorMessage.value = ''
  try {
    await sessionControllerChatApi.deleteSession(session.session_id)
    const remaining = sessions.value.filter((item) => item.session_id !== session.session_id)
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

const parseEventBlock = (block) => {
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
          updated_at: new Date().toISOString()
        })
        queueGraphChainRefresh(sessionId.value, { immediate: true })
      } else if (eventName === 'token') {
        const draft = ensureDraftAssistant()
        draft.content += payload.content || ''
      } else if (eventName === 'assistant_message') {
        if (draftAssistantId.value) {
          messages.value = messages.value.filter((item) => item.message_id !== draftAssistantId.value)
          draftAssistantId.value = null
        }
        upsertMessage(payload)
      } else if (eventName === 'result') {
        if (payload.dispatched_agents) {
          lastDispatchedAgents.value = payload.dispatched_agents
        }
        if (payload.graph_id) {
          const delegatedAgents = inferDelegatedAgentsFromEvent(eventName, payload)
          if (delegatedAgents.length) {
            patchSessionGraphMeta(payload.graph_id, {
              dispatched_agents: delegatedAgents,
              selected_container_keys: delegatedAgents
            })
          }
        }
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          applyGraphIncrementalPayload(payload, 'succeeded')
          await flushGraphChainRefresh(sessionId.value)
        }
      } else if (eventName === 'intent_judge_completed') {
        const delegatedAgents = inferDelegatedAgentsFromEvent(eventName, payload)
        if (payload.graph_id && delegatedAgents.length) {
          patchSessionGraphMeta(payload.graph_id, {
            selected_container_keys: delegatedAgents
          })
        }
      } else if (eventName === 'stage' || eventName === 'tool_call' || eventName === 'tool_result') {
        const delegatedAgents = inferDelegatedAgentsFromEvent(eventName, payload)
        if (payload.graph_id && delegatedAgents.length) {
          patchSessionGraphMeta(payload.graph_id, {
            selected_container_keys: delegatedAgents,
            dispatched_agents: delegatedAgents
          })
          lastDispatchedAgents.value = delegatedAgents
        }
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          const graphStatus = eventName === 'stage' && payload.status === 'failed' ? 'failed' : 'running'
          const patched = applyGraphIncrementalPayload(payload, graphStatus)
          if (!patched) {
            queueGraphChainRefresh(sessionId.value, { immediate: true })
          } else {
            queueGraphChainRefresh(sessionId.value)
          }
        }
      } else if (eventName === 'error') {
        errorMessage.value = payload.error || '处理失败'
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          applyGraphIncrementalPayload(payload, 'failed')
          await flushGraphChainRefresh(sessionId.value)
        }
      }
    }
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || !selectedProjectId.value || !sessionId.value) return

  isSending.value = true
  errorMessage.value = ''
  stageTimeline.value = []
  lastDispatchedAgents.value = []
  if (draftAssistantId.value) {
    messages.value = messages.value.filter((item) => item.message_id !== draftAssistantId.value)
    draftAssistantId.value = null
  }

  try {
    const message = inputMessage.value.trim()
    const effectiveDelegatedMaxToolCallRounds = normalizeDelegatedMaxToolCallRounds()
    clearScheduledGraphChainRefresh()
    const stream = await sessionControllerChatApi.streamMessage({
      sessionId: sessionId.value,
      projectId: selectedProjectId.value,
      message,
      model: selectedModel.value,
      useThinkingMode: useThinkingMode.value,
      delegatedMaxToolCallRounds: effectiveDelegatedMaxToolCallRounds
    })
    inputMessage.value = ''
    appendTimeline('submit', {
      message,
      execution_mode: GRAPH_EXECUTION_MODE,
      delegated_max_tool_call_rounds: effectiveDelegatedMaxToolCallRounds
    })
    upsertSessionPatch(sessionId.value, { updated_at: new Date().toISOString() })
    await consumeSSEStream(stream)
    await loadSessions({ preferredSessionId: sessionId.value })
  } catch (err) {
    errorMessage.value = err?.message || '发送消息失败'
  } finally {
    isSending.value = false
  }
}

const handleExportExecutionGraph = () => {
  if (!graphDetail.value?.nodes?.length) return
  try {
    const payload = buildExecutionGraphExportPayload(graphDetail.value)
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')
    downloadExecutionGraphFile(payload, `session-controller-graph_${timestamp}.json`)
  } catch (err) {
    errorMessage.value = '导出执行图失败: ' + (err.message || '未知错误')
  }
}

const scrollToDetailPanel = async () => {
  await nextTick()
  detailPanelRef.value?.scrollIntoView({
    behavior: 'smooth',
    block: 'start'
  })
}

const handleCanvasSelectNode = async (nodeId) => {
  selectedCanvasId.value = nodeId
  await scrollToDetailPanel()
}

const handleCanvasSelectEdge = async (edgeId) => {
  selectedCanvasId.value = edgeId
  await scrollToDetailPanel()
}

watch(selectedProjectId, async (projectId) => {
  sessionId.value = ''
  sessions.value = []
  resetSessionView()
  if (!projectId) return
  await loadSessions()
})

onMounted(async () => {
  await loadProjects()
})

onBeforeUnmount(() => {
  clearScheduledGraphChainRefresh()
})
</script>

<template>
  <div class="h-full overflow-y-auto bg-[linear-gradient(180deg,#f7f4ec_0%,#f5f7fb_60%,#ffffff_100%)]">

    <!-- 悬浮球按钮 -->
    <button
      v-if="!isAssistantOpen"
      @click="isAssistantOpen = true"
      class="fixed bottom-8 right-8 z-40 flex h-16 w-16 items-center justify-center bg-stone-900 text-white shadow-[0_12px_32px_rgba(15,23,42,0.24)] transition-transform hover:scale-105"
    >
      <Bot class="h-7 w-7" />
    </button>

    <!-- 悬浮对话面板 -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="translate-y-10 scale-95 opacity-0"
      enter-to-class="translate-y-0 scale-100 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="translate-y-0 scale-100 opacity-100"
      leave-to-class="translate-y-10 scale-95 opacity-0"
    >
      <section
        v-if="isAssistantOpen"
        class="fixed bottom-8 right-8 z-50 flex w-[500px] max-w-[calc(100vw-2rem)] h-[85vh] max-h-[900px] shrink-0 flex-col overflow-hidden border border-stone-200 bg-white/95 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur-xl"
      >
        <header class="border-b border-stone-200 bg-stone-50/80 px-5 py-4 shrink-0">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Bot class="h-5 w-5 text-stone-700" />
              <h1 class="text-base font-semibold text-stone-900">会话总控 Agent</h1>
            </div>
            <div class="flex items-center gap-1">
              <button
                class="p-2 text-stone-500 hover:bg-stone-200 transition"
                @click="refreshWorkspace"
                title="刷新"
              >
                <RefreshCw class="h-4 w-4" :class="isLoadingProjects || isLoadingSessions ? 'animate-spin' : ''" />
              </button>
              <button
                class="p-2 text-stone-500 hover:bg-stone-200 transition"
                @click="isAssistantOpen = false"
                title="收起助手"
              >
                <X class="h-4 w-4" />
              </button>
            </div>
          </div>

          <div class="mt-4 space-y-3">
            <div class="flex items-center gap-2">
              <select
                v-model="selectedProjectId"
                class="flex-1 border border-stone-300 bg-white px-3 py-2 text-sm text-stone-800 outline-none transition focus:border-stone-500"
              >
                <option value="">选择项目 ({{ projects.length }})</option>
                <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
                  {{ project.name }}
                </option>
              </select>
              <button
                class="inline-flex shrink-0 items-center justify-center gap-1 bg-stone-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-stone-700 disabled:opacity-50"
                :disabled="!selectedProjectId || isCreatingSession"
                @click="createSession"
              >
                <Plus class="h-4 w-4" />
                新建会话
              </button>
            </div>

            <div class="flex gap-2">
              <select
                v-model="sessionId"
                class="flex-1 border border-stone-300 bg-white px-3 py-2 text-sm text-stone-800 outline-none transition focus:border-stone-500"
                @change="(e) => handleSelectSession(sessions.find(s => s.session_id === e.target.value))"
              >
                <option value="">未选择会话</option>
                <option v-for="(session, index) in sessions" :key="session.session_id" :value="session.session_id">
                  {{ sessionTitle(session, index) }} ({{ session.message_count || 0 }}条)
                </option>
              </select>
            </div>

            <!-- 已调度的子Agent -->
            <div v-if="lastDispatchedAgents.length" class="flex flex-wrap gap-1.5">
              <span class="text-[11px] text-stone-400 self-center">已调度：</span>
              <span
                v-for="agent in lastDispatchedAgents"
                :key="agent"
                class="inline-flex items-center px-2 py-0.5 text-[11px] bg-stone-900 text-white"
              >
                {{ agent }}
              </span>
            </div>
          </div>

        <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
            <span class="flex items-center gap-1 bg-stone-900 px-1.5 py-0.5 text-white" title="会话总控固定使用 GraphExecutor 主链路">
              Pipeline: <span class="font-medium">GraphExecutor</span>
            </span>
            <span v-if="sessionId" class="flex items-center gap-1 bg-stone-200/50 px-1.5 py-0.5">
              Current: <span class="font-medium text-stone-700">{{ activeGraphId || '无' }}</span>
            </span>
            <span v-if="sessionId" class="flex items-center gap-1 bg-stone-200/50 px-1.5 py-0.5">
              Graphs: <span class="font-medium text-stone-700">{{ sessionGraphSummaries.length }}</span>
            </span>
            <span v-if="sessionId" class="flex items-center gap-1 bg-stone-200/50 px-1.5 py-0.5">
              Status: <span class="font-medium text-stone-700">{{ latestGraphStatus }}</span>
            </span>
          </div>
          <div v-if="sessionId && sessionGraphSummaries.length" class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="graph in sessionGraphSummaries"
              :key="graph.graphId"
              class="inline-flex items-center gap-1 border px-2 py-1 text-[11px]"
              :class="graph.active ? 'border-stone-900 bg-stone-900 text-white' : 'border-stone-300 bg-white text-stone-700'"
            >
              <span>第{{ graph.index }}轮</span>
              <span>{{ graph.status }}</span>
              <span v-if="graph.prevGraphId" class="opacity-70">← {{ graph.prevGraphId }}</span>
            </span>
          </div>
        </header>

        <div class="flex flex-1 flex-col min-h-0 bg-white backdrop-blur-md">
          <div v-if="sessionId" class="flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <article
              v-for="message in messages"
              :key="message.message_id"
              class="max-w-[92%] border px-4 py-3 shadow-sm"
              :class="message.role === 'user'
                ? 'ml-auto border-stone-900 bg-stone-900 text-white'
                : 'border-stone-200 bg-stone-50 text-stone-800'"
            >
              <div class="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.2em] opacity-70">
                <Bot v-if="message.role !== 'user'" class="h-3.5 w-3.5" />
                <Sparkles v-else class="h-3.5 w-3.5" />
                {{ message.role === 'user' ? 'User' : '会话总控' }}
              </div>
              <div class="whitespace-pre-wrap text-sm leading-6">{{ message.content }}</div>
            </article>
            <div v-if="messages.length === 0" class="py-10 text-center text-sm text-stone-400">暂无消息记录</div>
          </div>

          <div v-else class="flex flex-1 items-center justify-center px-6 py-10">
            <div class="text-center text-stone-500">
              <p class="text-sm">先选择或新建一个项目会话</p>
            </div>
          </div>

          <div class="shrink-0 border-t border-stone-200 bg-stone-50/50 px-5 py-4 backdrop-blur-md">
            <div v-if="errorMessage" class="mb-3 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {{ errorMessage }}
            </div>
            <div class="mb-3 flex items-center justify-between">
              <select
                v-model="selectedModel"
                class="border border-stone-300 bg-white px-2 py-1 text-xs text-stone-800 outline-none transition focus:border-stone-500"
              >
                <option value="deepseek-v4-pro">V4 Pro</option>
                <option value="deepseek-v4-flash">V4 Flash</option>
              </select>
              <label class="inline-flex items-center gap-3 text-xs font-medium text-stone-600">
                <input
                  v-model="useThinkingMode"
                  type="checkbox"
                  class="peer sr-only"
                >
                <span
                  class="relative h-5 w-9 transition"
                  :class="useThinkingMode ? 'bg-stone-900' : 'bg-stone-300'"
                >
                  <span
                    class="absolute left-0.5 top-0.5 h-4 w-4 bg-white shadow-sm transition-transform"
                    :class="useThinkingMode ? 'translate-x-4' : 'translate-x-0'"
                  />
                </span>
            <span>思考模式</span>
              </label>
              <div class="flex items-center gap-3">
                <div
                  class="inline-flex items-center gap-2 border border-stone-300 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-stone-700 shadow-sm"
                  title="当前仅保留 GraphExecutor 主链路"
                >
                  <Workflow class="h-3.5 w-3.5" />
                  GraphExecutor
                </div>
                <label class="flex items-center gap-2 text-xs font-medium text-stone-600">
                  <span>子Agent最大调用</span>
                  <input
                    v-model.number="delegatedMaxToolCallRounds"
                    type="number"
                    min="1"
                    max="50"
                    class="w-20 border border-stone-300 bg-white px-2 py-1 text-right text-xs text-stone-800 outline-none transition focus:border-stone-500 disabled:cursor-not-allowed disabled:opacity-60"
                    :disabled="isSending || !sessionId"
                    @blur="normalizeDelegatedMaxToolCallRounds"
                  >
                </label>
              </div>
            </div>
            <div class="border border-stone-300 bg-white p-2">
              <textarea
                v-model="inputMessage"
                class="h-24 w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 text-stone-800 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="!sessionId || isSending"
                placeholder="向会话总控发送指令，例如：帮我列出高优先级需求，或检测某两条需求是否冲突"
              />
              <div class="flex items-center justify-end gap-3 border-t border-stone-100 px-2 pt-2">
                <button
                  class="inline-flex items-center justify-center gap-2 bg-stone-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="isSending || !inputMessage.trim() || !sessionId"
                  @click="sendMessage"
                >
                  <Send class="h-3.5 w-3.5" />
                  {{ isSending ? '处理中' : '发送' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </Transition>

    <div class="min-h-full p-6 md:p-8">
      <div class="flex flex-col gap-6">

        <section class="flex flex-col gap-6 shrink-0 pb-8">
          <ExperienceSkillPanel
            :graph="activeRuntimeGraph"
          />

          <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] h-[1200px]">
            <div class="shrink-0 flex items-center justify-between border-b border-stone-200 px-5 py-4">
              <h2 class="flex items-center gap-2 text-lg font-semibold text-stone-900">
                <Workflow class="h-5 w-5" />
                执行图
              </h2>
              <div class="flex items-center gap-3">
                <button
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-stone-600 border border-stone-300 bg-white hover:bg-stone-100 transition disabled:opacity-40 disabled:cursor-not-allowed"
                  :disabled="!graphDetail.nodes.length"
                  title="导出执行图 JSON"
                  @click="handleExportExecutionGraph"
                >
                  <Download class="h-3.5 w-3.5" />
                  导出
                </button>
                <span class="text-xs uppercase tracking-[0.2em] text-stone-500">{{ graphDetail.nodes.length }} nodes</span>
              </div>
            </div>
            <div class="flex-1 min-h-0 h-full">
              <ExecutionGraphCanvas
                :containers="graphDetail.containers"
                :nodes="graphDetail.nodes"
                :edges="graphDetail.edges"
                :selected-id="selectedCanvasId"
                :layout="graphDetail.graph?.layout_json"
                @select-edge="handleCanvasSelectEdge"
                @select-node="handleCanvasSelectNode"
              />
            </div>
          </div>

          <div
            ref="detailPanelRef"
            class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] max-h-[800px]"
          >
            <div class="shrink-0 border-b border-stone-200 px-5 py-4">
              <h2 class="text-lg font-semibold text-stone-900">{{ detailPanelTitle }}</h2>
              <p class="mt-1 text-xs text-stone-500">
                点击执行图中的节点或连线后，这里会展示对应的运行信息与原始数据。
              </p>
            </div>
            <div class="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              <NodeDetailPanel
                :selected-node="selectedNode"
                :selected-edge="selectedEdge"
              />
            </div>
          </div>

          <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] max-h-[900px]">
            <div class="shrink-0 border-b border-stone-200 px-5 py-4">
              <h2 class="flex items-center gap-2 text-lg font-semibold text-stone-900">
                <Workflow class="h-5 w-5" />
                Subgraph 执行轨迹
              </h2>
            </div>
            <div class="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              <SubgraphTracePanel
                :containers="graphDetail.containers"
                :subgraphs="graphDetail.subgraphs"
                :nodes="graphDetail.nodes"
                :edges="graphDetail.edges"
              />
            </div>
          </div>

          <div class="flex flex-col gap-6">
            <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] max-h-[800px]">
              <div class="shrink-0 border-b border-stone-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-stone-900">工具调用结果</h2>
                <p class="mt-1 text-xs text-stone-500">
                  展示会话总控调用各执行层 Agent 工具的返回结果。
                </p>
              </div>
              <div class="flex-1 min-h-0 overflow-y-auto px-5 py-4">
                <NodeDetailPanel
                  :tool-results="flattenedToolResults"
                />
              </div>
            </div>
          </div>

          <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] h-[450px]">
            <div class="shrink-0 border-b border-stone-200 px-5 py-4">
              <h2 class="text-lg font-semibold text-stone-900">运行时间线</h2>
            </div>
            <div class="flex-1 min-h-0 space-y-3 overflow-y-auto px-5 py-4">
              <div
                v-for="item in stageTimeline"
                :key="item.id"
                class="border border-stone-200 bg-stone-50 px-4 py-3"
              >
                <p class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">{{ item.event }}</p>
                <pre class="mt-2 overflow-x-auto text-xs leading-6 text-stone-700">{{ formatJson(item.data) }}</pre>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
