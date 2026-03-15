<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useAuthStore } from '@/stores/auth.js'
import { authApi } from '@/api/auth'
import { mobileChatApi } from '@/api/chat'
import { Smartphone, PlugZap, Radio, Send, RefreshCw, CircleDot } from 'lucide-vue-next'

const authStore = useAuthStore()
authStore.init()

const normalizeUserId = (value) => (value || '').trim() || 'anonymous'
const getAuthUserId = () => (authStore.user?.user_id || '').trim()
const getSessionStorageKey = (userId) => `mobile_chat_session_id::${normalizeUserId(userId)}`
const getStoredSessionId = (userId) =>
    localStorage.getItem(getSessionStorageKey(userId)) || 'default'
const getInitialUserId = () => normalizeUserId(getAuthUserId() || localStorage.getItem('mobile_chat_user_id') || 'anonymous')

const selectedUserId = ref(
    getInitialUserId()
)
const sessionId = ref(getStoredSessionId(selectedUserId.value))
const messageInput = ref('')
const messages = ref([])
const isLoading = ref(false)
const isSending = ref(false)
const sessions = ref([])
const isLoadingSessions = ref(false)
const isLoadingUsers = ref(false)
const sseStatus = ref('disconnected')
const lastEventAt = ref(null)
const userOptions = ref([])

let eventSource = null
const messageIdSet = new Set()

const statusLabel = computed(() => {
    if (sseStatus.value === 'connected') return 'Connected'
    if (sseStatus.value === 'connecting') return 'Connecting'
    if (sseStatus.value === 'error') return 'Error'
    return 'Disconnected'
})

const statusClass = computed(() => {
    if (sseStatus.value === 'connected') return 'bg-green-100 text-green-700 border-green-200'
    if (sseStatus.value === 'connecting') return 'bg-yellow-100 text-yellow-700 border-yellow-200'
    if (sseStatus.value === 'error') return 'bg-red-100 text-red-700 border-red-200'
    return 'bg-zinc-100 text-zinc-600 border-zinc-200'
})

const formatTime = (isoString) => {
    if (!isoString) return '-'
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    })
}

const addMessage = (msg) => {
    if (!msg?.message_id) return
    if (messageIdSet.has(msg.message_id)) return
    messageIdSet.add(msg.message_id)
    messages.value.push(msg)
}

const activeUserId = () => {
    const normalized = normalizeUserId(resolveUserId(selectedUserId.value))
    if (normalized !== selectedUserId.value) {
        selectedUserId.value = normalized
    }
    return normalized
}

const buildUserOptions = (list) => {
    const byId = new Map()
    ;(list || []).forEach((user) => {
        const userId = (user?.user_id || '').trim()
        if (!userId) return
        if (!byId.has(userId)) {
            byId.set(userId, {
                user_id: userId,
                username: (user?.username || '').trim(),
                display_name: (user?.display_name || '').trim(),
            })
        }
    })
    return Array.from(byId.values())
}

function resolveUserId(value) {
    const raw = (value || '').trim()
    if (!raw) return ''

    const matchedById = userOptions.value.find((user) => user.user_id === raw)
    if (matchedById) return matchedById.user_id

    const matchedByUsername = userOptions.value.find((user) => user.username === raw)
    return matchedByUsername?.user_id || raw
}

const formatUserOptionLabel = (user) => {
    const userId = user?.user_id || ''
    const desc = user?.display_name || user?.username || ''
    return desc ? `${userId} (${desc})` : userId
}

const ensureCurrentUserInOptions = () => {
    const uid = activeUserId()
    if (!uid) return
    if (!userOptions.value.some((user) => user.user_id === uid)) {
        userOptions.value = [
            {
                user_id: uid,
                username: '',
                display_name: '',
            },
            ...userOptions.value,
        ]
    }
}

const collectUsers = async (requestUsers, pageSize = 500, maxPages = 20) => {
    const users = []
    let offset = 0
    let total = Number.POSITIVE_INFINITY

    for (let page = 0; page < maxPages && offset < total; page += 1) {
        const result = await requestUsers({ limit: pageSize, offset })
        const pageUsers = result?.users || []
        const declaredTotal = Number(result?.total)

        if (Number.isFinite(declaredTotal)) {
            total = declaredTotal
        }

        if (!pageUsers.length) {
            break
        }

        users.push(...pageUsers)
        offset += pageUsers.length

        if (!Number.isFinite(declaredTotal) && pageUsers.length < pageSize) {
            break
        }
    }

    return users
}

const collectRegistrations = async (status, pageSize = 200, maxPages = 20) => {
    const registrations = []
    let offset = 0
    let total = Number.POSITIVE_INFINITY

    for (let page = 0; page < maxPages && offset < total; page += 1) {
        const result = await authApi.listRegistrations({ status, limit: pageSize, offset })
        const pageRegistrations = result?.registrations || []
        const declaredTotal = Number(result?.total)

        if (Number.isFinite(declaredTotal)) {
            total = declaredTotal
        }

        if (!pageRegistrations.length) {
            break
        }

        registrations.push(...pageRegistrations)
        offset += pageRegistrations.length

        if (!Number.isFinite(declaredTotal) && pageRegistrations.length < pageSize) {
            break
        }
    }

    return registrations
}

const loadUserOptions = async () => {
    isLoadingUsers.value = true
    try {
        let users = []

        try {
            users = await collectUsers(({ limit, offset }) => authApi.listUserDirectory({ limit, offset }), 500)
        } catch (directoryError) {
            console.warn('加载用户目录失败，尝试管理员用户列表接口', directoryError)
            users = await collectUsers(({ limit, offset }) => authApi.listUsers({ limit, offset }), 200)
        }

        if (['super_admin', 'admin'].includes(authStore.user?.role)) {
            try {
                const [pendingUsers, approvedUsers, rejectedUsers] = await Promise.all([
                    collectRegistrations('pending'),
                    collectRegistrations('approved'),
                    collectRegistrations('rejected'),
                ])
                users = [
                    ...users,
                    ...pendingUsers,
                    ...approvedUsers,
                    ...rejectedUsers,
                ]
            } catch (registrationError) {
                console.warn('加载注册用户失败，仅显示已获取用户列表', registrationError)
            }
        }

        userOptions.value = buildUserOptions(users)

        const resolvedUserId = normalizeUserId(resolveUserId(selectedUserId.value))
        if (resolvedUserId !== selectedUserId.value) {
            selectedUserId.value = resolvedUserId
        }

        ensureCurrentUserInOptions()
    } catch (e) {
        console.warn('加载用户列表失败，切换为手动输入模式', e)
        ensureCurrentUserInOptions()
    } finally {
        isLoadingUsers.value = false
    }
}

const loadSessions = async () => {
    isLoadingSessions.value = true
    try {
        const list = await mobileChatApi.listSessions({
            userId: activeUserId(),
            limit: 200,
        })
        sessions.value = list || []
    } catch (e) {
        console.error('加载会话列表失败', e)
        alert('加载会话列表失败: ' + (e.message || e))
    } finally {
        isLoadingSessions.value = false
    }
}

const loadHistory = async () => {
    if (!sessionId.value.trim()) return
    isLoading.value = true
    try {
        const list = await mobileChatApi.listMessages({
            userId: activeUserId(),
            sessionId: sessionId.value.trim(),
            limit: 200,
        })
        messages.value = list || []
        messageIdSet.clear()
        messages.value.forEach((m) => {
            if (m?.message_id) messageIdSet.add(m.message_id)
        })
    } catch (e) {
        console.error('加载移动端消息失败', e)
        alert('加载移动端消息失败: ' + (e.message || e))
    } finally {
        isLoading.value = false
    }
}

const connectSSE = () => {
    if (!sessionId.value.trim()) {
        alert('请输入 session_id')
        return
    }
    disconnectSSE()
    sseStatus.value = 'connecting'
    eventSource = mobileChatApi.createSSEConnection(sessionId.value.trim(), activeUserId())

    eventSource.addEventListener('connected', (evt) => {
        sseStatus.value = 'connected'
        lastEventAt.value = new Date().toISOString()
        if (evt?.data) {
            try {
                const payload = JSON.parse(evt.data)
                if (payload?.session_id) sessionId.value = payload.session_id
                if (payload?.user_id) selectedUserId.value = normalizeUserId(payload.user_id)
            } catch (e) {
                // ignore
            }
        }
    })

    eventSource.addEventListener('message', (evt) => {
        lastEventAt.value = new Date().toISOString()
        if (!evt?.data) return
        try {
            const msg = JSON.parse(evt.data)
            addMessage(msg)
        } catch (e) {
            console.error('SSE JSON parse error', e)
        }
    })

    eventSource.addEventListener('heartbeat', () => {
        lastEventAt.value = new Date().toISOString()
    })

    eventSource.onerror = () => {
        sseStatus.value = 'error'
    }
}

const disconnectSSE = () => {
    if (eventSource) {
        eventSource.close()
        eventSource = null
    }
    sseStatus.value = 'disconnected'
}

const activateSession = async () => {
    if (!sessionId.value.trim()) {
        alert('请输入 session_id')
        return
    }
    await loadHistory()
    connectSSE()
}

const useSession = async (sid) => {
    if (!sid) return
    sessionId.value = sid
    await activateSession()
}

const sendMessage = async () => {
    if (!sessionId.value.trim()) {
        alert('请输入 session_id')
        return
    }
    if (!messageInput.value.trim()) return
    isSending.value = true
    try {
        const msg = await mobileChatApi.sendMessage({
            userId: activeUserId(),
            sessionId: sessionId.value.trim(),
            sender: 'web',
            content: messageInput.value.trim(),
        })
        addMessage(msg)
        messageInput.value = ''
        loadSessions()
    } catch (e) {
        console.error('发送消息失败', e)
        alert('发送消息失败: ' + (e.message || e))
    } finally {
        isSending.value = false
    }
}

watch(sessionId, (val) => {
    localStorage.setItem(getSessionStorageKey(activeUserId()), val || '')
})

watch(selectedUserId, async (val, oldVal) => {
    const normalized = normalizeUserId(resolveUserId(val))
    if (normalized !== val) {
        selectedUserId.value = normalized
        return
    }
    if (normalized === oldVal) return

    localStorage.setItem('mobile_chat_user_id', normalized)
    ensureCurrentUserInOptions()

    disconnectSSE()
    messages.value = []
    messageIdSet.clear()
    sessionId.value = getStoredSessionId(normalized)

    await loadSessions()
    await activateSession()
})

onMounted(async () => {
    localStorage.setItem('mobile_chat_user_id', activeUserId())
    await loadUserOptions()
    await loadSessions()
    await activateSession()
})

onBeforeUnmount(() => {
    disconnectSSE()
})
</script>

<template>
    <div class="h-full w-full overflow-y-auto">
        <div class="flex flex-col min-h-full max-w-6xl mx-auto px-6 py-8 gap-6">
            <div class="flex items-center justify-between">
                <div>
                    <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight flex items-center gap-2">
                        <Smartphone class="w-7 h-7" />
                        Mobile Bridge
                    </h2>
                    <p class="text-zinc-500 mt-2 text-sm">实时接收移动端消息，并支持网页端发送。</p>
                </div>
                <div class="flex items-center gap-2">
                    <span :class="`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${statusClass}`">
                        <CircleDot class="w-3 h-3" />
                        {{ statusLabel }}
                    </span>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="space-y-6">
                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="flex items-center gap-2 text-sm font-semibold text-zinc-700 mb-4">
                            <PlugZap class="w-4 h-4 text-zinc-500" />
                            Connection
                        </div>
                        <div class="flex items-center justify-between mb-2">
                            <label class="block text-xs font-semibold text-zinc-400 uppercase tracking-wider">User ID</label>
                            <button @click="loadUserOptions" :disabled="isLoadingUsers"
                                class="flex items-center gap-2 px-2 py-1 border border-zinc-200 rounded-lg text-[11px] hover:bg-zinc-50 transition-colors disabled:opacity-50">
                                <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': isLoadingUsers }" />
                                Users
                            </button>
                        </div>
                        <select v-model="selectedUserId"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-zinc-200">
                            <option
                                v-for="user in userOptions"
                                :key="user.user_id"
                                :value="user.user_id">
                                {{ formatUserOptionLabel(user) }}
                            </option>
                        </select>

                        <label class="mt-4 block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Session ID</label>
                        <input v-model="sessionId" type="text" placeholder="e.g. mobile-demo"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200" />
                        <div class="mt-4 flex items-center gap-2">
                            <button @click="activateSession"
                                class="flex items-center gap-2 px-3 py-2 bg-zinc-900 text-white rounded-lg text-sm hover:bg-zinc-800 transition-colors">
                                <Radio class="w-4 h-4" />
                                Connect
                            </button>
                            <button @click="disconnectSSE"
                                class="px-3 py-2 border border-zinc-200 rounded-lg text-sm hover:bg-zinc-50 transition-colors">
                                Disconnect
                            </button>
                        </div>
                        <div class="mt-4 text-xs text-zinc-500">
                            Last event: <span class="font-medium text-zinc-700">{{ formatTime(lastEventAt) }}</span>
                        </div>
                        <div class="mt-1 text-xs text-zinc-500">
                            Context: <span class="font-medium text-zinc-700">User {{ selectedUserId }}</span> |
                            <span class="font-medium text-zinc-700">Session {{ sessionId }}</span>
                        </div>
                    </div>

                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="flex items-center justify-between mb-4">
                            <div class="flex items-center gap-2 text-sm font-semibold text-zinc-700">
                                <PlugZap class="w-4 h-4 text-zinc-500" />
                                Sessions
                            </div>
                            <button @click="loadSessions" :disabled="isLoadingSessions"
                                class="flex items-center gap-2 px-3 py-1.5 border border-zinc-200 rounded-lg text-xs hover:bg-zinc-50 transition-colors disabled:opacity-50">
                                <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': isLoadingSessions }" />
                                Refresh
                            </button>
                        </div>
                        <div v-if="sessions.length === 0" class="text-xs text-zinc-400">
                            暂无会话，发送消息后自动出现。
                        </div>
                        <div v-else class="space-y-2 max-h-56 overflow-y-auto">
                            <button
                                v-for="session in sessions"
                                :key="session.session_id"
                                @click="useSession(session.session_id)"
                                class="w-full text-left px-3 py-2 rounded-lg border transition-colors"
                                :class="session.session_id === sessionId
                                    ? 'border-zinc-900 bg-zinc-900 text-white'
                                    : 'border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'">
                                <div class="flex items-center justify-between gap-2 text-xs">
                                    <span class="font-semibold">{{ session.session_id }}</span>
                                    <span class="opacity-80">{{ session.message_count }} msgs</span>
                                </div>
                                <div class="text-[11px] opacity-80 mt-1">
                                    Last: {{ formatTime(session.last_message_at) }}
                                </div>
                            </button>
                        </div>
                    </div>

                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="flex items-center justify-between mb-4">
                            <div class="flex items-center gap-2 text-sm font-semibold text-zinc-700">
                                <RefreshCw class="w-4 h-4 text-zinc-500" />
                                History
                            </div>
                            <button @click="loadHistory" :disabled="isLoading"
                                class="flex items-center gap-2 px-3 py-1.5 border border-zinc-200 rounded-lg text-xs hover:bg-zinc-50 transition-colors disabled:opacity-50">
                                <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': isLoading }" />
                                Reload
                            </button>
                        </div>
                        <p class="text-xs text-zinc-500">加载最近 200 条消息记录用于回放。</p>
                    </div>

                    <div class="p-5 bg-white border border-zinc-200 rounded-xl shadow-sm">
                        <div class="flex items-center gap-2 text-sm font-semibold text-zinc-700 mb-4">
                            <Send class="w-4 h-4 text-zinc-500" />
                            Send Message
                        </div>
                        <textarea v-model="messageInput" rows="3" placeholder="输入要发送的消息..."
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200 resize-none"></textarea>
                        <button @click="sendMessage" :disabled="isSending || !messageInput.trim()"
                            class="mt-3 flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-lg text-sm hover:bg-zinc-800 transition-colors disabled:opacity-50">
                            <Send class="w-4 h-4" />
                            Send
                        </button>
                    </div>
                </div>

                <div class="lg:col-span-2 flex flex-col">
                    <div class="p-4 bg-white border border-zinc-200 rounded-xl shadow-sm flex items-center justify-between">
                        <div class="text-sm font-semibold text-zinc-700">Live Feed</div>
                        <div class="text-xs text-zinc-500">Total: {{ messages.length }}</div>
                    </div>
                    <div class="mt-4 flex-1 bg-zinc-50 border border-zinc-200 rounded-xl p-4 overflow-y-auto max-h-[60vh]">
                        <div v-if="messages.length === 0" class="text-center text-zinc-400 py-12">
                            暂无消息，等待移动端推送…
                        </div>
                        <div v-else class="space-y-3">
                            <div v-for="msg in messages" :key="msg.message_id"
                                class="flex" :class="msg.sender === 'web' ? 'justify-end' : 'justify-start'">
                                <div
                                    :class="msg.sender === 'web'
                                        ? 'bg-zinc-900 text-white border-zinc-900'
                                        : 'bg-white text-zinc-800 border-zinc-200'"
                                    class="max-w-[70%] border rounded-2xl px-4 py-3 shadow-sm">
                                    <div class="flex items-center justify-between gap-3 text-xs mb-1 opacity-80">
                                        <span class="font-semibold uppercase tracking-wide">{{ msg.sender }}</span>
                                        <span>{{ formatTime(msg.created_at) }}</span>
                                    </div>
                                    <div class="text-sm leading-relaxed whitespace-pre-wrap">{{ msg.content }}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

