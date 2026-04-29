import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { requirementsL123Api, l4RequirementsApi } from '@/api/requirements'
import { manageApi } from '@/api/project'

// ---- 模块级共享状态（单例） ----
// 确保高级选项页面和采集主页面访问同一份 options
const sessionId = ref('')
const transcriptText = ref('')
const isSampleLoading = ref(false)
const showAdvanced = ref(false)

const options = reactive({
  // Phase 2: 上下文构建
  window_size: 8,
  step_size: 7,
  tau: 0.6,
  top_k: 3,
  token_limit_per_bundle: 4000,
  mock_llm: false,
  use_streaming_llm: false,
  enable_parallel_windows: true,
  max_concurrent_windows: 5,
  history_aware: true,

  // Phase 3: 需求抽取参数
  bundle_strategy: 'graph',
  anchor_strategy: 'informative',
  r: 2,
  adaptive_retry_r2: true,
  model: 'deepseek-v4-pro',
  use_thinking_mode: true,
  use_toolcall: true,
  max_spans_per_bundle: 12,
  token_limit: 1500,
  top_m_2hop: 5,
  keywords: '要,需要,必须,应该,决定,改成,提升,优化,实现',
  reset_before_extract: true,

  // Phase 3: Planner 超时与重试
  planner_connect_timeout_seconds: 30,
  planner_read_timeout_seconds: 600,
  planner_max_retries: 2,

  // Phase 3: 后处理去重
  post_dedup: false,
  dedup_with_llm: false,
  dedup_auto_merge: false,
  dedup_threshold: 0.85,
  pairwise_dedup: false,
  pairwise_auto_apply: false,
  pairwise_max_pairs: 120,

  // Phase 4: L4 生成参数
  l4_top_k_pattern: 5,
  l4_top_k_spec: 3,
  l4_top_k_nfr: 3,
  l4_max_per_top_req: 5,
  l4_min_per_top_req: 1,
  l4_confidence_threshold: 0.6,
  l4_max_concurrent: 4,
  l4_model: 'deepseek-v4-pro',
  l4_use_thinking_mode: true,
  l4_clear_existing: true,
})

const l4ModelId = computed(() => options.l4_model || 'deepseek-v4-pro')

// ---- 流程状态（也共享） ----
const pipelineState = reactive({
  status: 'idle',
  currentPhase: 0,
  phases: {
    1: { status: 'pending', sessionId: null, spanCount: 0 },
    2: { status: 'pending', contextRunId: null, bundleCount: 0 },
    3: { status: 'pending', l123Count: 0, deduplication: null },
    4: { status: 'pending', l4Count: 0 },
  },
  error: null,
})

const phases = [
  { title: '文本解析', desc: '解析转录文本，提取对话片段' },
  { title: '上下文构建', desc: '构建语义关联图，生成 Bundles' },
  { title: '需求抽取', desc: '从 Bundles 中抽取 L1/L2/L3 需求' },
  { title: '底层生成', desc: '基于顶层需求生成 L4 软件需求' },
]

const logs = ref([])

// ---- 辅助函数 ----
function normalizeKeywords(raw) {
  const text = (raw || '').trim()
  if (!text) return null
  return text
    .split(/[,，;\\n|]+/g)
    .map((s) => s.trim())
    .filter(Boolean)
}

function getPhaseStyle(phaseNum) {
  const status = pipelineState.phases[phaseNum].status
  if (status === 'running') return { background: 'rgba(196, 105, 47, 0.08)', borderColor: 'rgba(196, 105, 47, 0.3)' }
  if (status === 'completed') return { background: 'rgba(34, 197, 94, 0.06)', borderColor: 'rgba(34, 197, 94, 0.2)' }
  if (status === 'error') return { background: 'rgba(239, 68, 68, 0.06)', borderColor: 'rgba(239, 68, 68, 0.2)' }
  return {}
}

function addLog(phase, message, type = 'info') {
  const now = new Date()
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map(n => n.toString().padStart(2, '0'))
    .join(':')
  logs.value = [...logs.value, { time, phase, message, type }]
}

function resetPipelineState() {
  pipelineState.status = 'idle'
  pipelineState.currentPhase = 0
  pipelineState.error = null
  pipelineState.phases[1] = { status: 'pending', sessionId: null, spanCount: 0 }
  pipelineState.phases[2] = { status: 'pending', contextRunId: null, bundleCount: 0 }
  pipelineState.phases[3] = { status: 'pending', l123Count: 0, deduplication: null }
  pipelineState.phases[4] = { status: 'pending', l4Count: 0 }
  logs.value = []
}

// ---- Phase 1: 文本解析 ----
async function runPhase1() {
  pipelineState.phases[1].status = 'running'
  pipelineState.currentPhase = 1
  addLog('Phase 1', '开始解析转录文本...')

  const payload = {
    transcript_text: transcriptText.value,
    options: { estimate_timestamps_if_missing: true, default_span_ms: 8000, max_spans_returned: 200 },
  }
  if (sessionId.value.trim()) payload.session_id = sessionId.value.trim()

  const response = await fetch('/api/v2/analysis/ingest_transcript/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`)

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

      const dataStr = rawEvent.split('\n')
        .filter(l => l.startsWith('data:'))
        .map(l => l.slice(5).trim())
        .join('')
      if (!dataStr) continue

      try {
        const ev = JSON.parse(dataStr)
        if (ev.event === 'init') {
          if (ev.session_id) pipelineState.phases[1].sessionId = ev.session_id
          addLog('Phase 1', `接收 ${ev.received_chars || 0} 字符, ${ev.received_lines || 0} 行`)
        } else if (ev.event === 'parsed') {
          addLog('Phase 1', `解析完成: ${ev.span_total || 0} 个 spans`)
        } else if (ev.event === 'db_upserted') {
          addLog('Phase 1', `入库: ${ev.upserted_count || 0} 条记录`)
        } else if (ev.event === 'final') {
          const data = ev.data || {}
          if (data.session_id) pipelineState.phases[1].sessionId = data.session_id
          pipelineState.phases[1].spanCount = data.span_total || 0
          gotFinal = true
          addLog('Phase 1', `完成！Session: ${data.session_id?.slice(0, 8)}..., ${data.span_total} spans`, 'success')
          await reader.cancel()
          break
        }
      } catch { /* ignore JSON parse errors */ }
    }
    if (gotFinal) break
  }

  if (!gotFinal) throw new Error('Phase 1 流结束但未收到 final 事件')
  pipelineState.phases[1].status = 'completed'
}

// ---- Phase 2: 上下文构建 ----
async function runPhase2() {
  pipelineState.phases[2].status = 'running'
  pipelineState.currentPhase = 2
  addLog('Phase 2', '开始构建上下文...')

  const payload = {
    session_id: pipelineState.phases[1].sessionId,
    options: {
      window_size: options.window_size,
      step_size: options.step_size,
      tau: options.tau,
      top_k: options.top_k,
      token_limit_per_bundle: options.token_limit_per_bundle,
      mock_llm: options.mock_llm,
      use_streaming_llm: options.use_streaming_llm,
      enable_parallel_windows: options.enable_parallel_windows,
      max_concurrent_windows: options.max_concurrent_windows,
      llm_model: options.model,
      use_thinking_mode: !!options.use_thinking_mode,
    },
  }

  const response = await fetch('/api/v2/analysis/build_context/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.error || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let gotFinal = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const ev = JSON.parse(line.slice(6))
        if (ev.event === 'init') addLog('Phase 2', `初始化: ${ev.span_total} spans`)
        else if (ev.event === 'window_start') addLog('Phase 2', `处理窗口 #${ev.window_index}`)
        else if (ev.event === 'window_complete') addLog('Phase 2', `窗口 #${ev.window_index} 完成: ${ev.kept_edge_count} 边`)
        else if (ev.event === 'bundling_done') addLog('Phase 2', `打包完成: ${ev.bundle_total} bundles`)
        else if (ev.event === 'final') {
          pipelineState.phases[2].contextRunId = ev.context_run_id
          pipelineState.phases[2].bundleCount = ev.bundle_total || 0
          gotFinal = true
          addLog('Phase 2', `完成！${ev.bundle_total} bundles, ${ev.edge_count} edges`, 'success')
        } else if (ev.event === 'error') {
          throw new Error(ev.message)
        }
      } catch (e) {
        if (e.message && !e.message.includes('JSON')) throw e
      }
    }
  }

  if (!gotFinal) throw new Error('Phase 2 流结束但未收到 final 事件')
  pipelineState.phases[2].status = 'completed'
}

// ---- Phase 3: 需求抽取 ----
async function runPhase3() {
  pipelineState.phases[3].status = 'running'
  pipelineState.currentPhase = 3
  addLog('Phase 3', '开始抽取 L1/L2/L3 需求...')

  if (options.dedup_auto_merge && !options.post_dedup) {
    throw new Error('已选择"自动合并"，请先开启"抽取后去重"')
  }
  if (options.dedup_auto_merge && !options.dedup_with_llm) {
    options.dedup_with_llm = true
  }
  if (options.pairwise_auto_apply && !options.post_dedup) {
    throw new Error('已选择"2v2 自动应用"，请先开启"抽取后去重"')
  }
  if (options.pairwise_auto_apply && !options.pairwise_dedup) {
    options.pairwise_dedup = true
  }

  const payload = {
    session_id: pipelineState.phases[1].sessionId,
    context_run_id: pipelineState.phases[2].contextRunId,
    bundle_strategy: options.bundle_strategy,
    anchor_strategy: options.anchor_strategy,
    r: Number(options.r) || 2,
    adaptive_retry_r2: !!options.adaptive_retry_r2,
    model: options.model,
    use_thinking_mode: !!options.use_thinking_mode,
    use_toolcall: !!options.use_toolcall,
    max_spans_per_bundle: Number(options.max_spans_per_bundle) || 12,
    token_limit: Number(options.token_limit) || 0,
    top_m_2hop: Number(options.top_m_2hop) || 5,
    keywords: normalizeKeywords(options.keywords),
    enable_parallel_windows: options.enable_parallel_windows,
    max_concurrent_windows: options.max_concurrent_windows,
    history_aware: options.history_aware,
    reset_before_extract: !!options.reset_before_extract,
    post_dedup: options.post_dedup,
    dedup_with_llm: options.dedup_with_llm || options.dedup_auto_merge,
    dedup_auto_merge: options.dedup_auto_merge,
    dedup_threshold: Number(options.dedup_threshold) || 0.85,
    pairwise_dedup: !!options.pairwise_dedup,
    pairwise_auto_apply: !!options.pairwise_auto_apply,
    pairwise_max_pairs: Number(options.pairwise_max_pairs) || 120,
    planner_connect_timeout_seconds: Number(options.planner_connect_timeout_seconds) || 30,
    planner_read_timeout_seconds: Number(options.planner_read_timeout_seconds) || 600,
    planner_max_retries: Math.max(0, Number(options.planner_max_retries) || 0),
  }

  let totalInserted = 0
  let totalDuplicates = 0
  let bundlesProcessed = 0
  let gotFinal = false

  await requirementsL123Api.extractStream(payload, (eventName, eventData) => {
    if (eventName === 'init') {
      addLog('Phase 3', `初始化: ${eventData.total_spans} spans, ${eventData.total_anchors || 0} 锚点`)
    } else if (eventName === 'anchors_selected') {
      addLog('Phase 3', `选择锚点: ${eventData.total_anchors} 个`)
    } else if (eventName === 'parallel_batch_start') {
      addLog('Phase 3', `🚀 并行模式 | 总锚点: ${eventData.total_anchors} | 并发: ${eventData.max_concurrent}`)
    } else if (eventName === 'anchor_start') {
      addLog('Phase 3', `处理锚点 #${eventData.anchor_idx}`)
    } else if (eventName === 'anchor_complete') {
      bundlesProcessed++
      totalInserted += eventData.inserted || 0
      totalDuplicates += eventData.duplicates || 0
      addLog('Phase 3', `✓ 锚点 #${eventData.anchor_idx} | r=${eventData.r} | 插入: ${eventData.inserted} | 重复: ${eventData.duplicates}`)
    } else if (eventName === 'anchor_error') {
      addLog('Phase 3', `✗ 锚点 #${eventData.anchor_idx} 失败: ${eventData.error}`, 'warning')
    } else if (eventName === 'parallel_batch_complete') {
      addLog('Phase 3', `✅ 并行处理完成 | 总计: ${eventData.total_anchors_processed} 个锚点`)
    } else if (eventName === 'final') {
      totalInserted = eventData.total_inserted || totalInserted
      totalDuplicates = eventData.total_duplicates || totalDuplicates
      bundlesProcessed = eventData.bundles_processed || bundlesProcessed
      gotFinal = true
      addLog('Phase 3', `完成！抽取 ${totalInserted} 条需求（重复 ${totalDuplicates}），处理 ${bundlesProcessed} 个 bundles`, 'success')
    } else if (eventName === 'dedup_start') {
      addLog('Phase 3', '开始抽取后去重...', 'info')
    } else if (eventName === 'dedup_final') {
      pipelineState.phases[3].deduplication = eventData || null
      const dupCount = eventData?.total_duplicates ?? 0
      const merged = eventData?.total_merged
      addLog('Phase 3', `去重完成：重复组 ${dupCount}${merged == null ? '' : `，合并 ${merged}`}`, dupCount > 0 ? 'warning' : 'success')
    } else if (eventName === 'error') {
      throw new Error(eventData.message)
    }
  })

  if (!gotFinal) throw new Error('Phase 3 流结束但未收到 final 事件')
  pipelineState.phases[3].l123Count = totalInserted
  pipelineState.phases[3].status = 'completed'
}

// ---- Phase 4: 底层需求生成 ----
async function runPhase4() {
  pipelineState.phases[4].status = 'running'
  pipelineState.currentPhase = 4
  addLog('Phase 4', '开始生成 L4 底层需求...')

  const l123Data = await requirementsL123Api.listBySession(
    pipelineState.phases[1].sessionId,
    { page: 1, perPage: 500 },
  )
  const requirements = (l123Data.requirements || []).map(req => ({
    id: req.req_id || req.id,
    text: req.text || req.statement || '',
  }))

  if (requirements.length === 0) {
    addLog('Phase 4', '没有找到顶层需求，跳过 L4 生成', 'warning')
    pipelineState.phases[4].l4Count = 0
    pipelineState.phases[4].status = 'completed'
    return
  }

  addLog('Phase 4', `基于 ${requirements.length} 条顶层需求生成 L4...`)

  const l4Response = await l4RequirementsApi.generate(
    pipelineState.phases[1].sessionId,
    requirements,
    {
      config: {
        top_k_pattern: options.l4_top_k_pattern,
        top_k_spec: options.l4_top_k_spec,
        top_k_nfr: options.l4_top_k_nfr,
        max_l4_per_top_req: options.l4_max_per_top_req,
        min_l4_per_top_req: options.l4_min_per_top_req,
        confidence_threshold: options.l4_confidence_threshold,
        max_concurrent: options.l4_max_concurrent,
      },
      model: l4ModelId.value,
      useThinkingMode: !!options.l4_use_thinking_mode,
      forceRegenerate: !!options.l4_clear_existing,
    },
  )

  pipelineState.phases[4].l4Count = (l4Response.requirements || []).length
  addLog('Phase 4', `完成！生成 ${pipelineState.phases[4].l4Count} 条 L4 需求`, 'success')
  pipelineState.phases[4].status = 'completed'
}

// ---- 主流程 ----
async function runPipeline(selectedProjectId) {
  resetPipelineState()
  pipelineState.status = 'running'
  addLog('系统', '开始需求采集流程...')

  try {
    await runPhase1()
    await runPhase2()
    await runPhase3()
    await runPhase4()

    pipelineState.status = 'completed'
    addLog('系统', '需求采集流程完成！', 'success')

    if (pipelineState.phases[1].sessionId) {
      localStorage.setItem('lastSessionId', pipelineState.phases[1].sessionId)

      if (selectedProjectId) {
        try {
          await manageApi.setProjectSession(selectedProjectId, pipelineState.phases[1].sessionId)
          localStorage.setItem('lastProjectId', selectedProjectId)
          addLog('系统', 'Session 已绑定到项目', 'success')
        } catch (err) {
          addLog('系统', `绑定 Session 到项目失败: ${err.message}`, 'error')
        }
      }

      window.dispatchEvent(new CustomEvent('collection-completed', {
        detail: {
          sessionId: pipelineState.phases[1].sessionId,
          projectId: selectedProjectId,
          spanCount: pipelineState.phases[1].spanCount,
          bundleCount: pipelineState.phases[2].bundleCount,
          l123Count: pipelineState.phases[3].l123Count,
          l4Count: pipelineState.phases[4].l4Count,
        },
      }))
    }
  } catch (err) {
    pipelineState.status = 'error'
    pipelineState.error = err.message || '采集失败'
    pipelineState.phases[pipelineState.currentPhase].status = 'error'
    addLog(`Phase ${pipelineState.currentPhase}`, err.message || '执行失败', 'error')
  }
}

// ---- 从当前步骤重试 ----
async function retryFromCurrentPhase() {
  const startPhase = pipelineState.currentPhase
  pipelineState.status = 'running'
  pipelineState.error = null
  addLog('系统', `从 Phase ${startPhase} 重试...`)

  try {
    if (startPhase <= 2) { pipelineState.phases[2].status = 'pending'; await runPhase2() }
    if (startPhase <= 3) { pipelineState.phases[3].status = 'pending'; await runPhase3() }
    if (startPhase <= 4) { pipelineState.phases[4].status = 'pending'; await runPhase4() }
    pipelineState.status = 'completed'
    addLog('系统', '重试完成！', 'success')
  } catch (err) {
    pipelineState.status = 'error'
    pipelineState.error = err.message || '重试失败'
    pipelineState.phases[pipelineState.currentPhase].status = 'error'
    addLog(`Phase ${pipelineState.currentPhase}`, err.message || '执行失败', 'error')
  }
}

// ---- 加载示例文本 ----
async function loadSampleTranscript() {
  if (isSampleLoading.value) return
  isSampleLoading.value = true
  try {
    const response = await fetch('/api/v2/analysis/sample_transcript', { cache: 'no-store' })
    if (!response.ok) throw new Error(`加载示例失败: HTTP ${response.status}`)
    const text = await response.text()
    if (!text.trim()) throw new Error('示例文件为空')
    transcriptText.value = text
    addLog('系统', '已加载示例文本', 'success')
  } catch (err) {
    addLog('系统', err.message || '加载示例失败', 'error')
  } finally {
    isSampleLoading.value = false
  }
}

export function useCollectionPipeline() {
  const router = useRouter()

  function goToRequirements() {
    router.push({ name: 'beta-requirements' })
  }

  return {
    // 表单输入
    sessionId,
    transcriptText,
    isSampleLoading,
    showAdvanced,
    options,
    // 流程状态
    pipelineState,
    phases,
    logs,
    // 辅助
    getPhaseStyle,
    // 操作
    runPipeline,
    retryFromCurrentPhase,
    loadSampleTranscript,
    goToRequirements,
  }
}
