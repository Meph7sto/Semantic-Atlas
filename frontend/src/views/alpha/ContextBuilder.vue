<template>
  <div class="flex flex-col h-full w-full max-w-6xl mx-auto px-6 py-8 overflow-y-auto">
    <!-- Header -->
    <div class="text-center mb-8">
      <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight">Phase 2: 上下文构建</h2>
      <p class="text-zinc-500 mt-2 text-sm">基于关联图的语义分拣与动态打包 (Graph-based Context Building)</p>
    </div>

    <!-- Configuration Panel -->
    <div class="bg-white rounded-xl border border-zinc-200 shadow-sm p-6 mb-6">
      <h3 class="text-lg font-medium text-zinc-800 mb-4">配置参数</h3>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <!-- Session ID -->
        <div class="col-span-full">
          <label class="block text-sm font-medium text-zinc-700 mb-1">Session ID</label>
          <input
            v-model="sessionId"
            type="text"
            placeholder="输入 Phase 1 生成的 session_id"
            class="w-full px-3 py-2 border border-zinc-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
          />
        </div>

        <!-- Window Size -->
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">窗口大小 (window_size)</label>
          <div class="flex items-center gap-3">
            <input
              v-model.number="options.window_size"
              type="range"
              min="5"
              max="10"
              class="flex-1"
            />
            <span class="text-sm text-zinc-600 w-8">{{ options.window_size }}</span>
          </div>
        </div>

        <!-- Step Size -->
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">步长 (step_size)</label>
          <div class="flex items-center gap-3">
            <input
              v-model.number="options.step_size"
              type="range"
              min="1"
              :max="options.window_size - 1"
              class="flex-1"
            />
            <span class="text-sm text-zinc-600 w-8">{{ options.step_size }}</span>
          </div>
        </div>

        <!-- Tau -->
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">置信度阈值 (tau)</label>
          <div class="flex items-center gap-3">
            <input
              v-model.number="options.tau"
              type="range"
              min="0"
              max="1"
              step="0.05"
              class="flex-1"
            />
            <span class="text-sm text-zinc-600 w-12">{{ options.tau.toFixed(2) }}</span>
          </div>
        </div>

        <!-- Top K -->
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">Top-K per Node</label>
          <div class="flex items-center gap-3">
            <input
              v-model.number="options.top_k"
              type="range"
              min="2"
              max="5"
              class="flex-1"
            />
            <span class="text-sm text-zinc-600 w-8">{{ options.top_k }}</span>
          </div>
        </div>

        <!-- Token Limit -->
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">Bundle Token 上限</label>
          <input
            v-model.number="options.token_limit_per_bundle"
            type="number"
            min="1000"
            max="8000"
            step="500"
            class="w-full px-3 py-2 border border-zinc-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
          />
        </div>

        <!-- LLM Model -->
        <div class="col-span-full flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3">
          <div>
            <div class="text-sm font-medium text-zinc-700">DeepSeek 模型</div>
            <div class="text-xs text-zinc-500">当前: {{ llmModel }}</div>
          </div>
          <select
            v-model="selectedModel"
            class="h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-700 focus:border-zinc-500 focus:outline-none"
          >
            <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
            <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
          </select>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="useThinking" class="sr-only peer">
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
            <span class="ml-3 text-sm font-medium text-zinc-600">思考模式</span>
          </label>
        </div>

        <!-- Mock LLM -->
        <div class="flex items-center gap-2">
          <input
            v-model="options.mock_llm"
            type="checkbox"
            id="mock_llm"
            class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
          />
          <label for="mock_llm" class="text-sm font-medium text-zinc-700">Mock 模式 (无需 API Key)</label>
        </div>

        <div class="col-span-full rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-medium text-zinc-700">LLM 传输模式</div>
              <div class="text-xs text-zinc-500">流式接口更适合慢模型调用，适合长时间推理和窗口并行场景</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="options.use_streaming_llm" class="sr-only peer">
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
              <span class="ml-3 text-sm font-medium text-zinc-600">
                {{ options.use_streaming_llm ? '流式接口' : '普通补全' }}
              </span>
            </label>
          </div>
        </div>

        <!-- Parallel Processing Toggle -->
        <div class="col-span-full rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3">
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="text-sm font-medium text-zinc-700">窗口并行模式（Phase 2）</div>
              <div class="text-xs text-zinc-500">并行处理多个窗口（window），用于上下文构建提速</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="options.enable_parallel_windows" class="sr-only peer">
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              <span class="ml-3 text-sm font-medium text-zinc-600">启用窗口并行</span>
            </label>
          </div>

          <!-- Max Concurrent Windows -->
          <div v-if="options.enable_parallel_windows" class="mt-3">
            <label class="block text-sm font-medium text-zinc-700 mb-1">
              最大并发窗口数（Phase 2）
            </label>
            <div class="flex items-center gap-3">
              <input
                v-model.number="options.max_concurrent_windows"
                type="range"
                min="1"
                max="10"
                class="flex-1"
              />
              <span class="text-sm text-zinc-600 w-8">{{ options.max_concurrent_windows }}</span>
            </div>
            <p class="text-xs text-zinc-500 mt-1">推荐 3-5，过高可能触发 API 限流</p>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="mt-6 flex items-center gap-4">
        <button
          @click="startBuildContext"
          :disabled="!canStart"
          class="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium text-sm hover:bg-blue-700 disabled:bg-zinc-300 disabled:cursor-not-allowed transition-colors"
        >
          <span v-if="isLoading" class="flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            构建中...
          </span>
          <span v-else>开始构建上下文</span>
        </button>

        <button
          @click="resetState"
          class="px-4 py-2.5 border border-zinc-300 text-zinc-700 rounded-lg font-medium text-sm hover:bg-zinc-50 transition-colors"
        >
          重置
        </button>
      </div>
    </div>

    <!-- Progress Panel -->
    <div v-if="progressEvents.length > 0" class="bg-white rounded-xl border border-zinc-200 shadow-sm p-6 mb-6">
      <h3 class="text-lg font-medium text-zinc-800 mb-4">构建进度</h3>
      
      <div class="space-y-2 max-h-48 overflow-y-auto">
        <div
          v-for="(event, idx) in progressEvents"
          :key="idx"
          class="flex items-start gap-3 text-sm"
        >
          <span class="flex-shrink-0 w-20 text-zinc-400">{{ event.time }}</span>
          <span
            :class="{
              'text-blue-600': event.type === 'init' || event.type === 'window_start',
              'text-green-600': event.type === 'final' || event.type === 'bundling_done' || event.type === 'parallel_batch_complete' || event.type === 'window_complete',
              'text-amber-600': event.type === 'llm_edges' || event.type === 'pruned_edges',
              'text-purple-600': event.type === 'graph_progress' || event.type === 'parallel_batch_start',
              'text-red-600': event.type === 'error' || event.type === 'window_error'
            }"
            class="font-medium"
          >
            [{{ event.type }}]
          </span>
          <span class="text-zinc-600">{{ event.message }}</span>
        </div>
      </div>

      <!-- Stats Summary -->
      <div v-if="finalStats" class="mt-4 pt-4 border-t border-zinc-200">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="text-center p-3 bg-zinc-50 rounded-lg">
            <div class="text-2xl font-semibold text-zinc-800">{{ finalStats.edge_count }}</div>
            <div class="text-xs text-zinc-500">边数量</div>
          </div>
          <div class="text-center p-3 bg-zinc-50 rounded-lg">
            <div class="text-2xl font-semibold text-zinc-800">{{ finalStats.component_count }}</div>
            <div class="text-xs text-zinc-500">连通分量</div>
          </div>
          <div class="text-center p-3 bg-zinc-50 rounded-lg">
            <div class="text-2xl font-semibold text-zinc-800">{{ finalStats.bundle_total }}</div>
            <div class="text-xs text-zinc-500">Bundle 数</div>
          </div>
          <div class="text-center p-3 bg-zinc-50 rounded-lg">
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50 text-sm font-medium disabled:opacity-50"
              :disabled="!finalStats?.context_run_id"
              @click="copyContextRunId"
              :title="finalStats?.context_run_id || ''"
            >
              {{ copyStatusText }}
            </button>
            <div class="text-xs text-zinc-500">Context Run ID</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="error" class="bg-red-50 border border-red-200 rounded-xl p-4 mb-6">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div>
          <h4 class="text-red-800 font-medium">错误</h4>
          <p class="text-red-600 text-sm mt-1">{{ error }}</p>
        </div>
      </div>
    </div>

    <!-- Association Matrix -->
    <div class="bg-white rounded-xl border border-zinc-200 shadow-sm p-6 mb-6">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
        <div>
          <h3 class="text-lg font-medium text-zinc-800">关联矩阵</h3>
          <p class="text-sm text-zinc-500">Span -> Span 有向关联强度矩阵</p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2">
            <span class="text-sm text-zinc-600">关系类型</span>
            <select
              v-model="matrixRelationFilter"
              class="px-2 py-1 border border-zinc-300 rounded-md text-sm text-zinc-700 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option v-for="option in relationOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>
          <label class="flex items-center gap-2 text-sm text-zinc-600">
            <input
              v-model="matrixShowStrength"
              type="checkbox"
              class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
            />
            显示强度
          </label>
        </div>
      </div>

      <div class="flex items-center gap-4 text-xs text-zinc-500 mb-3">
        <span>Spans: {{ sessionSpans.length }}</span>
        <span>Edges: {{ matrixEdgeCount }}</span>
        <span v-if="finalStats?.context_run_id">Run: {{ finalStats.context_run_id.slice(0, 8) }}...</span>
      </div>

      <div v-if="matrixLoading" class="text-sm text-zinc-500">矩阵加载中...</div>
      <div v-else-if="matrixError" class="text-sm text-red-600">{{ matrixError }}</div>
      <div v-else-if="sessionSpans.length === 0" class="text-sm text-zinc-500">暂无可显示的 spans。</div>
      <div v-else class="overflow-auto border border-zinc-200 rounded-lg max-h-[520px]">
        <table class="min-w-max text-[11px] text-zinc-700">
          <thead class="sticky top-0 bg-white">
            <tr>
              <th class="sticky left-0 bg-white z-10 border border-zinc-200 px-2 py-2 text-xs text-zinc-500">
                Src\Dst
              </th>
              <th
                v-for="span in sessionSpans"
                :key="span.span_id"
                class="border border-zinc-200 px-2 py-2 text-xs text-zinc-500 whitespace-nowrap"
                :title="spanHeaderTitle(span)"
              >
                {{ span.span_ref }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(rowSpan, rowIdx) in sessionSpans" :key="rowSpan.span_id">
              <th
                class="sticky left-0 bg-white z-10 border border-zinc-200 px-2 py-2 text-xs text-zinc-500 whitespace-nowrap"
                :title="spanHeaderTitle(rowSpan)"
              >
                {{ rowSpan.span_ref }}
              </th>
              <td
                v-for="(colSpan, colIdx) in sessionSpans"
                :key="colSpan.span_id"
                class="w-12 h-10 border border-zinc-100 text-center align-middle"
                :style="matrixCellStyle(matrixCells[rowIdx][colIdx], rowIdx === colIdx)"
                :title="matrixCellTitle(rowSpan, colSpan, matrixCells[rowIdx][colIdx])"
              >
                <span v-if="rowIdx === colIdx" class="text-[10px] text-zinc-400">•</span>
                <span v-else-if="matrixCells[rowIdx][colIdx]" class="text-[10px] font-medium text-zinc-800 leading-tight">
                  <span v-if="matrixShowStrength">{{ matrixCells[rowIdx][colIdx].strength.toFixed(2) }}</span>
                  <span v-else>{{ relationShortLabel(matrixCells[rowIdx][colIdx].relation_type) }}</span>
                  <span v-if="matrixShowStrength" class="block text-[9px] text-zinc-600">
                    {{ relationShortLabel(matrixCells[rowIdx][colIdx].relation_type) }}
                  </span>
                </span>
                <span v-else class="text-[10px] text-zinc-300">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Bundles List -->
    <div v-if="bundles.length > 0" class="bg-white rounded-xl border border-zinc-200 shadow-sm p-6">
      <h3 class="text-lg font-medium text-zinc-800 mb-4">Bundles 列表 ({{ bundles.length }} 个)</h3>
      
      <div class="space-y-4">
        <div
          v-for="bundle in bundles"
          :key="bundle.bundle_id"
          class="border border-zinc-200 rounded-lg overflow-hidden"
        >
          <!-- Bundle Header -->
          <div
            @click="toggleBundle(bundle.bundle_id)"
            class="flex items-center justify-between px-4 py-3 bg-zinc-50 cursor-pointer hover:bg-zinc-100 transition-colors"
          >
            <div class="flex items-center gap-3">
              <span class="text-sm font-medium text-zinc-700">Bundle #{{ bundle.order_index }}</span>
              <span class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
                {{ bundle.items?.length || 0 }} spans
              </span>
              <span v-if="bundle.meta?.is_misc" class="px-2 py-0.5 bg-amber-100 text-amber-700 rounded text-xs">
                MISC
              </span>
              <span v-if="bundle.meta?.continuation_of" class="px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                续 {{ bundle.meta.continuation_of.slice(0, 8) }}...
              </span>
            </div>
            <svg
              :class="{ 'rotate-180': expandedBundles.has(bundle.bundle_id) }"
              class="w-5 h-5 text-zinc-400 transition-transform"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>

          <!-- Bundle Content -->
          <div v-show="expandedBundles.has(bundle.bundle_id)" class="p-4 bg-white">
            <div class="space-y-2">
              <div
                v-for="item in bundle.items"
                :key="item.span_id"
                class="flex items-start gap-3 text-sm"
              >
                <span class="flex-shrink-0 px-2 py-0.5 bg-zinc-100 text-zinc-600 rounded font-mono text-xs">
                  {{ item.span_ref }}
                </span>
                <span class="text-zinc-400 text-xs whitespace-nowrap">
                  {{ formatTime(item.start_ms) }} - {{ formatTime(item.end_ms) }}
                </span>
                <span class="text-zinc-500 text-xs whitespace-nowrap">
                  [{{ item.speaker || 'unknown' }}]
                </span>
                <span class="text-zinc-700 flex-1">{{ item.text }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!isLoading && bundles.length === 0 && progressEvents.length === 0" class="text-center py-16">
      <svg class="w-16 h-16 text-zinc-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
      <p class="text-zinc-500">输入 session_id 并点击"开始构建"来运行 Phase 2</p>
      <p class="text-zinc-400 text-sm mt-2">确保已通过 Phase 1 (Blank Page 1) 生成了 spans</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'

const sessionId = ref('')
const isLoading = ref(false)
const error = ref('')
const progressEvents = ref([])
const bundles = ref([])
const finalStats = ref(null)
const expandedBundles = ref(new Set())
const activeSessionId = ref('')
const spanLinks = ref([])
const sessionSpans = ref([])
const matrixRelationFilter = ref('all')
const matrixShowStrength = ref(true)
const matrixLoading = ref(false)
const matrixError = ref('')
const selectedModel = ref('deepseek-v4-pro')
const useThinking = ref(true)
const copyStatusText = ref('复制')

const relationLabels = {
  continuation: '延续',
  elaboration: '补充',
  dependency: '依赖',
  same_topic: '同主题',
  conflict: '冲突'
}

const relationShortLabels = {
  continuation: 'cont',
  elaboration: 'ela',
  dependency: 'dep',
  same_topic: 'topic',
  conflict: 'conf'
}

const relationColors = {
  continuation: [59, 130, 246],
  elaboration: [16, 185, 129],
  dependency: [245, 158, 11],
  same_topic: [148, 163, 184],
  conflict: [239, 68, 68]
}

const relationOptions = [
  { value: 'all', label: '全部关系' },
  { value: 'continuation', label: '延续 (continuation)' },
  { value: 'elaboration', label: '补充 (elaboration)' },
  { value: 'dependency', label: '依赖 (dependency)' },
  { value: 'same_topic', label: '同主题 (same_topic)' },
  { value: 'conflict', label: '冲突 (conflict)' }
]

const options = reactive({
  window_size: 8,
  step_size: 7,
  tau: 0.6,
  top_k: 3,
  max_edges_per_window: 24,
  token_limit_per_bundle: 4000,
  mock_llm: false,
  use_streaming_llm: false,
  enable_parallel_windows: false,
  max_concurrent_windows: 5
})

const canStart = computed(() => !isLoading.value && sessionId.value.trim().length > 0)
const llmModel = computed(() => selectedModel.value)
const filteredLinks = computed(() => {
  if (matrixRelationFilter.value === 'all') {
    return spanLinks.value
  }
  return spanLinks.value.filter((link) => link.relation_type === matrixRelationFilter.value)
})

const matrixEdgeCount = computed(() => filteredLinks.value.length)
const matrixCells = computed(() => {
  if (sessionSpans.value.length === 0) return []

  const cellMap = new Map()
  for (const link of filteredLinks.value) {
    const key = `${link.source_span_id}::${link.target_span_id}`
    const strength = Number(link.strength) || 0
    const existing = cellMap.get(key)
    if (!existing || strength > existing.strength) {
      cellMap.set(key, {
        relation_type: link.relation_type,
        strength,
        note: link.note || ''
      })
    }
  }

  return sessionSpans.value.map((rowSpan) =>
    sessionSpans.value.map((colSpan) => {
      const key = `${rowSpan.span_id}::${colSpan.span_id}`
      return cellMap.get(key) || null
    })
  )
})

function resetState() {
  error.value = ''
  progressEvents.value = []
  bundles.value = []
  finalStats.value = null
  expandedBundles.value = new Set()
  activeSessionId.value = ''
  spanLinks.value = []
  sessionSpans.value = []
  matrixError.value = ''
  matrixLoading.value = false
}

function formatTime(ms) {
  if (ms === null || ms === undefined) return '?'
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${minutes}:${secs.toString().padStart(2, '0')}`
}

async function copyContextRunId() {
  const id = finalStats.value?.context_run_id
  if (!id) return

  try {
    await navigator.clipboard.writeText(id)
    copyStatusText.value = '已复制'
  } catch (err) {
    try {
      const input = document.createElement('input')
      input.value = id
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      copyStatusText.value = '已复制'
    } catch (e2) {
      copyStatusText.value = '复制失败'
    }
  }

  window.setTimeout(() => {
    copyStatusText.value = '复制'
  }, 1200)
}

function addProgressEvent(type, message) {
  const now = new Date()
  const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
  progressEvents.value.push({ type, message, time })
}

function relationShortLabel(type) {
  return relationShortLabels[type] || type
}

function spanHeaderTitle(span) {
  const speaker = span.speaker || 'unknown'
  const start = formatTime(span.start_ms)
  const end = formatTime(span.end_ms)
  const text = (span.text || '').slice(0, 80)
  return `${span.span_ref} | ${speaker} | ${start}-${end} | ${text}`
}

function matrixCellTitle(sourceSpan, targetSpan, cell) {
  if (!cell) {
    return `${sourceSpan.span_ref} -> ${targetSpan.span_ref} | no link`
  }
  const label = relationLabels[cell.relation_type] || cell.relation_type
  const note = cell.note ? ` | ${cell.note}` : ''
  return `${sourceSpan.span_ref} -> ${targetSpan.span_ref} | ${label} | ${cell.strength.toFixed(2)}${note}`
}

function matrixCellStyle(cell, isDiagonal) {
  if (isDiagonal) {
    return { backgroundColor: 'rgba(148, 163, 184, 0.12)' }
  }
  if (!cell) return {}
  const rgb = relationColors[cell.relation_type] || [37, 99, 235]
  const alpha = Math.min(0.75, 0.15 + cell.strength * 0.6)
  return { backgroundColor: `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})` }
}

function toggleBundle(bundleId) {
  if (expandedBundles.value.has(bundleId)) {
    expandedBundles.value.delete(bundleId)
  } else {
    expandedBundles.value.add(bundleId)
  }
  // Force reactivity
  expandedBundles.value = new Set(expandedBundles.value)
}

async function fetchBundles(contextRunId) {
  try {
    const response = await fetch(`/api/v2/analysis/bundles/${contextRunId}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    if (data.success) {
      bundles.value = data.data
      // Expand first bundle by default
      if (data.data.length > 0) {
        expandedBundles.value.add(data.data[0].bundle_id)
      }
    }
  } catch (err) {
    console.error('Failed to fetch bundles:', err)
  }
}

async function fetchMatrixData(contextRunId) {
  const session = activeSessionId.value || sessionId.value.trim()
  if (!session) return

  matrixLoading.value = true
  matrixError.value = ''

  try {
    const [linksResponse, spansResponse] = await Promise.all([
      fetch(`/api/v2/analysis/span_links/${contextRunId}`),
      fetch(`/api/v2/analysis/spans/${encodeURIComponent(session)}`)
    ])

    if (!linksResponse.ok) {
      throw new Error(`span_links HTTP ${linksResponse.status}`)
    }
    if (!spansResponse.ok) {
      throw new Error(`spans HTTP ${spansResponse.status}`)
    }

    const linksData = await linksResponse.json()
    const spansData = await spansResponse.json()

    spanLinks.value = linksData.success ? linksData.data : []
    sessionSpans.value = spansData.success ? spansData.data : []
  } catch (err) {
    console.error('Failed to fetch matrix data:', err)
    matrixError.value = err.message || '加载关联矩阵失败'
  } finally {
    matrixLoading.value = false
  }
}

async function startBuildContext() {
  if (!canStart.value) return

  isLoading.value = true
  resetState()
  activeSessionId.value = sessionId.value.trim()

  const payload = {
    session_id: sessionId.value.trim(),
    options: { ...options, llm_model: llmModel.value, use_thinking_mode: useThinking.value }
  }

  try {
    const response = await fetch('/api/v2/analysis/build_context/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.error || `HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6))
            handleSSEEvent(eventData)
          } catch (e) {
            console.warn('Failed to parse SSE event:', line)
          }
        }
      }
    }
  } catch (err) {
    error.value = err.message || '构建失败'
    addProgressEvent('error', err.message)
  } finally {
    isLoading.value = false
  }
}

function handleSSEEvent(data) {
  const eventType = data.event

  switch (eventType) {
    case 'init':
      addProgressEvent(
        'init',
        `开始构建 | Session: ${data.session_id} | Spans: ${data.span_total} | LLM: ${data.llm_transport === 'stream' ? '流式' : '普通'}`
      )
      activeSessionId.value = data.session_id || activeSessionId.value
      break

    // === 并行事件 ===
    case 'parallel_batch_start':
      addProgressEvent('parallel_batch_start',
        `🚀 并行模式 | 总窗口: ${data.total_windows} | 并发: ${data.max_concurrent}`)
      break

    case 'window_complete':
      addProgressEvent('window_complete',
        `✓ 窗口 #${data.window_index} | Refs: ${data.span_refs?.join(', ')} | ` +
        `边数: ${data.raw_edge_count} → ${data.kept_edge_count}`)
      break

    case 'window_error':
      addProgressEvent('error',
        `✗ 窗口 #${data.window_index} 失败: ${data.error}`)
      break

    case 'parallel_batch_complete':
      addProgressEvent('parallel_batch_complete',
        `✅ 并行处理完成 | 总计: ${data.total_windows_processed} 个窗口`)
      break

    // === 串行事件（保持不变）===
    case 'window_start':
      addProgressEvent('window_start', `窗口 #${data.window_index} 开始 | Refs: ${data.span_refs?.join(', ')}`)
      break

    case 'llm_edges':
      addProgressEvent('llm_edges', `窗口 #${data.window_index} | LLM 产边: ${data.raw_edge_count}`)
      break

    case 'pruned_edges':
      addProgressEvent('pruned_edges', `窗口 #${data.window_index} | 剪枝后保留: ${data.kept_edge_count}`)
      break

    case 'graph_progress':
      addProgressEvent('graph_progress', `累计边数: ${data.total_edges_so_far}`)
      break

    case 'bundling_done':
      addProgressEvent('bundling_done', `打包完成 | Bundle 数: ${data.bundle_total}`)
      break

    case 'final':
      addProgressEvent('final', `✅ 构建完成 | Bundles: ${data.bundle_total} | Edges: ${data.edge_count} | Components: ${data.component_count}`)
      finalStats.value = data
      // Fetch full bundle data
      if (data.context_run_id) {
        fetchBundles(data.context_run_id)
        fetchMatrixData(data.context_run_id)
      }
      break

    case 'error':
      error.value = data.message
      addProgressEvent('error', data.message)
      break

    default:
      console.log('Unknown SSE event:', data)
  }
}
</script>
