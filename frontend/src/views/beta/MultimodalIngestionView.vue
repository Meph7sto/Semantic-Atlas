<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="currentUser?.role || roleType"
        :roleLabel="currentUser?.display_name || currentUser?.username || roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />

      <main class="canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 多模态采集</span>
          </div>
          <div class="page-actions">
            <span class="nav-text">复用现有后端接口</span>
          </div>
        </section>

        <section class="media-shell" data-animate style="--delay: 0.12s">
          <div class="media-tabs">
            <button
              type="button"
              class="media-tab"
              :class="{ active: activeTab === 'vision' }"
              @click="activeTab = 'vision'"
            >
              图生文
            </button>
            <button
              type="button"
              class="media-tab"
              :class="{ active: activeTab === 'asr' }"
              @click="activeTab = 'asr'"
            >
              音频转文字
            </button>
          </div>

          <div v-show="activeTab === 'vision'" class="media-panel">
            <header class="media-section-header">
              <h2>图生文</h2>
              <p>上传图片生成文字预览，并可确认写入 spans。</p>
            </header>

            <section class="card-block sa-card">
              <h3>步骤 1：上传图片并生成图生文</h3>

              <div class="form-grid">
                <label class="field">
                  <span>图片文件</span>
                  <input
                    type="file"
                    accept="image/*"
                    class="input"
                    @change="onVisionFileChange"
                  />
                  <small v-if="visionSelectedFileName">已选择：{{ visionSelectedFileName }}</small>
                </label>

                <label class="field">
                  <span>speaker</span>
                  <input v-model="visionSpeaker" type="text" class="input" />
                </label>
              </div>

              <div class="form-grid">
                <label class="field">
                  <span>prompt</span>
                  <textarea v-model="visionPrompt" rows="4" class="input textarea"></textarea>
                </label>

                <label class="field">
                  <span>max_new_tokens</span>
                  <input v-model.number="visionMaxNewTokens" type="number" min="1" class="input" />
                  <small>若远端服务未预热，首次生成可能耗时较长。</small>
                </label>
              </div>

              <button
                type="button"
                class="action-btn dark sa-button sa-button--primary"
                :disabled="visionGenerating"
                @click="generateCaption"
              >
                {{ visionGenerating ? '图生文生成中...' : '生成图生文' }}
              </button>
            </section>

            <section v-if="visionGenerated" class="card-block sa-card">
              <h3>步骤 2：确认入库 spans</h3>

              <div class="info-grid">
                <div class="info-card">
                  <div class="info-label">preview_id</div>
                  <div class="info-value mono">{{ visionGenerated.preview?.preview_id }}</div>
                </div>
                <div class="info-card">
                  <div class="info-label">filename</div>
                  <div class="info-value">{{ visionGenerated.result?.filename }}</div>
                </div>
              </div>

              <div class="preview-block">
                <h4>caption</h4>
                <div class="preview-box">{{ visionGenerated.result?.caption }}</div>
              </div>

              <div class="preview-block">
                <h4>transcript_text（将用于入库）</h4>
                <div class="preview-box mono">{{ visionGenerated.result?.transcript_text }}</div>
              </div>

              <div class="card-subtle sa-card">
                <h4>入库参数</h4>

                <div class="form-grid triple">
                  <label class="field">
                    <span>session_id（可空）</span>
                    <input
                      v-model="visionSessionId"
                      type="text"
                      class="input"
                      placeholder="留空则自动生成"
                    />
                  </label>
                  <label class="field">
                    <span>default_span_ms</span>
                    <input v-model.number="visionDefaultSpanMs" type="number" min="1" class="input" />
                  </label>
                  <label class="field">
                    <span>max_spans_returned</span>
                    <input v-model.number="visionMaxSpansReturned" type="number" min="1" class="input" />
                  </label>
                </div>

                <label class="checkbox-row">
                  <input v-model="visionEstimateTimestamps" type="checkbox" />
                  <span>estimate_timestamps_if_missing</span>
                </label>

                <button
                  type="button"
                  class="action-btn dark sa-button sa-button--primary"
                  :disabled="visionConfirming"
                  @click="confirmVisionIngest"
                >
                  {{ visionConfirming ? '确认中...' : '确认并写入 spans' }}
                </button>
              </div>
            </section>

            <div v-if="visionConfirmResult" class="message success">
              入库成功：session_id={{ visionConfirmResult.session_id }}，span_total={{ visionConfirmResult.span_total }}
            </div>

            <div v-if="visionError" class="message error">
              {{ visionError }}
            </div>
          </div>

          <div v-show="activeTab === 'asr'" class="media-panel">
            <header class="media-section-header">
              <h2>音频转文字</h2>
              <p>上传音视频文件，远端转写后可查看详情并导出结果。</p>
            </header>

            <section class="card-block sa-card">
              <div class="toolbar-row">
                <h3>上传文件</h3>
                <button type="button" class="action-btn light sa-button sa-button--secondary" @click="loadAsrSessions">刷新列表</button>
              </div>

              <div class="upload-row">
                <input
                  type="file"
                  accept=".wav,.mp3,.m4a,.mp4,audio/*,video/mp4"
                  class="input"
                  @change="onAsrFileChange"
                />
                <button
                  type="button"
                  class="action-btn dark sa-button sa-button--primary"
                  :disabled="!asrSelectedFile || asrUploading"
                  @click="createAsrSession"
                >
                  {{ asrUploading ? '上传中...' : '开始转写' }}
                </button>
                <span class="hint">支持 wav / mp3 / m4a / mp4</span>
              </div>
            </section>

            <section class="card-block sa-card">
              <h3>会话列表</h3>

              <div class="table-wrap">
                <table class="data-table">
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
                    <tr v-for="item in asrSessions" :key="item.session_id">
                      <td class="mono">{{ item.session_id }}</td>
                      <td>{{ item.source_filename }}</td>
                      <td>
                        <span class="status-pill" :class="asrStatusClass(item.status)">
                          {{ item.status }}
                        </span>
                      </td>
                      <td>{{ item.attempt_count }}</td>
                      <td>{{ item.updated_at }}</td>
                      <td class="actions">
                        <button type="button" class="action-btn tiny light sa-button sa-button--secondary" @click="viewAsrDetail(item.session_id)">
                          查看
                        </button>
                        <button
                          type="button"
                          class="action-btn tiny light sa-button sa-button--secondary"
                          :disabled="item.status !== 'failed' && item.status !== 'timeout'"
                          @click="retryAsrSession(item.session_id)"
                        >
                          重试
                        </button>
                        <button
                          type="button"
                          class="action-btn tiny light sa-button sa-button--secondary"
                          :disabled="item.status !== 'succeeded'"
                          @click="downloadAsr(item.session_id, 'txt')"
                        >
                          导出 TXT
                        </button>
                        <button
                          type="button"
                          class="action-btn tiny light sa-button sa-button--secondary"
                          :disabled="item.status !== 'succeeded'"
                          @click="downloadAsr(item.session_id, 'json')"
                        >
                          导出 JSON
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <p v-if="!asrSessions.length" class="empty-text">暂无会话记录</p>
            </section>
          </div>
        </section>
      </main>
    </div>

    <div v-if="asrDetailOpen" class="drawer-mask" @click="closeAsrDetail"></div>
    <aside v-if="asrDetailOpen" class="detail-drawer">
      <div class="detail-head">
        <h2>会话详情</h2>
        <div class="drawer-actions">
          <button
            type="button"
            class="action-btn light sa-button sa-button--secondary"
            :disabled="!asrCurrentDetail || asrCurrentDetail.status !== 'succeeded'"
            @click="downloadAsrRawOut"
          >
            下载 raw_out
          </button>
          <button type="button" class="action-btn light sa-button sa-button--secondary" @click="closeAsrDetail">关闭</button>
        </div>
      </div>

      <template v-if="asrCurrentDetail">
        <p><strong>Session:</strong> {{ asrCurrentDetail.session_id }}</p>
        <p><strong>状态:</strong> {{ asrCurrentDetail.status }}</p>
        <p v-if="asrDetailStatusHint"><strong>提示:</strong> {{ asrDetailStatusHint }}</p>
        <p v-if="asrDetailError" class="message error">{{ asrDetailError }}</p>
        <p v-if="asrCurrentDetail.error_message" class="message error">{{ asrCurrentDetail.error_message }}</p>

        <div class="preview-block">
          <h4>模型原始输出 (raw_out)</h4>
          <pre class="preview-box mono preformatted">{{ asrRawOutDisplay }}</pre>
        </div>
      </template>
      <template v-else>
        <p class="empty-text">暂无详情数据</p>
      </template>
    </aside>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Sidebar from '../../components/beta/Sidebar.vue'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'
import { visionApi } from '@/api'
import { asrApi } from '@/api/asr'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('multimodal-ingestion')
const { currentUser, roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

const activeTab = ref('vision')

const visionPrompt = ref('请详细描述图片内容，并总结关键信息。')
const visionSpeaker = ref('vision_agent')
const visionMaxNewTokens = ref(256)
const visionSessionId = ref('')
const visionDefaultSpanMs = ref(8000)
const visionMaxSpansReturned = ref(200)
const visionEstimateTimestamps = ref(true)
const visionSelectedFile = ref(null)
const visionSelectedFileName = ref('')
const visionGenerating = ref(false)
const visionConfirming = ref(false)
const visionError = ref('')
const visionGenerated = ref(null)
const visionConfirmResult = ref(null)

function normalizeError(err, fallback = '请求失败') {
  if (!err) return fallback
  if (typeof err === 'string') return err
  return err.response?.data?.detail || err.message || fallback
}

function onVisionFileChange(event) {
  const file = event?.target?.files?.[0] || null
  visionSelectedFile.value = file
  visionSelectedFileName.value = file?.name || ''
}

async function generateCaption() {
  if (!visionSelectedFile.value) {
    visionError.value = '请先选择图片'
    return
  }

  visionGenerating.value = true
  visionError.value = ''
  visionConfirmResult.value = null
  try {
    const data = await visionApi.captionImage(visionSelectedFile.value, {
      prompt: visionPrompt.value,
      speaker: visionSpeaker.value,
      maxNewTokens: visionMaxNewTokens.value,
    })
    visionGenerated.value = data
  } catch (error) {
    visionError.value = normalizeError(error, '图生文生成失败')
  } finally {
    visionGenerating.value = false
  }
}

async function confirmVisionIngest() {
  const previewId = visionGenerated.value?.preview?.preview_id
  if (!previewId) {
    visionError.value = '请先生成图生文结果'
    return
  }

  visionConfirming.value = true
  visionError.value = ''
  visionConfirmResult.value = null
  try {
    const data = await visionApi.confirmPreview(previewId, {
      sessionId: visionSessionId.value,
      estimateTimestampsIfMissing: visionEstimateTimestamps.value,
      defaultSpanMs: visionDefaultSpanMs.value,
      maxSpansReturned: visionMaxSpansReturned.value,
    })
    visionConfirmResult.value = data
  } catch (error) {
    visionError.value = normalizeError(error, '确认入库失败')
  } finally {
    visionConfirming.value = false
  }
}

const asrSelectedFile = ref(null)
const asrUploading = ref(false)
const asrSessions = ref([])
const asrCurrentDetail = ref(null)
const asrDetailOpen = ref(false)
const asrDetailError = ref('')
const asrDetailRefreshing = ref(false)
const asrTerminalStatuses = new Set(['succeeded', 'failed', 'timeout'])
let asrDetailPollTimer = null

const asrRawOutDisplay = computed(() => asrCurrentDetail.value?.transcript_text || '无原始结果')
const asrDetailStatusHint = computed(() => {
  const status = asrCurrentDetail.value?.status
  if (!status) return ''
  if (status === 'queued') return '转写任务已排队，正在等待远端处理...'
  if (status === 'running') return '转写任务正在处理，请稍候...'
  if (status === 'failed') return '转写失败，请查看错误信息并可点击重试。'
  if (status === 'timeout') return '转写超时，请点击重试。'
  if (status === 'succeeded') return '转写已完成。'
  return ''
})

function asrStatusClass(status) {
  if (status === 'succeeded') return 'success'
  if (status === 'failed' || status === 'timeout') return 'danger'
  if (status === 'running') return 'info'
  return 'muted'
}

function onAsrFileChange(event) {
  const file = event?.target?.files?.[0]
  asrSelectedFile.value = file || null
}

async function createAsrSession() {
  if (!asrSelectedFile.value || asrUploading.value) return
  asrUploading.value = true
  try {
    await asrApi.createSession(asrSelectedFile.value)
    asrSelectedFile.value = null
    await loadAsrSessions()
  } catch (error) {
    window.alert(normalizeError(error, '上传失败'))
  } finally {
    asrUploading.value = false
  }
}

async function loadAsrSessions() {
  try {
    const data = await asrApi.listSessions({ page: 1, per_page: 30 })
    asrSessions.value = data.items || []
  } catch (error) {
    window.alert(normalizeError(error, '加载会话失败'))
  }
}

function stopAsrDetailPolling() {
  if (asrDetailPollTimer) {
    clearInterval(asrDetailPollTimer)
    asrDetailPollTimer = null
  }
}

async function refreshAsrDetail(sessionId, silent = false) {
  if (!sessionId || asrDetailRefreshing.value) return
  asrDetailRefreshing.value = true
  try {
    const detail = await asrApi.getSession(sessionId)
    asrCurrentDetail.value = detail
    asrDetailError.value = ''
    if (asrTerminalStatuses.has(detail.status)) {
      stopAsrDetailPolling()
    }
    if (!silent) {
      await loadAsrSessions()
    }
  } catch (error) {
    stopAsrDetailPolling()
    asrDetailError.value = normalizeError(error, '加载详情失败')
  } finally {
    asrDetailRefreshing.value = false
  }
}

function startAsrDetailPolling(sessionId) {
  stopAsrDetailPolling()
  asrDetailPollTimer = setInterval(() => {
    refreshAsrDetail(sessionId, true)
  }, 2500)
}

function closeAsrDetail() {
  asrDetailOpen.value = false
  stopAsrDetailPolling()
}

async function viewAsrDetail(sessionId) {
  asrDetailOpen.value = true
  asrDetailError.value = ''
  if (!asrCurrentDetail.value || asrCurrentDetail.value.session_id !== sessionId) {
    const row = asrSessions.value.find((item) => item.session_id === sessionId)
    if (row) {
      asrCurrentDetail.value = { ...row }
    }
  }
  await refreshAsrDetail(sessionId)
  const status = asrCurrentDetail.value?.status
  if (status && !asrTerminalStatuses.has(status)) {
    startAsrDetailPolling(sessionId)
  } else {
    stopAsrDetailPolling()
  }
}

async function retryAsrSession(sessionId) {
  try {
    await asrApi.retrySession(sessionId)
    await loadAsrSessions()
  } catch (error) {
    window.alert(normalizeError(error, '重试失败'))
  }
}

function downloadAsr(sessionId, format) {
  window.open(asrApi.exportUrl(sessionId, format), '_blank')
}

function downloadAsrRawOut() {
  if (!asrCurrentDetail.value?.session_id) return
  const content = asrCurrentDetail.value?.transcript_text || ''
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${asrCurrentDetail.value.session_id}_raw_out.txt`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  await loadAsrSessions()
})

onBeforeUnmount(() => {
  stopAsrDetailPolling()
})
</script>

<style scoped>
/* ── 媒体采集 shell ── */
.media-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Tab 切换 ── */
.media-tabs {
  display: inline-flex;
  gap: 4px;
  width: fit-content;
  padding: 4px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  background: rgba(255, 255, 255, 0.95);
}

.media-tab {
  border: 0;
  border-radius: 0;
  background: transparent;
  color: rgba(28, 40, 52, 0.6);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 16px;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.media-tab.active {
  background: var(--ink-950, #1b2730);
  color: #fff;
}

.media-tab:not(.active):hover {
  background: rgba(28, 40, 52, 0.05);
  color: var(--ink-950, #1b2730);
}

/* ── Panel ── */
.media-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.media-section-header h2,
.card-block h3,
.card-subtle h4,
.preview-block h4 {
  margin: 0;
  font-size: 14px;
  color: var(--ink-950, #1b2730);
}

.media-section-header p,
.hint,
.empty-text,
.field small {
  color: rgba(28, 40, 52, 0.55);
  font-size: 13px;
}

/* ── 卡片 ── */
.card-block {
  background: #fdfcf9;
  border: 1px solid rgba(28, 40, 52, 0.08);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-subtle {
  background: rgba(28, 40, 52, 0.03);
  border: 1px solid rgba(28, 40, 52, 0.06);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ── 表单 ── */
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-grid.triple {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.field > span {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(28, 40, 52, 0.5);
}

.input {
  width: 100%;
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 0;
  background: #fff;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--ink-950, #1b2730);
  outline: none;
  box-sizing: border-box;
}

.input:focus {
  border-color: rgba(47, 143, 137, 0.5);
}

.textarea {
  resize: vertical;
}

/* ── 按钮 ── */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  border-radius: 0;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  background: #fff;
  color: rgba(28, 40, 52, 0.7);
  transition: all 0.15s ease;
}

.action-btn:hover {
  background: rgba(28, 40, 52, 0.04);
  color: var(--ink-950, #1b2730);
}

.action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* dark → beta brown（主操作） */
.action-btn.dark {
  background: var(--accent, #c4692f);
  color: #fff;
  border-color: var(--accent, #c4692f);
}

.action-btn.dark:hover:not(:disabled) {
  background: var(--accent-strong, #a85424);
  border-color: var(--accent-strong, #a85424);
}

/* light → beta ghost */
.action-btn.light {
  background: #fff;
  border-color: rgba(28, 40, 52, 0.15);
  color: rgba(28, 40, 52, 0.7);
}

.action-btn.tiny {
  padding: 4px 10px;
  font-size: 11px;
}

/* ── 信息卡片 ── */
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.info-card {
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: rgba(28, 40, 52, 0.03);
  padding: 12px;
}

.info-label {
  color: rgba(28, 40, 52, 0.5);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  margin-top: 6px;
  color: var(--ink-950, #1b2730);
  font-size: 13px;
}

/* ── 预览块 ── */
.preview-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-box {
  max-height: 220px;
  overflow: auto;
  border: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(28, 40, 52, 0.02);
  padding: 12px;
  white-space: pre-wrap;
  color: rgba(28, 40, 52, 0.85);
  font-size: 13px;
}

.preformatted {
  margin: 0;
}

.mono {
  font-family: Consolas, 'Courier New', monospace;
}

/* ── 工具栏行 ── */
.checkbox-row,
.toolbar-row,
.upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-row {
  justify-content: space-between;
}

.upload-row {
  flex-wrap: wrap;
}

/* ── 表格 ── */
.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}

.data-table th {
  background: rgba(28, 40, 52, 0.03);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(28, 40, 52, 0.6);
}

.data-table tbody tr:hover {
  background: rgba(28, 40, 52, 0.02);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ── 状态标签 ── */
.status-pill {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
}

.status-pill.success {
  background: rgba(47, 143, 137, 0.12);
  color: #2f8f89;
  border: 1px solid rgba(47, 143, 137, 0.25);
}

.status-pill.danger {
  background: rgba(196, 91, 96, 0.12);
  color: #c45b60;
  border: 1px solid rgba(196, 91, 96, 0.25);
}

.status-pill.info {
  background: rgba(28, 40, 52, 0.08);
  color: rgba(28, 40, 52, 0.7);
  border: 1px solid rgba(28, 40, 52, 0.12);
}

.status-pill.muted {
  background: rgba(28, 40, 52, 0.05);
  color: rgba(28, 40, 52, 0.45);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

/* ── 消息提示 ── */
.message {
  padding: 10px 14px;
  font-size: 13px;
  border: 1px solid;
}

.message.success {
  background: rgba(47, 143, 137, 0.08);
  border-color: rgba(47, 143, 137, 0.25);
  color: #2f8f89;
}

.message.error {
  background: rgba(196, 91, 96, 0.08);
  border-color: rgba(196, 91, 96, 0.25);
  color: #c45b60;
}

/* ── 详情抽屉 ── */
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(28, 40, 52, 0.25);
  z-index: 70;
}

.detail-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: min(720px, 92vw);
  height: 100vh;
  overflow-y: auto;
  z-index: 80;
  background: #fdfcf9;
  border-left: 1px solid rgba(28, 40, 52, 0.12);
  box-shadow: -8px 0 24px rgba(28, 40, 52, 0.1);
  padding: 24px;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.drawer-actions {
  display: flex;
  gap: 8px;
}

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .form-grid,
  .form-grid.triple,
  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
