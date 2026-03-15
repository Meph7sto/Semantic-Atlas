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
  Workflow
} from 'lucide-vue-next'

import { manageApi } from '@/api/project'
import { agentChatApi } from '@/api/agentChat'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'

const createEmptyGraphDetail = () => ({ graph: null, containers: [], nodes: [], edges: [] })

const projects = ref([])
const requirements = ref([])
const sessions = ref([])
const selectedProjectId = ref('')
const sessionId = ref('')
const messages = ref([])
const inputMessage = ref('')
const isSending = ref(false)
const isLoadingProjects = ref(false)
const isLoadingRequirements = ref(false)
const isLoadingSessions = ref(false)
const isCreatingSession = ref(false)
const errorMessage = ref('')
const activeGraphId = ref('')
const graphDetail = ref(createEmptyGraphDetail())
const stageTimeline = ref([])
const selectedCanvasId = ref(null)
const draftAssistantId = ref(null)

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

const refreshGraphDetail = async (graphId = activeGraphId.value) => {
  if (!graphId) {
    graphDetail.value = createEmptyGraphDetail()
    selectedCanvasId.value = null
    return
  }
  try {
    graphDetail.value = await agentChatApi.getGraphDetail(graphId)
  } catch (err) {
    console.error('加载执行图失败', err)
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
  errorMessage.value = ''
  resetSessionView()

  try {
    messages.value = await agentChatApi.listMessages(session.session_id)
    activeGraphId.value = session.active_graph_id || ''
    await refreshGraphDetail(activeGraphId.value)
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
    sessions.value = data

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
  await loadRequirements()
  await loadSessions({ preferredSessionId: sessionId.value })
}

const createSession = async () => {
  if (!selectedProjectId.value) return
  isCreatingSession.value = true
  errorMessage.value = ''
  try {
    const session = await agentChatApi.createSession(selectedProjectId.value, generateSessionTitle())
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
        await refreshGraphDetail(activeGraphId.value)
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
          await refreshGraphDetail(payload.graph_id)
        }
      } else if (eventName === 'error') {
        errorMessage.value = payload.error || '处理失败'
        if (payload.graph_id) {
          activeGraphId.value = payload.graph_id
          upsertSessionPatch(sessionId.value, {
            active_graph_id: payload.graph_id,
            updated_at: new Date().toISOString()
          })
          await refreshGraphDetail(payload.graph_id)
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
      message
    })
    inputMessage.value = ''
    appendTimeline('submit', { message })
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
    <div class="min-h-full p-6 md:p-8">
      <div class="flex flex-col gap-6">
        <section class="flex shrink-0 flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <header class="border-b border-stone-200 bg-stone-50/80 px-6 py-5">
            <div class="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.28em] text-stone-500">Alpha Workspace</p>
                <h1 class="mt-2 flex items-center gap-2 text-2xl font-semibold text-stone-900">
                  <MessageSquare class="h-6 w-6" />
                  Requirement Agent Chat
                </h1>
              </div>
              <button
                class="inline-flex items-center gap-2 rounded-full border border-stone-300 px-4 py-2 text-sm text-stone-700 transition hover:border-stone-400 hover:bg-stone-100"
                :disabled="isLoadingProjects || isLoadingSessions"
                @click="refreshWorkspace"
              >
                <RefreshCw class="h-4 w-4" :class="isLoadingProjects || isLoadingSessions ? 'animate-spin' : ''" />
                刷新
              </button>
            </div>

            <div class="mt-5 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
              <label class="space-y-2">
                <span class="text-xs font-medium text-stone-500">项目</span>
                <select
                  v-model="selectedProjectId"
                  class="w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm text-stone-800 outline-none transition focus:border-stone-500"
                >
                  <option value="">请选择项目</option>
                  <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
                    {{ project.name }}
                  </option>
                </select>
              </label>

              <div class="rounded-[24px] border border-stone-300 bg-stone-50 px-4 py-4">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p class="text-xs font-medium text-stone-500">定位方式</p>
                    <p class="mt-2 text-sm leading-6 text-stone-800">
                      每个会话独立管理消息与执行图。切换会话时，聊天记录和当前执行图一起切换。
                    </p>
                  </div>
                  <button
                    class="inline-flex items-center gap-2 rounded-full bg-stone-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="!selectedProjectId || isCreatingSession"
                    @click="createSession"
                  >
                    <Plus class="h-4 w-4" />
                    {{ isCreatingSession ? '创建中...' : '新建会话' }}
                  </button>
                </div>
                <p class="mt-3 text-xs text-stone-500">
                  当前项目需求数: {{ isLoadingRequirements ? '加载中...' : requirements.length }}
                </p>
              </div>
            </div>

            <div class="mt-5 rounded-[24px] border border-stone-200 bg-white px-4 py-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-xs font-semibold uppercase tracking-[0.24em] text-stone-500">Sessions</p>
                  <p class="mt-1 text-sm text-stone-600">选择会话后，会同步切换消息列表和执行图。</p>
                </div>
                <span class="rounded-full bg-stone-100 px-3 py-1 text-xs text-stone-600">
                  {{ sessions.length }} 个会话
                </span>
              </div>

              <div v-if="sessions.length" class="mt-4 flex gap-3 overflow-x-auto pb-2">
                <article
                  v-for="(session, index) in sessions"
                  :key="session.session_id"
                  class="relative min-w-[280px] rounded-[24px] border p-4 transition"
                  :class="sessionId === session.session_id
                    ? 'border-stone-900 bg-stone-900 text-white shadow-[0_16px_40px_rgba(15,23,42,0.18)]'
                    : 'border-stone-200 bg-stone-50 text-stone-800 hover:border-stone-300'"
                >
                  <button
                    class="absolute right-3 top-3 rounded-full p-2 transition"
                    :class="sessionId === session.session_id ? 'text-white/80 hover:bg-white/10 hover:text-white' : 'text-stone-400 hover:bg-stone-200 hover:text-stone-700'"
                    :disabled="isSending"
                    @click.stop="handleDeleteSession(session)"
                  >
                    <Trash2 class="h-4 w-4" />
                  </button>

                  <button class="w-full text-left" @click="handleSelectSession(session)">
                    <p class="pr-10 text-sm font-semibold">{{ sessionTitle(session, index) }}</p>
                    <p
                      class="mt-2 text-xs uppercase tracking-[0.18em]"
                      :class="sessionId === session.session_id ? 'text-white/60' : 'text-stone-400'"
                    >
                      {{ session.session_id }}
                    </p>
                    <div class="mt-4 flex flex-wrap gap-2 text-xs">
                      <span
                        class="rounded-full px-2.5 py-1"
                        :class="sessionId === session.session_id ? 'bg-white/10 text-white' : 'bg-white text-stone-600'"
                      >
                        {{ session.message_count || 0 }} 条消息
                      </span>
                      <span
                        class="rounded-full px-2.5 py-1"
                        :class="sessionId === session.session_id ? 'bg-emerald-400/15 text-emerald-100' : 'bg-emerald-50 text-emerald-700'"
                      >
                        {{ session.active_graph_id ? '已绑定执行图' : '暂无执行图' }}
                      </span>
                    </div>
                    <p
                      class="mt-4 text-xs"
                      :class="sessionId === session.session_id ? 'text-white/70' : 'text-stone-500'"
                    >
                      更新于 {{ formatTime(session.updated_at) }}
                    </p>
                  </button>
                </article>
              </div>

              <div v-else class="mt-4 rounded-[20px] border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-center text-sm text-stone-500">
                当前项目还没有会话。点击右上角“新建会话”开始。
              </div>
            </div>

            <div class="mt-4 flex flex-wrap items-center gap-3 text-sm text-stone-600">
              <span class="rounded-full bg-stone-100 px-3 py-1">Session: {{ currentSession ? sessionTitle(currentSession) : '未选择' }}</span>
              <span class="rounded-full bg-stone-100 px-3 py-1">ID: {{ sessionId || '未建立' }}</span>
              <span class="rounded-full bg-amber-100 px-3 py-1 text-amber-800">Graph: {{ activeGraphId || '等待运行' }}</span>
              <span class="rounded-full bg-emerald-100 px-3 py-1 text-emerald-800">状态: {{ latestGraphStatus }}</span>
            </div>
          </header>

          <div class="flex h-[1800px] flex-col">
            <div v-if="sessionId" class="flex-1 space-y-4 overflow-y-auto px-6 py-5">
              <article
                v-for="message in messages"
                :key="message.message_id"
                class="max-w-[92%] rounded-3xl border px-4 py-3 shadow-sm"
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
            </div>

            <div v-else class="flex flex-1 items-center justify-center px-6 py-10">
              <div class="max-w-md rounded-[28px] border border-dashed border-stone-300 bg-stone-50 px-6 py-8 text-center text-stone-600">
                <p class="text-lg font-semibold text-stone-900">先选择或新建一个会话</p>
                <p class="mt-2 text-sm leading-6">
                  会话建立后，这里展示对话记录；下方执行图区会同步显示该会话对应的执行图。
                </p>
              </div>
            </div>

            <div class="border-t border-stone-200 bg-white px-6 py-5">
              <div v-if="errorMessage" class="mb-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {{ errorMessage }}
              </div>

              <div class="rounded-[24px] border border-stone-300 bg-stone-50 p-3">
                <textarea
                  v-model="inputMessage"
                  class="h-28 w-full resize-none bg-transparent px-2 py-2 text-sm leading-6 text-stone-800 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="!sessionId || isSending"
                  placeholder="例如：把登录性能那条需求的验收标准改成“用户在 3 秒内完成登录并看到首页”"
                />
                <div class="flex items-center justify-between gap-3 border-t border-stone-200 px-2 pt-3">
                  <p class="text-xs text-stone-500">
                    当前定位: {{ resolvedRequirement?.title || resolvedRequirementId || '待模型定位' }}
                  </p>
                  <button
                    class="inline-flex items-center gap-2 rounded-full bg-stone-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="isSending || !inputMessage.trim() || !sessionId"
                    @click="sendMessage"
                  >
                    <Send class="h-4 w-4" />
                    {{ isSending ? '处理中...' : '发送' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="flex flex-col gap-6 shrink-0 pb-8">
          <div class="flex flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] h-[1200px]">
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

          <div class="flex flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)] max-h-[600px]">
            <div class="shrink-0 border-b border-stone-200 px-5 py-4">
              <h2 class="text-lg font-semibold text-stone-900">节点详情</h2>
            </div>
            <div class="flex-1 min-h-0 space-y-5 overflow-y-auto px-5 py-4 text-sm text-stone-700">
              <div>
                <p class="text-xs uppercase tracking-[0.2em] text-stone-500">当前选中</p>
                <p class="mt-2 font-medium text-stone-900">
                  {{ selectedNode?.label || selectedEdge?.label || '未选择节点/边' }}
                </p>
              </div>

              <div v-if="selectedNode" class="space-y-4">
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">类型</p>
                  <p class="mt-2">{{ selectedNode.node_type }}</p>
                </div>
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">状态摘要</p>
                  <pre class="mt-2 overflow-x-auto rounded-2xl bg-stone-900 p-4 text-xs leading-6 text-stone-100">{{ formatJson(selectedNode.config_json) }}</pre>
                </div>
              </div>

              <div v-else-if="selectedEdge" class="space-y-4">
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">边类型</p>
                  <p class="mt-2">{{ selectedEdge.edge_type }}</p>
                </div>
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">配置</p>
                  <pre class="mt-2 overflow-x-auto rounded-2xl bg-stone-900 p-4 text-xs leading-6 text-stone-100">{{ formatJson(selectedEdge.config_json) }}</pre>
                </div>
              </div>

              <div class="space-y-3 rounded-[24px] bg-stone-50 p-4">
                <p class="text-xs uppercase tracking-[0.2em] text-stone-500">最新写入结果</p>
                <pre class="overflow-x-auto text-xs leading-6 text-stone-700">{{ formatJson(latestWriteSummary) }}</pre>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.1fr] h-[450px]">
            <div class="flex flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
              <div class="shrink-0 border-b border-stone-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-stone-900">运行时间线</h2>
              </div>
              <div class="flex-1 min-h-0 space-y-3 overflow-y-auto px-5 py-4">
                <div
                  v-for="item in stageTimeline"
                  :key="item.id"
                  class="rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3"
                >
                  <p class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">{{ item.event }}</p>
                  <pre class="mt-2 overflow-x-auto text-xs leading-6 text-stone-700">{{ formatJson(item.data) }}</pre>
                </div>
              </div>
            </div>

            <div class="flex flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
              <div class="shrink-0 border-b border-stone-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-stone-900">模型定位结果</h2>
              </div>
              <div class="flex-1 min-h-0 space-y-4 overflow-y-auto px-5 py-4 text-sm text-stone-700">
                <div class="rounded-[24px] bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">目标需求</p>
                  <p class="mt-2 text-base font-medium text-stone-900">
                    {{ resolvedRequirement?.title || resolvedRequirementId || '本轮尚未定位到唯一需求' }}
                  </p>
                </div>
                <div class="grid gap-4 md:grid-cols-2">
                  <div class="rounded-[24px] bg-stone-50 p-4">
                    <p class="text-xs uppercase tracking-[0.2em] text-stone-500">优先级</p>
                    <p class="mt-2">{{ resolvedRequirement?.priority || '未设置' }}</p>
                  </div>
                  <div class="rounded-[24px] bg-stone-50 p-4">
                    <p class="text-xs uppercase tracking-[0.2em] text-stone-500">状态</p>
                    <p class="mt-2">{{ resolvedRequirement?.status || '未知' }}</p>
                  </div>
                </div>
                <div class="rounded-[24px] bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">描述</p>
                  <p class="mt-2 whitespace-pre-wrap leading-6">{{ resolvedRequirement?.description || '暂无描述' }}</p>
                </div>
                <div class="rounded-[24px] bg-stone-50 p-4">
                  <p class="text-xs uppercase tracking-[0.2em] text-stone-500">候选窗口</p>
                  <div class="mt-3 space-y-3">
                    <div
                      v-for="item in candidateRequirements"
                      :key="item.requirement_id"
                      class="rounded-2xl border border-stone-200 bg-white px-3 py-3"
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
