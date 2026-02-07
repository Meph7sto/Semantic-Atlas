<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { X, Minus, MessageSquare, ClipboardCheck, Send, Loader2, RefreshCw } from 'lucide-vue-next'
import { aiChatApi, agentTaskApi } from '../../utils/api'

const props = defineProps({
    projectId: {
        type: String,
        default: null,
    },
    anchorSide: {
        type: String,
        default: 'right',
    },
    unreadCount: {
        type: Number,
        default: 0,
    },
    pendingTaskCount: {
        type: Number,
        default: 0,
    },
})

const emit = defineEmits(['close', 'minimize', 'messages-read', 'task-resolved'])

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

// Task state
const tasks = ref([])
const isLoadingTasks = ref(false)
const processingTaskId = ref(null)

// Refs
const messagesContainer = ref(null)
const inputRef = ref(null)

// Computed
const canSend = computed(() => messageInput.value.trim() && !isSending.value && !isStreaming.value)

const panelPositionClass = computed(() => (props.anchorSide === 'left' ? 'left-0' : 'right-0'))

const PAGE_SIZE = 50

const markSessionReadIfNeeded = async () => {
    if (!session.value?.session_id) return
    if (!props.unreadCount) return
    try {
        const marked = await aiChatApi.markRead(session.value.session_id)
        if (marked > 0) emit('messages-read')
    } catch (e) {
        console.warn('Failed to mark messages read:', e)
    }
}

// Chat methods
const initSession = async () => {
    try {
        session.value = await aiChatApi.getCurrentSession({ projectId: props.projectId })
        await loadMessages()
    } catch (e) {
        console.error('Failed to init session:', e)
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
        
        // Mark as read
        if (messages.value.length > 0) {
            await aiChatApi.markRead(session.value.session_id)
            emit('messages-read')
        }
    } catch (e) {
        console.error('Failed to load messages:', e)
    } finally {
        isLoadingMessages.value = false
    }
}

const loadMoreHistory = async () => {
    if (!session.value?.session_id) return
    if (isLoadingMessages.value || isLoadingMore.value) return
    if (!hasMoreHistory.value) return
    if (!messages.value.length) return

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
        if (!older.length) {
            hasMoreHistory.value = false
            return
        }

        messages.value = [...older, ...messages.value]
        hasMoreHistory.value = older.length >= PAGE_SIZE

        await nextTick()
        if (container) {
            const newScrollHeight = container.scrollHeight
            container.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
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
    
    // Add user message optimistically
    const userMessage = {
        message_id: `temp_${Date.now()}`,
        session_id: session.value.session_id,
        role: 'user',
        content: content,
        created_at: new Date().toISOString(),
    }
    messages.value.push(userMessage)
    await nextTick()
    scrollToBottom()
    
    try {
        const response = await aiChatApi.sendMessageStream({
            sessionId: session.value.session_id,
            content: content,
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
                            // Update temp user message with real one
                            const idx = messages.value.findIndex(m => m.message_id === userMessage.message_id)
                            if (idx !== -1) {
                                messages.value[idx] = data
                            }
                        } else if (currentEvent === 'token') {
                            streamingContent.value += data.content || ''
                            await nextTick()
                            scrollToBottom()
                        } else if (currentEvent === 'thinking') {
                            streamingThinking.value += data.content || ''
                        } else if (currentEvent === 'assistant_message') {
                            // Add final assistant message
                            messages.value.push(data)
                            streamingContent.value = ''
                            streamingThinking.value = ''
                            try {
                                await aiChatApi.markRead(session.value.session_id)
                            } catch (e) {
                                console.warn('Failed to mark assistant reply read:', e)
                            }
                            emit('messages-read')
                        } else if (currentEvent === 'error') {
                            console.error('Stream error:', data.error)
                            if (data.message) {
                                messages.value.push(data.message)
                            }
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE data:', line, e)
                    }
                }
            }
        }
    } catch (e) {
        console.error('Failed to send message:', e)
        // Add error message
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
        tasks.value = await agentTaskApi.listTasks({ projectId: props.projectId })
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
        emit('task-resolved')
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
        emit('task-resolved')
    } catch (e) {
        console.error('Failed to reject task:', e)
        alert('拒绝任务失败: ' + e.message)
    } finally {
        processingTaskId.value = null
    }
}

// Format time
const formatTime = (isoString) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const formatDate = (isoString) => {
    if (!isoString) return ''
    const date = new Date(isoString)
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// Task type labels
const taskTypeLabels = {
    'requirement_create': '创建需求',
    'requirement_update': '更新需求',
    'requirement_delete': '删除需求',
    'project_update': '更新项目',
    'default': '执行操作',
}

const getTaskTypeLabel = (type) => taskTypeLabels[type] || taskTypeLabels['default']

// Watch tab changes
watch(activeTab, (tab) => {
    if (tab === 'chat' && !session.value) {
        initSession()
    } else if (tab === 'chat' && session.value) {
        markSessionReadIfNeeded()
    } else if (tab === 'review' && tasks.value.length === 0) {
        loadTasks()
    }
})

watch(
    () => props.unreadCount,
    () => {
        if (activeTab.value === 'chat') markSessionReadIfNeeded()
    }
)

// Lifecycle
onMounted(() => {
    initSession()
    loadTasks()
    nextTick(() => {
        inputRef.value?.focus()
    })
})

onBeforeUnmount(() => {
    // Best-effort: if user closes while on chat tab, clear unread.
    if (activeTab.value === 'chat') {
        markSessionReadIfNeeded()
    }
})
</script>

<template>
    <div
        class="ai-panel absolute bottom-16 w-[min(24rem,calc(100vw-2rem))] h-[min(32rem,calc(100vh-6rem))] rounded-2xl shadow-2xl border flex flex-col overflow-hidden"
        :class="panelPositionClass"
    >
        <!-- Header -->
        <div class="ai-panel-header flex items-center justify-between px-4 py-3 border-b">
            <div class="flex gap-1">
                <button
                    @click="activeTab = 'chat'"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                    :class="activeTab === 'chat' 
                        ? 'ai-tab-active' 
                        : 'ai-tab'"
                >
                    <MessageSquare class="w-4 h-4" />
                    聊天
                    <span
                        v-if="unreadCount > 0 && activeTab !== 'chat'"
                        class="ai-badge ml-1 min-w-4 h-4 px-1 text-white text-xs rounded-full flex items-center justify-center"
                    >
                        {{ unreadCount > 99 ? '99+' : unreadCount }}
                    </span>
                </button>
                <button
                    @click="activeTab = 'review'"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
                    :class="activeTab === 'review' 
                        ? 'ai-tab-active' 
                        : 'ai-tab'"
                >
                    <ClipboardCheck class="w-4 h-4" />
                    待审
                    <span
                        v-if="pendingTaskCount > 0"
                        class="ai-badge ml-1 min-w-4 h-4 px-1 text-white text-xs rounded-full flex items-center justify-center"
                    >
                        {{ pendingTaskCount > 99 ? '99+' : pendingTaskCount }}
                    </span>
                </button>
            </div>
            <div class="flex items-center gap-1">
                <button
                    @click="$emit('minimize')"
                    class="ai-icon-btn p-1.5 rounded-lg transition-colors"
                    title="最小化"
                >
                    <Minus class="w-4 h-4" />
                </button>
                <button
                    @click="$emit('close')"
                    class="ai-icon-btn p-1.5 rounded-lg transition-colors"
                    title="关闭"
                >
                    <X class="w-4 h-4" />
                </button>
            </div>
        </div>

        <!-- Chat Tab -->
        <template v-if="activeTab === 'chat'">
            <!-- Messages -->
            <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-3 ai-panel-body">
                <!-- Loading -->
                <div v-if="isLoadingMessages" class="flex justify-center py-8">
                    <Loader2 class="w-6 h-6 text-zinc-400 animate-spin" />
                </div>

                <!-- Empty state -->
                <div v-else-if="messages.length === 0 && !isStreaming" class="flex flex-col items-center justify-center h-full text-center py-8">
                    <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4 ai-empty-icon">
                        <MessageSquare class="w-8 h-8" style="color: var(--ink-500);" />
                    </div>
                    <p class="text-zinc-500 text-sm">开始与 AI 助手对话</p>
                    <p class="text-zinc-400 text-xs mt-1">我可以帮助你分析需求、生成文档等</p>
                </div>

                <!-- Messages list -->
                <template v-else>
                    <!-- Load more -->
                    <div class="flex justify-center pb-1">
                        <button
                            v-if="hasMoreHistory"
                            @click="loadMoreHistory"
                            :disabled="isLoadingMore"
                            class="text-xs text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
                        >
                            <Loader2 v-if="isLoadingMore" class="w-3.5 h-3.5 animate-spin" />
                            <span>{{ isLoadingMore ? '加载中...' : '加载更多历史' }}</span>
                        </button>
                        <div v-else class="text-[11px] text-zinc-400">已是最早消息</div>
                    </div>

                    <div
                        v-for="msg in messages"
                        :key="msg.message_id"
                        class="flex"
                        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
                    >
                        <div
                            class="max-w-[85%] rounded-2xl px-4 py-2.5 shadow-sm"
                            :class="msg.role === 'user'
                                ? 'ai-bubble-user text-white rounded-br-md'
                                : 'ai-bubble-assistant rounded-bl-md'"
                        >
                            <div class="text-sm leading-relaxed whitespace-pre-wrap break-words">{{ msg.content }}</div>
                            <div 
                                class="text-[10px] mt-1 opacity-60"
                                :class="msg.role === 'user' ? 'text-right' : 'text-left'"
                            >
                                {{ formatTime(msg.created_at) }}
                            </div>
                        </div>
                    </div>

                    <!-- Streaming message -->
                    <div v-if="isStreaming && streamingContent" class="flex justify-start">
                        <div class="max-w-[85%] ai-bubble-assistant rounded-2xl rounded-bl-md px-4 py-2.5 shadow-sm">
                            <div class="text-sm leading-relaxed whitespace-pre-wrap break-words">
                                {{ streamingContent }}
                                <span class="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse ml-0.5 align-middle"></span>
                            </div>
                        </div>
                    </div>

                    <!-- Typing indicator -->
                    <div v-if="isStreaming && !streamingContent" class="flex justify-start">
                        <div class="bg-zinc-100 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                            <div class="flex gap-1">
                                <span class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                                <span class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                                <span class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                            </div>
                        </div>
                    </div>
                </template>
            </div>

            <!-- Input -->
            <div class="ai-input-bar p-3 border-t">
                <div class="flex gap-2">
                    <textarea
                        ref="inputRef"
                        v-model="messageInput"
                        @keydown="handleKeyDown"
                        placeholder="输入消息..."
                        rows="1"
                        class="ai-textarea flex-1 px-3 py-2 text-sm rounded-xl resize-none focus:outline-none focus:ring-2 max-h-24"
                        :disabled="isSending || isStreaming"
                    />
                    <button
                        @click="sendMessage"
                        :disabled="!canSend"
                        class="ai-send-btn flex items-center justify-center w-10 h-10 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
                <!-- Loading -->
                <div v-if="isLoadingTasks" class="flex justify-center py-8">
                    <Loader2 class="w-6 h-6 text-zinc-400 animate-spin" />
                </div>

                <!-- Empty state -->
                <div v-else-if="tasks.length === 0" class="flex flex-col items-center justify-center h-full text-center py-8">
                    <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4 ai-empty-icon">
                        <ClipboardCheck class="w-8 h-8" style="color: var(--teal);" />
                    </div>
                    <p class="text-zinc-500 text-sm">暂无待审批任务</p>
                    <p class="text-zinc-400 text-xs mt-1">Agent 的操作需要你批准后才会执行</p>
                </div>

                <!-- Tasks list -->
                <div v-else class="p-3 space-y-2">
                    <div
                        v-for="task in tasks"
                        :key="task.task_id"
                        class="p-3 bg-zinc-50 rounded-xl border border-zinc-100"
                    >
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-2">
                                    <span class="text-xs font-medium text-zinc-500 bg-zinc-200 px-2 py-0.5 rounded">
                                        {{ getTaskTypeLabel(task.task_type) }}
                                    </span>
                                    <span class="text-xs text-zinc-400">
                                        {{ formatDate(task.created_at) }} {{ formatTime(task.created_at) }}
                                    </span>
                                </div>
                                <h4 class="font-medium text-sm text-zinc-800 mt-1.5 truncate">{{ task.title }}</h4>
                                <p v-if="task.description" class="text-xs text-zinc-500 mt-1 line-clamp-2">
                                    {{ task.description }}
                                </p>
                            </div>
                        </div>
                        <div class="flex gap-2 mt-3">
                            <button
                                @click="rejectTask(task.task_id)"
                                :disabled="processingTaskId === task.task_id"
                                class="flex-1 px-3 py-1.5 text-xs font-medium text-zinc-600 bg-white border border-zinc-200 rounded-lg hover:bg-zinc-50 transition-colors disabled:opacity-50"
                            >
                                拒绝
                            </button>
                            <button
                                @click="approveTask(task.task_id)"
                                :disabled="processingTaskId === task.task_id"
                                class="ai-approve-btn flex-1 px-3 py-1.5 text-xs font-medium text-white rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                            >
                                <Loader2 v-if="processingTaskId === task.task_id" class="w-3 h-3 animate-spin" />
                                批准
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Refresh button -->
                <div class="p-3 border-t border-zinc-100">
                    <button
                        @click="loadTasks"
                        :disabled="isLoadingTasks"
                        class="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 rounded-lg transition-colors disabled:opacity-50"
                    >
                        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoadingTasks }" />
                        刷新列表
                    </button>
                </div>
            </div>
        </template>
    </div>
</template>

<style scoped>
.ai-panel {
  background: linear-gradient(135deg, rgba(247, 242, 232, 0.98) 0%, rgba(239, 229, 212, 0.96) 100%);
  border-color: rgba(158, 171, 180, 0.45);
  color: var(--ink-950);
}

.ai-panel-header {
  background: radial-gradient(circle at 12% 18%, rgba(196, 105, 47, 0.14), transparent 55%),
    linear-gradient(135deg, rgba(247, 242, 232, 0.92) 0%, rgba(239, 229, 212, 0.92) 100%);
  border-bottom-color: rgba(158, 171, 180, 0.35);
}

.ai-panel-body {
  background: transparent;
}

.ai-tab {
  color: var(--ink-700);
}

.ai-tab:hover {
  background: rgba(27, 39, 48, 0.06);
}

.ai-tab-active {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  color: #fff;
}

.ai-badge {
  background: var(--signal);
}

.ai-icon-btn {
  color: var(--ink-500);
}

.ai-icon-btn:hover {
  color: var(--ink-900);
  background: rgba(27, 39, 48, 0.06);
}

.ai-bubble-user {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
}

.ai-bubble-assistant {
  background: rgba(35, 50, 61, 0.08);
  color: var(--ink-950);
  border: 1px solid rgba(158, 171, 180, 0.25);
}

.ai-empty-icon {
  background: rgba(35, 50, 61, 0.06);
  border: 1px solid rgba(158, 171, 180, 0.25);
}

.ai-input-bar {
  background: rgba(247, 242, 232, 0.92);
  border-top-color: rgba(158, 171, 180, 0.35);
}

.ai-textarea {
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(158, 171, 180, 0.55);
  color: var(--ink-950);
}

.ai-textarea::placeholder {
  color: rgba(93, 107, 118, 0.75);
}

.ai-textarea:focus {
  border-color: rgba(196, 105, 47, 0.65);
  box-shadow: 0 0 0 4px rgba(196, 105, 47, 0.18);
}

.ai-send-btn {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
}

.ai-send-btn:hover:not(:disabled) {
  filter: saturate(1.05);
}

.ai-approve-btn {
  background: linear-gradient(135deg, var(--teal) 0%, color-mix(in srgb, var(--teal) 78%, #0b3b3f 22%) 100%);
}

.ai-approve-btn:hover:not(:disabled) {
  filter: saturate(1.05);
}
</style>
