<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { asrApi } from '@/api/asr'

const selectedFile = ref(null)
const uploading = ref(false)
const sessions = ref([])
const currentDetail = ref(null)
const detailOpen = ref(false)
const detailError = ref('')
const detailRefreshing = ref(false)
const terminalStatuses = new Set(['succeeded', 'failed', 'timeout'])
let detailPollTimer = null

const rawOutDisplay = computed(() => {
  return currentDetail.value?.transcript_text || '无原始结果'
})

const detailStatusHint = computed(() => {
  const status = currentDetail.value?.status
  if (!status) return ''
  if (status === 'queued') return '转写任务已排队，正在等待远端处理...'
  if (status === 'running') return '转写任务正在处理，请稍候...'
  if (status === 'failed') return '转写失败，请查看错误信息并可点击重试。'
  if (status === 'timeout') return '转写超时，请点击重试。'
  if (status === 'succeeded') return '转写已完成。'
  return ''
})

function statusClass(status) {
  if (status === 'succeeded') return 'bg-emerald-50 text-emerald-700 border border-emerald-200'
  if (status === 'failed' || status === 'timeout') return 'bg-red-50 text-red-700 border border-red-200'
  if (status === 'running') return 'bg-blue-50 text-blue-700 border border-blue-200'
  return 'bg-zinc-100 text-zinc-600 border border-zinc-200'
}

function onSelectFile(event) {
  const file = event?.target?.files?.[0]
  selectedFile.value = file || null
}

async function createSession() {
  if (!selectedFile.value || uploading.value) return
  uploading.value = true
  try {
    await asrApi.createSession(selectedFile.value)
    selectedFile.value = null
    await loadSessions()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '上传失败'
    window.alert(detail)
  } finally {
    uploading.value = false
  }
}

async function loadSessions() {
  try {
    const data = await asrApi.listSessions({ page: 1, per_page: 30 })
    sessions.value = data.items || []
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '加载会话失败'
    window.alert(detail)
  }
}

function stopDetailPolling() {
  if (detailPollTimer) {
    clearInterval(detailPollTimer)
    detailPollTimer = null
  }
}

async function refreshDetail(sessionId, silent = false) {
  if (!sessionId) return
  if (detailRefreshing.value) return
  detailRefreshing.value = true
  try {
    const detail = await asrApi.getSession(sessionId)
    currentDetail.value = detail
    detailError.value = ''
    if (terminalStatuses.has(detail.status)) {
      stopDetailPolling()
    }
    if (!silent) {
      await loadSessions()
    }
  } catch (error) {
    stopDetailPolling()
    const detail = error?.response?.data?.detail || error?.message || '加载详情失败'
    detailError.value = detail
  } finally {
    detailRefreshing.value = false
  }
}

function startDetailPolling(sessionId) {
  stopDetailPolling()
  detailPollTimer = setInterval(() => {
    refreshDetail(sessionId, true)
  }, 2500)
}

function closeDetail() {
  detailOpen.value = false
  stopDetailPolling()
}

async function viewDetail(sessionId) {
  detailOpen.value = true
  detailError.value = ''
  if (!currentDetail.value || currentDetail.value.session_id !== sessionId) {
    const row = sessions.value.find((item) => item.session_id === sessionId)
    if (row) {
      currentDetail.value = { ...row }
    }
  }
  await refreshDetail(sessionId)
  const status = currentDetail.value?.status
  if (status && !terminalStatuses.has(status)) {
    startDetailPolling(sessionId)
  } else {
    stopDetailPolling()
  }
}

async function retry(sessionId) {
  try {
    await asrApi.retrySession(sessionId)
    await loadSessions()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '重试失败'
    window.alert(detail)
  }
}

function download(sessionId, format) {
  window.open(asrApi.exportUrl(sessionId, format), '_blank')
}

function downloadRawOut() {
  if (!currentDetail.value?.session_id) return
  const content = currentDetail.value?.transcript_text || ''
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${currentDetail.value.session_id}_raw_out.txt`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  await loadSessions()
})

onBeforeUnmount(() => {
  stopDetailPolling()
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <!-- Header -->
    <header class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-zinc-900">语音转写</h2>
        <p class="text-sm text-zinc-500 mt-1">上传音视频文件，远端推理后返回模型原始输出</p>
      </div>
      <button
        class="text-sm text-zinc-600 border border-zinc-300 rounded-lg px-3 py-1.5 hover:bg-zinc-100 transition-colors"
        @click="loadSessions"
      >
        刷新列表
      </button>
    </header>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      <!-- Upload Section -->
      <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm">
        <h3 class="text-base font-semibold text-zinc-900 mb-3">上传文件</h3>
        <div class="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".wav,.mp3,.m4a,.mp4,audio/*,video/mp4"
            class="text-sm text-zinc-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border file:border-zinc-300 file:text-sm file:font-medium file:bg-white file:text-zinc-700 hover:file:bg-zinc-50 file:cursor-pointer"
            @change="onSelectFile"
          />
          <button
            class="bg-black text-white text-sm py-2 px-5 rounded-lg font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            :disabled="!selectedFile || uploading"
            @click="createSession"
          >
            {{ uploading ? '上传中...' : '开始转写' }}
          </button>
          <span class="text-xs text-zinc-400">支持 wav / mp3 / m4a / mp4</span>
        </div>
      </section>

      <!-- Sessions Table -->
      <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm">
        <h3 class="text-base font-semibold text-zinc-900 mb-4">会话列表</h3>
        <div class="overflow-x-auto border border-zinc-200 rounded-lg">
          <table class="min-w-full text-sm text-left">
            <thead class="bg-zinc-100 text-zinc-600">
              <tr>
                <th class="px-3 py-2 font-medium">Session</th>
                <th class="px-3 py-2 font-medium">文件</th>
                <th class="px-3 py-2 font-medium">状态</th>
                <th class="px-3 py-2 font-medium">尝试次数</th>
                <th class="px-3 py-2 font-medium">更新时间</th>
                <th class="px-3 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in sessions" :key="item.session_id" class="border-t border-zinc-200">
                <td class="px-3 py-2 font-mono text-xs text-zinc-500">{{ item.session_id }}</td>
                <td class="px-3 py-2">{{ item.source_filename }}</td>
                <td class="px-3 py-2">
                  <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium" :class="statusClass(item.status)">
                    {{ item.status }}
                  </span>
                </td>
                <td class="px-3 py-2">{{ item.attempt_count }}</td>
                <td class="px-3 py-2 text-zinc-500">{{ item.updated_at }}</td>
                <td class="px-3 py-2">
                  <div class="flex gap-2 flex-wrap">
                    <button
                      class="text-xs border border-zinc-300 rounded-lg px-2.5 py-1 hover:bg-zinc-100 transition-colors"
                      @click="viewDetail(item.session_id)"
                    >
                      查看
                    </button>
                    <button
                      class="text-xs border border-zinc-300 rounded-lg px-2.5 py-1 hover:bg-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      :disabled="item.status !== 'failed' && item.status !== 'timeout'"
                      @click="retry(item.session_id)"
                    >
                      重试
                    </button>
                    <button
                      class="text-xs border border-zinc-300 rounded-lg px-2.5 py-1 hover:bg-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      :disabled="item.status !== 'succeeded'"
                      @click="download(item.session_id, 'txt')"
                    >
                      导出 TXT
                    </button>
                    <button
                      class="text-xs border border-zinc-300 rounded-lg px-2.5 py-1 hover:bg-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      :disabled="item.status !== 'succeeded'"
                      @click="download(item.session_id, 'json')"
                    >
                      导出 JSON
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!sessions.length" class="text-sm text-zinc-400 mt-3">暂无会话记录</p>
      </section>
    </div>

    <!-- Detail Drawer -->
    <div v-if="detailOpen" class="fixed inset-0 bg-black/30 z-[70]" @click="closeDetail"></div>
    <aside
      v-if="detailOpen"
      class="fixed top-0 right-0 w-[min(720px,92vw)] h-screen overflow-y-auto bg-zinc-50 border-l border-zinc-200 shadow-xl z-[80] p-6"
    >
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-semibold text-zinc-900">会话详情</h2>
        <div class="flex gap-2">
          <button
            class="text-sm border border-zinc-300 rounded-lg px-3 py-1.5 hover:bg-zinc-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            :disabled="!currentDetail || currentDetail.status !== 'succeeded'"
            @click="downloadRawOut"
          >
            下载 raw_out
          </button>
          <button
            class="text-sm text-zinc-600 border border-zinc-300 rounded-lg px-3 py-1.5 hover:bg-zinc-100 transition-colors"
            @click="closeDetail"
          >
            关闭
          </button>
        </div>
      </div>

      <template v-if="currentDetail">
        <div class="space-y-2 text-sm">
          <p><span class="font-medium text-zinc-700">Session:</span> {{ currentDetail.session_id }}</p>
          <p>
            <span class="font-medium text-zinc-700">状态:</span>
            <span class="inline-block ml-1 px-2 py-0.5 rounded-full text-xs font-medium" :class="statusClass(currentDetail.status)">
              {{ currentDetail.status }}
            </span>
          </p>
          <p v-if="detailStatusHint" class="text-zinc-500">{{ detailStatusHint }}</p>
          <p v-if="detailError" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            详情请求错误: {{ detailError }}
          </p>
          <p v-if="currentDetail.error_message" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            错误: {{ currentDetail.error_message }}
          </p>
        </div>

        <div class="mt-5 bg-white border border-zinc-200 rounded-xl p-4">
          <h3 class="text-sm font-semibold text-zinc-900 mb-2">模型原始输出 (raw_out)</h3>
          <pre class="max-h-[260px] overflow-auto p-3 rounded-lg border border-zinc-200 bg-zinc-50 text-xs leading-relaxed whitespace-pre-wrap break-words">{{ rawOutDisplay }}</pre>
        </div>
      </template>
      <template v-else>
        <p class="text-sm text-zinc-400">暂无详情数据</p>
      </template>
    </aside>
  </div>
</template>
