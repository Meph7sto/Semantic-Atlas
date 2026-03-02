<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
    AlertCircle,
    Bot,
    Clock3,
    MessageCircle,
    RefreshCw,
    Search,
    Workflow,
} from 'lucide-vue-next'
import { agentMonitorApi } from '@/api/agent'
import AlphaRequirementsPanel from '../../components/alpha/AlphaRequirementsPanel.vue'

const loading = ref(false)
const error = ref('')
const searchText = ref('')
const activeTab = ref('chat')
const autoRefresh = ref(true)
const refreshEveryMs = 6000
const selectedChannelId = ref('')
const projectId = ref(localStorage.getItem('lastProjectId') || '')

const snapshot = ref({
    generated_at: null,
    agents: [],
    channels: [],
    messages: [],
    tasks: [],
    events: [],
})

let refreshTimer = null

const parseTime = (value) => {
    if (!value) return 0
    const ts = Date.parse(value)
    return Number.isFinite(ts) ? ts : 0
}

const fmtTime = (value) => {
    if (!value) return '--'
    const dt = new Date(value)
    if (Number.isNaN(dt.getTime())) return '--'
    return dt.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    })
}

const messagePreview = (msg) => {
    const content = msg?.content
    if (!content || typeof content !== 'object') return '系统消息'
    if (content.action === 'delegate_task') return `委派: ${content.task_description || '未命名任务'}`
    if (content.action === 'query') return `查询: ${content.query || '无'}`
    if (content.notification) return `通知: ${content.notification}`
    if (content.status === 'completed') return '任务已完成并回传'
    if (content.status === 'failed') return '任务失败'
    return JSON.stringify(content).slice(0, 72)
}

const eventSummary = (event) => {
    if (event.summary) return event.summary
    if (event.action) return String(event.action)
    return '系统事件'
}

const statusClass = (status) => {
    if (status === 'approved') return 'bg-emerald-100 text-emerald-800 border-emerald-200'
    if (status === 'rejected') return 'bg-rose-100 text-rose-700 border-rose-200'
    if (status === 'pending') return 'bg-amber-100 text-amber-800 border-amber-200'
    return 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

const senderColorClass = (senderId) => {
    if (!senderId) return 'bg-zinc-200 text-zinc-700'
    if (senderId.includes('conductor')) return 'bg-blue-500 text-white'
    if (senderId.includes('requirements')) return 'bg-teal-500 text-white'
    if (senderId.includes('conflict')) return 'bg-rose-500 text-white'
    return 'bg-violet-500 text-white'
}

const groupedMessages = computed(() => {
    const map = new Map()
    for (const msg of snapshot.value.messages || []) {
        const channelId = msg.channel_id || 'unknown'
        if (!map.has(channelId)) map.set(channelId, [])
        map.get(channelId).push(msg)
    }
    for (const list of map.values()) {
        list.sort((a, b) => parseTime(a.timestamp) - parseTime(b.timestamp))
    }
    return map
})

const channels = computed(() => {
    const source = snapshot.value.channels || []
    const fromRegistry = source.map((ch) => {
        const msgList = groupedMessages.value.get(ch.channel_id) || []
        const last = msgList[msgList.length - 1] || null
        return {
            ...ch,
            last_message: last,
            sort_ts: last ? parseTime(last.timestamp) : parseTime(ch.created_at),
        }
    })

    for (const [channelId, msgList] of groupedMessages.value.entries()) {
        if (fromRegistry.some((c) => c.channel_id === channelId)) continue
        const last = msgList[msgList.length - 1] || null
        fromRegistry.push({
            channel_id: channelId,
            channel_type: 'direct',
            name: channelId,
            members: [],
            created_at: last?.timestamp || null,
            last_message: last,
            sort_ts: last ? parseTime(last.timestamp) : 0,
        })
    }

    const q = searchText.value.trim().toLowerCase()
    const filtered = fromRegistry.filter((c) => {
        if (!q) return true
        const base = `${c.name || ''} ${(c.members || []).join(' ')}`.toLowerCase()
        const preview = messagePreview(c.last_message || {}).toLowerCase()
        return base.includes(q) || preview.includes(q)
    })
    return filtered.sort((a, b) => b.sort_ts - a.sort_ts)
})

const selectedChannel = computed(() => {
    const list = channels.value
    if (!list.length) return null
    return list.find((c) => c.channel_id === selectedChannelId.value) || list[0]
})

const selectedMessages = computed(() => {
    const channelId = selectedChannel.value?.channel_id
    if (!channelId) return []
    return groupedMessages.value.get(channelId) || []
})

const channelEvents = computed(() => {
    const all = snapshot.value.events || []
    const cid = selectedChannel.value?.channel_id
    const filtered = cid ? all.filter((e) => e.channel_id === cid || (e.event_type === 'task' && !e.channel_id)) : all
    return [...filtered].sort((a, b) => parseTime(b.timestamp) - parseTime(a.timestamp))
})

const tasks = computed(() => {
    return [...(snapshot.value.tasks || [])].sort((a, b) => parseTime(b.created_at) - parseTime(a.created_at))
})

const agentCards = computed(() => {
    const all = snapshot.value.agents || []
    const events = snapshot.value.events || []
    return all.map((agent) => {
        const count = events.filter((e) => e.agent_id === agent.agent_id).length
        return { ...agent, event_count: count }
    })
})

const loadSnapshot = async ({ silent = false } = {}) => {
    if (!silent) loading.value = true
    error.value = ''
    try {
        const data = await agentMonitorApi.getOverview({
            projectId: projectId.value || null,
            limitMessages: 400,
            limitTasks: 300,
            limitEvents: 800,
        })
        snapshot.value = {
            generated_at: data.generated_at || null,
            agents: data.agents || [],
            channels: data.channels || [],
            messages: data.messages || [],
            tasks: data.tasks || [],
            events: data.events || [],
        }

        const current = selectedChannelId.value
        if (!current || !channels.value.some((c) => c.channel_id === current)) {
            selectedChannelId.value = channels.value[0]?.channel_id || ''
        }
    } catch (e) {
        error.value = e?.message || '加载 Agent 协作监控失败'
    } finally {
        if (!silent) loading.value = false
    }
}

const resetTimer = () => {
    if (refreshTimer) {
        clearInterval(refreshTimer)
        refreshTimer = null
    }
    if (autoRefresh.value) {
        refreshTimer = setInterval(() => {
            loadSnapshot({ silent: true })
        }, refreshEveryMs)
    }
}

watch(autoRefresh, () => resetTimer())

onMounted(async () => {
    await loadSnapshot()
    resetTimer()
})

onBeforeUnmount(() => {
    if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
    <div class="agent-monitor-shell min-h-full w-full overflow-y-auto">
        <div class="w-full p-6 md:p-8 space-y-8">
            <div class="rounded-3xl border border-zinc-200/70 bg-white/80 shadow-2xl backdrop-blur-sm overflow-hidden">
                <header class="px-6 py-5 border-b border-zinc-200/70 agent-monitor-header">
                    <div class="flex flex-wrap items-center justify-between gap-4">
                        <div>
                            <h2 class="text-2xl md:text-3xl font-semibold text-zinc-900 tracking-tight flex items-center gap-3">
                                <Workflow class="w-7 h-7 text-zinc-700" />
                                Agent 协作总线
                            </h2>
                            <p class="text-sm text-zinc-600 mt-1">
                                任务审批、Agent 动作与消息通信总览（WhatsApp 风格会话视图）
                            </p>
                        </div>

                        <div class="flex items-center gap-2">
                            <label class="text-xs text-zinc-500">Project</label>
                            <input
                                v-model="projectId"
                                placeholder="可选: project_id"
                                class="w-52 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-300"
                            />
                            <button
                                @click="loadSnapshot()"
                                :disabled="loading"
                                class="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-zinc-700 border border-zinc-200 bg-white hover:bg-zinc-50 disabled:opacity-60"
                            >
                                <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
                                刷新
                            </button>
                            <label class="inline-flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-600">
                                <input v-model="autoRefresh" type="checkbox" />
                                自动刷新
                            </label>
                        </div>
                    </div>

                    <div class="mt-4 flex flex-wrap items-center gap-2">
                        <span class="metric-chip">
                            <Bot class="w-3.5 h-3.5" />
                            Agents {{ agentCards.length }}
                        </span>
                        <span class="metric-chip">
                            <MessageCircle class="w-3.5 h-3.5" />
                            Channels {{ channels.length }}
                        </span>
                        <span class="metric-chip">
                            <Clock3 class="w-3.5 h-3.5" />
                            Events {{ snapshot.events.length }}
                        </span>
                        <span class="text-xs text-zinc-500 ml-1">更新时间: {{ fmtTime(snapshot.generated_at) }}</span>
                    </div>
                </header>

                <div class="min-h-[500px] max-h-[70vh] flex overflow-hidden">
                    <aside class="w-[22rem] border-r border-zinc-200/70 bg-zinc-50/60 flex flex-col">
                        <div class="p-4 border-b border-zinc-200/70">
                            <div class="relative">
                                <Search class="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                                <input
                                    v-model="searchText"
                                    placeholder="搜索频道 / Agent"
                                    class="w-full rounded-xl border border-zinc-200 bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-300"
                                />
                            </div>
                        </div>

                        <div class="flex-1 overflow-y-auto p-2 space-y-1.5">
                            <button
                                v-for="channel in channels"
                                :key="channel.channel_id"
                                @click="selectedChannelId = channel.channel_id"
                                class="w-full text-left rounded-2xl px-3 py-3 border transition-all"
                                :class="selectedChannelId === channel.channel_id
                                    ? 'bg-white border-zinc-300 shadow-sm'
                                    : 'bg-transparent border-transparent hover:bg-white/80 hover:border-zinc-200'"
                            >
                                <div class="flex items-start justify-between gap-2">
                                    <div class="min-w-0">
                                        <div class="font-medium text-sm text-zinc-800 truncate">
                                            {{ channel.name || channel.channel_id }}
                                        </div>
                                        <div class="text-xs text-zinc-500 mt-1 truncate">
                                            {{ (channel.members || []).join(' · ') || channel.channel_type }}
                                        </div>
                                        <div class="text-xs text-zinc-600 mt-2 truncate">
                                            {{ messagePreview(channel.last_message || {}) }}
                                        </div>
                                    </div>
                                    <div class="text-[11px] text-zinc-400 whitespace-nowrap">
                                        {{ fmtTime(channel.last_message?.timestamp || channel.created_at) }}
                                    </div>
                                </div>
                            </button>

                            <div v-if="!channels.length" class="p-4 text-xs text-zinc-500 text-center">
                                暂无 Agent 通信频道。先在聊天面板使用 `conductor_agent` 发起一次委派任务。
                            </div>
                        </div>
                    </aside>

                    <section class="flex-1 flex flex-col overflow-hidden">
                        <div class="px-5 py-3 border-b border-zinc-200/70 bg-white/80 flex items-center justify-between">
                            <div>
                                <div class="text-sm font-semibold text-zinc-900">
                                    {{ selectedChannel?.name || '未选择频道' }}
                                </div>
                                <div class="text-xs text-zinc-500">
                                    {{ selectedChannel?.channel_type || '--' }} · {{ (selectedChannel?.members || []).join(', ') || 'no members' }}
                                </div>
                            </div>
                            <div class="flex items-center gap-1">
                                <button
                                    @click="activeTab = 'chat'"
                                    class="tab-btn"
                                    :class="activeTab === 'chat' ? 'tab-btn-active' : ''"
                                >消息流</button>
                                <button
                                    @click="activeTab = 'actions'"
                                    class="tab-btn"
                                    :class="activeTab === 'actions' ? 'tab-btn-active' : ''"
                                >动作日志</button>
                                <button
                                    @click="activeTab = 'tasks'"
                                    class="tab-btn"
                                    :class="activeTab === 'tasks' ? 'tab-btn-active' : ''"
                                >审批任务</button>
                            </div>
                        </div>

                        <div class="flex-1 overflow-y-auto p-5">
                            <div v-if="loading" class="h-full flex items-center justify-center text-zinc-500">
                                <RefreshCw class="w-5 h-5 animate-spin mr-2" />
                                正在加载 Agent 协作数据...
                            </div>

                            <div v-else-if="error" class="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-700 text-sm flex items-start gap-2">
                                <AlertCircle class="w-4 h-4 mt-0.5" />
                                {{ error }}
                            </div>

                            <div v-else-if="activeTab === 'chat'" class="space-y-3">
                                <div
                                    v-for="msg in selectedMessages"
                                    :key="msg.message_id"
                                    class="max-w-[85%] rounded-2xl border px-4 py-3 shadow-sm"
                                    :class="msg.sender_id === 'conductor_agent'
                                        ? 'ml-auto bg-blue-50 border-blue-200'
                                        : 'mr-auto bg-white border-zinc-200'"
                                >
                                    <div class="flex items-center justify-between gap-3 mb-2">
                                        <div class="inline-flex items-center gap-2">
                                            <span class="w-6 h-6 rounded-full inline-flex items-center justify-center text-[10px] font-semibold"
                                                :class="senderColorClass(msg.sender_id)">
                                                {{ (msg.sender_id || '?').slice(0, 2).toUpperCase() }}
                                            </span>
                                            <span class="text-xs font-semibold text-zinc-700">{{ msg.sender_id }}</span>
                                            <span class="text-[11px] rounded-full border border-zinc-200 bg-zinc-100 px-2 py-0.5 text-zinc-600">
                                                {{ msg.message_type }}
                                            </span>
                                        </div>
                                        <span class="text-[11px] text-zinc-400">{{ fmtTime(msg.timestamp) }}</span>
                                    </div>

                                    <div class="text-xs text-zinc-700 whitespace-pre-wrap break-words">
                                        <template v-if="typeof msg.content === 'object'">
{{ JSON.stringify(msg.content, null, 2) }}
                                        </template>
                                        <template v-else>
{{ msg.content || '-' }}
                                        </template>
                                    </div>
                                </div>

                                <div v-if="!selectedMessages.length" class="text-center text-zinc-500 text-sm py-16">
                                    当前频道暂无消息。
                                </div>
                            </div>

                            <div v-else-if="activeTab === 'actions'" class="space-y-3">
                                <article
                                    v-for="ev in channelEvents"
                                    :key="ev.event_id"
                                    class="rounded-2xl border border-zinc-200 bg-white px-4 py-3"
                                >
                                    <div class="flex items-center justify-between gap-2">
                                        <div class="flex items-center gap-2">
                                            <span class="text-[11px] rounded-full px-2 py-0.5 border"
                                                :class="ev.event_type === 'task' ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-cyan-50 text-cyan-700 border-cyan-200'">
                                                {{ ev.event_type }}
                                            </span>
                                            <span class="text-xs font-semibold text-zinc-700">{{ ev.agent_id || 'system' }}</span>
                                            <span class="text-xs text-zinc-500">{{ ev.message_type || ev.action || '-' }}</span>
                                        </div>
                                        <span class="text-[11px] text-zinc-400">{{ fmtTime(ev.timestamp) }}</span>
                                    </div>
                                    <div class="mt-2 text-sm text-zinc-700">{{ eventSummary(ev) }}</div>
                                </article>

                                <div v-if="!channelEvents.length" class="text-center text-zinc-500 text-sm py-16">
                                    暂无动作日志。
                                </div>
                            </div>

                            <div v-else class="space-y-3">
                                <article
                                    v-for="task in tasks"
                                    :key="task.task_id"
                                    class="rounded-2xl border border-zinc-200 bg-white px-4 py-3"
                                >
                                    <div class="flex items-start justify-between gap-3">
                                        <div class="min-w-0">
                                            <div class="text-sm font-semibold text-zinc-800 truncate">{{ task.title }}</div>
                                            <div class="text-xs text-zinc-500 mt-1">
                                                {{ task.task_type }} · {{ task.project_id || 'no project' }}
                                            </div>
                                            <div class="text-xs text-zinc-500 mt-1">
                                                创建: {{ fmtTime(task.created_at) }} · 处理: {{ fmtTime(task.resolved_at) }}
                                            </div>
                                        </div>
                                        <span class="text-xs rounded-full border px-2 py-1"
                                            :class="statusClass(task.status)">
                                            {{ task.status }}
                                        </span>
                                    </div>
                                </article>

                                <div v-if="!tasks.length" class="text-center text-zinc-500 text-sm py-16">
                                    暂无审批任务。
                                </div>
                            </div>
                        </div>
                    </section>

                    <aside class="w-[18rem] border-l border-zinc-200/70 bg-zinc-50/60 p-4 overflow-y-auto">
                        <h3 class="text-sm font-semibold text-zinc-800 mb-3">Agent 活跃度</h3>
                        <div class="space-y-2">
                            <div
                                v-for="agent in agentCards"
                                :key="agent.agent_id"
                                class="rounded-xl border border-zinc-200 bg-white px-3 py-2"
                            >
                                <div class="flex items-center justify-between">
                                    <div class="text-xs font-semibold text-zinc-800">{{ agent.name }}</div>
                                    <span class="text-[11px] text-zinc-500">{{ agent.event_count }} 事件</span>
                                </div>
                                <div class="text-[11px] text-zinc-500 mt-1">{{ agent.agent_id }}</div>
                                <div class="text-[11px] text-zinc-500 mt-1">
                                    child: {{ (agent.child_agent_ids || []).join(', ') || '-' }}
                                </div>
                            </div>

                            <div v-if="!agentCards.length" class="text-xs text-zinc-500">
                                没有检测到已注册 Agent。
                            </div>
                        </div>
                    </aside>
                </div>
            </div>

            <!-- Requirements Panel -->
            <div class="rounded-3xl border border-zinc-200/70 bg-white/80 shadow-2xl backdrop-blur-sm p-6">
                <AlphaRequirementsPanel :project-id="projectId" />
            </div>
        </div>
    </div>
</template>

<style scoped>
.agent-monitor-shell {
    background:
        radial-gradient(80rem 60rem at -10% -30%, rgba(99, 102, 241, 0.14), transparent 60%),
        radial-gradient(80rem 60rem at 110% 0%, rgba(20, 184, 166, 0.12), transparent 62%),
        linear-gradient(180deg, #fafaf9 0%, #f4f4f5 100%);
}

.agent-monitor-header {
    background:
        radial-gradient(circle at 20% 20%, rgba(59, 130, 246, 0.1), transparent 32%),
        radial-gradient(circle at 85% 15%, rgba(20, 184, 166, 0.1), transparent 35%),
        rgba(255, 255, 255, 0.8);
}

.metric-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    border: 1px solid rgba(161, 161, 170, 0.35);
    background: rgba(255, 255, 255, 0.88);
    padding: 0.3rem 0.55rem;
    border-radius: 999px;
    font-size: 11px;
    color: rgb(82, 82, 91);
}

.tab-btn {
    border: 1px solid transparent;
    border-radius: 0.75rem;
    padding: 0.4rem 0.75rem;
    font-size: 12px;
    color: rgb(82, 82, 91);
    transition: all 0.18s ease;
}

.tab-btn:hover {
    border-color: rgba(161, 161, 170, 0.35);
    background: rgba(255, 255, 255, 0.8);
}

.tab-btn-active {
    border-color: rgba(59, 130, 246, 0.25);
    color: rgb(30, 64, 175);
    background: rgba(219, 234, 254, 0.72);
}
</style>

