<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Copy, Loader2, Play, RefreshCw, Trash2 } from 'lucide-vue-next'
import { analysisApi, requirementsL123Api } from '@/api/requirements'

const sessionId = ref('')
const contextRunId = ref('')
const copyRunStatus = ref('复制')

const contextRuns = ref([])
const isLoadingRuns = ref(false)
const runsError = ref('')

const spans = ref([])
const spanLinks = ref([])
const isLoadingGraph = ref(false)
const graphError = ref('')

const form = ref({
  bundleStrategy: 'graph', // graph | sequence
  anchorStrategy: 'informative', // all | keyword | informative
  maxR: 2, // 1 or 2
  adaptiveRetryR2: true, // r>=2 时：先 r=1，不足再 r=2
  useToolcall: true,
  model: 'deepseek-chat',
  maxSpansPerBundle: 12,
  tokenLimit: 1500, // null/0 表示不限制
  topM2Hop: 5,
  keywords: '要,需要,必须,应该,决定,改成,提升,优化,实现',
  enableParallel: false, // 是否启用并行处理
  maxConcurrent: 5, // 最大并发数
  historyAware: false, // 是否启用历史感知（串行记忆）
  resetBeforeExtract: true, // 抽取前是否清理该 session 的历史结果

  // Post extraction deduplication
  postDedup: false,
  dedupWithLLM: false,
  dedupAutoMerge: false,
  dedupThreshold: 0.85
})

const isExtracting = ref(false)
const extractionError = ref('')
const extractionResult = ref(null)

const deduplicationResult = computed(() => extractionResult.value?.deduplication || null)

const reqLevelFilter = ref('') // '' | L1 | L2 | L3
const reqPage = ref(1)
const reqPerPage = ref(50)
const reqData = ref(null)
const reqStats = ref(null)
const isLoadingReqs = ref(false)
const reqError = ref('')

const useReasoningModel = computed({
  get: () => form.value.model === 'deepseek-reasoner',
  set: (value) => {
    form.value.model = value ? 'deepseek-reasoner' : 'deepseek-chat'
  }
})

const selectedRun = computed(() => {
  return contextRuns.value.find((run) => run.context_run_id === contextRunId.value) || null
})

const canLoadGraph = computed(() => {
  if (!sessionId.value.trim()) return false
  if (form.value.bundleStrategy === 'graph' && !contextRunId.value.trim()) return false
  return true
})

const canExtract = computed(() => {
  if (isExtracting.value) return false
  if (!sessionId.value.trim()) return false
  if (form.value.bundleStrategy === 'graph' && !contextRunId.value.trim()) return false
  return true
})

function normalizeKeywords(raw) {
  const text = (raw || '').trim()
  if (!text) return null
  return text
    .split(/[,，;\n|]+/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function loadContextRuns({ useSessionFilter = true } = {}) {
  runsError.value = ''
  isLoadingRuns.value = true
  try {
    const sid = sessionId.value.trim()
    const runs = await analysisApi.listContextRuns(useSessionFilter ? sid : '')
    contextRuns.value = Array.isArray(runs) ? runs : []
  } catch (err) {
    runsError.value = err?.message || '加载 context_runs 失败'
  } finally {
    isLoadingRuns.value = false
  }
}

async function copySelectedContextRunId() {
  const id = contextRunId.value.trim()
  if (!id) return

  try {
    await navigator.clipboard.writeText(id)
    copyRunStatus.value = '已复制'
  } catch (err) {
    try {
      const input = document.createElement('input')
      input.value = id
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      copyRunStatus.value = '已复制'
    } catch (e2) {
      copyRunStatus.value = '复制失败'
    }
  }

  window.setTimeout(() => {
    copyRunStatus.value = '复制'
  }, 1200)
}

async function loadGraphInfo() {
  graphError.value = ''
  isLoadingGraph.value = true
  try {
    const sid = sessionId.value.trim()
    if (!sid) {
      throw new Error('请先填写 session_id')
    }

    const tasks = [analysisApi.getSpans(sid)]
    if (form.value.bundleStrategy === 'graph') {
      const rid = contextRunId.value.trim()
      if (!rid) {
        throw new Error('graph 策略需要 context_run_id')
      }
      tasks.push(analysisApi.getSpanLinks(rid))
    }

    const [spansData, linksData] = await Promise.all(tasks)
    spans.value = Array.isArray(spansData) ? spansData : []
    spanLinks.value = Array.isArray(linksData) ? linksData : []
  } catch (err) {
    graphError.value = err?.message || '加载 spans/span_links 失败'
  } finally {
    isLoadingGraph.value = false
  }
}

async function refreshRequirements({ resetPage = false } = {}) {
  reqError.value = ''
  if (resetPage) reqPage.value = 1

  const sid = sessionId.value.trim()
  if (!sid) {
    reqData.value = null
    reqStats.value = null
    return
  }

  isLoadingReqs.value = true
  try {
    const data = await requirementsL123Api.listBySession(sid, {
      level: reqLevelFilter.value || null,
      page: reqPage.value,
      perPage: reqPerPage.value
    })
    reqData.value = data
    reqStats.value = await requirementsL123Api.stats(sid)
  } catch (err) {
    reqError.value = err?.message || '加载需求列表失败'
  } finally {
    isLoadingReqs.value = false
  }
}

async function startExtraction() {
  extractionError.value = ''
  extractionResult.value = null

  const sid = sessionId.value.trim()
  if (!sid) {
    extractionError.value = '请先填写 session_id'
    return
  }
  if (form.value.bundleStrategy === 'graph' && !contextRunId.value.trim()) {
    extractionError.value = 'graph 策略需要 context_run_id'
    return
  }

  isExtracting.value = true
  try {
    if (form.value.dedupAutoMerge && !form.value.postDedup) {
      throw new Error('已选择“自动合并”，请先开启“抽取后去重”')
    }
    if (form.value.dedupAutoMerge && !form.value.dedupWithLLM) {
      form.value.dedupWithLLM = true
    }

    const payload = {
      session_id: sid,
      context_run_id: contextRunId.value.trim() || null,
      bundle_strategy: form.value.bundleStrategy,
      anchor_strategy: form.value.anchorStrategy,
      r: Number(form.value.maxR) || 2,
      adaptive_retry_r2: !!form.value.adaptiveRetryR2,
      model: form.value.model,
      use_toolcall: !!form.value.useToolcall,
      max_spans_per_bundle: Number(form.value.maxSpansPerBundle) || 12,
      token_limit: Number(form.value.tokenLimit) || 0,
      top_m_2hop: Number(form.value.topM2Hop) || 5,
      keywords: normalizeKeywords(form.value.keywords),
      enable_parallel_windows: !!form.value.enableParallel,
      max_concurrent_windows: Number(form.value.maxConcurrent) || 5,
      history_aware: !!form.value.historyAware,
      reset_before_extract: !!form.value.resetBeforeExtract,

      post_dedup: !!form.value.postDedup,
      dedup_with_llm: !!form.value.dedupWithLLM || !!form.value.dedupAutoMerge,
      dedup_auto_merge: !!form.value.dedupAutoMerge,
      dedup_threshold: Number(form.value.dedupThreshold) || 0.85
    }

    extractionResult.value = await requirementsL123Api.extract(payload)
    await refreshRequirements({ resetPage: true })
  } catch (err) {
    extractionError.value = err?.message || '抽取失败'
  } finally {
    isExtracting.value = false
  }
}

async function deleteRequirement(reqId) {
  reqError.value = ''
  try {
    await requirementsL123Api.delete(reqId)
    await refreshRequirements()
  } catch (err) {
    reqError.value = err?.message || '删除失败'
  }
}

watch(contextRunId, (rid) => {
  const run = contextRuns.value.find((r) => r.context_run_id === rid)
  if (run?.session_id && !sessionId.value.trim()) {
    sessionId.value = run.session_id
  }
})

watch(reqLevelFilter, async () => {
  await refreshRequirements({ resetPage: true })
})

onMounted(async () => {
  await loadContextRuns({ useSessionFilter: false })
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <header class="bg-white border-b border-zinc-200 px-6 py-4">
      <h2 class="text-xl font-semibold text-zinc-900">Phase 3: 需求抽取（EgoBundle → L1/L2/L3）</h2>
      <p class="text-sm text-zinc-500 mt-1">
        从 Phase 2 的 span 关联图（context_run_id）生成 EgoBundle，并通过 tool-call 写入 `requirements_l123`
      </p>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-5">
          <div>
            <h3 class="text-sm font-semibold text-zinc-900">输入选择</h3>
            <p class="text-xs text-zinc-500 mt-1">优先使用 graph 策略：EgoBundle 来自 Phase 2 的 `span_links`</p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="md:col-span-2">
              <label class="block text-sm font-medium text-zinc-700">Session ID</label>
              <input
                v-model="sessionId"
                type="text"
                placeholder="Phase 1 ingest_transcript 返回的 session_id"
                class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
              />
            </div>

            <div class="md:col-span-2">
              <div class="flex items-center justify-between gap-3">
                <label class="block text-sm font-medium text-zinc-700">Context Run (Phase 2)</label>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="inline-flex items-center gap-2 text-xs text-zinc-700 border border-zinc-300 rounded-md px-2 py-1 hover:bg-zinc-50 disabled:opacity-50"
                    :disabled="!contextRunId.trim()"
                    @click="copySelectedContextRunId"
                    :title="contextRunId"
                  >
                    <Copy class="w-3.5 h-3.5" />
                    {{ copyRunStatus }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex items-center gap-2 text-xs text-zinc-700 border border-zinc-300 rounded-md px-2 py-1 hover:bg-zinc-50 disabled:opacity-50"
                    :disabled="isLoadingRuns"
                    @click="loadContextRuns({ useSessionFilter: true })"
                  >
                    <RefreshCw class="w-3.5 h-3.5" />
                    {{ isLoadingRuns ? '加载中…' : '刷新列表' }}
                  </button>
                </div>
              </div>
              <select
                v-model="contextRunId"
                class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
              >
                <option value="">（可空：sequence 策略不需要）</option>
                <option v-for="run in contextRuns" :key="run.context_run_id" :value="run.context_run_id">
                  {{ run.context_run_id }} · {{ run.session_id }} · {{ run.status }} · {{ run.created_at }}
                </option>
              </select>
              <p v-if="runsError" class="mt-2 text-xs text-red-600">{{ runsError }}</p>
            </div>

            <div class="md:col-span-2" v-if="selectedRun">
              <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-700 space-y-1">
                <div><span class="text-zinc-500">status:</span> {{ selectedRun.status }}</div>
                <div><span class="text-zinc-500">created_at:</span> {{ selectedRun.created_at }}</div>
                <div v-if="selectedRun.stats">
                  <span class="text-zinc-500">stats:</span>
                  <span class="ml-1">{{ typeof selectedRun.stats === 'string' ? selectedRun.stats : JSON.stringify(selectedRun.stats) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div>
            <h3 class="text-sm font-semibold text-zinc-900">抽取参数（反映后端可选项）</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
              <div>
                <label class="block text-sm font-medium text-zinc-700">bundle_strategy</label>
                <select
                  v-model="form.bundleStrategy"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                >
                  <option value="graph">graph（基于 span_links）</option>
                  <option value="sequence">sequence（按时间窗口）</option>
                </select>
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">anchor_strategy</label>
                <select
                  v-model="form.anchorStrategy"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                >
                  <option value="informative">informative</option>
                  <option value="keyword">keyword</option>
                  <option value="all">all</option>
                </select>
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">r（max）</label>
                <select
                  v-model.number="form.maxR"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                >
                  <option :value="1">1</option>
                  <option :value="2">2</option>
                </select>
                <label class="mt-2 flex items-center gap-2 text-xs text-zinc-600">
                  <input v-model="form.adaptiveRetryR2" type="checkbox" class="w-4 h-4 rounded border-zinc-300" />
                  r=2 时先尝试 r=1，不足再 r=2
                </label>
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">model</label>
                <div class="mt-2 flex items-center gap-3">
                  <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" v-model="useReasoningModel" class="sr-only peer">
                    <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
                    <span class="ml-3 text-sm font-medium text-zinc-600">DeepSeek R1 (Reasoning Mode)</span>
                  </label>
                </div>
                <label class="mt-2 flex items-center gap-2 text-xs text-zinc-600">
                  <input v-model="form.useToolcall" type="checkbox" class="w-4 h-4 rounded border-zinc-300" />
                  使用 tool-call（需要推理后端 provider=deepseek）
                </label>
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">max_spans_per_bundle</label>
                <input
                  v-model.number="form.maxSpansPerBundle"
                  type="number"
                  min="1"
                  max="64"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">token_limit（字数近似）</label>
                <input
                  v-model.number="form.tokenLimit"
                  type="number"
                  min="0"
                  step="100"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                />
                <p class="mt-1 text-xs text-zinc-500">填 0 表示不限制</p>
              </div>

              <div>
                <label class="block text-sm font-medium text-zinc-700">top_m_2hop</label>
                <input
                  v-model.number="form.topM2Hop"
                  type="number"
                  min="1"
                  max="50"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                />
              </div>

              <div class="md:col-span-2">
                <label class="block text-sm font-medium text-zinc-700">keywords（用于 keyword/informative）</label>
                <input
                  v-model="form.keywords"
                  type="text"
                  placeholder="逗号分隔，例如：要,需要,必须"
                  class="mt-2 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                />
              </div>

              <div class="md:col-span-2">
                <label class="flex items-center justify-between text-sm font-medium text-zinc-700">
                  <span class="flex items-center gap-2">
                    锚点并行处理（Phase 3）
                    <span class="text-xs text-zinc-500 font-normal">并行抽取多个锚点</span>
                  </span>
                  <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" v-model="form.enableParallel" class="sr-only peer">
                    <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
                  </label>
                </label>
                <div v-if="form.enableParallel" class="mt-3 pl-4 border-l-2 border-zinc-200">
                  <label class="block text-sm font-medium text-zinc-700">最大并发锚点数（Phase 3）</label>
                  <input
                    v-model.number="form.maxConcurrent"
                    type="number"
                    min="1"
                    max="20"
                    class="mt-2 w-32 rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                  />
                  <p class="mt-1 text-xs text-zinc-500">同时处理的锚点数量（1-20）</p>
                </div>
                <div v-else class="mt-3 pl-4 border-l-2 border-zinc-200">
                  <label class="flex items-center gap-2">
                    <input v-model="form.historyAware" type="checkbox" class="w-4 h-4 rounded border-zinc-300" />
                    <span class="text-sm text-zinc-700 font-medium">串行记忆（History Aware）</span>
                  </label>
                  <p class="mt-1 text-xs text-zinc-500">
                    仅在关闭并行处理时生效。开启后大模型可以看到前面锚点已生成的需求，避免重复。
                  </p>
                </div>
              </div>

              <div class="md:col-span-2">
                <label class="flex items-center gap-2">
                  <input v-model="form.resetBeforeExtract" type="checkbox" class="w-4 h-4 rounded border-zinc-300" />
                  <span class="text-sm text-zinc-700 font-medium">重跑前清理该 session 的 L1/L2/L3 结果</span>
                </label>
                <p class="mt-1 text-xs text-zinc-500">
                  建议开启。每次点击“开始抽取并写库”前先删除该 session 的历史需求，避免多次重跑累积重复条目。
                </p>
              </div>

              <div class="md:col-span-2">
                <label class="flex items-center justify-between text-sm font-medium text-zinc-700">
                  <span class="flex items-center gap-2">
                    抽取后去重（Phase 3 后处理）
                    <span class="text-xs text-zinc-500 font-normal">并行模式推荐</span>
                  </span>
                  <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" v-model="form.postDedup" class="sr-only peer">
                    <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
                  </label>
                </label>

                <div v-if="form.postDedup" class="mt-3 pl-4 border-l-2 border-zinc-200 grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label class="block text-sm font-medium text-zinc-700">相似度阈值</label>
                    <input
                      v-model.number="form.dedupThreshold"
                      type="number"
                      min="0.5"
                      max="0.99"
                      step="0.01"
                      class="mt-2 w-32 rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                    />
                    <p class="mt-1 text-xs text-zinc-500">默认 0.85，越高越严格</p>
                  </div>

                  <div class="flex items-start gap-2">
                    <input v-model="form.dedupWithLLM" type="checkbox" class="mt-1 w-4 h-4 rounded border-zinc-300" />
                    <div>
                      <div class="text-sm font-medium text-zinc-700">LLM 给出去重建议</div>
                      <p class="text-xs text-zinc-500">输出每组是否合并/合并文本/主需求ID（不自动改库）</p>
                    </div>
                  </div>

                  <div class="flex items-start gap-2 md:col-span-2">
                    <input v-model="form.dedupAutoMerge" type="checkbox" class="mt-1 w-4 h-4 rounded border-zinc-300" />
                    <div>
                      <div class="text-sm font-medium text-zinc-700">自动合并（会写库）</div>
                      <p class="text-xs text-zinc-500">需要开启 LLM 建议；将按 LLM 决策合并并删除重复项</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-lg bg-white border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50"
              :disabled="!canLoadGraph || isLoadingGraph"
              @click="loadGraphInfo"
            >
              <Loader2 v-if="isLoadingGraph" class="w-4 h-4 animate-spin" />
              <span v-else class="w-4 h-4 inline-flex items-center justify-center">⛓</span>
              加载 spans / span_links
            </button>

            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
              :disabled="!canExtract"
              @click="startExtraction"
            >
              <Loader2 v-if="isExtracting" class="w-4 h-4 animate-spin" />
              <Play v-else class="w-4 h-4" />
              开始抽取并写库
            </button>

            <p v-if="graphError" class="text-xs text-red-600 w-full">{{ graphError }}</p>
            <p v-if="extractionError" class="text-xs text-red-600 w-full">{{ extractionError }}</p>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">spans</div>
              <div class="text-lg font-semibold text-zinc-900">{{ spans.length }}</div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">span_links</div>
              <div class="text-lg font-semibold text-zinc-900">{{ spanLinks.length }}</div>
            </div>
          </div>

          <div v-if="extractionResult" class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm">
            <div class="font-medium text-zinc-900">本次抽取结果</div>
            <div class="mt-2 grid grid-cols-2 gap-3 text-xs text-zinc-700">
              <div>anchors: {{ extractionResult.total_anchors }}</div>
              <div>bundles_processed: {{ extractionResult.bundles_processed }}</div>
              <div>cleared: {{ extractionResult.cleared_before_extract ?? 0 }}</div>
              <div>inserted: {{ extractionResult.total_inserted }}</div>
              <div>duplicates: {{ extractionResult.total_duplicates }}</div>
            </div>
            <div v-if="extractionResult.errors?.length" class="mt-3">
              <div class="text-xs font-medium text-red-700">errors ({{ extractionResult.errors.length }})</div>
              <div class="mt-1 max-h-28 overflow-y-auto text-[11px] text-red-700 whitespace-pre-wrap">
                {{ JSON.stringify(extractionResult.errors, null, 2) }}
              </div>
            </div>
          </div>

          <div
            v-if="deduplicationResult"
            class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm"
          >
            <div class="font-medium text-zinc-900">抽取后去重结果</div>
            <div class="mt-2 grid grid-cols-2 gap-3 text-xs text-zinc-700">
              <div>groups: {{ deduplicationResult.total_duplicates ?? 0 }}</div>
              <div>scanned: {{ deduplicationResult.total_requirements_scanned ?? 0 }}</div>
              <div class="col-span-2" v-if="deduplicationResult.total_merged !== null && deduplicationResult.total_merged !== undefined">
                merged: {{ deduplicationResult.total_merged }}
              </div>
            </div>

            <div v-if="deduplicationResult.duplicate_groups?.length" class="mt-3 space-y-3">
              <div
                v-for="group in deduplicationResult.duplicate_groups"
                :key="group.group_id"
                class="rounded-lg border border-zinc-200 bg-white px-3 py-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="text-xs font-semibold text-zinc-900">
                    {{ group.level }} · {{ group.group_id }}
                  </div>
                  <div class="text-[11px] text-zinc-600">similarity: {{ group.similarity }}</div>
                </div>

                <div v-if="group.representative_text" class="mt-2 text-[11px] text-zinc-600">
                  <span class="text-zinc-500">repr:</span>
                  <span class="ml-1 whitespace-pre-wrap break-words">{{ group.representative_text }}</span>
                </div>

                <div class="mt-2">
                  <div class="text-[11px] font-medium text-zinc-700">requirements ({{ group.requirements?.length || 0 }})</div>
                  <div class="mt-1 max-h-40 overflow-y-auto space-y-2">
                    <div
                      v-for="req in group.requirements || []"
                      :key="req.req_id"
                      class="rounded-md border border-zinc-100 bg-zinc-50 px-2 py-2"
                    >
                      <div class="text-[11px] text-zinc-600">id: {{ req.req_id }}</div>
                      <div class="mt-1 text-xs text-zinc-800 whitespace-pre-wrap break-words">{{ req.text }}</div>
                    </div>
                  </div>
                </div>

                <div v-if="group.llm_decision" class="mt-3 rounded-md border border-zinc-200 bg-zinc-50 px-2 py-2">
                  <div class="text-[11px] font-medium text-zinc-700">llm_decision</div>
                  <div class="mt-1 grid grid-cols-2 gap-2 text-[11px] text-zinc-700">
                    <div>should_merge: {{ group.llm_decision.should_merge }}</div>
                    <div>primary: {{ group.llm_decision.primary_req_id || '-' }}</div>
                    <div class="col-span-2">merged_level: {{ group.llm_decision.merged_level || '-' }}</div>
                  </div>
                  <div v-if="group.llm_decision.reason" class="mt-2 text-[11px] text-zinc-700 whitespace-pre-wrap">
                    <span class="text-zinc-500">reason:</span>
                    <span class="ml-1">{{ group.llm_decision.reason }}</span>
                  </div>
                  <div v-if="group.llm_decision.merged_text" class="mt-2 text-[11px] text-zinc-700 whitespace-pre-wrap break-words">
                    <span class="text-zinc-500">merged_text:</span>
                    <div class="mt-1 rounded-md border border-zinc-200 bg-white px-2 py-2">{{ group.llm_decision.merged_text }}</div>
                  </div>
                  <div v-if="group.llm_decision.error" class="mt-2 text-[11px] text-red-700 whitespace-pre-wrap">
                    error: {{ group.llm_decision.error }}
                  </div>
                </div>

                <div v-if="group.merge_result" class="mt-3 rounded-md border border-zinc-200 bg-white px-2 py-2">
                  <div class="text-[11px] font-medium text-zinc-700">merge_result</div>
                  <div class="mt-1 grid grid-cols-2 gap-2 text-[11px] text-zinc-700">
                    <div>success: {{ group.merge_result.success }}</div>
                    <div>deleted_count: {{ group.merge_result.deleted_count ?? 0 }}</div>
                    <div class="col-span-2">primary: {{ group.merge_result.primary_req_id || '-' }}</div>
                  </div>
                  <div v-if="group.merge_result.error" class="mt-2 text-[11px] text-red-700 whitespace-pre-wrap">
                    error: {{ group.merge_result.error }}
                  </div>
                </div>
              </div>
            </div>

            <div v-else class="mt-2 text-xs text-zinc-600">
              {{ deduplicationResult.message || '未检测到重复组' }}
            </div>
          </div>
        </section>

        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="text-sm font-semibold text-zinc-900">已入库需求（requirements_l123）</h3>
              <p class="text-xs text-zinc-500 mt-1">按 session_id 查询，可按 L1/L2/L3 过滤</p>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-2 text-xs text-zinc-700 border border-zinc-300 rounded-md px-2 py-1 hover:bg-zinc-50 disabled:opacity-50"
              :disabled="isLoadingReqs || !sessionId.trim()"
              @click="refreshRequirements({ resetPage: false })"
            >
              <RefreshCw class="w-3.5 h-3.5" />
              刷新
            </button>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <label class="text-xs text-zinc-600">level</label>
            <select
              v-model="reqLevelFilter"
              class="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-800"
            >
              <option value="">全部</option>
              <option value="L1">L1</option>
              <option value="L2">L2</option>
              <option value="L3">L3</option>
            </select>

            <label class="text-xs text-zinc-600">per_page</label>
            <select
              v-model.number="reqPerPage"
              class="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-800"
              @change="refreshRequirements({ resetPage: true })"
            >
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>

            <span v-if="isLoadingReqs" class="inline-flex items-center gap-2 text-xs text-zinc-500">
              <Loader2 class="w-3.5 h-3.5 animate-spin" /> 加载中…
            </span>
          </div>

          <p v-if="reqError" class="text-xs text-red-600">{{ reqError }}</p>

          <div v-if="reqStats" class="grid grid-cols-4 gap-3">
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">total</div>
              <div class="text-base font-semibold text-zinc-900">{{ reqStats.total }}</div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">L1</div>
              <div class="text-base font-semibold text-zinc-900">{{ reqStats.by_level?.L1 || 0 }}</div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">L2</div>
              <div class="text-base font-semibold text-zinc-900">{{ reqStats.by_level?.L2 || 0 }}</div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
              <div class="text-xs text-zinc-500">L3</div>
              <div class="text-base font-semibold text-zinc-900">{{ reqStats.by_level?.L3 || 0 }}</div>
            </div>
          </div>

          <div class="overflow-x-auto border border-zinc-200 rounded-lg">
            <table class="min-w-full text-xs">
              <thead class="bg-zinc-50 text-zinc-600">
                <tr>
                  <th class="px-3 py-2 text-left font-medium">level</th>
                  <th class="px-3 py-2 text-left font-medium">text</th>
                  <th class="px-3 py-2 text-left font-medium">anchor_span_id</th>
                  <th class="px-3 py-2 text-left font-medium">r</th>
                  <th class="px-3 py-2 text-left font-medium">created_at</th>
                  <th class="px-3 py-2 text-right font-medium">actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-200">
                <tr v-for="req in reqData?.requirements || []" :key="req.req_id" class="hover:bg-zinc-50">
                  <td class="px-3 py-2 font-medium text-zinc-900">{{ req.level }}</td>
                  <td class="px-3 py-2 text-zinc-800">
                    <div class="max-w-[520px] whitespace-pre-wrap break-words">{{ req.text }}</div>
                  </td>
                  <td class="px-3 py-2 text-zinc-600">
                    <div class="max-w-[180px] truncate" :title="req.anchor_span_id">{{ req.anchor_span_id }}</div>
                  </td>
                  <td class="px-3 py-2 text-zinc-600">{{ req.r }}</td>
                  <td class="px-3 py-2 text-zinc-600">{{ req.created_at }}</td>
                  <td class="px-3 py-2 text-right">
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 text-red-700 hover:text-red-800"
                      @click="deleteRequirement(req.req_id)"
                      title="删除"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                      删除
                    </button>
                  </td>
                </tr>
                <tr v-if="(reqData?.requirements || []).length === 0">
                  <td colspan="6" class="px-3 py-6 text-center text-zinc-500">暂无数据</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="reqData" class="flex items-center justify-between text-xs text-zinc-600">
            <div>total: {{ reqData.total }} · page {{ reqData.current_page }} / {{ reqData.pages }}</div>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="px-2 py-1 border border-zinc-300 rounded-md hover:bg-zinc-50 disabled:opacity-50"
                :disabled="reqPage <= 1 || isLoadingReqs"
                @click="reqPage -= 1; refreshRequirements()"
              >
                Prev
              </button>
              <button
                type="button"
                class="px-2 py-1 border border-zinc-300 rounded-md hover:bg-zinc-50 disabled:opacity-50"
                :disabled="reqPage >= (reqData.pages || 1) || isLoadingReqs"
                @click="reqPage += 1; refreshRequirements()"
              >
                Next
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>


