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

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

/**
 * @param {import('vue').Ref<string>} sessionId
 * @param {import('vue').Ref<Array>} highLevelRequirements - 由 useAnalysisSession 提供，此处可写入
 * @param {import('vue').Ref<Array>} lowLevelRequirements  - 由 useAnalysisSession 提供，此处可写入
 */
export function useRequirementsAnalysis(sessionId, highLevelRequirements, lowLevelRequirements) {
  // 分析状态
  const isAnalyzing = ref(false)
  const analysisStep = ref(0) // 0:未开始 1:L4生成 2:追溯 3:冲突 4:分类 5:完成
  const analysisError = ref(null)
  const analysisNotice = ref('')
  const l4GenerationProgress = ref({ current: 0, total: 0 })
  const conflictProgress = ref({ current: 0, total: 0 })

  // 分析结果
  const traceResult = ref(null)
  const conflictResults = ref([])
  const classificationResult = ref(null)

  // 视图状态
  const activeTab = ref('network')

  // 计算属性
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

  const conflictStats = computed(() => {
    if (!conflictResults.value.length) return null
    const conflicts = conflictResults.value.filter((r) => r.is_conflict)
    return {
      total: conflictResults.value.length,
      conflicts: conflicts.length,
      compatible: conflictResults.value.length - conflicts.length,
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
    const stepPercents = [0, 20, 40, 70, 90, 100]
    const basePercent = stepPercents[analysisStep.value - 1] || 0
    const stepWidth = (stepPercents[analysisStep.value] || 100) - basePercent
    if (analysisStep.value === 1 && l4GenerationProgress.value.total > 0) {
      return basePercent + Math.round((l4GenerationProgress.value.current / l4GenerationProgress.value.total) * stepWidth)
    }
    if (analysisStep.value === 3 && conflictProgress.value.total > 0) {
      return basePercent + Math.round((conflictProgress.value.current / conflictProgress.value.total) * stepWidth)
    }
    return basePercent + Math.round(stepWidth / 2)
  })

  const analysisStepText = computed(() => {
    switch (analysisStep.value) {
      case 1: return l4GenerationProgress.value.total > 0
        ? `正在生成底层需求 (${l4GenerationProgress.value.current}/${l4GenerationProgress.value.total})...`
        : '正在生成底层需求...'
      case 2: return '正在进行追溯分析...'
      case 3: return `正在进行冲突检测 (${conflictProgress.value.current}/${conflictProgress.value.total})...`
      case 4: return '正在进行需求分类...'
      case 5: return '分析完成!'
      default: return ''
    }
  })

  const progressColorClass = computed(() => {
    const colorMap = { 1: 'color-l4gen', 2: 'color-trace', 3: 'color-conflict', 4: 'color-classify', 5: 'color-complete' }
    return colorMap[analysisStep.value] || ''
  })

  // 一键分析（含 L4 生成 → 追溯 → 冲突 → 分类）
  async function runFullAnalysis() {
    if (!canAnalyze.value) return

    isAnalyzing.value = true
    analysisError.value = null
    analysisNotice.value = ''
    analysisStep.value = 1
    l4GenerationProgress.value = { current: 0, total: 0 }
    conflictProgress.value = { current: 0, total: 0 }

    const currentSessionId = sessionId.value.trim()
    localStorage.setItem('lastSessionId', currentSessionId)

    try {
      // 加载顶层需求 L1-L3
      const l123Data = await requirementsL123Api.listBySession(currentSessionId, { page: 1, perPage: 500 })
      highLevelRequirements.value = (l123Data.requirements || []).map((req) => ({
        ...req,
        level: normalizeLevel(req.level || req.category),
      }))

      if (highLevelRequirements.value.length === 0) {
        throw new Error('未找到顶层需求，请先在需求分析流程中抽取需求')
      }

      // Step 1: 生成 L4 底层需求
      analysisNotice.value = '正在基于顶层需求生成底层需求...'
      l4GenerationProgress.value = { current: 0, total: highLevelRequirements.value.length }

      const reqsForL4 = highLevelRequirements.value.map(req => ({
        id: req.req_id || req.id,
        text: req.text || req.statement || '',
      }))

      try {
        const l4Response = await l4RequirementsApi.generate(
          currentSessionId,
          reqsForL4,
          {
            config: {
              top_k_pattern: 5, top_k_spec: 3, top_k_nfr: 3,
              max_l4_per_top_req: 5, min_l4_per_top_req: 1, confidence_threshold: 0.6,
            },
            model: 'deepseek-chat',
            forceRegenerate: false,
          }
        )
        const l4Reqs = l4Response.requirements || []
        lowLevelRequirements.value = l4Reqs.map((r, idx) => ({
          ...r,
          id: r.req_id || r.id || `l4_${idx}`,
          level: 'L4',
          statement: r.text || r.shall_statement || '',
          text: r.text || r.shall_statement || '',
        }))
        l4GenerationProgress.value = { current: l4Reqs.length, total: l4Reqs.length }
        analysisNotice.value = `已生成 ${l4Reqs.length} 条底层需求`
      } catch (l4Err) {
        console.warn('L4 生成失败，尝试加载已有数据:', l4Err)
        try {
          const existingL4 = await l4RequirementsApi.getBySession(currentSessionId, { perPage: 500 })
          lowLevelRequirements.value = (existingL4.requirements || []).map(r => ({
            ...r,
            level: 'L4',
            statement: r.text || r.shall_statement || '',
          }))
          if (lowLevelRequirements.value.length > 0) {
            analysisNotice.value = `使用已有的 ${lowLevelRequirements.value.length} 条底层需求`
          }
        } catch {
          lowLevelRequirements.value = []
        }
      }

      // Step 2: 追溯分析
      analysisStep.value = 2
      traceResult.value = null
      analysisNotice.value = ''

      const highReqs = allHighLevelRequirements.value.map(r => r.statement || r.text || '').filter(s => s && s.trim())
      const lowReqs = lowLevelRequirements.value.map(r => r.statement || r.text || '').filter(s => s && s.trim())

      if (highReqs.length > 0 && lowReqs.length > 0) {
        const mappingResult = await traceabilityApi.traceByMapping(currentSessionId, true, 800)
        traceResult.value = mappingResult.data
      }

      // Step 3: 冲突检测
      analysisStep.value = 3
      conflictResults.value = []

      if (allHighLevelRequirements.value.length >= 2 && traceResult.value?.relations) {
        const pairs = []
        traceResult.value.relations.forEach((rel) => {
          if (rel.has_relation) {
            const highReq = allHighLevelRequirements.value[rel.high_level_index]
            const lowReq = lowLevelRequirements.value[rel.low_level_index]
            if (highReq && lowReq) pairs.push({ reqA: highReq, reqB: lowReq })
          }
        })
        const pairsToCheck = pairs.slice(0, 10)
        conflictProgress.value = { current: 0, total: pairsToCheck.length }
        for (const { reqA, reqB } of pairsToCheck) {
          try {
            const res = await conflictApi.check(
              reqA.statement || reqA.text || '',
              reqB.statement || reqB.text || '',
              true,
              currentSessionId
            )
            conflictResults.value = [...conflictResults.value, { reqA, reqB, ...(res.data || res) }]
          } catch { /* 忽略单个失败 */ }
          conflictProgress.value = { ...conflictProgress.value, current: conflictProgress.value.current + 1 }
        }
      }

      // Step 4: 需求分类
      analysisStep.value = 4
      classificationResult.value = null

      const classifyReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]
      if (classifyReqs.length > 0) {
        const requirements = classifyReqs.map(r => r.statement || r.text || '')
        const response = await classifyTexts({ requirements }, true, currentSessionId)
        const data = response.data
        classificationResult.value = {
          predictions: data.predictions.map((pred, idx) => ({ ...pred, originalReq: classifyReqs[idx] })),
          label_distribution: data.label_distribution,
          total: data.total,
        }
      }

      analysisStep.value = 5
      activeTab.value = 'network'

      window.dispatchEvent(new CustomEvent('analysis-completed', {
        detail: {
          sessionId: currentSessionId,
          hasTrace: !!traceResult.value,
          hasConflict: conflictResults.value.length > 0,
          hasClassification: !!classificationResult.value,
          l4Count: lowLevelRequirements.value.length,
        },
      }))
    } catch (err) {
      analysisError.value = err?.response?.data?.error || err?.response?.data?.detail || err.message || '分析失败'
    } finally {
      isAnalyzing.value = false
    }
  }

  // 加载已有的缓存分析结果
  async function loadExistingResults() {
    if (!sessionId.value.trim()) return
    const sid = sessionId.value.trim()

    try {
      const traceData = await analysisApi.getLatestTrace(sid)
      if (traceData && traceData.relations) traceResult.value = traceData
    } catch { /* 无缓存数据，忽略 */ }

    try {
      const conflictData = await conflictApi.getLatest(sid)
      if (conflictData?.data?.results) {
        conflictResults.value = conflictData.data.results.map(r => ({
          reqA: { statement: r.requirement_a },
          reqB: { statement: r.requirement_b },
          is_conflict: r.is_conflict,
          raw_response: r.raw_response,
        }))
      }
    } catch { /* 无缓存数据，忽略 */ }

    try {
      const classData = await getLatestClassification(sid)
      if (classData?.predictions) {
        classificationResult.value = {
          predictions: classData.predictions,
          label_distribution: classData.label_distribution,
          total: classData.total,
        }
      }
    } catch { /* 无缓存数据，忽略 */ }
  }

  return {
    isAnalyzing,
    analysisStep,
    analysisError,
    analysisNotice,
    l4GenerationProgress,
    conflictProgress,
    traceResult,
    conflictResults,
    classificationResult,
    activeTab,
    allHighLevelRequirements,
    canAnalyze,
    conflictStats,
    classificationGroups,
    analysisPercent,
    analysisStepText,
    progressColorClass,
    runFullAnalysis,
    loadExistingResults,
  }
}

