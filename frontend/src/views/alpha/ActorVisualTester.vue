<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/api/request'
import { manageApi } from '@/api/project'

// 项目和需求选择相关
const projects = ref([])
const selectedProjectId = ref('')
const requirements = ref([])
const isLoadingProjects = ref(false)
const isLoadingReqs = ref(false)
const projectError = ref('')

// Actor 测试相关
const requirementId = ref('')
const minVersion = ref('')
const updatePayloadText = ref('{"title":"actor visual test"}')
const queryResult = ref(null)
const stats = ref(null)
const logs = ref([])
const wsState = ref('disconnected')
const busy = ref(false)
const errorMessage = ref('')

let wsClient = null
let statsTimer = null

const selectedMailboxSize = computed(() => {
  const id = requirementId.value.trim()
  if (!id || !stats.value) return 0
  return stats.value.mailbox_sizes?.[id] || 0
})

const appendLog = (payload) => {
  logs.value.unshift(payload)
  if (logs.value.length > 300) {
    logs.value = logs.value.slice(0, 300)
  }
}

const buildWsUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/api/v2/_internals/actors/ws`
}

const connectWs = () => {
  if (wsClient && (wsClient.readyState === WebSocket.OPEN || wsClient.readyState === WebSocket.CONNECTING)) {
    return
  }
  wsState.value = 'connecting'
  wsClient = new WebSocket(buildWsUrl())

  wsClient.onopen = () => {
    wsState.value = 'connected'
  }
  wsClient.onclose = () => {
    wsState.value = 'closed'
  }
  wsClient.onerror = () => {
    wsState.value = 'error'
  }
  wsClient.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data?.event === 'actor_dev_trace' && data?.data) {
        appendLog(data.data)
      }
    } catch (_err) {
      // ignore malformed payload
    }
  }
}

const disconnectWs = () => {
  if (wsClient) {
    wsClient.close()
    wsClient = null
  }
}

const refreshStats = async () => {
  try {
    const resp = await api.get('/_internals/actors/stats')
    stats.value = resp.data || {}
  } catch (err) {
    errorMessage.value = err?.response?.data?.detail || String(err)
  }
}

const runAction = async (action) => {
  busy.value = true
  errorMessage.value = ''
  try {
    await action()
    await refreshStats()
  } catch (err) {
    errorMessage.value = err?.response?.data?.detail || String(err)
  } finally {
    busy.value = false
  }
}

const forceActivate = async () => {
  const id = requirementId.value.trim()
  if (!id) return
  await runAction(async () => {
    await api.post(`/requirement-actor/force-activate/${encodeURIComponent(id)}`)
  })
}

const forcePassivate = async () => {
  const id = requirementId.value.trim()
  if (!id) return
  await runAction(async () => {
    await api.post(`/requirement-actor/force-passivate/${encodeURIComponent(id)}`)
  })
}

const sendUpdate = async () => {
  const id = requirementId.value.trim()
  if (!id) return
  await runAction(async () => {
    const updates = JSON.parse(updatePayloadText.value || '{}')
    await api.post('/requirement-actor/command/update-content', { updates }, {
      params: { requirement_id: id }
    })
  })
}

const queryWithFence = async () => {
  const id = requirementId.value.trim()
  if (!id) return
  await runAction(async () => {
    const params = { requirement_id: id }
    if (minVersion.value !== '') {
      params.min_version = Number(minVersion.value)
    }
    const resp = await api.get('/requirement-actor/query', { params })
    queryResult.value = resp.data
  })
}

// 项目和需求加载函数
const loadProjects = async () => {
  projectError.value = ''
  isLoadingProjects.value = true
  try {
    const data = await manageApi.listProjects()
    projects.value = data.projects || []
    // 默认选择第一个项目（最高权限）
    if (projects.value.length > 0 && !selectedProjectId.value) {
      selectedProjectId.value = projects.value[0].project_id
    }
  } catch (err) {
    projectError.value = err?.message || '加载项目失败'
  } finally {
    isLoadingProjects.value = false
  }
}

const loadRequirements = async () => {
  if (!selectedProjectId.value) {
    requirements.value = []
    return
  }
  isLoadingReqs.value = true
  try {
    const listData = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = listData.requirements || []
  } catch (err) {
    console.error('加载需求失败:', err)
    requirements.value = []
  } finally {
    isLoadingReqs.value = false
  }
}

// 监听项目选择变化，自动加载对应的需求
watch(selectedProjectId, () => {
  if (selectedProjectId.value) {
    loadRequirements()
  }
})

onMounted(async () => {
  connectWs()
  await refreshStats()
  statsTimer = setInterval(refreshStats, 5000)
  await loadProjects()
})

onBeforeUnmount(() => {
  if (statsTimer) {
    clearInterval(statsTimer)
    statsTimer = null
  }
  disconnectWs()
})
</script>

<template>
  <div class="h-full w-full overflow-y-auto bg-zinc-50">
    <div class="mx-auto w-full max-w-7xl p-6 md:p-8 space-y-6">
      <!-- 项目和需求选择区 -->
      <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div class="flex flex-wrap items-center gap-3">
          <div class="min-w-[200px] flex-1">
            <label class="block text-xs font-medium text-zinc-500 mb-1">项目</label>
            <select
              v-model="selectedProjectId"
              :disabled="isLoadingProjects"
              @change="() => { requirementId = '' }"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
            >
              <option value="">选择项目</option>
              <option v-for="p in projects" :key="p.project_id" :value="p.project_id">{{ p.name }}</option>
            </select>
          </div>
          <div class="min-w-[200px] flex-1">
            <label class="block text-xs font-medium text-zinc-500 mb-1">需求</label>
            <select
              v-model="requirementId"
              :disabled="isLoadingReqs || !selectedProjectId"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
            >
              <option value="">选择需求</option>
              <option v-for="req in requirements" :key="req.req_id" :value="req.req_id">
                {{ req.title || req.text }} ({{ req.req_id }})
              </option>
            </select>
          </div>
          <button
            class="inline-flex items-center gap-2 text-sm text-zinc-700 border border-zinc-300 rounded-md px-3 py-1.5 hover:bg-zinc-50"
            @click="loadProjects"
            :disabled="isLoadingProjects"
          >
            <span v-if="isLoadingProjects">刷新中...</span>
            <span v-else>刷新项目</span>
          </button>
        </div>
        <p v-if="projectError" class="mt-3 text-sm text-red-600">{{ projectError }}</p>
      </section>

      <!-- Actor 操作区 -->
      <section class="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div class="flex flex-wrap items-end gap-3">
          <div class="min-w-[220px] flex-1">
            <label class="block text-xs font-medium text-zinc-500 mb-1">需求ID</label>
            <input
              v-model="requirementId"
              type="text"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
              placeholder="req-123"
            />
          </div>
          <div class="w-36">
            <label class="block text-xs font-medium text-zinc-500 mb-1">最小版本</label>
            <input
              v-model="minVersion"
              type="number"
              min="0"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
            />
          </div>
          <button class="rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50" :disabled="busy" @click="forceActivate">
            强制激活
          </button>
          <button class="rounded-lg bg-zinc-700 px-4 py-2 text-sm text-white disabled:opacity-50" :disabled="busy" @click="forcePassivate">
            强制停用
          </button>
          <button class="rounded-lg bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50" :disabled="busy" @click="queryWithFence">
            带围栏查询
          </button>
        </div>

        <div class="mt-4">
          <label class="block text-xs font-medium text-zinc-500 mb-1">更新载荷 (JSON)</label>
          <textarea
            v-model="updatePayloadText"
            rows="3"
            class="w-full rounded-lg border border-zinc-300 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-zinc-400"
          />
          <button class="mt-2 rounded-lg bg-blue-700 px-4 py-2 text-sm text-white disabled:opacity-50" :disabled="busy" @click="sendUpdate">
            发送更新命令
          </button>
        </div>

        <p v-if="errorMessage" class="mt-3 text-sm text-red-600">{{ errorMessage }}</p>
      </section>

      <section class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <article class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <h2 class="text-base font-semibold text-zinc-900">Actor 内部状态</h2>
          <p class="mt-1 text-xs text-zinc-500">
            ws={{ wsState }} | total={{ stats?.total_actors || 0 }} | active={{ stats?.active_actors || 0 }} | faulted={{ stats?.faulted_actors || 0 }} | mailbox({{ requirementId || '-' }})={{ selectedMailboxSize }}
          </p>
          <pre class="mt-3 max-h-[360px] overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">{{ JSON.stringify(stats, null, 2) }}</pre>
        </article>

        <article class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
          <h2 class="text-base font-semibold text-zinc-900">查询结果</h2>
          <pre class="mt-3 max-h-[360px] overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">{{ JSON.stringify(queryResult, null, 2) }}</pre>
        </article>
      </section>

      <section class="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 class="text-base font-semibold text-zinc-900">实时追踪 (actor_dev_trace)</h2>
        <div class="mt-3 max-h-[420px] overflow-auto rounded-lg border border-zinc-200">
          <table class="w-full min-w-[780px] border-collapse text-xs">
            <thead class="bg-zinc-100 text-zinc-600">
              <tr>
                <th class="px-3 py-2 text-left font-medium">时间戳</th>
                <th class="px-3 py-2 text-left font-medium">需求</th>
                <th class="px-3 py-2 text-left font-medium">阶段</th>
                <th class="px-3 py-2 text-left font-medium">级别</th>
                <th class="px-3 py-2 text-left font-medium">详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in logs" :key="index" class="border-t border-zinc-200">
                <td class="px-3 py-2 text-zinc-700">{{ item.timestamp || '-' }}</td>
                <td class="px-3 py-2 font-medium text-zinc-900">{{ item.requirement_id || '-' }}</td>
                <td class="px-3 py-2 text-zinc-700">{{ item.stage || '-' }}</td>
                <td class="px-3 py-2">
                  <span class="rounded bg-zinc-200 px-2 py-0.5 text-[11px] uppercase text-zinc-700">{{ item.level || 'info' }}</span>
                </td>
                <td class="px-3 py-2">
                  <pre class="whitespace-pre-wrap break-all text-zinc-600">{{ JSON.stringify(item, null, 2) }}</pre>
                </td>
              </tr>
              <tr v-if="logs.length === 0">
                <td colspan="5" class="px-3 py-6 text-center text-zinc-500">暂无追踪事件</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
