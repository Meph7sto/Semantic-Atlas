import { ref, computed } from 'vue'
import {
  traceabilityApi,
  conflictApi,
  classifyTexts,
  analysisApi,
  requirementsL123Api,
  getLatestClassification,
  l4RequirementsApi,
} from '@/api/requirements'

const ACTIVE_ANALYSIS_LABELS = {
  network: '追溯',
  conflict: '冲突',
  classification: '分类',
  full: '完整分析',
}

const WORKFLOW_STEPS = {
  full: [1, 2, 3, 4],
}

const DEFAULT_CONFLICT_CONCURRENCY = 3
const DEFAULT_MAX_CANDIDATES_PER_BUCKET = 20

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

function normalizeL4Requirement(raw, idx = 0) {
  return {
    ...raw,
    id: raw.req_id || raw.id || `l4_${idx}`,
    level: 'L4',
    statement: raw.text || raw.shall_statement || '',
    text: raw.text || raw.shall_statement || '',
  }
}

function unwrapTraceCache(payload) {
  if (!payload) return null
  if (payload.data && typeof payload.data === 'object') return payload.data
  return payload
}

function hasTraceRelations(tracePayload) {
  const data = unwrapTraceCache(tracePayload)
  return Array.isArray(data?.relations) && data.relations.length > 0
}

function normalizeClassificationResult(raw, requirements = []) {
  if (!raw) return null
  const predictions = Array.isArray(raw.predictions) ? raw.predictions : []
  return {
    predictions: predictions.map((pred, idx) => {
      const originalReq = requirements[idx] || null
      if (typeof pred === 'string') {
        return {
          predicted_label: pred,
          requirement: originalReq?.statement || originalReq?.text || '',
          originalReq,
          index: idx,
        }
      }
      return {
        ...pred,
        predicted_label: pred.predicted_label || pred.label || pred.category || pred.class || '未分类',
        requirement: pred.requirement || pred.text || pred.input || originalReq?.statement || originalReq?.text || '',
        originalReq,
        index: pred.index ?? idx,
      }
    }),
    label_distribution: raw.label_distribution || {},
    total: raw.total ?? predictions.length,
  }
}

/**
 * @param {import('vue').Ref<string>} sessionId
 * @param {import('vue').Ref<Array>} highLevelRequirements - 由 useAnalysisSession 提供，此处可写入
 * @param {import('vue').Ref<Array>} lowLevelRequirements  - 由 useAnalysisSession 提供，此处可写入
 */
export function useRequirementsAnalysis(sessionId, highLevelRequirements, lowLevelRequirements) {
  const isAnalyzing = ref(false)
  const analysisStep = ref(0) // 0:未开始 1:L4生成 2:追溯 3:冲突 4:分类 5:完成
  const analysisError = ref(null)
  const analysisNotice = ref('')
  const analysisTargetTab = ref('full')
  const analysisRuns = ref([])
  const selectedAnalysisRunId = ref('')
  const isLoadingAnalysisRuns = ref(false)
  const l4GenerationProgress = ref({ current: 0, total: 0 })
  const conflictProgress = ref({ current: 0, total: 0 })
  const conflictConcurrency = ref(DEFAULT_CONFLICT_CONCURRENCY)

  const traceResult = ref(null)
  const conflictResults = ref([])
  const classificationResult = ref(null)

  const activeTab = ref('network')

  const allHighLevelRequirements = computed(() =>
    highLevelRequirements.value.map((req, idx) => {
      const level = normalizeLevel(req.level || req.category)
      return {
        ...req,
        id: req.req_id || req.id || `${level}-${idx}`,
        category: level,
        level,
        statement: req.text || req.statement || '',
      }
    })
  )

  const canAnalyze = computed(() => sessionId.value.trim().length > 0)

  const activeAnalysisLabel = computed(() => ACTIVE_ANALYSIS_LABELS[activeTab.value] || '分析')

  const conflictStats = computed(() => {
    if (!conflictResults.value.length) return null
    const conflicts = conflictResults.value.filter((r) => r.verdict === 'confirmed')
    const suspected = conflictResults.value.filter((r) => r.verdict === 'suspected')
    const evaluatedTotal = conflictProgress.value.total || conflictResults.value.length
    return {
      total: evaluatedTotal,
      conflicts: conflicts.length,
      suspected: suspected.length,
      compatible: Math.max(evaluatedTotal - conflicts.length - suspected.length, 0),
      requestedConcurrency: conflictProgress.value.requestedConcurrency || conflictConcurrency.value,
      appliedConcurrency: conflictProgress.value.appliedConcurrency || 0,
    }
  })

  const classificationGroups = computed(() => {
    if (!classificationResult.value?.predictions) return []
    const groups = {}
    classificationResult.value.predictions.forEach((pred) => {
      const label = pred.predicted_label || '未分类'
      if (!groups[label]) groups[label] = []
      groups[label].push(pred)
    })
    return Object.entries(groups).sort((a, b) => b[1].length - a[1].length)
  })

  const analysisPercent = computed(() => {
    if (analysisStep.value === 0) return 0
    if (analysisStep.value === 5) return 100

    const workflow = WORKFLOW_STEPS[analysisTargetTab.value] || WORKFLOW_STEPS.full
    const stepIndex = workflow.indexOf(analysisStep.value)
    if (stepIndex === -1) return 0

    const segmentWidth = 100 / workflow.length
    let segmentProgress = 0.5

    if (analysisStep.value === 1 && l4GenerationProgress.value.total > 0) {
      segmentProgress = l4GenerationProgress.value.current / l4GenerationProgress.value.total
    } else if (analysisStep.value === 3 && conflictProgress.value.total > 0) {
      segmentProgress = conflictProgress.value.current / conflictProgress.value.total
    }

    segmentProgress = Math.max(0, Math.min(1, segmentProgress))
    return Math.round((stepIndex * segmentWidth) + (segmentProgress * segmentWidth))
  })

  const analysisStepText = computed(() => {
    switch (analysisStep.value) {
      case 1:
        return l4GenerationProgress.value.total > 0
          ? `正在生成底层需求 (${l4GenerationProgress.value.current}/${l4GenerationProgress.value.total})...`
          : '正在生成底层需求...'
      case 2:
        return '正在进行追溯分析...'
      case 3:
        return conflictProgress.value.total > 0
          ? `正在进行冲突检测 (${conflictProgress.value.current}/${conflictProgress.value.total})...`
          : '正在进行冲突检测...'
      case 4:
        return '正在进行需求分类...'
      case 5:
        return `${ACTIVE_ANALYSIS_LABELS[analysisTargetTab.value] || '分析'}完成!`
      default:
        return ''
    }
  })

  const progressColorClass = computed(() => {
    const colorMap = { 1: 'color-l4gen', 2: 'color-trace', 3: 'color-conflict', 4: 'color-classify', 5: 'color-complete' }
    return colorMap[analysisStep.value] || ''
  })

  function clearAnalysisResults() {
    traceResult.value = null
    conflictResults.value = []
    classificationResult.value = null
  }

  function buildConflictResultPayload() {
    return {
      items: conflictResults.value,
      summary: {
        completed_pairs: conflictProgress.value.current || conflictResults.value.length,
        pairs_evaluated: conflictProgress.value.total || conflictResults.value.length,
        requested_concurrency: conflictProgress.value.requestedConcurrency || conflictConcurrency.value,
        applied_concurrency: conflictProgress.value.appliedConcurrency || 0,
      },
    }
  }

  function applyAnalysisRun(run) {
    if (!run) return
    if (Array.isArray(run.high_level_requirements) && run.high_level_requirements.length) {
      highLevelRequirements.value = run.high_level_requirements.map((req) => ({
        ...req,
        level: normalizeLevel(req.level || req.category),
      }))
    }
    if (Array.isArray(run.low_level_requirements)) {
      lowLevelRequirements.value = run.low_level_requirements.map((req, idx) => normalizeL4Requirement(req, idx))
    }
    traceResult.value = run.trace_result || null
    conflictResults.value = Array.isArray(run.conflict_result?.items) ? run.conflict_result.items : []
    classificationResult.value = normalizeClassificationResult(
      run.classification_result || null,
      [...allHighLevelRequirements.value, ...lowLevelRequirements.value],
    )
    const summary = run.conflict_result?.summary || {}
    conflictProgress.value = {
      current: summary.completed_pairs || summary.pairs_evaluated || conflictResults.value.length,
      total: summary.pairs_evaluated || summary.candidate_count || conflictResults.value.length,
      requestedConcurrency: summary.requested_concurrency || conflictConcurrency.value,
      appliedConcurrency: summary.applied_concurrency || 0,
    }
    selectedAnalysisRunId.value = run.analysis_run_id || ''
  }

  async function loadHighLevelRequirements(currentSessionId) {
    const l123Data = await requirementsL123Api.listBySession(currentSessionId, { page: 1, perPage: 500 })
    highLevelRequirements.value = (l123Data.requirements || []).map((req) => ({
      ...req,
      level: normalizeLevel(req.level || req.category),
    }))

    if (highLevelRequirements.value.length === 0) {
      throw new Error('未找到顶层需求，请先在需求分析流程中抽取需求')
    }
  }

  async function ensureLowLevelRequirements(currentSessionId) {
    analysisStep.value = 1
    l4GenerationProgress.value = { current: 0, total: 0 }
    analysisNotice.value = '正在基于顶层需求生成底层需求...'

    const existingLowLevel = (lowLevelRequirements.value || []).filter(
      (req) => (req.statement || req.text || '').trim(),
    )

    if (existingLowLevel.length > 0) {
      lowLevelRequirements.value = existingLowLevel.map((req, idx) => normalizeL4Requirement(req, idx))
      l4GenerationProgress.value = { current: existingLowLevel.length, total: existingLowLevel.length }
      analysisNotice.value = `检测到已有 ${existingLowLevel.length} 条底层需求，跳过 L4 生成`
      return lowLevelRequirements.value
    }

    l4GenerationProgress.value = { current: 0, total: highLevelRequirements.value.length }

    try {
      const hasCachedL4 = await l4RequirementsApi.checkExists(currentSessionId)
      if (hasCachedL4) {
        const existingL4 = await l4RequirementsApi.getBySession(currentSessionId, { perPage: 500 })
        lowLevelRequirements.value = (existingL4.requirements || []).map((r, idx) => normalizeL4Requirement(r, idx))
        l4GenerationProgress.value = {
          current: lowLevelRequirements.value.length,
          total: lowLevelRequirements.value.length,
        }
        analysisNotice.value = `使用缓存中的 ${lowLevelRequirements.value.length} 条底层需求`
        return lowLevelRequirements.value
      }

      const reqsForL4 = highLevelRequirements.value.map((req) => ({
        id: req.req_id || req.id,
        text: req.text || req.statement || '',
      }))

      const l4Response = await l4RequirementsApi.generate(
        currentSessionId,
        reqsForL4,
        {
          config: {
            top_k_pattern: 5,
            top_k_spec: 3,
            top_k_nfr: 3,
            max_l4_per_top_req: 5,
            min_l4_per_top_req: 1,
            confidence_threshold: 0.6,
          },
          model: 'deepseek-v4-pro',
          forceRegenerate: false,
        },
      )
      const l4Reqs = l4Response.requirements || []
      lowLevelRequirements.value = l4Reqs.map((r, idx) => normalizeL4Requirement(r, idx))
      l4GenerationProgress.value = { current: l4Reqs.length, total: l4Reqs.length }
      analysisNotice.value = `已生成 ${l4Reqs.length} 条底层需求`
      return lowLevelRequirements.value
    } catch (l4Err) {
      console.warn('L4 生成失败，尝试加载已有数据:', l4Err)
      try {
        const existingL4 = await l4RequirementsApi.getBySession(currentSessionId, { perPage: 500 })
        lowLevelRequirements.value = (existingL4.requirements || []).map((r, idx) => normalizeL4Requirement(r, idx))
        if (lowLevelRequirements.value.length > 0) {
          l4GenerationProgress.value = {
            current: lowLevelRequirements.value.length,
            total: lowLevelRequirements.value.length,
          }
          analysisNotice.value = `使用已有的 ${lowLevelRequirements.value.length} 条底层需求`
        }
      } catch {
        lowLevelRequirements.value = []
      }
    }

    return lowLevelRequirements.value
  }

  async function ensureTraceAnalysis(currentSessionId) {
    analysisStep.value = 2
    analysisNotice.value = ''

    const highReqs = allHighLevelRequirements.value.map((r) => r.statement || r.text || '').filter((s) => s && s.trim())
    const lowReqs = lowLevelRequirements.value.map((r) => r.statement || r.text || '').filter((s) => s && s.trim())

    if (hasTraceRelations(traceResult.value)) {
      analysisNotice.value = `检测到已有 ${traceResult.value.relations.length} 条追溯关系，跳过追溯分析`
      return traceResult.value
    }

    if (highReqs.length === 0 || lowReqs.length === 0) {
      traceResult.value = null
      analysisNotice.value = '缺少可分析的顶层或底层需求，未执行追溯分析'
      return null
    }

    try {
      const cachedTrace = await analysisApi.getLatestTrace(currentSessionId)
      const normalizedTrace = unwrapTraceCache(cachedTrace)
      if (hasTraceRelations(normalizedTrace)) {
        traceResult.value = normalizedTrace
        analysisNotice.value = `使用缓存中的 ${normalizedTrace.relations.length} 条追溯关系`
        return traceResult.value
      }

      traceResult.value = null
      const mappingResult = await traceabilityApi.traceByMapping(currentSessionId, true, 800)
      traceResult.value = mappingResult.data
      return traceResult.value
    } catch (traceErr) {
      console.warn('读取追溯缓存失败，执行追溯分析:', traceErr)
      traceResult.value = null
      const mappingResult = await traceabilityApi.traceByMapping(currentSessionId, true, 800)
      traceResult.value = mappingResult.data
      return traceResult.value
    }
  }

  function buildConflictRequirementSnapshots() {
    const highSnapshots = allHighLevelRequirements.value
      .filter((req) => (req.statement || req.text || '').trim())
      .map((req, idx) => ({
        requirement_id: req.req_id || req.id || `high_${idx}`,
        text: req.statement || req.text || '',
        level: req.level || req.category || 'L1',
        parent_id: req.parent_id || null,
        source_top_id: req.source_top_id || null,
        title: req.title || null,
        component: req.component || null,
        module: req.module || null,
        status: req.status || null,
        priority: req.priority || null,
      }))
    const lowSnapshots = lowLevelRequirements.value
      .filter((req) => (req.statement || req.text || '').trim())
      .map((req, idx) => ({
        requirement_id: req.req_id || req.id || `low_${idx}`,
        text: req.statement || req.text || '',
        level: 'L4',
        parent_id: req.parent_id || null,
        source_top_id: req.source_top_id || null,
        title: req.title || null,
        component: req.component || null,
        module: req.module || null,
        status: req.status || null,
        priority: req.priority || null,
      }))
    return [...highSnapshots, ...lowSnapshots]
  }

  async function ensureConflictAnalysis(currentSessionId) {
    analysisStep.value = 3
    conflictResults.value = []
    const requirementSnapshots = buildConflictRequirementSnapshots()
    conflictProgress.value = {
      current: 0,
      total: 0,
      requestedConcurrency: conflictConcurrency.value,
      appliedConcurrency: 0,
    }

    if (requirementSnapshots.length < 2) {
      analysisNotice.value = '需要至少两条同范围需求才能进行冲突检测'
      return conflictResults.value
    }

    const response = await conflictApi.analyze(requirementSnapshots, {
      saveToDb: true,
      sessionId: currentSessionId,
      conflictConcurrency: conflictConcurrency.value,
      maxCandidatesPerBucket: DEFAULT_MAX_CANDIDATES_PER_BUCKET,
    })
    const data = response?.data || {}
    const summary = data.summary || {}
    conflictResults.value = Array.isArray(data.conflicts) ? data.conflicts : []
    conflictProgress.value = {
      current: summary.completed_pairs || summary.pairs_evaluated || conflictResults.value.length,
      total: summary.pairs_evaluated || summary.candidate_count || conflictResults.value.length,
      requestedConcurrency: summary.requested_concurrency || conflictConcurrency.value,
      appliedConcurrency: summary.applied_concurrency || 0,
    }
    analysisNotice.value = `已完成 ${summary.pairs_evaluated || conflictResults.value.length} 对候选需求的冲突检测`
    return conflictResults.value
  }

  async function ensureClassificationAnalysis(currentSessionId) {
    analysisStep.value = 4

    const classifyReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]
    if (classifyReqs.length === 0) {
      classificationResult.value = null
      analysisNotice.value = '未找到可分类的需求'
      return null
    }

    if (classificationResult.value?.predictions?.length) {
      classificationResult.value = normalizeClassificationResult(classificationResult.value, classifyReqs)
      analysisNotice.value = `检测到已有 ${classificationResult.value.total || classificationResult.value.predictions.length} 条分类结果，跳过需求分类`
      return classificationResult.value
    }

    try {
      const cachedClassification = await getLatestClassification(currentSessionId)
      if (cachedClassification?.predictions?.length) {
        classificationResult.value = normalizeClassificationResult(cachedClassification, classifyReqs)
        analysisNotice.value = `使用缓存中的 ${classificationResult.value.total || classificationResult.value.predictions.length} 条分类结果`
        return classificationResult.value
      }

      const requirements = classifyReqs.map((r) => r.statement || r.text || '')
      const response = await classifyTexts({ requirements }, true, currentSessionId)
      const data = response.data
      classificationResult.value = normalizeClassificationResult(data, classifyReqs)
      analysisNotice.value = `已完成 ${classificationResult.value.total || classificationResult.value.predictions.length} 条需求分类`
      return classificationResult.value
    } catch (classErr) {
      console.warn('读取分类缓存失败，执行需求分类:', classErr)
      const requirements = classifyReqs.map((r) => r.statement || r.text || '')
      const response = await classifyTexts({ requirements }, true, currentSessionId)
      const data = response.data
      classificationResult.value = normalizeClassificationResult(data, classifyReqs)
      analysisNotice.value = `已完成 ${classificationResult.value.total || classificationResult.value.predictions.length} 条需求分类`
      return classificationResult.value
    }
  }

  function dispatchAnalysisCompleted(currentSessionId) {
    window.dispatchEvent(new CustomEvent('analysis-completed', {
      detail: {
        sessionId: currentSessionId,
        activeTab: analysisTargetTab.value,
        hasTrace: !!traceResult.value,
        hasConflict: conflictResults.value.length > 0,
        hasClassification: !!classificationResult.value,
        l4Count: lowLevelRequirements.value.length,
      },
    }))
  }

  async function saveAnalysisRun(currentSessionId) {
    const result = await analysisApi.saveRun({
      session_id: currentSessionId,
      high_level_requirements: allHighLevelRequirements.value,
      low_level_requirements: lowLevelRequirements.value,
      trace_result: traceResult.value || {},
      conflict_result: buildConflictResultPayload(),
      classification_result: classificationResult.value || {},
      meta: {
        source: 'requirements-analysis',
        active_tab_at_save: activeTab.value,
      },
    })
    selectedAnalysisRunId.value = result?.analysis_run_id || ''
    return result
  }

  async function runActiveAnalysis() {
    if (!canAnalyze.value) return

    const currentSessionId = sessionId.value.trim()

    isAnalyzing.value = true
    analysisTargetTab.value = 'full'
    analysisError.value = null
    analysisNotice.value = ''
    analysisStep.value = 0
    l4GenerationProgress.value = { current: 0, total: 0 }
    conflictProgress.value = { current: 0, total: 0 }
    clearAnalysisResults()
    localStorage.setItem('lastSessionId', currentSessionId)

    try {
      await loadHighLevelRequirements(currentSessionId)
      await ensureLowLevelRequirements(currentSessionId)
      await ensureTraceAnalysis(currentSessionId)
      await ensureConflictAnalysis(currentSessionId)
      await ensureClassificationAnalysis(currentSessionId)
      await saveAnalysisRun(currentSessionId)
      await loadAnalysisRuns()

      analysisStep.value = 5
      analysisNotice.value = '已保存本次分析结果，包含追溯、冲突检测和分类'
      dispatchAnalysisCompleted(currentSessionId)
    } catch (err) {
      analysisError.value = err?.response?.data?.error || err?.response?.data?.detail || err.message || '分析失败'
    } finally {
      isAnalyzing.value = false
    }
  }

  async function loadExistingResults() {
    if (!sessionId.value.trim()) return
    const sid = sessionId.value.trim()

    try {
      const latestRun = await analysisApi.getLatestRun(sid)
      if (latestRun) {
        applyAnalysisRun(latestRun)
        return
      }
    } catch {
      // 无缓存数据，忽略
    }

    try {
      const traceData = await analysisApi.getLatestTrace(sid)
      const normalizedTrace = unwrapTraceCache(traceData)
      if (normalizedTrace?.relations) traceResult.value = normalizedTrace
    } catch {
      // 无缓存数据，忽略
    }

    try {
      const conflictData = await conflictApi.getLatest(sid)
      const items = conflictData?.data?.items || []
      if (items.length) {
        conflictResults.value = items.map((r) => ({
          requirement_id_a: r.result_json?.requirement_id_a || '',
          requirement_id_b: r.result_json?.requirement_id_b || '',
          requirement_a_text: r.result_json?.requirement_a_text || r.requirement_a,
          requirement_b_text: r.result_json?.requirement_b_text || r.requirement_b,
          verdict: r.result_json?.verdict || (r.is_conflict ? 'confirmed' : 'clear'),
          conflict_type: r.result_json?.conflict_type || 'other',
          description: r.result_json?.description || r.raw_response,
          evidence_a: r.result_json?.evidence_a || '',
          evidence_b: r.result_json?.evidence_b || '',
          confidence: r.result_json?.confidence ?? null,
          candidate_reason: r.result_json?.candidate_reason || '',
          is_conflict: r.is_conflict,
          raw_response: r.raw_response,
        }))
      }
    } catch {
      // 无缓存数据，忽略
    }

    try {
      const classData = await getLatestClassification(sid)
      if (classData?.predictions) {
        const knownReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]
        classificationResult.value = normalizeClassificationResult(classData, knownReqs)
      }
    } catch {
      // 无缓存数据，忽略
    }
  }

  async function loadAnalysisRuns() {
    if (!sessionId.value.trim()) {
      analysisRuns.value = []
      return
    }
    isLoadingAnalysisRuns.value = true
    try {
      const rows = await analysisApi.listRuns(sessionId.value.trim(), 20)
      analysisRuns.value = Array.isArray(rows) ? rows : []
    } catch {
      analysisRuns.value = []
    } finally {
      isLoadingAnalysisRuns.value = false
    }
  }

  async function loadAnalysisRunDetail(analysisRunId) {
    if (!analysisRunId) return
    const run = await analysisApi.getRun(analysisRunId)
    applyAnalysisRun(run)
  }

  return {
    isAnalyzing,
    analysisStep,
    analysisError,
    analysisNotice,
    analysisTargetTab,
    analysisRuns,
    selectedAnalysisRunId,
    isLoadingAnalysisRuns,
    l4GenerationProgress,
    conflictProgress,
    traceResult,
    conflictResults,
    classificationResult,
    activeTab,
    activeAnalysisLabel,
    allHighLevelRequirements,
    canAnalyze,
    conflictStats,
    classificationGroups,
    analysisPercent,
    analysisStepText,
    progressColorClass,
    conflictConcurrency,
    runActiveAnalysis,
    loadExistingResults,
    loadAnalysisRuns,
    loadAnalysisRunDetail,
  }
}
