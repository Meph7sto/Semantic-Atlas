<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { mobileChatApi } from '../../utils/api'
import { Smartphone, PlugZap, Radio, Send, RefreshCw, CircleDot } from 'lucide-vue-next'

const sessionId = ref(localStorage.getItem('mobile_chat_session_id') || 'default')
const messageInput = ref('')
const messages = ref([])
const isLoading = ref(false)
const isSending = ref(false)
const sseStatus = ref('disconnected')
const lastEventAt = ref(null)

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

const loadHistory = async () => {
    if (!sessionId.value.trim()) return
    isLoading.value = true
    try {
        const list = await mobileChatApi.listMessages({
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
    eventSource = mobileChatApi.createSSEConnection(sessionId.value.trim())

    eventSource.addEventListener('connected', (evt) => {
        sseStatus.value = 'connected'
        lastEventAt.value = new Date().toISOString()
        if (evt?.data) {
            try {
                const payload = JSON.parse(evt.data)
                if (payload?.session_id) sessionId.value = payload.session_id
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

const sendMessage = async () => {
    if (!sessionId.value.trim()) {
        alert('请输入 session_id')
        return
    }
    if (!messageInput.value.trim()) return
    isSending.value = true
    try {
        const msg = await mobileChatApi.sendMessage({
            sessionId: sessionId.value.trim(),
            sender: 'web',
            content: messageInput.value.trim(),
        })
        addMessage(msg)
        messageInput.value = ''
    } catch (e) {
        console.error('发送消息失败', e)
        alert('发送消息失败: ' + (e.message || e))
    } finally {
        isSending.value = false
    }
}

watch(sessionId, (val) => {
    localStorage.setItem('mobile_chat_session_id', val || '')
})

onMounted(async () => {
    await loadHistory()
    connectSSE()
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
                        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Session ID</label>
                        <input v-model="sessionId" type="text" placeholder="e.g. mobile-demo"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200" />
                        <div class="mt-4 flex items-center gap-2">
                            <button @click="connectSSE"
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
