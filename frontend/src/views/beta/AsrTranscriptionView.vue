<template>
  <div class="asr-page">
    <header class="asr-header">
      <h1>语音转写</h1>
      <p>上传音频或 MP4，远端 VibeVoice ASR 转写后回传并保存为会话。</p>
    </header>

    <section class="asr-upload">
      <input type="file" accept=".wav,.mp3,.m4a,.mp4,audio/*,video/mp4" @change="onSelectFile" />
      <button :disabled="!selectedFile || uploading" @click="createSession">
        {{ uploading ? "上传中..." : "开始转写" }}
      </button>
      <span class="asr-hint">支持 wav/mp3/m4a/mp4</span>
    </section>

    <section class="asr-list">
      <div class="asr-toolbar">
        <h2>会话列表</h2>
        <button @click="loadSessions">刷新</button>
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
              <button @click="viewDetail(item.session_id)">查看</button>
              <button
                :disabled="item.status !== 'failed' && item.status !== 'timeout'"
                @click="retry(item.session_id)"
              >
                重试
              </button>
              <button :disabled="item.status !== 'succeeded'" @click="download(item.session_id, 'txt')">
                导出 TXT
              </button>
              <button :disabled="item.status !== 'succeeded'" @click="download(item.session_id, 'json')">
                导出 JSON
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="currentDetail" class="asr-detail">
      <h2>会话详情</h2>
      <p><strong>Session:</strong> {{ currentDetail.session_id }}</p>
      <p><strong>状态:</strong> {{ currentDetail.status }}</p>
      <p v-if="currentDetail.error_message"><strong>错误:</strong> {{ currentDetail.error_message }}</p>
      <textarea readonly :value="currentDetail.transcript_text || ''"></textarea>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { asrApi } from '@/api/asr'

const selectedFile = ref(null)
const uploading = ref(false)
const sessions = ref([])
const currentDetail = ref(null)

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

async function viewDetail(sessionId) {
  try {
    currentDetail.value = await asrApi.getSession(sessionId)
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '加载详情失败'
    window.alert(detail)
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

onMounted(async () => {
  await loadSessions()
})
</script>

<style scoped>
.asr-page {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.asr-header h1 {
  margin: 0 0 8px;
}

.asr-upload {
  display: flex;
  align-items: center;
  gap: 12px;
}

.asr-hint {
  color: #5f6368;
  font-size: 13px;
}

.asr-list table {
  width: 100%;
  border-collapse: collapse;
}

.asr-list th,
.asr-list td {
  border: 1px solid #e4e7ec;
  padding: 8px;
  text-align: left;
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.asr-detail textarea {
  width: 100%;
  min-height: 220px;
  resize: vertical;
}
</style>

