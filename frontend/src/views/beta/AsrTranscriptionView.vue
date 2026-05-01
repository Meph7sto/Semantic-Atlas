<template>
  <div class="asr-page">
    <header class="asr-header card sa-card">
      <div>
        <h1>语音转写</h1>
        <p>上传音视频文件，远端推理后返回模型原始输出。</p>
      </div>
      <button class="btn ghost sa-button sa-button--secondary" @click="loadSessions">刷新列表</button>
    </header>

    <section class="asr-upload card sa-card">
      <input
        type="file"
        accept=".wav,.mp3,.m4a,.mp4,audio/*,video/mp4"
        @change="onSelectFile"
      />
      <button class="btn primary sa-button sa-button--primary" :disabled="!selectedFile || uploading" @click="createSession">
        {{ uploading ? "上传中..." : "开始转写" }}
      </button>
      <span class="asr-hint">支持 wav/mp3/m4a/mp4</span>
    </section>

    <section class="asr-list card sa-card">
      <div class="asr-toolbar">
        <h2>会话列表</h2>
      </div>
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>文件</th>
            <th>状态</th>
            <th>尝试次数</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in sessions" :key="item.session_id">
            <td>{{ item.session_id }}</td>
            <td>{{ item.source_filename }}</td>
            <td>{{ item.status }}</td>
            <td>{{ item.attempt_count }}</td>
            <td>{{ item.updated_at }}</td>
            <td class="actions">
              <button class="btn" @click="viewDetail(item.session_id)">查看</button>
              <button
                class="btn"
                :disabled="item.status !== 'failed' && item.status !== 'timeout'"
                @click="retry(item.session_id)"
              >
                重试
              </button>
              <button class="btn" :disabled="item.status !== 'succeeded'" @click="download(item.session_id, 'txt')">
                导出 TXT
              </button>
              <button class="btn" :disabled="item.status !== 'succeeded'" @click="download(item.session_id, 'json')">
                导出 JSON
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="detailOpen" class="drawer-mask" @click="closeDetail"></div>
    <aside v-if="detailOpen" class="detail-drawer">
      <div class="detail-head">
        <h2>会话详情</h2>
        <div class="drawer-actions">
          <button
            class="btn"
            :disabled="!currentDetail || currentDetail.status !== 'succeeded'"
            @click="downloadRawOut"
          >
            下载 raw_out
          </button>
          <button class="btn ghost sa-button sa-button--secondary" @click="closeDetail">关闭</button>
        </div>
      </div>

      <template v-if="currentDetail">
        <p><strong>Session:</strong> {{ currentDetail.session_id }}</p>
        <p><strong>状态:</strong> <span :class="`status ${currentDetail.status}`">{{ currentDetail.status }}</span></p>
        <p v-if="detailStatusHint"><strong>提示:</strong> {{ detailStatusHint }}</p>
        <p v-if="detailError"><strong>详情请求错误:</strong> {{ detailError }}</p>
        <p v-if="currentDetail.error_message"><strong>错误:</strong> {{ currentDetail.error_message }}</p>

        <div class="panel">
          <h3>模型原始输出 (raw_out)</h3>
          <pre>{{ rawOutDisplay }}</pre>
        </div>
      </template>
      <template v-else>
        <p class="empty">暂无详情数据</p>
      </template>
    </aside>
  </div>
</template>

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

<style scoped>
.asr-page {
  --bg: linear-gradient(135deg, #f7fbff 0%, #f2f8f2 50%, #fff7ec 100%);
  --card-bg: rgba(255, 255, 255, 0.82);
  --line: #dde7dd;
  --text-muted: #52606d;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: var(--bg);
  min-height: 100%;
}

.card {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--card-bg);
  box-shadow: 0 10px 28px rgba(22, 38, 30, 0.06);
  padding: 14px;
}

.btn {
  border: 1px solid #c8d4c8;
  background: #fff;
  color: #1d2a1d;
  border-radius: 10px;
  padding: 6px 12px;
  cursor: pointer;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.btn.primary {
  background: linear-gradient(135deg, #1d7a5f, #31916f);
  border-color: transparent;
  color: #fff;
}

.btn.ghost {
  background: transparent;
}

.asr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.asr-header h1 {
  margin: 0 0 6px;
  letter-spacing: 0.5px;
}

.asr-header p {
  margin: 0;
  color: var(--text-muted);
}

.asr-upload {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.asr-hint {
  color: var(--text-muted);
  font-size: 13px;
}

.asr-toolbar h2 {
  margin: 0 0 8px;
}

.asr-list table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
}

.asr-list th,
.asr-list td {
  border: 1px solid #edf1ed;
  padding: 8px;
  text-align: left;
  font-size: 13px;
}

.asr-list th {
  background: #f7faf7;
}

.actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.drawer-actions {
  display: flex;
  gap: 8px;
}

.panel {
  border: 1px solid #e8efea;
  border-radius: 10px;
  padding: 10px;
  margin-top: 10px;
  background: #fff;
}

.panel h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.detail-drawer textarea {
  width: 100%;
  min-height: 180px;
  resize: vertical;
  border: 1px solid #dce6dc;
  border-radius: 8px;
  padding: 8px;
}

.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(10, 15, 12, 0.32);
  z-index: 70;
}

.detail-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: min(720px, 92vw);
  height: 100vh;
  padding: 18px;
  overflow-y: auto;
  background: #f8fcf8;
  border-left: 1px solid #dce8dc;
  box-shadow: -16px 0 28px rgba(17, 34, 22, 0.2);
  z-index: 80;
}

.empty {
  color: var(--text-muted);
  font-size: 13px;
}

pre {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid #dce6dc;
  background: #f8fbf8;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}

.status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: #eef2ef;
}

.status.succeeded {
  background: #e1f5ec;
  color: #0f6b45;
}

.status.failed,
.status.timeout {
  background: #fdecea;
  color: #a1301c;
}

@media (max-width: 960px) {
  .asr-page {
    padding: 12px;
  }

  .asr-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .detail-drawer {
    width: 100vw;
  }
}
</style>
