<script setup>
import { computed, ref } from 'vue'

const sessionId = ref('')
const transcriptText = ref('')
const isLoading = ref(false)
const isSampleLoading = ref(false)
const error = ref('')
const warnings = ref([])
const spansPreview = ref([])
const stats = ref(null)

const receivedChars = ref(0)
const receivedLines = ref(0)
const spanTotal = ref(0)
const upsertedCount = ref(0)

const canSubmit = computed(() => !isLoading.value && transcriptText.value.trim().length > 0)

function resetState() {
  error.value = ''
  warnings.value = []
  spansPreview.value = []
  stats.value = null
  receivedChars.value = 0
  receivedLines.value = 0
  spanTotal.value = 0
  upsertedCount.value = 0
}

function handleStreamEvent(payload) {
  const eventType = payload?.event
  if (eventType === 'init') {
    if (payload.session_id) {
      sessionId.value = payload.session_id
    }
    receivedChars.value = payload.received_chars || 0
    receivedLines.value = payload.received_lines || 0
    return
  }
  if (eventType === 'parsed') {
    spanTotal.value = payload.span_total || 0
    warnings.value = payload.warnings || []
    stats.value = payload.stats || null
    return
  }
  if (eventType === 'db_upserted') {
    upsertedCount.value = payload.upserted_count || 0
    return
  }
  if (eventType === 'final') {
    const data = payload.data || {}
    if (data.session_id) {
      sessionId.value = data.session_id
    }
    spanTotal.value = data.span_total || spanTotal.value
    warnings.value = data.warnings || warnings.value
    stats.value = data.stats || stats.value
    spansPreview.value = data.spans_preview || []
  }
}

async function loadSampleTranscript() {
  if (isSampleLoading.value) return
  isSampleLoading.value = true

  try {
    const response = await fetch('/api/v2/analysis/sample_transcript', { cache: 'no-store' })
    if (!response.ok) {
      throw new Error(`加载示例失败: HTTP ${response.status}`)
      return
    }
    const text = await response.text()
    if (!text.trim()) {
      throw new Error('示例文件为空')
    }
    transcriptText.value = text
  } catch (err) {
    error.value = err.message || '加载示例失败'
  } finally {
    isSampleLoading.value = false
  }
}

async function ingestTranscript() {
  if (!canSubmit.value) return

  isLoading.value = true
  resetState()

  const payload = {
    transcript_text: transcriptText.value,
    options: {
      estimate_timestamps_if_missing: true,
      default_span_ms: 8000,
      max_spans_returned: 200
    }
  }
  if (sessionId.value.trim()) {
    payload.session_id = sessionId.value.trim()
  }

  try {
    const response = await fetch('/api/v2/analysis/ingest_transcript/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `HTTP ${response.status}`)
    }

    if (!response.body) {
      throw new Error('Empty response body')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let gotFinal = false

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let splitIndex = buffer.indexOf('\n\n')
      while (splitIndex !== -1) {
        const rawEvent = buffer.slice(0, splitIndex)
        buffer = buffer.slice(splitIndex + 2)
        splitIndex = buffer.indexOf('\n\n')

        const lines = rawEvent.split('\n')
        const dataLines = lines.filter((line) => line.startsWith('data:'))
        const dataStr = dataLines.map((line) => line.slice(5).trim()).join('')
        if (!dataStr) continue
        try {
          const payload = JSON.parse(dataStr)
          handleStreamEvent(payload)
          if (payload.event === 'final') {
            gotFinal = true
            await reader.cancel()
            break
          }
        } catch (err) {
          error.value = 'Invalid stream payload'
        }
      }
      if (gotFinal || error.value) {
        break
      }
    }

    if (!gotFinal && !error.value) {
      error.value = 'Stream ended without final event'
    }
  } catch (err) {
    error.value = err.message || '请求失败'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <header class="bg-white border-b border-zinc-200 px-6 py-4">
      <h2 class="text-xl font-semibold text-zinc-900">Transcript 解析入库</h2>
      <p class="text-sm text-zinc-500 mt-1">仅执行第 1 阶段：解析 spans 并写入数据库</p>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm">
          <div class="space-y-4">
            <div>
              <label class="text-sm font-medium text-zinc-700">Session ID（可空）</label>
              <input
                v-model="sessionId"
                type="text"
                placeholder="留空则后端自动生成"
                class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
              />
            </div>

            <div>
              <div class="flex items-center justify-between">
                <label class="text-sm font-medium text-zinc-700">会议转写文本</label>
                <button
                  type="button"
                  class="text-xs text-zinc-600 border border-zinc-300 rounded-full px-2 py-1 hover:bg-zinc-100 disabled:opacity-50"
                  :disabled="isSampleLoading"
                  @click="loadSampleTranscript"
                >
                  {{ isSampleLoading ? '加载中...' : '加载示例' }}
                </button>
              </div>
              <textarea
                v-model="transcriptText"
                class="mt-2 w-full min-h-[220px] rounded-lg border border-zinc-300 p-3 text-sm leading-relaxed resize-y focus:border-black focus:ring-black"
                placeholder="粘贴会议转写文本（支持 [start-end] speaker text 或 speaker: text）"
              ></textarea>
            </div>

            <button
              @click="ingestTranscript"
              :disabled="!canSubmit"
              class="w-full bg-black text-white py-2.5 rounded-lg font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isLoading ? '解析中...' : '开始解析并入库' }}
            </button>

            <p v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {{ error }}
            </p>
          </div>
        </section>

        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-5">
          <div>
            <h3 class="text-base font-semibold text-zinc-900">解析进度</h3>
            <div class="mt-3 grid grid-cols-2 gap-3 text-sm text-zinc-600">
              <div class="rounded-lg border border-zinc-200 px-3 py-2">
                <div class="text-xs uppercase text-zinc-400">Init</div>
                <div class="mt-1">chars: {{ receivedChars }}</div>
                <div>lines: {{ receivedLines }}</div>
              </div>
              <div class="rounded-lg border border-zinc-200 px-3 py-2">
                <div class="text-xs uppercase text-zinc-400">Parsed</div>
                <div class="mt-1">spans: {{ spanTotal }}</div>
                <div>speakers: {{ stats?.speaker_count ?? '-' }}</div>
              </div>
              <div class="rounded-lg border border-zinc-200 px-3 py-2">
                <div class="text-xs uppercase text-zinc-400">DB Upserted</div>
                <div class="mt-1">count: {{ upsertedCount }}</div>
              </div>
              <div class="rounded-lg border border-zinc-200 px-3 py-2">
                <div class="text-xs uppercase text-zinc-400">Timestamp Ratio</div>
                <div class="mt-1">{{ stats ? stats.has_timestamp_ratio.toFixed(2) : '-' }}</div>
              </div>
            </div>
          </div>

          <div>
            <h3 class="text-base font-semibold text-zinc-900">Warnings</h3>
            <div v-if="warnings.length" class="mt-2 space-y-1 text-sm text-amber-700">
              <div v-for="(warning, index) in warnings" :key="index" class="bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
                {{ warning }}
              </div>
            </div>
            <p v-else class="text-sm text-zinc-400 mt-2">暂无警告</p>
          </div>

          <div>
            <h3 class="text-base font-semibold text-zinc-900">Spans 预览</h3>
            <div v-if="spansPreview.length" class="mt-3 overflow-x-auto border border-zinc-200 rounded-lg">
              <table class="min-w-full text-sm text-left">
                <thead class="bg-zinc-100 text-zinc-600">
                  <tr>
                    <th class="px-3 py-2 font-medium">span_id</th>
                    <th class="px-3 py-2 font-medium">start-end</th>
                    <th class="px-3 py-2 font-medium">speaker</th>
                    <th class="px-3 py-2 font-medium">text</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="span in spansPreview" :key="span.span_id" class="border-t border-zinc-200">
                    <td class="px-3 py-2 font-mono text-xs text-zinc-500">{{ span.span_id }}</td>
                    <td class="px-3 py-2">
                      {{ span.start_ms ?? '-' }} - {{ span.end_ms ?? '-' }}
                    </td>
                    <td class="px-3 py-2">{{ span.speaker }}</td>
                    <td class="px-3 py-2">{{ span.text }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="text-sm text-zinc-400 mt-2">暂无解析结果</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
