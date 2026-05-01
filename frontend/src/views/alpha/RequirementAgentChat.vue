<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  Bot,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  Workflow,
  X
} from 'lucide-vue-next'

import { manageApi } from '@/api/project'
import { agentChatApi } from '@/api/agentChat'
import { api } from '@/api/request'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'
import NodeDetailPanel from '@/components/alpha/NodeDetailPanel.vue'
import SubgraphTracePanel from '@/components/alpha/SubgraphTracePanel.vue'
import { createEmptyGraphDetail, buildMergedSessionGraphDetail } from '@/utils/sessionGraphLayout'

const PROMPT_FORMAT_OPTIONS = [
  { value: 'json', label: 'JSON' },
  { value: 'yaml', label: 'YAML' },
  { value: 'markdown', label: 'Markdown' }
]
const DEFAULT_PROMPT_FORMAT = 'json'

const CONTEXT_MODE_OPTIONS = [
  { value: 'full', label: '全量 (Full)', description: '传入完整历史节点上下文' },
  { value: 'incremental', label: '增量 (Incremental)', description: '仅保留架构/文件上下文' },
  { value: 'scratchpad', label: '蒸馏 (Scratchpad)', description: 'Subgraph 间通过工作记忆传递关键信息，而非全量历史' }
]
const DEFAULT_CONTEXT_MODE = 'full'

const projects = ref([])
const requirements = ref([])
const sessions = ref([])
const selectedProjectId = ref('')
const sessionId = ref('')
const messages = ref([])
const inputMessage = ref('')
const selectedModel = ref('deepseek-v4-pro')
const useThinkingMode = ref(true)
const isSending = ref(false)
const isLoadingProjects = ref(false)
const isLoadingRequirements = ref(false)
const isLoadingSessions = ref(false)
const isCreatingSession = ref(false)
const isUpdatingSessionFormat = ref(false)
const errorMessage = ref('')
const activeGraphId = ref('')
const sessionGraphChain = ref([])
const graphDetail = ref(createEmptyGraphDetail())
const stageTimeline = ref([])
const selectedCanvasId = ref(null)
const draftAssistantId = ref(null)
const promptPayloadFormatDraft = ref('markdown')
const contextModeDraft = ref(DEFAULT_CONTEXT_MODE)
const isUpdatingContextMode = ref(false)
const isAssistantOpen = ref(false)

const currentSession = computed(() => {
  return sessions.value.find((item) => item.session_id === sessionId.value) || null
})

const selectedNode = computed(() => {
  return graphDetail.value.nodes.find((node) => node.node_id === selectedCanvasId.value) || null
})

const selectedEdge = computed(() => {
  return graphDetail.value.edges.find((edge) => edge.edge_id === selectedCanvasId.value) || null
})

const latestGraphStatus = computed(() => graphDetail.value.graph?.status || 'idle')

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

const latestWriteSummary = computed(() => {
  return [...flattenedToolResults.value]
    .reverse()
    .find((entry) => entry.tool_name === 'update_requirement_content' && !entry.result?.is_error)?.result || null
})

const latestCandidateWindow = computed(() => {
  return [...flattenedToolResults.value]
    .reverse()
    .find((entry) => ['list_requirements', 'search_requirements'].includes(entry.tool_name) && !entry.result?.is_error)?.result || null
})

const latestResolvedRequirementSummary = computed(() => {
  return [...flattenedToolResults.value]
    .reverse()
    .find((entry) => ['get_requirement_state', 'update_requirement_content'].includes(entry.tool_name) && !entry.result?.is_error)?.result || null
})

const resolvedRequirementId = computed(() => {
  return graphDetail.value.graph?.meta_json?.resolved_requirement_id
    || latestWriteSummary.value?.requirement_id
    || latestResolvedRequirementSummary.value?.requirement_id
    || ''
})

const resolvedRequirement = computed(() => {
  const fromList = requirements.value.find((item) => item.req_id === resolvedRequirementId.value) || null
  const fromTool = latestResolvedRequirementSummary.value || latestWriteSummary.value
  if (!fromTool) return fromList
  return {
    ...fromList,
    req_id: fromTool.requirement_id || fromList?.req_id,
    title: fromTool.title || fromList?.title,
    status: fromTool.status || fromList?.status,
    priority: fromTool.priority || fromList?.priority,
    description: fromTool.description || fromList?.description,
    acceptance_criteria: fromTool.acceptance_criteria || fromList?.acceptance_criteria
  }
})

const candidateRequirements = computed(() => {
  if (latestCandidateWindow.value?.items?.length) {
    return latestCandidateWindow.value.items
  }
  return requirements.value.slice(0, 5).map((item) => ({
    requirement_id: item.req_id,
    title: item.title || item.text || item.req_id,
    status: item.status,
    priority: item.priority,
    parent_id: item.parent_id,
    order_index: item.order_index,
    description_excerpt: item.description || ''
  }))
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

const normalizePromptPayloadFormat = (value) => {
  const normalized = String(value || '').trim().toLowerCase()
  return PROMPT_FORMAT_OPTIONS.some((item) => item.value === normalized)
    ? normalized
    : DEFAULT_PROMPT_FORMAT
}

const normalizeContextMode = (value) => {
  const normalized = String(value || '').trim().toLowerCase()
  return CONTEXT_MODE_OPTIONS.some((item) => item.value === normalized)
    ? normalized
    : DEFAULT_CONTEXT_MODE
}

const promptPayloadFormatLabel = (value) => {
  const normalized = normalizePromptPayloadFormat(value)
  return PROMPT_FORMAT_OPTIONS.find((item) => item.value === normalized)?.label || normalized
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
  return `需求会话 ${stamp}`
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

const refreshSessionGraphChain = async (targetSessionId = sessionId.value) => {
  if (!targetSessionId) {
    sessionGraphChain.value = []
    graphDetail.value = createEmptyGraphDetail()
    selectedCanvasId.value = null
    return
  }
  try {
    const chainPayload = await agentChatApi.getSessionGraphChain(targetSessionId)
    sessionGraphChain.value = chainPayload?.graphs || []
    activeGraphId.value = chainPayload?.active_graph_id || activeGraphId.value || ''
    graphDetail.value = buildMergedSessionGraphDetail(chainPayload)
  } catch (err) {
    console.error('加载会话执行图链失败', err)
    sessionGraphChain.value = []
    graphDetail.value = createEmptyGraphDetail()
  }
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

const loadRequirements = async () => {
  if (!selectedProjectId.value) {
    requirements.value = []
    return
  }
  isLoadingRequirements.value = true
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = data.requirements || []
  } catch (err) {
    errorMessage.value = err?.message || '加载需求失败'
  } finally {
    isLoadingRequirements.value = false
  }
}

const loadSessionContent = async (session) => {
  if (!session?.session_id) {
    sessionId.value = ''
    resetSessionView()
    return
  }

  sessionId.value = session.session_id
  promptPayloadFormatDraft.value = normalizePromptPayloadFormat(session.prompt_payload_format)
  contextModeDraft.value = normalizeContextMode(session.context_mode)
  errorMessage.value = ''
  resetSessionView()

  try {
    messages.value = await agentChatApi.listMessages(session.session_id)
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
    const data = await agentChatApi.listSessions(selectedProjectId.value)
    sessions.value = (data || []).map((item) => ({
      ...item,
      prompt_payload_format: normalizePromptPayloadFormat(item.prompt_payload_format)
    }))
    const existingCurrent = sessions.value.find((item) => item.session_id === sessionId.value)
    if (existingCurrent) {
      promptPayloadFormatDraft.value = normalizePromptPayloadFormat(existingCurrent.prompt_payload_format)
      contextModeDraft.value = normalizeContextMode(existingCurrent.context_mode)
    }

    if (!sessions.value.length) {
      sessionId.value = ''
      promptPayloadFormatDraft.value = 'markdown'
      contextModeDraft.value = DEFAULT_CONTEXT_MODE
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
  await loadRequirements()
  await loadSessions({ preferredSessionId: sessionId.value })
}

const createSession = async () => {
  if (!selectedProjectId.value) return
  isCreatingSession.value = true
  errorMessage.value = ''
  try {
    const preferredFormat = normalizePromptPayloadFormat(promptPayloadFormatDraft.value || 'markdown')
    let session = await agentChatApi.createSession(selectedProjectId.value, generateSessionTitle())
    if (session?.session_id && normalizePromptPayloadFormat(session.prompt_payload_format) !== preferredFormat) {
      const resp = await api.patch(`/agent-chat/sessions/${encodeURIComponent(session.session_id)}`, {
        prompt_payload_format: preferredFormat
      })
      session = { ...session, ...(resp.data || {}) }
    }
    session = {
      ...session,
      prompt_payload_format: normalizePromptPayloadFormat(session.prompt_payload_format)
    }
    sessions.value = [session, ...sessions.value.filter((item) => item.session_id !== session.session_id)]
    await loadSessionContent(session)
  } catch (err) {
    errorMessage.value = err?.message || '新建会话失败'
  } finally {
    isCreatingSession.value = false
  }
}

const updateCurrentSessionPromptFormat = async () => {
  if (!sessionId.value || isSending.value || isUpdatingSessionFormat.value) return
  const nextFormat = normalizePromptPayloadFormat(promptPayloadFormatDraft.value)
  const currentFormat = normalizePromptPayloadFormat(currentSession.value?.prompt_payload_format)
  if (nextFormat === currentFormat) return

  isUpdatingSessionFormat.value = true
  errorMessage.value = ''
  try {
    const resp = await api.patch(`/agent-chat/sessions/${encodeURIComponent(sessionId.value)}`, {
      prompt_payload_format: nextFormat
    })
    const updated = resp.data || {}
    const normalized = normalizePromptPayloadFormat(updated.prompt_payload_format || nextFormat)
    upsertSessionPatch(sessionId.value, {
      ...updated,
      prompt_payload_format: normalized
    })
    promptPayloadFormatDraft.value = normalized
  } catch (err) {
    promptPayloadFormatDraft.value = currentFormat
    errorMessage.value = err?.message || '更新 Prompt 结构失败'
  } finally {
    isUpdatingSessionFormat.value = false
  }
}

const updateCurrentSessionContextMode = async () => {
  if (!sessionId.value || isSending.value || isUpdatingContextMode.value) return
  const nextMode = normalizeContextMode(contextModeDraft.value)
  const currentMode = normalizeContextMode(currentSession.value?.context_mode)
  if (nextMode === currentMode) return

  isUpdatingContextMode.value = true
  errorMessage.value = ''
  try {
    const resp = await api.patch(`/agent-chat/sessions/${encodeURIComponent(sessionId.value)}`, {
      context_mode: nextMode
    })
    const updated = resp.data || {}
    const normalized = normalizeContextMode(updated.context_mode || nextMode)
    upsertSessionPatch(sessionId.value, {
      ...updated,
      context_mode: normalized
    })
    contextModeDraft.value = normalized
  } catch (err) {
    contextModeDraft.value = currentMode
    errorMessage.value = err?.message || '更新上下文模式失败'
  } finally {
    isUpdatingContextMode.value = false
  }
}

const handleSelectSession = async (session) => {
  if (!session?.session_id) return
  await loadSessionContent(session)
}

const handleDeleteSession = async (session) => {
  if (!session?.session_id || isSending.value) return
  const confirmed = window.confirm(`删除会话“${sessionTitle(session)}”？对应执行图也会一起删除。`)
  if (!confirmed) return

  errorMessage.value = ''
  try {
    await agentChatApi.deleteSession(session.session_id)
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
        await refreshSessionGraphChain(sessionId.value)
      } else if (eventName === 'token') {
        const draft = ensureDraftAssistant()
        draft.content += payload.content || ''
      } else if (eventName === 'assistant_message') {
        if (draftAssistantId.value) {
          messages.value = messages.value.filter((item) => item.message_id !== draftAssistantId.value)
          draftAssistantId.value = null
        }
        upsertMessage(payload)
      } else if (eventName === 'stage' || eventName === 'tool_call' || eventName === 'tool_result' || eventName === 'result') {
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          await refreshSessionGraphChain(sessionId.value)
        }
      } else if (eventName === 'error') {
        errorMessage.value = payload.error || '处理失败'
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          await refreshSessionGraphChain(sessionId.value)
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
  if (draftAssistantId.value) {
    messages.value = messages.value.filter((item) => item.message_id !== draftAssistantId.value)
    draftAssistantId.value = null
  }

  try {
    const message = inputMessage.value.trim()
    const stream = await agentChatApi.streamMessage({
      sessionId: sessionId.value,
      projectId: selectedProjectId.value,
      requirementId: null,
      message,
      model: selectedModel.value,
      useThinkingMode: useThinkingMode.value
    })
    inputMessage.value = ''
    appendTimeline('submit', {
      message,
      model: selectedModel.value,
      use_thinking_mode: useThinkingMode.value
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

const handleCanvasSelectNode = (nodeId) => {
  selectedCanvasId.value = nodeId
}

const handleCanvasSelectEdge = (edgeId) => {
  selectedCanvasId.value = edgeId
}

watch(selectedProjectId, async (projectId) => {
  sessionId.value = ''
  sessions.value = []
  promptPayloadFormatDraft.value = 'markdown'
  contextModeDraft.value = DEFAULT_CONTEXT_MODE
  resetSessionView()
  if (!projectId) {
    requirements.value = []
    return
  }
  await loadRequirements()
  await loadSessions()
})

onMounted(async () => {
  await loadProjects()
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
      <MessageSquare class="h-7 w-7" />
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
              <MessageSquare class="h-5 w-5 text-stone-700" />
              <h1 class="text-base font-semibold text-stone-900">Requirement Agent</h1>
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

            <!-- 会话配置选项 -->
            <div v-if="sessionId" class="flex flex-col gap-1.5">
              <!-- Prompt 格式 -->
              <div class="flex items-center gap-2">
                <span class="w-[80px] shrink-0 text-[11px] text-stone-400">Prompt 格式</span>
                <select
                  v-model="promptPayloadFormatDraft"
                  class="flex-1 border border-stone-200 bg-white px-2 py-1 text-xs text-stone-700 outline-none transition focus:border-stone-400"
                  :disabled="isUpdatingSessionFormat || isSending"
                  @change="updateCurrentSessionPromptFormat"
                >
                  <option v-for="opt in PROMPT_FORMAT_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
              <!-- 上下文模式 -->
              <div class="flex items-center gap-2">
                <span class="w-[80px] shrink-0 text-[11px] text-stone-400">上下文模式</span>
                <select
                  v-model="contextModeDraft"
                  class="flex-1 border border-stone-200 bg-white px-2 py-1 text-xs text-stone-700 outline-none transition focus:border-stone-400"
                  :disabled="isUpdatingContextMode || isSending"
                  @change="updateCurrentSessionContextMode"
                  :title="CONTEXT_MODE_OPTIONS.find(o => o.value === contextModeDraft)?.description || ''"
                >
                  <option v-for="opt in CONTEXT_MODE_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
                <span v-if="isUpdatingContextMode" class="text-[11px] text-stone-400 shrink-0">保存中...</span>
              </div>
            </div>
          </div>
          
          <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
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
                {{ message.role === 'user' ? 'User' : 'Agent' }}
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
            <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
              <select
                v-model="selectedModel"
                class="border border-stone-300 bg-white px-2 py-1 text-xs text-stone-800 outline-none transition focus:border-stone-500 disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="isSending || !sessionId"
              >
                <option value="deepseek-v4-pro">V4 Pro</option>
                <option value="deepseek-v4-flash">V4 Flash</option>
              </select>
              <label class="inline-flex items-center gap-3 text-xs font-medium text-stone-600">
                <input
                  v-model="useThinkingMode"
                  type="checkbox"
                  class="peer sr-only"
                  :disabled="isSending || !sessionId"
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
            </div>
            <div class="border border-stone-300 bg-white p-2">
              <textarea
                v-model="inputMessage"
                class="h-24 w-full resize-none bg-transparent px-2 py-1 text-sm leading-6 text-stone-800 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="!sessionId || isSending"
                placeholder="发送消息给 Requirement Agent..."
              />
              <div class="flex items-center justify-between gap-3 border-t border-stone-100 px-2 pt-2">
                <p class="truncate text-[11px] text-stone-400 max-w-[200px]" :title="resolvedRequirement?.title || resolvedRequirementId || '待模型定位'">
                  定位: {{ resolvedRequirement?.title || resolvedRequirementId || '待定位' }}
                </p>
                <button
                  class="inline-flex items-center justify-center gap-2 bg-stone-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="isSending || !inputMessage.trim() || !sessionId"
                  @click="sendMessage"
                >
                  <Send class="h-3.5 w-3.5" />
                  {{ isSending ? '发送中' : '发送' }}
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
          <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] h-[1200px]">
            <div class="shrink-0 flex items-center justify-between border-b border-stone-200 px-5 py-4">
              <h2 class="flex items-center gap-2 text-lg font-semibold text-stone-900">
                <Workflow class="h-5 w-5" />
                执行图
              </h2>
              <span class="text-xs uppercase tracking-[0.2em] text-stone-500">{{ graphDetail.nodes.length }} nodes</span>
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

          <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] max-h-[800px]">
            <div class="shrink-0 border-b border-stone-200 px-5 py-4">
              <h2 class="text-lg font-semibold text-stone-900">节点详情</h2>
            </div>
            <div class="flex-1 min-h-0 overflow-y-auto px-5 py-4">
              <NodeDetailPanel
                :selected-node="selectedNode"
                :selected-edge="selectedEdge"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.1fr] h-[450px]">
            <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
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

            <div class="flex flex-col overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
              <div class="shrink-0 border-b border-stone-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-stone-900">模型定位结果</h2>
              </div>
              <div class="flex-1 min-h-0 space-y-4 overflow-y-auto px-5 py-4 text-sm text-stone-700">
                <div class="bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">目标需求</p>
                  <p class="mt-2 text-base font-medium text-stone-900">
                    {{ resolvedRequirement?.title || resolvedRequirementId || '本轮尚未定位到唯一需求' }}
                  </p>
                </div>
                <div class="grid gap-4 md:grid-cols-2">
                  <div class="bg-stone-50 p-4">
                    <p class="text-xs uppercase tracking-[0.2em] text-stone-500">优先级</p>
                    <p class="mt-2">{{ resolvedRequirement?.priority || '未设置' }}</p>
                  </div>
                  <div class="bg-stone-50 p-4">
                    <p class="text-xs uppercase tracking-[0.2em] text-stone-500">状态</p>
                    <p class="mt-2">{{ resolvedRequirement?.status || '未知' }}</p>
                  </div>
                </div>
                <div class="bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">描述</p>
                  <p class="mt-2 whitespace-pre-wrap leading-6">{{ resolvedRequirement?.description || '暂无描述' }}</p>
                </div>
                <div class="bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">候选窗口</p>
                  <div class="mt-3 space-y-3">
                    <div
                      v-for="item in candidateRequirements"
                      :key="item.requirement_id"
                      class="border border-stone-200 bg-white px-3 py-3"
                    >
                      <div class="flex items-center justify-between gap-3">
                        <p class="text-sm font-medium text-stone-900">
                          {{ item.title || item.requirement_id }}
                        </p>
                        <span class="text-[11px] uppercase tracking-[0.18em] text-stone-400">
                          {{ item.requirement_id }}
                        </span>
                      </div>
                      <p class="mt-2 text-xs leading-5 text-stone-600">
                        {{ item.description_excerpt || '暂无摘要' }}
                      </p>
                    </div>
                    <p v-if="candidateRequirements.length === 0" class="text-xs text-stone-500">
                      当前还没有可展示的候选需求窗口。
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
