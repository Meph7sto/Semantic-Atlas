<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import {
  MessageSquare, ClipboardCheck, History, Plus, Trash2, Pencil, Check, Send,
  Loader2, RefreshCw, X, Bot
} from 'lucide-vue-next'
import { aiChatApi } from '@/api/chat'
import { agentTaskApi } from '@/api/agent'
import { manageApi } from '@/api/project'

// Project context
const projectId = ref(localStorage.getItem('lastProjectId') || '')
const projectName = ref('')

// Agent selector
const selectedAgentId = ref('conductor_agent')
const agentOptions = [
  { id: 'conductor_agent', label: 'Conductor Agent' },
  { id: 'requirements_agent', label: 'Requirements Agent' },
]

// Tab state
const activeTab = ref('chat')

// Chat state
const session = ref(null)
const messages = ref([])
const messageInput = ref('')
const isLoadingMessages = ref(false)
const isLoadingMore = ref(false)
const hasMoreHistory = ref(true)
const isSending = ref(false)
const streamingContent = ref('')
const streamingThinking = ref('')
const isStreaming = ref(false)
const REASONER_PREF_KEY = 'ai_chat_use_reasoner'
const useReasonerMode = ref(false)

// Agent stream cards
const streamingToolCalls = ref([])
const streamingTasksCreated = ref([])

// Task state
const tasks = ref([])
const isLoadingTasks = ref(false)
const processingTaskId = ref(null)

// History state
const sessions = ref([])
const isLoadingSessions = ref(false)
const sessionSearch = ref('')
const editingSessionId = ref(null)
const editingTitle = ref('')

// Notification polling
const pendingTaskCount = ref(0)
const unreadCount = ref(0)
let pollTimer = null

// Refs
const messagesContainer = ref(null)
const inputRef = ref(null)

// Computed
const canSend = computed(() => messageInput.value.trim() && !isSending.value && !isStreaming.value)

const PAGE_SIZE = 50

const loadReasonerPreference = () => {
  try { return localStorage.getItem(REASONER_PREF_KEY) === '1' } catch (_) { return false }
}

const filteredSessions = computed(() => {
  const q = sessionSearch.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter(s => (s?.title || '').toLowerCase().includes(q))
})

// Polling for notifications (from AiFloatingBall)
const pollNotifications = async () => {
  try {
    const [taskResult, unreadResult] = await Promise.allSettled([
      agentTaskApi.listTasks({ projectId: projectId.value }),
      aiChatApi.getUnreadCount({ projectId: projectId.value }),
    ])
    if (taskResult.status === 'fulfilled') {
      pendingTaskCount.value = Array.isArray(taskResult.value) ? taskResult.value.length : 0
    }
    if (unreadResult.status === 'fulfilled') {
      unreadCount.value = unreadResult.value?.count ?? 0
    }
  } catch (_) { /* ignore */ }
}

// Chat methods
const initSession = async () => {
  try {
    if (projectId.value) {
      try {
        const project = await manageApi.getProject(projectId.value)
        projectName.value = project?.name || ''
      } catch (_) { projectName.value = '' }
    } else {
      projectName.value = ''
    }
    session.value = await aiChatApi.getCurrentSession({ projectId: projectId.value })
    await loadMessages()
  } catch (e) {
    console.error('Failed to init session:', e)
  }
}

const loadSessions = async () => {
  isLoadingSessions.value = true
  try {
    sessions.value = await aiChatApi.listSessions({ projectId: projectId.value, limit: 200 })
  } catch (e) {
    console.error('Failed to load sessions:', e)
    sessions.value = []
  } finally {
    isLoadingSessions.value = false
  }
}

const openSession = async (s) => {
  if (!s?.session_id) return
  session.value = {
    session_id: s.session_id,
    project_id: s.project_id ?? projectId.value ?? null,
    user_id: s.user_id,
    title: s.title,
    created_at: s.created_at,
    updated_at: s.updated_at,
  }
  activeTab.value = 'chat'
  await loadMessages()
}

const createNewSession = async () => {
  try {
    const s = await aiChatApi.createSession({ projectId: projectId.value })
    session.value = s
    messages.value = []
    hasMoreHistory.value = true
    streamingContent.value = ''
    streamingThinking.value = ''
    streamingToolCalls.value = []
    streamingTasksCreated.value = []
    activeTab.value = 'chat'
    await nextTick()
    inputRef.value?.focus()
    loadSessions()
  } catch (e) {
    console.error('Failed to create session:', e)
    alert('创建会话失败: ' + e.message)
  }
}

const startEditSessionTitle = (s) => {
  if (!s?.session_id) return
  editingSessionId.value = s.session_id
  editingTitle.value = (s.title || '').toString()
}

const cancelEditSessionTitle = () => {
  editingSessionId.value = null
  editingTitle.value = ''
}

const saveSessionTitle = async (s) => {
  if (!s?.session_id) return
  const title = editingTitle.value.trim()
  try {
    await aiChatApi.updateSession(s.session_id, { title })
    cancelEditSessionTitle()
    await loadSessions()
    if (session.value?.session_id === s.session_id) {
      session.value = { ...(session.value || {}), title }
    }
  } catch (e) {
    console.error('Failed to update session title:', e)
    alert('更新会话标题失败: ' + e.message)
  }
}

const deleteSession = async (s) => {
  if (!s?.session_id) return
  if (!confirm('确定删除该会话及其全部消息？')) return
  try {
    await aiChatApi.deleteSession(s.session_id)
    if (session.value?.session_id === s.session_id) {
      session.value = null
      messages.value = []
      await initSession()
    }
    await loadSessions()
  } catch (e) {
    console.error('Failed to delete session:', e)
    alert('删除会话失败: ' + e.message)
  }
}

const loadMessages = async () => {
  if (!session.value?.session_id) return
  isLoadingMessages.value = true
  try {
    const fetched = await aiChatApi.listMessages({
      sessionId: session.value.session_id,
      limit: PAGE_SIZE,
    })
    messages.value = fetched
    hasMoreHistory.value = fetched.length >= PAGE_SIZE
    await nextTick()
    scrollToBottom()
    if (messages.value.length > 0) {
      await aiChatApi.markRead(session.value.session_id)
    }
  } catch (e) {
    console.error('Failed to load messages:', e)
  } finally {
    isLoadingMessages.value = false
  }
}

const loadMoreHistory = async () => {
  if (!session.value?.session_id || isLoadingMessages.value || isLoadingMore.value || !hasMoreHistory.value || !messages.value.length) return
  const before = messages.value[0]?.created_at
  if (!before) return
  const container = messagesContainer.value
  const prevScrollHeight = container?.scrollHeight || 0
  const prevScrollTop = container?.scrollTop || 0
  isLoadingMore.value = true
  try {
    const older = await aiChatApi.listMessages({
      sessionId: session.value.session_id,
      limit: PAGE_SIZE,
      before,
    })
    if (!older.length) { hasMoreHistory.value = false; return }
    messages.value = [...older, ...messages.value]
    hasMoreHistory.value = older.length >= PAGE_SIZE
    await nextTick()
    if (container) {
      container.scrollTop = prevScrollTop + (container.scrollHeight - prevScrollHeight)
    }
  } catch (e) {
    console.error('Failed to load more history:', e)
  } finally {
    isLoadingMore.value = false
  }
}

const sendMessage = async () => {
  if (!canSend.value || !session.value?.session_id) return
  const content = messageInput.value.trim()
  messageInput.value = ''
  isSending.value = true
  isStreaming.value = true
  streamingContent.value = ''
  streamingThinking.value = ''
  streamingToolCalls.value = []
  streamingTasksCreated.value = []

  const userMessage = {
    message_id: `temp_${Date.now()}`,
    session_id: session.value.session_id,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  }
  messages.value.push(userMessage)
  await nextTick()
  scrollToBottom()

  try {
    const response = await aiChatApi.sendAgentMessageStream({
      sessionId: session.value.session_id,
      content,
      projectId: projectId.value,
      agentId: selectedAgentId.value,
      useThinking: useReasonerMode.value,
    })
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = 'message'
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (currentEvent === 'user_message') {
              const idx = messages.value.findIndex(m => m.message_id === userMessage.message_id)
              if (idx !== -1) messages.value[idx] = data
            } else if (currentEvent === 'token') {
              streamingContent.value += data.content || ''
              await nextTick(); scrollToBottom()
            } else if (currentEvent === 'thinking') {
              streamingThinking.value += data.content || ''
            } else if (currentEvent === 'tool_call') {
              streamingToolCalls.value.push({ id: data.id, name: data.name, arguments: data.arguments })
              await nextTick(); scrollToBottom()
            } else if (currentEvent === 'task_created') {
              streamingTasksCreated.value.push(data)
              loadTasks()
              await nextTick(); scrollToBottom()
            } else if (currentEvent === 'assistant_message') {
              const assistantMsg = {
                ...data,
                metadata: {
                  ...(data.metadata || {}),
                  tool_calls: streamingToolCalls.value,
                  tasks_created: streamingTasksCreated.value,
                },
              }
              messages.value.push(assistantMsg)
              streamingContent.value = ''
              streamingThinking.value = ''
              streamingToolCalls.value = []
              streamingTasksCreated.value = []
              try { await aiChatApi.markRead(session.value.session_id) } catch (_) {}
            } else if (currentEvent === 'error') {
              console.error('Stream error:', data.error)
              if (data.message) messages.value.push(data.message)
            }
          } catch (e) {
            console.warn('Failed to parse SSE data:', line, e)
          }
        }
      }
    }
  } catch (e) {
    console.error('Failed to send message:', e)
    messages.value.push({
      message_id: `error_${Date.now()}`,
      session_id: session.value.session_id,
      role: 'assistant',
      content: `Sorry, an error occurred: ${e.message}`,
      metadata: { error: true },
      created_at: new Date().toISOString(),
    })
  } finally {
    isSending.value = false
    isStreaming.value = false
    streamingContent.value = ''
    streamingThinking.value = ''
    streamingToolCalls.value = []
    streamingTasksCreated.value = []
    await nextTick()
    scrollToBottom()
  }
}

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// Task methods
const loadTasks = async () => {
  isLoadingTasks.value = true
  try {
    tasks.value = await agentTaskApi.listTasks({ projectId: projectId.value })
    pendingTaskCount.value = tasks.value.length
  } catch (e) {
    console.error('Failed to load tasks:', e)
  } finally {
    isLoadingTasks.value = false
  }
}

const approveTask = async (taskId) => {
  processingTaskId.value = taskId
  try {
    await agentTaskApi.approveTask(taskId)
    tasks.value = tasks.value.filter(t => t.task_id !== taskId)
    pendingTaskCount.value = tasks.value.length
  } catch (e) {
    console.error('Failed to approve task:', e)
    alert('批准任务失败: ' + e.message)
  } finally {
    processingTaskId.value = null
  }
}

const rejectTask = async (taskId) => {
  processingTaskId.value = taskId
  try {
    await agentTaskApi.rejectTask(taskId)
    tasks.value = tasks.value.filter(t => t.task_id !== taskId)
    pendingTaskCount.value = tasks.value.length
  } catch (e) {
    console.error('Failed to reject task:', e)
    alert('拒绝任务失败: ' + e.message)
  } finally {
    processingTaskId.value = null
  }
}

// Format
const formatTime = (isoString) => {
  if (!isoString) return ''
  return new Date(isoString).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const formatDate = (isoString) => {
  if (!isoString) return ''
  return new Date(isoString).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const taskTypeLabels = {
  'requirement_create': '创建需求',
  'requirement_update': '更新需求',
  'requirement_delete': '删除需求',
  'project_update': '更新项目',
  'default': '执行操作',
}
const getTaskTypeLabel = (type) => taskTypeLabels[type] || taskTypeLabels['default']

// Watchers
watch(activeTab, (tab) => {
  if (tab === 'chat' && !session.value) initSession()
  else if (tab === 'review' && tasks.value.length === 0) loadTasks()
  else if (tab === 'history' && sessions.value.length === 0) loadSessions()
})

watch(useReasonerMode, (enabled) => {
  try { localStorage.setItem(REASONER_PREF_KEY, enabled ? '1' : '0') } catch (_) {}
})

// Listen for project changes from other pages
const handleProjectChanged = (event) => {
  const newPid = event.detail?.projectId
  if (newPid && newPid !== projectId.value) {
    projectId.value = newPid
  }
}

watch(projectId, () => {
  localStorage.setItem('lastProjectId', projectId.value)
  initSession()
  loadTasks()
  sessions.value = []
  sessionSearch.value = ''
  cancelEditSessionTitle()
})

// Lifecycle
onMounted(() => {
  document.body.classList.add('agent-chat-no-rounded')
  useReasonerMode.value = loadReasonerPreference()
  initSession()
  loadTasks()
  pollNotifications()
  pollTimer = setInterval(pollNotifications, 30000)
  window.addEventListener('project-changed', handleProjectChanged)
  nextTick(() => inputRef.value?.focus())
})

onBeforeUnmount(() => {
  document.body.classList.remove('agent-chat-no-rounded')
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('project-changed', handleProjectChanged)
})
</script>

<template>
  <div class="h-full w-full overflow-hidden flex flex-col"
    style="background: radial-gradient(80rem 60rem at -10% -30%, rgba(99, 102, 241, 0.08), transparent 60%), radial-gradient(80rem 60rem at 110% 0%, rgba(20, 184, 166, 0.06), transparent 62%), linear-gradient(180deg, #fafaf9 0%, #f4f4f5 100%);"
  >
    <div class="flex-1 flex flex-col p-6 md:p-8 min-h-0">
      <div class="flex-1 flex flex-col rounded-none border border-zinc-200/70 bg-white/80 shadow-2xl backdrop-blur-sm overflow-hidden">
        <!-- Header -->
        <header class="px-6 py-4 border-b border-zinc-200/70 bg-white/80">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <!-- Left: Title + Agent selector -->
            <div class="flex items-center gap-4">
              <h2 class="text-xl font-semibold text-zinc-900 tracking-tight flex items-center gap-2">
                <Bot class="w-6 h-6 text-zinc-700" />
                Agent Chat
              </h2>
              <select
                v-model="selectedAgentId"
                class="rounded-none border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-300 cursor-pointer"
              >
                <option v-for="a in agentOptions" :key="a.id" :value="a.id">{{ a.label }}</option>
              </select>
            </div>

            <!-- Center: Tabs -->
            <div class="flex gap-1 bg-zinc-100 rounded-none p-1">
              <button
                @click="activeTab = 'chat'"
                class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-none transition-all"
                :class="activeTab === 'chat' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-700'"
              >
                <MessageSquare class="w-4 h-4" />
                聊天
                <span
                  v-if="unreadCount > 0 && activeTab !== 'chat'"
                  class="ml-1 min-w-4 h-4 px-1 bg-red-500 text-white text-xs rounded-none inline-flex items-center justify-center"
                >{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
              </button>
              <button
                @click="activeTab = 'review'"
                class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-none transition-all"
                :class="activeTab === 'review' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-700'"
              >
                <ClipboardCheck class="w-4 h-4" />
                待审
                <span
                  v-if="pendingTaskCount > 0"
                  class="ml-1 min-w-4 h-4 px-1 bg-red-500 text-white text-xs rounded-none inline-flex items-center justify-center"
                >{{ pendingTaskCount > 99 ? '99+' : pendingTaskCount }}</span>
              </button>
              <button
                @click="activeTab = 'history'"
                class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-none transition-all"
                :class="activeTab === 'history' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-zinc-700'"
              >
                <History class="w-4 h-4" />
                历史
              </button>
            </div>

            <!-- Right: Project display -->
            <div v-if="projectName" class="px-3 py-1.5 rounded-none text-xs text-zinc-600 bg-zinc-100 border border-zinc-200 max-w-[12rem] truncate" :title="projectName">
              {{ projectName }}
            </div>
          </div>
        </header>

        <!-- Chat Tab -->
        <template v-if="activeTab === 'chat'">
          <!-- Messages -->
          <div ref="messagesContainer" class="flex-1 overflow-y-auto p-6 space-y-4">
            <!-- Loading -->
            <div v-if="isLoadingMessages" class="flex justify-center py-16">
              <Loader2 class="w-8 h-8 text-zinc-300 animate-spin" />
            </div>

            <!-- Empty -->
            <div v-else-if="messages.length === 0 && !isStreaming" class="flex flex-col items-center justify-center h-full text-center py-16">
              <div class="w-20 h-20 rounded-none bg-zinc-100 border border-zinc-200 flex items-center justify-center mb-4">
                <MessageSquare class="w-10 h-10 text-zinc-400" />
              </div>
              <p class="text-zinc-500 text-sm">开始与 AI 助手对话</p>
              <p class="text-zinc-400 text-xs mt-1">我可以帮助你分析需求、生成文档等</p>
            </div>

            <!-- Messages list -->
            <template v-else>
              <!-- Load more -->
              <div class="flex justify-center pb-2">
                <button
                  v-if="hasMoreHistory"
                  @click="loadMoreHistory"
                  :disabled="isLoadingMore"
                  class="text-xs text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 px-3 py-1.5 rounded-none transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  <Loader2 v-if="isLoadingMore" class="w-3.5 h-3.5 animate-spin" />
                  <span>{{ isLoadingMore ? '加载中...' : '加载更多历史' }}</span>
                </button>
                <div v-else class="text-[11px] text-zinc-400">已是最早消息</div>
              </div>

              <div v-for="msg in messages" :key="msg.message_id" class="space-y-2">
                <div class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
                  <div
                    class="max-w-[75%] rounded-none px-4 py-3 shadow-sm"
                    :class="msg.role === 'user'
                      ? 'bg-zinc-800 text-white rounded-none'
                      : 'bg-zinc-100 text-zinc-900 border border-zinc-200 rounded-none'"
                  >
                    <div class="text-sm leading-relaxed whitespace-pre-wrap break-words">{{ msg.content }}</div>
                    <div class="text-[10px] mt-1 opacity-60" :class="msg.role === 'user' ? 'text-right' : 'text-left'">
                      {{ formatTime(msg.created_at) }}
                    </div>
                  </div>
                </div>

                <!-- Tool call cards -->
                <div v-if="msg.role === 'assistant' && msg.metadata?.tool_calls?.length" class="space-y-2">
                  <div v-for="tc in msg.metadata.tool_calls" :key="tc.id" class="flex justify-start">
                    <div class="max-w-[90%] rounded-none px-3 py-2 shadow-sm border border-amber-200 bg-amber-50">
                      <div class="text-xs font-medium text-amber-800">tool_call: {{ tc.name }}</div>
                      <div class="text-xs text-zinc-600 mt-1 whitespace-pre-wrap break-words">{{ JSON.stringify(tc.arguments, null, 2) }}</div>
                    </div>
                  </div>
                </div>

                <!-- Task created cards -->
                <div v-if="msg.role === 'assistant' && msg.metadata?.tasks_created?.length" class="space-y-2">
                  <div v-for="task in msg.metadata.tasks_created" :key="task.task_id" class="flex justify-start">
                    <div class="max-w-[90%] rounded-none px-3 py-2 shadow-sm border border-teal-200 bg-teal-50">
                      <div class="text-xs font-medium text-teal-800">已创建待审任务</div>
                      <div class="text-xs text-zinc-800 mt-1">{{ task.title }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Streaming tool calls -->
              <div v-if="isStreaming && streamingToolCalls.length" class="space-y-2">
                <div v-for="tc in streamingToolCalls" :key="tc.id" class="flex justify-start">
                  <div class="max-w-[90%] rounded-none px-3 py-2 shadow-sm border border-amber-200 bg-amber-50">
                    <div class="text-xs font-medium text-amber-800">tool_call: {{ tc.name }}</div>
                    <div class="text-xs text-zinc-600 mt-1 whitespace-pre-wrap break-words">{{ JSON.stringify(tc.arguments, null, 2) }}</div>
                  </div>
                </div>
              </div>

              <!-- Streaming tasks -->
              <div v-if="isStreaming && streamingTasksCreated.length" class="space-y-2">
                <div v-for="task in streamingTasksCreated" :key="task.task_id" class="flex justify-start">
                  <div class="max-w-[90%] rounded-none px-3 py-2 shadow-sm border border-teal-200 bg-teal-50">
                    <div class="text-xs font-medium text-teal-800">已创建待审任务</div>
                    <div class="text-xs text-zinc-800 mt-1">{{ task.title }}</div>
                  </div>
                </div>
              </div>

              <!-- Streaming message -->
              <div v-if="isStreaming && streamingContent" class="flex justify-start">
                <div class="max-w-[75%] bg-zinc-100 text-zinc-900 border border-zinc-200 rounded-none rounded-none px-4 py-3 shadow-sm">
                  <div class="text-sm leading-relaxed whitespace-pre-wrap break-words">
                    {{ streamingContent }}
                    <span class="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse ml-0.5 align-middle"></span>
                  </div>
                </div>
              </div>

              <!-- Typing indicator -->
              <div v-if="isStreaming && !streamingContent" class="flex justify-start">
                <div class="bg-zinc-100 rounded-none rounded-none px-4 py-3 shadow-sm">
                  <div class="flex gap-1">
                    <span class="w-2 h-2 bg-zinc-400 rounded-none animate-bounce" style="animation-delay: 0ms"></span>
                    <span class="w-2 h-2 bg-zinc-400 rounded-none animate-bounce" style="animation-delay: 150ms"></span>
                    <span class="w-2 h-2 bg-zinc-400 rounded-none animate-bounce" style="animation-delay: 300ms"></span>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <!-- Input -->
          <div class="p-4 border-t border-zinc-200/70 bg-zinc-50/50">
            <div class="mb-2 flex items-center justify-between">
              <label class="inline-flex items-center gap-2 text-xs text-zinc-600">
                <input
                  v-model="useReasonerMode"
                  type="checkbox"
                  :disabled="isSending || isStreaming"
                  class="h-3.5 w-3.5 rounded-none border-zinc-300 text-zinc-800 focus:ring-zinc-500 disabled:opacity-60"
                />
                <span>思考模式 (Reasoner)</span>
              </label>
              <span class="text-[11px] text-zinc-500">{{ useReasonerMode ? 'deepseek-reasoner' : 'deepseek-chat' }}</span>
            </div>
            <div class="flex gap-2">
              <textarea
                ref="inputRef"
                v-model="messageInput"
                @keydown="handleKeyDown"
                placeholder="输入消息..."
                rows="1"
                class="flex-1 rounded-none border border-zinc-200 bg-white px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-300 max-h-24"
                :disabled="isSending || isStreaming"
              />
              <button
                @click="sendMessage"
                :disabled="!canSend"
                class="flex items-center justify-center w-10 h-10 bg-zinc-800 hover:bg-zinc-900 text-white rounded-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Loader2 v-if="isSending || isStreaming" class="w-4 h-4 animate-spin" />
                <Send v-else class="w-4 h-4" />
              </button>
            </div>
          </div>
        </template>

        <!-- Review Tab -->
        <template v-if="activeTab === 'review'">
          <div class="flex-1 overflow-y-auto">
            <div v-if="isLoadingTasks" class="flex justify-center py-16">
              <Loader2 class="w-8 h-8 text-zinc-300 animate-spin" />
            </div>

            <div v-else-if="tasks.length === 0" class="flex flex-col items-center justify-center h-full text-center py-16">
              <div class="w-20 h-20 rounded-none bg-zinc-100 border border-zinc-200 flex items-center justify-center mb-4">
                <ClipboardCheck class="w-10 h-10 text-zinc-400" />
              </div>
              <p class="text-zinc-500 text-sm">暂无待审批任务</p>
              <p class="text-zinc-400 text-xs mt-1">Agent 的操作需要你批准后才会执行</p>
            </div>

            <div v-else class="p-4 space-y-3 max-w-3xl mx-auto">
              <div
                v-for="task in tasks"
                :key="task.task_id"
                class="p-4 bg-zinc-50 rounded-none border border-zinc-200"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-medium text-zinc-500 bg-zinc-200 px-2 py-0.5 rounded-none">
                        {{ getTaskTypeLabel(task.task_type) }}
                      </span>
                      <span class="text-xs text-zinc-400">
                        {{ formatDate(task.created_at) }} {{ formatTime(task.created_at) }}
                      </span>
                    </div>
                    <h4 class="font-medium text-sm text-zinc-800 mt-2 truncate">{{ task.title }}</h4>
                    <p v-if="task.description" class="text-xs text-zinc-500 mt-1 line-clamp-2">{{ task.description }}</p>
                  </div>
                </div>
                <div class="flex gap-2 mt-3">
                  <button
                    @click="rejectTask(task.task_id)"
                    :disabled="processingTaskId === task.task_id"
                    class="flex-1 px-3 py-1.5 text-xs font-medium text-zinc-600 bg-white border border-zinc-200 rounded-none hover:bg-zinc-50 transition-colors disabled:opacity-50"
                  >拒绝</button>
                  <button
                    @click="approveTask(task.task_id)"
                    :disabled="processingTaskId === task.task_id"
                    class="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-none transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                  >
                    <Loader2 v-if="processingTaskId === task.task_id" class="w-3 h-3 animate-spin" />
                    批准
                  </button>
                </div>
              </div>
            </div>

            <div class="p-4 border-t border-zinc-100">
              <button
                @click="loadTasks"
                :disabled="isLoadingTasks"
                class="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 rounded-none transition-colors disabled:opacity-50"
              >
                <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoadingTasks }" />
                刷新列表
              </button>
            </div>
          </div>
        </template>

        <!-- History Tab -->
        <template v-if="activeTab === 'history'">
          <div class="flex-1 overflow-y-auto">
            <!-- Toolbar -->
            <div class="p-4 border-b border-zinc-100 bg-zinc-50/50">
              <div class="flex gap-2 max-w-3xl mx-auto">
                <button
                  @click="createNewSession"
                  class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-zinc-800 hover:bg-zinc-900 rounded-none transition-colors"
                >
                  <Plus class="w-4 h-4" />
                  新建
                </button>
                <input
                  v-model="sessionSearch"
                  placeholder="搜索标题..."
                  class="flex-1 rounded-none border border-zinc-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
                />
                <button
                  @click="loadSessions"
                  :disabled="isLoadingSessions"
                  class="w-10 h-10 flex items-center justify-center rounded-none border border-zinc-200 bg-white text-zinc-500 hover:bg-zinc-50 hover:text-zinc-700 transition-colors disabled:opacity-50"
                >
                  <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoadingSessions }" />
                </button>
              </div>
            </div>

            <div v-if="isLoadingSessions" class="flex justify-center py-16">
              <Loader2 class="w-8 h-8 text-zinc-300 animate-spin" />
            </div>

            <div v-else-if="filteredSessions.length === 0" class="flex flex-col items-center justify-center h-full text-center py-16">
              <div class="w-20 h-20 rounded-none bg-zinc-100 border border-zinc-200 flex items-center justify-center mb-4">
                <History class="w-10 h-10 text-zinc-400" />
              </div>
              <p class="text-zinc-500 text-sm">暂无历史会话</p>
              <p class="text-zinc-400 text-xs mt-1">会话与消息会自动保存，可在此查看与管理</p>
            </div>

            <div v-else class="p-4 space-y-2 max-w-3xl mx-auto">
              <div
                v-for="s in filteredSessions"
                :key="s.session_id"
                class="p-4 rounded-none border transition-colors"
                :class="session?.session_id === s.session_id
                  ? 'bg-zinc-100 border-zinc-300'
                  : 'bg-white border-zinc-200 hover:bg-zinc-50'"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <span
                        v-if="session?.session_id === s.session_id"
                        class="text-[10px] font-semibold px-1.5 py-0.5 rounded-none bg-zinc-800 text-white"
                      >当前</span>
                      <span
                        v-if="s.unread_count > 0"
                        class="min-w-4 h-4 px-1 bg-red-500 text-white text-xs rounded-none inline-flex items-center justify-center"
                      >{{ s.unread_count > 99 ? '99+' : s.unread_count }}</span>
                    </div>

                    <div class="mt-2">
                      <div v-if="editingSessionId === s.session_id" class="flex items-center gap-2">
                        <input
                          v-model="editingTitle"
                          class="flex-1 px-2 py-1.5 text-sm rounded-none border border-zinc-200 focus:outline-none focus:ring-2 focus:ring-zinc-300"
                          placeholder="会话标题"
                        />
                        <button @click="saveSessionTitle(s)" class="p-1.5 rounded-none text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700"><Check class="w-4 h-4" /></button>
                        <button @click="cancelEditSessionTitle" class="p-1.5 rounded-none text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700"><X class="w-4 h-4" /></button>
                      </div>
                      <button v-else @click="openSession(s)" class="w-full text-left">
                        <div class="font-medium text-sm text-zinc-800 truncate">{{ s.title || '未命名会话' }}</div>
                        <div class="text-xs text-zinc-500 mt-1 flex items-center gap-2">
                          <span>{{ formatDate(s.updated_at || s.created_at) }} {{ formatTime(s.updated_at || s.created_at) }}</span>
                          <span class="text-zinc-300">&#183;</span>
                          <span>{{ s.message_count || 0 }} 条</span>
                        </div>
                      </button>
                    </div>
                  </div>

                  <div class="flex items-center gap-1">
                    <button v-if="editingSessionId !== s.session_id" @click="startEditSessionTitle(s)" class="p-1.5 rounded-none text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" title="编辑标题">
                      <Pencil class="w-4 h-4" />
                    </button>
                    <button @click="deleteSession(s)" class="p-1.5 rounded-none text-zinc-400 hover:bg-zinc-100 hover:text-red-600" title="删除会话">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style>
/* 强制取消 Agent Chat 页面下所有元素的圆角 */
.agent-chat-no-rounded * {
  border-radius: 0 !important;
}
</style>

