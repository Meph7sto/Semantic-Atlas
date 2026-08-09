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
const DEMO_PCA_SESSION_ID = 'demo-pca-infusion-pump-session'

const DEMO_CONFLICTS = [
  {
    a: 'PCA-L-13',
    b: 'PCA-L-15',
    verdict: 'suspected',
    conflict_type: 'logic_timing',
    confidence: 0.78,
    description: 'L-13 对“受命令停泵”仍保留“是否完成当前行程”的疑问，L-15 对普通停止明确要求完成当前行程。二者不是必然冲突，但需要把正常停止和报警响应拆成条件化规则。',
    evidence_a: 'halt pumping when commanded or caused in response to an alarm condition (at end of pump stoke?)',
    evidence_b: 'When the stop button is pressed the current pump stroke shall be completed prior to stopping the pump',
    candidate_reason: '停泵时序均涉及“完成当前泵送行程”',
  },
  {
    a: 'PCA-L-15',
    b: 'PCA-L-17',
    verdict: 'confirmed',
    conflict_type: 'logic_timing',
    confidence: 0.91,
    description: '普通按键停止要求完成当前泵送行程，闭塞报警要求立即停止且不完成当前行程。演示中应标注为“条件区分后的可消解冲突”，用于说明冲突检测能发现表述边界。',
    evidence_a: 'stop button is pressed ... current pump stroke shall be completed',
    evidence_b: 'occlusion alarm occurs the pump shall be stopped immediately without completing the current pump stroke',
    candidate_reason: '同一执行动作在不同触发条件下存在相反约束',
  },
  {
    a: 'PCA-L-14',
    b: 'PCA-H-02',
    verdict: 'suspected',
    conflict_type: 'terminology',
    confidence: 0.83,
    description: '上层需求描述泵过热提示，细化需求标题为过热报警但正文写成“泵过载报警”。需要统一告警名称和测温点。',
    evidence_a: 'If the pump gets overheated to more than Tpoh = 55 C ... pump overloaded alarm',
    evidence_b: 'indicates when it is too hot',
    candidate_reason: '过热/过载告警名称不一致',
  },
  {
    a: 'PCA-L-23',
    b: 'PCA-L-51',
    verdict: 'confirmed',
    conflict_type: 'other',
    confidence: 0.89,
    description: 'L-23 的 KVO 单位写作 1/ml 且依赖 Table 4 决定哪些报警完全停流；L-51 又说明优先级见 Table 4，但该表未随数据提供。当前验收基线不完整。',
    evidence_a: 'FKVO = 1/ml ... Table 4 defines which alarms also stop drug flow completely',
    evidence_b: 'Priority for alarms and warnings is shown in Table 4',
    candidate_reason: '共享缺失外部表和不完整单位',
  },
  {
    a: 'PCA-L-54',
    b: 'PCA-H-09',
    verdict: 'confirmed',
    conflict_type: 'other',
    confidence: 0.86,
    description: '“成功屏蔽的故障”按常规可理解为影响被隔离，但 L-54 又要求仍触发报警。需确认是“记录但不报警”还是“屏蔽影响但仍报警”。',
    evidence_a: 'Successfully masked faults shall be recorded in the Fault Log but raise an alarm',
    evidence_b: 'Alarm Thread evaluates fault signals ... issues alarm and warning signals',
    candidate_reason: '故障屏蔽与报警触发语义相互牵制',
  },
  {
    a: 'PCA-L-38',
    b: 'PCA-L-37',
    verdict: 'suspected',
    conflict_type: 'logic_timing',
    confidence: 0.76,
    description: 'L-37 要求市电中断后电池至少支持 10 分钟继续输注，L-38 的组合条件句结构残缺，可能导致“电池故障+市电异常”下泵速关闭动作不可测试。',
    evidence_a: 'continue to infuse for 10 minutes during interruption of mains electricity supply',
    evidence_b: 'if the battery failure alarm and either the voltage out-o-range or the power supply failure alarms the the pump rate will be off',
    candidate_reason: '供电故障组合逻辑未闭合',
  },
  {
    a: 'PCA-L-04',
    b: 'PCA-L-05',
    verdict: 'clear',
    conflict_type: 'other',
    confidence: 0.95,
    description: '1 ml 触发低液量预警，0.5 ml 触发空仓报警并停泵，阈值动作分层清晰；需另行评估测量误差带来的边界风险。',
    evidence_a: 'less than Vlra = 1 ml ... low-reservoir warning',
    evidence_b: 'less than Vers =0.5 ml ... empty-reservoir alarm ... stopping the pump',
    candidate_reason: '同一储液仓余量阈值链',
  },
  {
    a: 'PCA-L-30',
    b: 'PCA-L-31',
    verdict: 'clear',
    conflict_type: 'other',
    confidence: 0.93,
    description: '软限制允许医护确认后继续，硬限制必须拒绝，二者边界明确且适合演示需求分类中的安全/权限规则。',
    evidence_a: 'soft limits ... warning requiring a soft limit confirmation',
    evidence_b: 'hard limit ... shall be rejected',
    candidate_reason: '同属药物库限制策略',
  },
]

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

function getRequirementId(req, fallback = '') {
  return req?.req_id || req?.id || fallback
}

function getRequirementText(req) {
  return String(req?.statement || req?.text || req?.shall_statement || req?.title || '').trim()
}

function findRequirementById(requirements, reqId) {
  return requirements.find((req) => getRequirementId(req) === reqId) || null
}

function getDemoRelationType(lowReq) {
  const text = getRequirementText(lowReq).toLowerCase()
  if (text.includes('table 4') || text.includes('tolerance') || text.includes('iec')) return 'dependency'
  if (text.includes('logger') || text.includes('timestamp') || text.includes('record')) return 'support'
  return 'implementation'
}

function buildDemoTraceResult(highReqs, lowReqs) {
  const highIds = new Set(highReqs.map((req) => getRequirementId(req)).filter(Boolean))
  const lowIds = new Set(lowReqs.map((req) => getRequirementId(req)).filter(Boolean))
  const relations = []

  lowReqs.forEach((lowReq, index) => {
    const lowId = getRequirementId(lowReq, `PCA-L-${String(index + 1).padStart(2, '0')}`)
    const sourceTopIds = Array.isArray(lowReq.source_top_ids) && lowReq.source_top_ids.length
      ? lowReq.source_top_ids
      : (lowReq.source_top_id ? [lowReq.source_top_id] : [])

    sourceTopIds.forEach((topId) => {
      if (!highIds.has(topId) || !lowIds.has(lowId)) return
      relations.push({
        high_req_id: topId,
        low_req_id: lowId,
        high_level_index: highReqs.findIndex((req) => getRequirementId(req) === topId),
        low_level_index: lowReqs.findIndex((req) => getRequirementId(req) === lowId),
        has_relation: true,
        relation_type: getDemoRelationType(lowReq),
        confidence: Number(lowReq.confidence || 0.9),
        reason: '来自原始清单 label=1 的正向追踪关系，并由会议纪要确认系统模块边界。',
      })
    })
  })

  const totalCombinations = highReqs.length * lowReqs.length
  return {
    summary: `PCA输液泵演示追溯：${highReqs.length} 条上层需求、${lowReqs.length} 条细化需求、${relations.length} 条正向追踪关系`,
    statistics: {
      total_combinations: totalCombinations,
      pairs_analyzed: relations.length,
      relations_found: relations.length,
      relation_rate: totalCombinations ? relations.length / totalCombinations : 0,
    },
    high_level_requirements: highReqs.map(getRequirementText),
    low_level_requirements: lowReqs.map(getRequirementText),
    relations,
    trace_network: {
      nodes: [
        ...highReqs.map((req) => ({ id: getRequirementId(req), label: getRequirementText(req), level: req.level || 'L3' })),
        ...lowReqs.map((req) => ({ id: getRequirementId(req), label: getRequirementText(req), level: 'L4' })),
      ],
      links: relations.map((rel) => ({
        source: rel.high_req_id,
        target: rel.low_req_id,
        type: rel.relation_type,
        confidence: rel.confidence,
      })),
    },
    relation_types_count: relations.reduce((acc, rel) => {
      acc[rel.relation_type] = (acc[rel.relation_type] || 0) + 1
      return acc
    }, {}),
  }
}

function buildDemoConflictResults(requirements) {
  return DEMO_CONFLICTS.map((item) => {
    const reqA = findRequirementById(requirements, item.a)
    const reqB = findRequirementById(requirements, item.b)
    return {
      ...item,
      requirement_id_a: item.a,
      requirement_id_b: item.b,
      requirement_a_text: getRequirementText(reqA) || item.evidence_a,
      requirement_b_text: getRequirementText(reqB) || item.evidence_b,
      is_conflict: item.verdict === 'confirmed',
      raw_response: item.description,
    }
  })
}

function classifyDemoRequirement(req) {
  const id = getRequirementId(req)
  const text = getRequirementText(req).toLowerCase()
  if (['PCA-L-23', 'PCA-L-38', 'PCA-L-46', 'PCA-L-47', 'PCA-L-48', 'PCA-L-49', 'PCA-L-51', 'PCA-L-54'].includes(id)) {
    return '待确认项'
  }
  if (text.includes('alarm') || text.includes('warning') || text.includes('alert') || text.includes('priority') || text.includes('visual')) {
    return '报警需求'
  }
  if (text.includes('fault') || text.includes('failure') || text.includes('hard limit') || text.includes('tamper') || text.includes('reverse') || text.includes('safety') || text.includes('occlusion')) {
    return '安全需求'
  }
  if (text.includes('log') || text.includes('timestamp') || text.includes('retained') || text.includes('clock') || text.includes('record')) {
    return '数据与日志'
  }
  if (text.includes('battery') || text.includes('mains') || text.includes('power') || text.includes('voltage') || text.includes('energy')) {
    return '电源需求'
  }
  if (text.includes('clinician') || text.includes('authorized') || text.includes('confirmation') || text.includes('prescription') || text.includes('door') || text.includes('dea')) {
    return '权限与防拆'
  }
  return '功能需求'
}

function buildDemoClassificationResult(requirements) {
  const predictions = requirements.map((req, index) => {
    const label = classifyDemoRequirement(req)
    return {
      index,
      requirement_id: getRequirementId(req),
      requirement: getRequirementText(req),
      predicted_label: label,
      confidence: label === '待确认项' ? 0.82 : 0.91,
      originalReq: req,
    }
  })
  const labelDistribution = predictions.reduce((acc, item) => {
    acc[item.predicted_label] = (acc[item.predicted_label] || 0) + 1
    return acc
  }, {})
  return {
    predictions,
    label_distribution: labelDistribution,
    total: predictions.length,
    source: 'pca_demo_click_analysis',
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
        source: currentSessionId === DEMO_PCA_SESSION_ID
          ? 'pca_demo_click_analysis'
          : 'requirements-analysis',
        active_tab_at_save: activeTab.value,
      },
    })
    selectedAnalysisRunId.value = result?.analysis_run_id || ''
    return result
  }

  async function runDemoPcaAnalysis(currentSessionId) {
    analysisStep.value = 1
    analysisNotice.value = '正在加载PCA输液泵演示需求...'
    await loadHighLevelRequirements(currentSessionId)
    await ensureLowLevelRequirements(currentSessionId)

    const allRequirements = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]

    analysisStep.value = 2
    traceResult.value = buildDemoTraceResult(allHighLevelRequirements.value, lowLevelRequirements.value)

    analysisStep.value = 3
    conflictResults.value = buildDemoConflictResults(allRequirements)
    conflictProgress.value = {
      current: conflictResults.value.length,
      total: conflictResults.value.length,
      requestedConcurrency: conflictConcurrency.value,
      appliedConcurrency: 1,
    }

    analysisStep.value = 4
    classificationResult.value = buildDemoClassificationResult(allRequirements)

    await saveAnalysisRun(currentSessionId)
    await loadAnalysisRuns()

    analysisStep.value = 5
    analysisNotice.value = 'PCA输液泵演示分析已生成并保存，包含追溯、冲突检测和需求分类'
    dispatchAnalysisCompleted(currentSessionId)
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
      if (currentSessionId === DEMO_PCA_SESSION_ID) {
        await runDemoPcaAnalysis(currentSessionId)
      } else {
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
      }
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
