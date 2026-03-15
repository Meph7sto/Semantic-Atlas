<script setup>
import { ref, onMounted, computed } from 'vue'
import { pushApi } from '@/api/system'
import { Send, Plus, Trash2, Eye, Bell, RefreshCw, CheckCircle, Clock, AlertTriangle } from 'lucide-vue-next'

// 消息列表
const messages = ref([])
const isLoading = ref(false)
const currentPage = ref(1)
const totalPages = ref(0)
const filterType = ref('')
const filterPushed = ref('')

// 创建消息表单
const showCreateForm = ref(false)
const newMessage = ref({
    message_type: 'review',
    title: '',
    content: '',
    source: '',
    priority: 'medium',
    ai_suggestion: '',
})
const isCreating = ref(false)

// SSE 连接状态
const sseConnected = ref(false)
const recentPushes = ref([])

// 加载消息列表
const loadMessages = async () => {
    isLoading.value = true
    try {
        const params = {
            page: currentPage.value,
            perPage: 20,
        }
        if (filterType.value) {
            params.messageType = filterType.value
        }
        if (filterPushed.value !== '') {
            params.pushed = filterPushed.value === 'true'
        }
        const result = await pushApi.listMessages(params)
        messages.value = result.messages
        totalPages.value = result.pages
    } catch (e) {
        console.error('加载消息失败', e)
        alert('加载消息失败: ' + e.message)
    } finally {
        isLoading.value = false
    }
}

// 创建消息
const createMessage = async () => {
    if (!newMessage.value.title.trim()) {
        alert('请输入消息标题')
        return
    }
    isCreating.value = true
    try {
        await pushApi.createMessage(newMessage.value)
        // 重置表单
        newMessage.value = {
            message_type: 'review',
            title: '',
            content: '',
            source: '',
            priority: 'medium',
            ai_suggestion: '',
        }
        showCreateForm.value = false
        await loadMessages()
    } catch (e) {
        console.error('创建消息失败', e)
        alert('创建消息失败: ' + e.message)
    } finally {
        isCreating.value = false
    }
}

// 推送消息
const pushMessage = async (messageId) => {
    try {
        await pushApi.pushMessage(messageId)
        await loadMessages()
    } catch (e) {
        console.error('推送消息失败', e)
        alert('推送消息失败: ' + e.message)
    }
}

// 删除消息
const deleteMessage = async (messageId) => {
    if (!confirm('确定要删除此消息吗?')) return
    try {
        await pushApi.deleteMessage(messageId)
        await loadMessages()
    } catch (e) {
        console.error('删除消息失败', e)
        alert('删除消息失败: ' + e.message)
    }
}

// 消息类型标签
const typeLabel = (type) => {
    return type === 'review' ? '待审' : '变更'
}

// 优先级样式
const priorityClass = (priority) => {
    switch (priority) {
        case 'high': return 'bg-red-100 text-red-700'
        case 'medium': return 'bg-yellow-100 text-yellow-700'
        case 'low': return 'bg-green-100 text-green-700'
        default: return 'bg-zinc-100 text-zinc-700'
    }
}

// 格式化时间
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

// 初始化
onMounted(() => {
    loadMessages()
})
</script>

<template>
    <div class="h-full w-full overflow-y-auto">
        <div class="flex flex-col min-h-full max-w-6xl mx-auto px-6 py-8">
            <!-- Header -->
            <div class="flex items-center justify-between mb-8">
                <div>
                    <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight flex items-center gap-2">
                        <Bell class="w-8 h-8" />
                        Message Push
                    </h2>
                    <p class="text-zinc-500 mt-2 text-sm">Manage and push messages to mobile clients</p>
                </div>
                <div class="flex items-center gap-3">
                    <button @click="loadMessages" :disabled="isLoading"
                        class="flex items-center gap-2 px-4 py-2 border border-zinc-200 rounded-lg hover:bg-zinc-50 transition-colors disabled:opacity-50">
                        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
                        Refresh
                    </button>
                    <button @click="showCreateForm = !showCreateForm"
                        class="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 transition-colors">
                        <Plus class="w-4 h-4" />
                        New Message
                    </button>
                </div>
            </div>

            <!-- Create Form -->
            <div v-if="showCreateForm" class="mb-8 p-6 bg-white border border-zinc-200 rounded-xl shadow-sm">
                <h3 class="text-lg font-medium text-zinc-800 mb-4">Create New Message</h3>
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div>
                        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Type</label>
                        <select v-model="newMessage.message_type"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200">
                            <option value="review">Review (待审)</option>
                            <option value="change">Change (变更)</option>
                        </select>
                    </div>
                    <div>
                        <label
                            class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Priority</label>
                        <select v-model="newMessage.priority"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                </div>
                <div class="mb-4">
                    <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Title *</label>
                    <input v-model="newMessage.title" type="text" placeholder="Enter message title"
                        class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200" />
                </div>
                <div class="mb-4">
                    <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Content</label>
                    <textarea v-model="newMessage.content" rows="3" placeholder="Enter message content"
                        class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200 resize-none"></textarea>
                </div>
                <div class="grid grid-cols-2 gap-4 mb-4">
                    <div>
                        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Source</label>
                        <input v-model="newMessage.source" type="text" placeholder="e.g. Architecture Review Meeting"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200" />
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">AI
                            Suggestion</label>
                        <input v-model="newMessage.ai_suggestion" type="text" placeholder="e.g. Low risk, compliant"
                            class="w-full px-3 py-2 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-200" />
                    </div>
                </div>
                <div class="flex justify-end gap-3">
                    <button @click="showCreateForm = false"
                        class="px-4 py-2 border border-zinc-200 rounded-lg hover:bg-zinc-50 transition-colors">
                        Cancel
                    </button>
                    <button @click="createMessage" :disabled="isCreating || !newMessage.title.trim()"
                        class="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50">
                        <Plus class="w-4 h-4" />
                        Create
                    </button>
                </div>
            </div>

            <!-- Filters -->
            <div class="flex items-center gap-4 mb-6">
                <div class="flex items-center gap-2">
                    <label class="text-sm text-zinc-500">Type:</label>
                    <select v-model="filterType" @change="loadMessages"
                        class="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-200">
                        <option value="">All</option>
                        <option value="review">Review</option>
                        <option value="change">Change</option>
                    </select>
                </div>
                <div class="flex items-center gap-2">
                    <label class="text-sm text-zinc-500">Status:</label>
                    <select v-model="filterPushed" @change="loadMessages"
                        class="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-200">
                        <option value="">All</option>
                        <option value="false">Not Pushed</option>
                        <option value="true">Pushed</option>
                    </select>
                </div>
            </div>

            <!-- Messages List -->
            <div class="flex-1">
                <div v-if="isLoading" class="flex items-center justify-center py-12">
                    <RefreshCw class="w-8 h-8 animate-spin text-zinc-400" />
                </div>

                <div v-else-if="messages.length === 0" class="text-center py-12 text-zinc-400">
                    No messages found
                </div>

                <div v-else class="space-y-4">
                    <div v-for="msg in messages" :key="msg.message_id"
                        class="p-4 bg-white border border-zinc-200 rounded-xl hover:shadow-md transition-shadow">
                        <div class="flex items-start justify-between">
                            <div class="flex-1">
                                <div class="flex items-center gap-2 mb-2">
                                    <span
                                        :class="`px-2 py-0.5 text-xs font-medium rounded-full ${msg.message_type === 'review' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}`">
                                        {{ typeLabel(msg.message_type) }}
                                    </span>
                                    <span :class="`px-2 py-0.5 text-xs font-medium rounded-full ${priorityClass(msg.priority)}`">
                                        {{ msg.priority }}
                                    </span>
                                    <span v-if="msg.pushed"
                                        class="flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700">
                                        <CheckCircle class="w-3 h-3" />
                                        Pushed
                                    </span>
                                    <span v-else
                                        class="flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-100 text-zinc-600">
                                        <Clock class="w-3 h-3" />
                                        Pending
                                    </span>
                                </div>
                                <h4 class="text-lg font-medium text-zinc-800 mb-1">{{ msg.title }}</h4>
                                <p v-if="msg.content" class="text-sm text-zinc-600 mb-2">{{ msg.content }}</p>
                                <div class="flex items-center gap-4 text-xs text-zinc-400">
                                    <span v-if="msg.source">Source: {{ msg.source }}</span>
                                    <span>Created: {{ formatTime(msg.created_at) }}</span>
                                    <span v-if="msg.pushed_at">Pushed: {{ formatTime(msg.pushed_at) }}</span>
                                </div>
                                <p v-if="msg.ai_suggestion" class="mt-2 text-sm text-blue-600">
                                    AI: {{ msg.ai_suggestion }}
                                </p>
                            </div>
                            <div class="flex items-center gap-2 ml-4">
                                <button v-if="!msg.pushed" @click="pushMessage(msg.message_id)"
                                    class="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                                    title="Push to clients">
                                    <Send class="w-4 h-4" />
                                    Push
                                </button>
                                <button @click="deleteMessage(msg.message_id)"
                                    class="p-1.5 text-zinc-400 hover:text-red-600 transition-colors" title="Delete">
                                    <Trash2 class="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Pagination -->
                <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-8">
                    <button @click="currentPage--; loadMessages()" :disabled="currentPage <= 1"
                        class="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed">
                        Previous
                    </button>
                    <span class="text-sm text-zinc-600">Page {{ currentPage }} of {{ totalPages }}</span>
                    <button @click="currentPage++; loadMessages()" :disabled="currentPage >= totalPages"
                        class="px-3 py-1.5 border border-zinc-200 rounded-lg text-sm hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed">
                        Next
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

