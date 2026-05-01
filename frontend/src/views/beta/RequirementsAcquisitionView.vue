<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="roleType"
        :roleLabel="roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <!-- 页面头部 -->
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 需求采集</span>
          </div>
          <div class="nav-center">
            <span class="jama-pill">Phase 1: 录音解析入库</span>
          </div>
          <div class="page-actions">
            <button 
              type="button" 
              class="action-btn brown sa-button sa-button--primary"
              @click="loadSampleTranscript"
              :disabled="isSampleLoading"
            >
              {{ isSampleLoading ? '加载中...' : '加载示例' }}
            </button>
          </div>
        </section>

        <!-- 主内容区域 -->
        <section class="acquisition-content" data-animate style="--delay: 0.1s">
          <div class="acquisition-grid">
            <!-- 左侧：输入区域 -->
            <div class="input-panel">
              <div class="panel-header">
                <h3 class="panel-title">转写文本输入</h3>
              </div>
              <div class="panel-body">
                <!-- Session ID -->
                <div class="form-group">
                  <label class="form-label">Session ID（可空）</label>
                  <input
                    v-model="sessionId"
                    type="text"
                    placeholder="留空则后端自动生成"
                    class="form-input sa-input"
                  />
                </div>

                <!-- 转写文本 -->
                <div class="form-group">
                  <label class="form-label">会议转写文本</label>
                  <textarea
                    v-model="transcriptText"
                    class="form-textarea sa-input"
                    placeholder="粘贴会议转写文本（支持 [start-end] speaker text 或 speaker: text）"
                  ></textarea>
                </div>

                <!-- 提交按钮 -->
                <button
                  @click="ingestTranscript"
                  :disabled="!canSubmit"
                  class="action-btn brown full-width sa-button sa-button--primary"
                >
                  {{ isLoading ? '解析中...' : '开始解析并入库' }}
                </button>

                <!-- 错误提示 -->
                <div v-if="error" class="error-box">
                  {{ error }}
                </div>
              </div>
            </div>

            <!-- 右侧：结果区域 -->
            <div class="result-panel">
              <div class="panel-header">
                <h3 class="panel-title">解析进度</h3>
              </div>
              <div class="panel-body">
                <!-- 进度卡片 -->
                <div class="progress-grid">
                  <div class="progress-card">
                    <div class="progress-label">INIT</div>
                    <div class="progress-value">chars: {{ receivedChars }}</div>
                    <div class="progress-value">lines: {{ receivedLines }}</div>
                  </div>
                  <div class="progress-card">
                    <div class="progress-label">PARSED</div>
                    <div class="progress-value">spans: {{ spanTotal }}</div>
                    <div class="progress-value">speakers: {{ stats?.speaker_count ?? '-' }}</div>
                  </div>
                  <div class="progress-card">
                    <div class="progress-label">DB UPSERTED</div>
                    <div class="progress-value">count: {{ upsertedCount }}</div>
                  </div>
                  <div class="progress-card">
                    <div class="progress-label">TIMESTAMP RATIO</div>
                    <div class="progress-value">{{ stats ? stats.has_timestamp_ratio.toFixed(2) : '-' }}</div>
                  </div>
                </div>

                <!-- Warnings -->
                <div class="section-block">
                  <h4 class="section-title">Warnings</h4>
                  <div v-if="warnings.length" class="warnings-list">
                    <div v-for="(warning, index) in warnings" :key="index" class="warning-item">
                      {{ warning }}
                    </div>
                  </div>
                  <p v-else class="empty-text">暂无警告</p>
                </div>

                <!-- Spans 预览 -->
                <div class="section-block">
                  <h4 class="section-title">Spans 预览</h4>
                  <div v-if="spansPreview.length" class="spans-table-wrapper">
                    <table class="spans-table">
                      <thead>
                        <tr>
                          <th>span_id</th>
                          <th>start-end</th>
                          <th>speaker</th>
                          <th>text</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="span in spansPreview" :key="span.span_id">
                          <td class="col-id">{{ span.span_id }}</td>
                          <td>{{ span.start_ms ?? '-' }} - {{ span.end_ms ?? '-' }}</td>
                          <td>{{ span.speaker }}</td>
                          <td class="col-text">{{ span.text }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="empty-text">暂无解析结果</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import Sidebar from "../../components/beta/Sidebar.vue";
import { useBetaNavigation, useBetaSidebarProps } from "@/composables/useBetaNavigation";

const { activePage, handleNavigate, handleExit } = useBetaNavigation("requirements-acquisition");
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps();

// Phase 1 解析状态（复用 TranscriptIngestion.vue）
const sessionId = ref('');
const transcriptText = ref('');
const isLoading = ref(false);
const isSampleLoading = ref(false);
const error = ref('');
const warnings = ref([]);
const spansPreview = ref([]);
const stats = ref(null);

const receivedChars = ref(0);
const receivedLines = ref(0);
const spanTotal = ref(0);
const upsertedCount = ref(0);

const canSubmit = computed(() => !isLoading.value && transcriptText.value.trim().length > 0);

function resetState() {
  error.value = '';
  warnings.value = [];
  spansPreview.value = [];
  stats.value = null;
  receivedChars.value = 0;
  receivedLines.value = 0;
  spanTotal.value = 0;
  upsertedCount.value = 0;
}

function handleStreamEvent(payload) {
  const eventType = payload?.event;
  if (eventType === 'init') {
    if (payload.session_id) {
      sessionId.value = payload.session_id;
    }
    receivedChars.value = payload.received_chars || 0;
    receivedLines.value = payload.received_lines || 0;
    return;
  }
  if (eventType === 'parsed') {
    spanTotal.value = payload.span_total || 0;
    warnings.value = payload.warnings || [];
    stats.value = payload.stats || null;
    return;
  }
  if (eventType === 'db_upserted') {
    upsertedCount.value = payload.upserted_count || 0;
    return;
  }
  if (eventType === 'final') {
    const data = payload.data || {};
    if (data.session_id) {
      sessionId.value = data.session_id;
      // 保存到 localStorage，便于其他界面使用
      localStorage.setItem('lastSessionId', data.session_id);
    }
    spanTotal.value = data.span_total || spanTotal.value;
    warnings.value = data.warnings || warnings.value;
    stats.value = data.stats || stats.value;
    spansPreview.value = data.spans_preview || [];
  }
}

async function loadSampleTranscript() {
  if (isSampleLoading.value) return;
  isSampleLoading.value = true;

  try {
    const response = await fetch('/api/analysis/sample_transcript', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`加载示例失败: HTTP ${response.status}`);
    }
    const text = await response.text();
    if (!text.trim()) {
      throw new Error('示例文件为空');
    }
    transcriptText.value = text;
  } catch (err) {
    error.value = err.message || '加载示例失败';
  } finally {
    isSampleLoading.value = false;
  }
}

async function ingestTranscript() {
  if (!canSubmit.value) return;

  isLoading.value = true;
  resetState();

  const payload = {
    transcript_text: transcriptText.value,
    options: {
      estimate_timestamps_if_missing: true,
      default_span_ms: 8000,
      max_spans_returned: 200
    }
  };
  if (sessionId.value.trim()) {
    payload.session_id = sessionId.value.trim();
  }

  try {
    const response = await fetch('/api/analysis/ingest_transcript/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    if (!response.body) {
      throw new Error('Empty response body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let gotFinal = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let splitIndex = buffer.indexOf('\n\n');
      while (splitIndex !== -1) {
        const rawEvent = buffer.slice(0, splitIndex);
        buffer = buffer.slice(splitIndex + 2);
        splitIndex = buffer.indexOf('\n\n');

        const lines = rawEvent.split('\n');
        const dataLines = lines.filter((line) => line.startsWith('data:'));
        const dataStr = dataLines.map((line) => line.slice(5).trim()).join('');
        if (!dataStr) continue;
        try {
          const eventPayload = JSON.parse(dataStr);
          handleStreamEvent(eventPayload);
          if (eventPayload.event === 'final') {
            gotFinal = true;
            await reader.cancel();
            break;
          }
        } catch {
          error.value = 'Invalid stream payload';
        }
      }
      if (gotFinal || error.value) {
        break;
      }
    }

    if (!gotFinal && !error.value) {
      error.value = 'Stream ended without final event';
    }
  } catch (err) {
    error.value = err.message || '请求失败';
  } finally {
    isLoading.value = false;
  }
}

</script>

<style scoped>
/* 主内容区域 */
.acquisition-content {
  padding: 24px;
  height: calc(100vh - 140px);
  overflow-y: auto;
}

.acquisition-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  height: 100%;
}

/* 面板通用样式 */
.input-panel,
.result-panel {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
  background: rgba(250, 250, 250, 0.5);
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-950);
  margin: 0;
}

.panel-body {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
}

/* 表单样式 */
.form-group {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-950);
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
  color: var(--ink-950);
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--copper-500);
}

.form-textarea {
  width: 100%;
  min-height: 240px;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
  color: var(--ink-950);
  resize: vertical;
  font-family: inherit;
}

.form-textarea:focus {
  outline: none;
  border-color: var(--copper-500);
}

.action-btn.full-width {
  width: 100%;
  padding: 12px;
  font-size: 14px;
}

.error-box {
  margin-top: 16px;
  padding: 12px 16px;
  font-size: 13px;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
}

/* 进度卡片 */
.progress-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.progress-card {
  padding: 14px;
  background: rgba(250, 250, 250, 0.8);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.progress-label {
  font-size: 10px;
  font-weight: 600;
  color: rgba(28, 40, 52, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.progress-value {
  font-size: 13px;
  color: var(--ink-950);
  margin-bottom: 2px;
}

/* 区块样式 */
.section-block {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-950);
  margin: 0 0 12px 0;
}

.empty-text {
  font-size: 13px;
  color: rgba(28, 40, 52, 0.5);
}

/* Warnings */
.warnings-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.warning-item {
  padding: 10px 14px;
  font-size: 13px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

/* Spans 表格 */
.spans-table-wrapper {
  overflow-x: auto;
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.spans-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.spans-table thead {
  background: rgba(250, 250, 250, 0.8);
}

.spans-table th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: rgba(28, 40, 52, 0.7);
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.3px;
}

.spans-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
  color: var(--ink-950);
}

.spans-table .col-id {
  font-family: monospace;
  font-size: 11px;
  color: rgba(28, 40, 52, 0.5);
}

.spans-table .col-text {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spans-table tbody tr:hover {
  background: rgba(196, 105, 47, 0.04);
}

/* 响应式 */
@media (max-width: 1200px) {
  .acquisition-grid {
    grid-template-columns: 1fr;
  }
}
</style>
