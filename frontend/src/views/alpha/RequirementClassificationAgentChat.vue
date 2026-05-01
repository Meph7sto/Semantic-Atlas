<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  BrainCircuit,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Workflow,
  X
} from 'lucide-vue-next'

import { manageApi } from '@/api/project'
import { requirementClassificationAgentChatApi } from '@/api/requirementClassificationAgentChat'
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
  { value: 'scratchpad', label: '蒸馏 (Scratchpad)', description: '后续阶段通过工作记忆传递关键信息' }
]
const DEFAULT_CONTEXT_MODE = 'full'

const projects = ref([])
const requirements = ref([])
const sessions = ref([])
const selectedProjectId = ref('')
const selectedRequirementId = ref('')
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
const isUpdatingContextMode = ref(false)
const errorMessage = ref('')
const activeGraphId = ref('')
const sessionGraphChain = ref([])
const graphDetail = ref(createEmptyGraphDetail())
const stageTimeline = ref([])
const selectedCanvasId = ref(null)
const draftAssistantId = ref(null)
const promptPayloadFormatDraft = ref('markdown')
const contextModeDraft = ref(DEFAULT_CONTEXT_MODE)
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

const latestClassificationResult = computed(() => {
  const fromGraph = graphDetail.value.graph?.meta_json?.classification_result
  if (fromGraph) return fromGraph
  return [...flattenedToolResults.value]
    .reverse()
    .find((entry) => entry.tool_name === 'classify_requirement' && !entry.result?.is_error)?.result || null
})

const resolvedRequirement = computed(() => {
  const result = latestClassificationResult.value
  if (!result?.requirement_id) return null
  return requirements.value.find((item) => item.req_id === result.requirement_id) || null
})

const formatJson = (value) => {
  if (!value) return '暂无'
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
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
  return `需求分类 ${stamp}`
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
    const chainPayload = await requirementClassificationAgentChatApi.getSessionGraphChain(targetSessionId)
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
    selectedRequirementId.value = ''
    return
  }
  isLoadingRequirements.value = true
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = data.requirements || []
    if (selectedRequirementId.value && !requirements.value.find((item) => item.req_id === selectedRequirementId.value)) {
      selectedRequirementId.value = ''
    }
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
    messages.value = await requirementClassificationAgentChatApi.listMessages(session.session_id)
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
    const data = await requirementClassificationAgentChatApi.listSessions(selectedProjectId.value)
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
    let session = await requirementClassificationAgentChatApi.createSession(selectedProjectId.value, generateSessionTitle())
    if (session?.session_id && normalizePromptPayloadFormat(session.prompt_payload_format) !== preferredFormat) {
      const resp = await api.patch(`/requirement-classification-agent/sessions/${encodeURIComponent(session.session_id)}`, {
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
    const resp = await api.patch(`/requirement-classification-agent/sessions/${encodeURIComponent(sessionId.value)}`, {
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
    const resp = await api.patch(`/requirement-classification-agent/sessions/${encodeURIComponent(sessionId.value)}`, {
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
    await requirementClassificationAgentChatApi.deleteSession(session.session_id)
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
    const stream = await requirementClassificationAgentChatApi.streamMessage({
      sessionId: sessionId.value,
      projectId: selectedProjectId.value,
      requirementId: selectedRequirementId.value || null,
      message,
      model: selectedModel.value,
      useThinkingMode: useThinkingMode.value
    })
    inputMessage.value = ''
    appendTimeline('submit', {
      message,
      requirement_id: selectedRequirementId.value || null,
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
    selectedRequirementId.value = ''
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
    <button
      v-if="!isAssistantOpen"
      @click="isAssistantOpen = true"
      class="fixed bottom-8 right-8 z-40 flex h-16 w-16 items-center justify-center bg-stone-900 text-white shadow-[0_12px_32px_rgba(15,23,42,0.24)] transition-transform hover:scale-105"
    >
      <BrainCircuit class="h-7 w-7" />
    </button>

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
        class="fixed bottom-8 right-8 z-50 flex w-[520px] max-w-[calc(100vw-2rem)] h-[85vh] max-h-[920px] shrink-0 flex-col overflow-hidden border border-stone-200 bg-white/95 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur-xl"
      >
        <header class="border-b border-stone-200 bg-stone-50/80 px-5 py-4 shrink-0">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <BrainCircuit class="h-5 w-5 text-stone-700" />
              <h1 class="text-base font-semibold text-stone-900">Requirement Classification Agent</h1>
            </div>
            <div class="flex items-center gap-1">
              <button
                class="p-2 text-stone-500 hover:bg-stone-200 transition"
                @click="refreshWorkspace"
                title="刷新"
              >
                <RefreshCw class="h-4 w-4" :class="isLoadingProjects || isLoadingSessions || isLoadingRequirements ? 'animate-spin' : ''" />
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

            <div class="flex gap-2">
              <select
                v-model="selectedRequirementId"
                class="flex-1 border border-stone-300 bg-white px-3 py-2 text-sm text-stone-800 outline-none transition focus:border-stone-500"
              >
                <option value="">让 Agent 自行定位需求</option>
                <option v-for="item in requirements" :key="item.req_id" :value="item.req_id">
                  {{ item.title || item.req_id }}
                </option>
              </select>
            </div>

            <div v-if="sessionId" class="flex flex-col gap-1.5">
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
              <div class="flex items-center gap-2">
                <span class="w-[80px] shrink-0 text-[11px] text-stone-400">上下文模式</span>
                <select
                  v-model="contextModeDraft"
                  class="flex-1 border border-stone-200 bg-white px-2 py-1 text-xs text-stone-700 outline-none transition focus:border-stone-400"
                  :disabled="isUpdatingContextMode || isSending"
                  @change="updateCurrentSessionContextMode"
                >
                  <option v-for="opt in CONTEXT_MODE_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
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
        </header>

        <div class="flex-1 min-h-0 overflow-hidden">
          <div class="grid h-full grid-rows-[auto_1fr_auto]">
            <div v-if="latestClassificationResult" class="border-b border-stone-200 bg-stone-50/70 px-5 py-4 text-sm text-stone-700">
              <div class="grid gap-3 md:grid-cols-2">
                <div class="bg-white p-3">
                  <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">目标需求</p>
                  <p class="mt-2 font-medium text-stone-900">
                    {{ latestClassificationResult.title || resolvedRequirement?.title || latestClassificationResult.requirement_id }}
                  </p>
                </div>
                <div class="bg-white p-3">
                  <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">Level / Nature</p>
                  <p class="mt-2 text-stone-900">
                    {{ latestClassificationResult.level }} / {{ latestClassificationResult.requirement_nature }}
                  </p>
                </div>
                <div class="bg-white p-3">
                  <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">领域标签</p>
                  <p class="mt-2 text-stone-900">
                    {{ (latestClassificationResult.domain_tags || []).join('、') || '暂无' }}
                  </p>
                </div>
                <div class="bg-white p-3">
                  <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">优先级初判</p>
                  <p class="mt-2 text-stone-900">{{ latestClassificationResult.priority_suggestion || '暂无' }}</p>
                </div>
              </div>
              <div class="mt-3 bg-white p-3">
                <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">解释</p>
                <p class="mt-2 leading-6 text-stone-800">{{ latestClassificationResult.reasoning || '暂无' }}</p>
              </div>
            </div>

            <div class="min-h-0 overflow-y-auto px-5 py-4">
              <div class="space-y-3">
                <div
                  v-for="message in messages"
                  :key="message.message_id"
                  class="border px-4 py-3"
                  :class="message.role === 'assistant' ? 'border-stone-200 bg-stone-50' : 'border-stone-300 bg-white'"
                >
                  <p class="text-[11px] uppercase tracking-[0.18em] text-stone-500">{{ message.role }}</p>
                  <p class="mt-2 whitespace-pre-wrap leading-6 text-sm text-stone-800">{{ message.content }}</p>
                </div>
                <div v-if="!messages.length" class="border border-dashed border-stone-300 bg-stone-50 px-4 py-5 text-sm text-stone-500">
                  当前会话还没有消息。可以直接让 Agent 分类一条需求，或让它先帮你定位目标需求。
                </div>
              </div>
            </div>

            <div class="border-t border-stone-200 px-5 py-4">
              <div v-if="errorMessage" class="mb-3 bg-rose-50 px-3 py-2 text-xs text-rose-700">
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
              <textarea
                v-model="inputMessage"
                rows="4"
                class="w-full resize-none border border-stone-300 bg-white px-3 py-3 text-sm text-stone-800 outline-none transition focus:border-stone-500"
                :disabled="!sessionId || isSending"
                placeholder="描述分类任务，例如：请判断这条需求属于哪个层级，并给出领域标签和优先级初判"
              />
              <div class="flex items-center justify-between gap-3 border-t border-stone-100 px-2 pt-2">
                <p class="truncate text-[11px] text-stone-400 max-w-[240px]">
                  已选需求: {{ selectedRequirementId || '由 Agent 自行定位' }}
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

          <div class="grid grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.1fr] h-[500px]">
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
                <h2 class="text-lg font-semibold text-stone-900">分类结果 / 节点详情</h2>
              </div>
              <div class="flex-1 min-h-0 overflow-y-auto px-5 py-4">
                <div v-if="latestClassificationResult" class="space-y-4 text-sm text-stone-700">
                  <div class="bg-stone-50 p-4">
                    <p class="text-xs uppercase tracking-[0.2em] text-stone-500">模型结论</p>
                    <pre class="mt-3 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-stone-700">{{ formatJson(latestClassificationResult) }}</pre>
                  </div>
                </div>
                <NodeDetailPanel
                  :selected-node="selectedNode"
                  :selected-edge="selectedEdge"
                  :tool-results="flattenedToolResults"
                />
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
