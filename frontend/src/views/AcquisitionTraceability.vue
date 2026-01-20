<script setup>
import { ref, computed, watch } from 'vue'
import { traceabilityApi, conflictApi, classifyTexts } from '../utils/api'
import {
  FileText,
  Loader2,
  ArrowRight,
  Briefcase,
  Users,
  Layout,
  Quote,
  Settings2,
  Link2,
  Network,
  Layers,
  ChevronDown,
  Lock,
  Tags,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  BarChart3
} from 'lucide-vue-next'
import * as echarts from 'echarts'

// ========== 状态管理 ==========
const currentStep = ref(1) // 1: 需求获取, 2: 追溯分析, 3: 冲突检测, 4: 需求分类
const activeTab = ref('board') // 'board' | 'network' | 'conflict' | 'classification'

// 需求获取相关状态
const inputText = ref('')
const isLoading = ref(false)
const error = ref(null)
const result = ref(null)
const progress = ref({
  stage: '',
  clean: { current: 0, total: 0 },
  extract: { current: 0, total: 0 }
})

// 模型设置
const extractModel = ref('deepseek-reasoner')
const cleanModel = ref('deepseek-chat')

// 底层需求（预留）
const lowLevelRequirements = ref([])
const isExtractingLowLevel = ref(false)

// 追溯分析相关状态
const isTracingLoading = ref(false)
const traceResult = ref(null)
const traceError = ref(null)

// 需求分类相关状态
const isClassifying = ref(false)
const classificationResult = ref(null)
const classificationError = ref(null)

// 冲突检测相关状态
const isDetectingConflict = ref(false)
const conflictResults = ref([])
const conflictError = ref(null)
const conflictProgress = ref({ current: 0, total: 0 })

// 一键分析相关状态
const isAnalyzing = ref(false)
const analysisStep = ref(0) // 0: 未开始, 1: 追溯中, 2: 冲突检测中, 3: 分类中, 4: 完成
const analysisError = ref(null)

// 图表相关
const chartContainer = ref(null)
let chart = null

// ========== 计算属性 ==========
const INFERENCE_BASE = '/api/requirements'

const cleanPercent = computed(() => {
  const total = progress.value.clean.total
  if (!total) return 0
  return Math.round((progress.value.clean.current / total) * 100)
})

const extractPercent = computed(() => {
  const total = progress.value.extract.total
  if (!total) return 0
  return Math.round((progress.value.extract.current / total) * 100)
})

// 所有顶层需求（L1 + L2 + L3）
const allHighLevelRequirements = computed(() => {
  if (!result.value) return []
  const all = []
  const addItems = (items, category) => {
    ;(items || []).forEach((item, idx) => {
      all.push({
        id: `${category}-${idx}`,
        category,
        ...item
      })
    })
  }
  addItems(result.value.business_requirements, 'L1')
  addItems(result.value.stakeholder_requirements, 'L2')
  addItems(result.value.system_requirements, 'L3')
  return all
})

// 是否可以进行追溯分析
const canTrace = computed(() => {
  return allHighLevelRequirements.value.length > 0 && lowLevelRequirements.value.length > 0
})

// 看板列配置
const baseColumns = [
  {
    id: 'L1',
    title: 'L1 业务需求',
    icon: Briefcase,
    headerClass: 'bg-sky-50/70 border-sky-200',
    iconClass: 'text-sky-700',
    badgeClass: 'bg-sky-100 text-sky-700 border-sky-200'
  },
  {
    id: 'L2',
    title: 'L2 利益相关者需求',
    icon: Users,
    headerClass: 'bg-zinc-100/80 border-zinc-200',
    iconClass: 'text-zinc-700',
    badgeClass: 'bg-zinc-100 text-zinc-700 border-zinc-200'
  },
  {
    id: 'L3',
    title: 'L3 系统需求',
    icon: Layout,
    headerClass: 'bg-amber-50/70 border-amber-200',
    iconClass: 'text-amber-700',
    badgeClass: 'bg-amber-100 text-amber-700 border-amber-200'
  },
  {
    id: 'low',
    title: '底层需求',
    icon: Layers,
    headerClass: 'bg-emerald-50/70 border-emerald-200',
    iconClass: 'text-emerald-700',
    badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200'
  }
]

const boardColumns = computed(() => {
  if (!result.value) {
    return baseColumns.map((col) => ({ ...col, items: [] }))
  }

  let counter = 0
  const toItems = (items, category) =>
    (items || []).map((item) => ({
      id: `${category}-${++counter}`,
      category,
      ...item
    }))

  return baseColumns.map((col) => {
    if (col.id === 'L1') {
      return { ...col, items: toItems(result.value.business_requirements, 'L1') }
    }
    if (col.id === 'L2') {
      return { ...col, items: toItems(result.value.stakeholder_requirements, 'L2') }
    }
    if (col.id === 'L3') {
      return { ...col, items: toItems(result.value.system_requirements, 'L3') }
    }
    // 底层需求列
    return { ...col, items: lowLevelRequirements.value }
  })
})

// ========== 辅助函数 ==========
function getConfidenceColor(conf) {
  if (conf >= 0.8) return 'text-green-600 bg-green-50 border-green-200'
  if (conf >= 0.5) return 'text-yellow-600 bg-yellow-50 border-yellow-200'
  return 'text-red-600 bg-red-50 border-red-200'
}

function getRelationTypeLabel(type) {
  const labels = {
    implementation: '实现关系',
    support: '支持关系',
    dependency: '依赖关系',
    decomposition: '分解关系',
    general: '追溯关系',
    unknown: '未知关系'
  }
  return labels[type] || '追溯关系'
}

function getRelationTypeColor(type) {
  const colors = {
    implementation: '#22c55e',
    support: '#3b82f6',
    dependency: '#ef4444',
    decomposition: '#f59e0b',
    general: '#6b7280'
  }
  return colors[type] || '#6b7280'
}

function getCategoryColor(category) {
  const colors = {
    L1: '#0ea5e9',
    L2: '#71717a',
    L3: '#f59e0b',
    low: '#10b981'
  }
  return colors[category] || '#6b7280'
}

// ========== API 调用 ==========
async function readResponsePayload(response) {
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()
  if (!text) {
    return { data: null, text: '' }
  }
  if (contentType.includes('application/json')) {
    try {
      return { data: JSON.parse(text), text }
    } catch {
      return { data: null, text }
    }
  }
  try {
    return { data: JSON.parse(text), text }
  } catch {
    return { data: null, text }
  }
}

async function analyzeRequirements() {
  if (!inputText.value.trim()) return

  isLoading.value = true
  error.value = null
  result.value = null
  lowLevelRequirements.value = []
  traceResult.value = null
  progress.value = {
    stage: '',
    clean: { current: 0, total: 0 },
    extract: { current: 0, total: 0 }
  }

  try {
    const response = await fetch(`${INFERENCE_BASE}/extract/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: inputText.value,
        chunk_size: 3600,
        overlap: 500,
        clean_model: cleanModel.value,
        extract_model: extractModel.value
      })
    })

    if (!response.ok) {
      const { data, text } = await readResponsePayload(response)
      const message = data?.error || data?.detail || `HTTP ${response.status}`
      const snippet = text ? text.replace(/\s+/g, ' ').slice(0, 200) : ''
      throw new Error(snippet ? `${message}: ${snippet}` : message)
    }

    if (!response.body) {
      throw new Error('Empty response body')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let streamError = null
    let gotResult = false

    const handleEvent = (event, payload) => {
      if (event === 'progress') {
        if (payload.stage === 'clean_polish') {
          progress.value.stage = 'clean_polish'
          progress.value.clean.current = payload.current || 0
          progress.value.clean.total = payload.total || 0
        } else if (payload.stage === 'extract') {
          progress.value.stage = 'extract'
          progress.value.extract.current = payload.current || 0
          progress.value.extract.total = payload.total || 0
        } else if (payload.stage === 'done') {
          progress.value.stage = 'done'
        }
        return
      }
      if (event === 'error') {
        streamError = payload?.error || 'Server error'
        return
      }
      if (event === 'result') {
        result.value = payload
        gotResult = true
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let splitIdx = buffer.indexOf('\n\n')
      while (splitIdx !== -1) {
        const rawEvent = buffer.slice(0, splitIdx)
        buffer = buffer.slice(splitIdx + 2)
        splitIdx = buffer.indexOf('\n\n')

        const lines = rawEvent.split('\n')
        let event = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            event = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            data += line.slice(5).trim()
          }
        }
        if (!data) continue
        try {
          const payload = JSON.parse(data)
          handleEvent(event, payload)
        } catch {
          streamError = 'Invalid stream payload'
        }
        if (streamError || gotResult) {
          await reader.cancel()
          break
        }
      }
      if (streamError || gotResult) {
        break
      }
    }

    if (streamError) {
      throw new Error(streamError)
    }
    if (!gotResult) {
      throw new Error('Stream ended without result')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

// 预留：提取底层需求接口
async function extractLowLevelRequirements() {
  if (allHighLevelRequirements.value.length === 0) return

  isExtractingLowLevel.value = true
  traceError.value = null

  try {
    // TODO: 调用底层需求提取接口
    // const response = await api.post('/api/requirements/extract-low-level', {
    //   high_level_requirements: allHighLevelRequirements.value.map(r => r.statement)
    // })
    // lowLevelRequirements.value = response.data.low_level_requirements

    // 暂时模拟：显示功能开发中提示
    await new Promise((resolve) => setTimeout(resolve, 500))
    alert('功能开发中：底层需求提取接口尚未实现\n\n请使用「加载示例底层需求」按钮测试追溯功能')
  } catch (err) {
    traceError.value = err.message || '提取底层需求失败'
  } finally {
    isExtractingLowLevel.value = false
  }
}

// 加载示例底层需求（用于测试/演示）
function loadMockLowLevelRequirements() {
  const mockLowLevel = [
    {
      id: 'low-1',
      category: 'low',
      statement: '实现用户认证模块，支持用户名密码登录',
      rationale: '满足用户登录功能的基础实现',
      evidence: '系统登录',
      confidence: 0.92
    },
    {
      id: 'low-2',
      category: 'low',
      statement: '设计数据库表结构，包含用户表、权限表、日志表',
      rationale: '数据持久化的基础设施',
      evidence: '数据存储',
      confidence: 0.88
    },
    {
      id: 'low-3',
      category: 'low',
      statement: '开发RESTful API接口，响应时间小于200ms',
      rationale: '满足性能需求的技术实现',
      evidence: '性能要求',
      confidence: 0.85
    },
    {
      id: 'low-4',
      category: 'low',
      statement: '实现数据导入导出功能，支持Excel和CSV格式',
      rationale: '满足数据交互需求',
      evidence: '导入导出',
      confidence: 0.90
    },
    {
      id: 'low-5',
      category: 'low',
      statement: '集成消息队列，实现异步任务处理',
      rationale: '提升系统并发处理能力',
      evidence: '异步处理',
      confidence: 0.78
    }
  ]

  lowLevelRequirements.value = mockLowLevel
  currentStep.value = 2
}

// 加载完整的模拟数据（顶层需求 + 底层需求 + 追溯结果）用于完全离线测试
function loadFullMockData() {
  // 模拟顶层需求抽取结果
  result.value = {
    business_requirements: [
      {
        statement: '实现自动对账功能，提升财务效率',
        rationale: '解决人工对账慢、易出错的问题',
        evidence: '财务那边希望...',
        confidence: 0.95
      },
      {
        statement: '系统必须在下月底前上线，满足审计要求',
        rationale: '时间约束，影响审计',
        evidence: '下个月底上线',
        confidence: 0.88
      }
    ],
    stakeholder_requirements: [
      {
        statement: '支持导入银行流水并与内部单据自动匹配',
        rationale: '用户核心使用场景',
        evidence: '导入银行流水',
        confidence: 0.92
      },
      {
        statement: '匹配不上的记录需要高亮显示',
        rationale: '便于人工复核',
        evidence: '高亮显示',
        confidence: 0.90
      }
    ],
    system_requirements: [
      {
        statement: '系统需支持处理1万条数据，耗时不超过1分钟',
        rationale: '性能基线要求',
        evidence: '一万条数据一分钟',
        confidence: 0.87
      },
      {
        statement: '支持Excel和CSV格式的数据导入',
        rationale: '兼容常见数据格式',
        evidence: '导入',
        confidence: 0.85
      }
    ]
  }

  // 模拟底层需求
  lowLevelRequirements.value = [
    {
      id: 'low-1',
      category: 'low',
      statement: '实现银行流水解析模块，支持主流银行格式',
      rationale: '数据导入的技术实现',
      evidence: '银行流水',
      confidence: 0.91
    },
    {
      id: 'low-2',
      category: 'low',
      statement: '开发智能匹配算法，基于金额、日期、摘要进行多维匹配',
      rationale: '自动匹配的核心算法',
      evidence: '自动匹配',
      confidence: 0.89
    },
    {
      id: 'low-3',
      category: 'low',
      statement: '实现差异标记功能，支持红色高亮和批注',
      rationale: '匹配失败的可视化展示',
      evidence: '高亮显示',
      confidence: 0.93
    },
    {
      id: 'low-4',
      category: 'low',
      statement: '采用批量处理和分页加载，确保大数据量下的响应速度',
      rationale: '性能优化措施',
      evidence: '一万条',
      confidence: 0.86
    }
  ]

  // 模拟追溯分析结果
  const mockHighReqs = [
    ...result.value.business_requirements,
    ...result.value.stakeholder_requirements,
    ...result.value.system_requirements
  ]

  traceResult.value = {
    summary: `批量分析了 ${mockHighReqs.length} 个顶层需求和 ${lowLevelRequirements.value.length} 个底层需求`,
    statistics: {
      total_combinations: mockHighReqs.length * lowLevelRequirements.value.length,
      relations_found: 8,
      relation_rate: 0.33
    },
    high_level_requirements: mockHighReqs.map((r) => r.statement),
    low_level_requirements: lowLevelRequirements.value.map((r) => r.statement),
    relations: [
      // L1[0] 自动对账 -> low[1] 智能匹配算法
      {
        high_level_index: 0,
        low_level_index: 1,
        has_relation: true,
        relation_type: 'decomposition',
        confidence: 0.92,
        summary: '自动对账功能需要智能匹配算法作为核心实现'
      },
      // L2[0] 导入银行流水 -> low[0] 银行流水解析
      {
        high_level_index: 2,
        low_level_index: 0,
        has_relation: true,
        relation_type: 'implementation',
        confidence: 0.95,
        summary: '导入银行流水功能由解析模块直接实现'
      },
      // L2[0] 导入银行流水 -> low[1] 智能匹配
      {
        high_level_index: 2,
        low_level_index: 1,
        has_relation: true,
        relation_type: 'support',
        confidence: 0.78,
        summary: '导入后的数据需要智能匹配处理'
      },
      // L2[1] 高亮显示 -> low[2] 差异标记
      {
        high_level_index: 3,
        low_level_index: 2,
        has_relation: true,
        relation_type: 'implementation',
        confidence: 0.97,
        summary: '高亮显示需求由差异标记功能直接实现'
      },
      // L3[0] 性能要求 -> low[3] 批量处理
      {
        high_level_index: 4,
        low_level_index: 3,
        has_relation: true,
        relation_type: 'implementation',
        confidence: 0.88,
        summary: '性能要求通过批量处理技术满足'
      },
      // L3[1] Excel/CSV导入 -> low[0] 银行流水解析
      {
        high_level_index: 5,
        low_level_index: 0,
        has_relation: true,
        relation_type: 'support',
        confidence: 0.72,
        summary: '格式支持需求与解析模块相关'
      },
      // L1[0] 自动对账 -> low[0] 银行流水解析
      {
        high_level_index: 0,
        low_level_index: 0,
        has_relation: true,
        relation_type: 'dependency',
        confidence: 0.85,
        summary: '自动对账依赖银行流水解析'
      },
      // L1[0] 自动对账 -> low[2] 差异标记
      {
        high_level_index: 0,
        low_level_index: 2,
        has_relation: true,
        relation_type: 'support',
        confidence: 0.70,
        summary: '对账结果需要差异标记展示'
      }
    ],
    relation_types_count: {
      implementation: 3,
      decomposition: 1,
      support: 3,
      dependency: 1
    }
  }

  // 模拟冲突检测结果
  const allMockReqs = [
    ...result.value.business_requirements.map((r, i) => ({ ...r, id: `L1-${i}`, category: 'L1' })),
    ...result.value.stakeholder_requirements.map((r, i) => ({ ...r, id: `L2-${i}`, category: 'L2' })),
    ...result.value.system_requirements.map((r, i) => ({ ...r, id: `L3-${i}`, category: 'L3' })),
    ...lowLevelRequirements.value
  ]

  conflictResults.value = [
    {
      reqA: allMockReqs[0], // 自动对账
      reqB: allMockReqs[1], // 下月底上线
      is_conflict: false,
      raw_response: '不冲突。这两个需求分别描述功能目标和时间约束，属于不同维度，可以同时满足。'
    },
    {
      reqA: allMockReqs[4], // 1万条数据1分钟
      reqB: allMockReqs[9], // 批量处理
      is_conflict: false,
      raw_response: '不冲突。底层需求"批量处理"正是为了满足顶层性能需求而设计的实现方案。'
    },
    {
      reqA: allMockReqs[1], // 下月底上线
      reqB: allMockReqs[6], // 银行流水解析
      is_conflict: true,
      raw_response: '冲突。下月底上线的紧迫时间约束可能与实现复杂的银行流水解析模块存在冲突，需要评估开发工期。'
    },
    {
      reqA: allMockReqs[2], // 导入银行流水自动匹配
      reqB: allMockReqs[3], // 高亮显示
      is_conflict: false,
      raw_response: '不冲突。这两个需求描述的是同一业务流程的不同阶段：先匹配，匹配失败后高亮显示。'
    }
  ]

  // 模拟分类结果
  classificationResult.value = {
    total: allMockReqs.length,
    predictions: [
      { index: 0, requirement: allMockReqs[0].statement, predicted_label: '功能性需求', originalReq: allMockReqs[0] },
      { index: 1, requirement: allMockReqs[1].statement, predicted_label: '非功能性需求', originalReq: allMockReqs[1] },
      { index: 2, requirement: allMockReqs[2].statement, predicted_label: '功能性需求', originalReq: allMockReqs[2] },
      { index: 3, requirement: allMockReqs[3].statement, predicted_label: '功能性需求', originalReq: allMockReqs[3] },
      { index: 4, requirement: allMockReqs[4].statement, predicted_label: '非功能性需求', originalReq: allMockReqs[4] },
      { index: 5, requirement: allMockReqs[5].statement, predicted_label: '功能性需求', originalReq: allMockReqs[5] },
      { index: 6, requirement: allMockReqs[6].statement, predicted_label: '功能性需求', originalReq: allMockReqs[6] },
      { index: 7, requirement: allMockReqs[7].statement, predicted_label: '功能性需求', originalReq: allMockReqs[7] },
      { index: 8, requirement: allMockReqs[8].statement, predicted_label: '功能性需求', originalReq: allMockReqs[8] },
      { index: 9, requirement: allMockReqs[9].statement, predicted_label: '非功能性需求', originalReq: allMockReqs[9] }
    ],
    label_distribution: {
      '功能性需求': 7,
      '非功能性需求': 3
    }
  }

  currentStep.value = 4
  activeTab.value = 'network'

  // 延迟更新图表
  setTimeout(() => {
    if (chart) {
      updateChart()
    } else {
      initChart()
    }
  }, 100)
}

// 追溯分析
async function runTraceAnalysis() {
  if (!canTrace.value) return

  isTracingLoading.value = true
  traceError.value = null
  traceResult.value = null

  try {
    // 过滤空值并确保所有项都是字符串
    const highReqs = allHighLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())
    const lowReqs = lowLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())

    console.log('[Trace] highReqs:', highReqs)
    console.log('[Trace] lowReqs:', lowReqs)

    if (highReqs.length === 0 || lowReqs.length === 0) {
      throw new Error('顶层需求或底层需求为空，请先完成需求抽取和底层需求加载')
    }

    const apiResult = await traceabilityApi.batchAnalyzeRelation(highReqs, lowReqs)
    console.log('[Trace] API result:', apiResult)
    traceResult.value = apiResult
    currentStep.value = 2
    activeTab.value = 'network'
    updateChart()
  } catch (err) {
    console.error('[Trace] Error:', err)
    const errMsg = err?.response?.data?.error || err?.response?.data?.detail || err.message || '追溯分析失败'
    traceError.value = errMsg
  } finally {
    isTracingLoading.value = false
  }
}

// 冲突检测 - 检测所有需求两两之间是否存在冲突
async function runConflictDetection() {
  const allReqs = [
    ...allHighLevelRequirements.value.map((r) => ({ ...r, type: 'high' })),
    ...lowLevelRequirements.value.map((r) => ({ ...r, type: 'low' }))
  ]

  if (allReqs.length < 2) {
    conflictError.value = '需要至少两条需求才能进行冲突检测'
    return
  }

  isDetectingConflict.value = true
  conflictError.value = null
  conflictResults.value = []

  // 生成需要检测的需求对（避免重复：只检测 i < j）
  const pairs = []
  for (let i = 0; i < allReqs.length; i++) {
    for (let j = i + 1; j < allReqs.length; j++) {
      pairs.push({ reqA: allReqs[i], reqB: allReqs[j], indexA: i, indexB: j })
    }
  }

  conflictProgress.value = { current: 0, total: pairs.length }

  try {
    const results = []
    for (const pair of pairs) {
      try {
        const response = await conflictApi.check(pair.reqA.statement, pair.reqB.statement)
        const data = response.data ?? response
        results.push({
          reqA: pair.reqA,
          reqB: pair.reqB,
          is_conflict: data.is_conflict,
          raw_response: data.raw_response
        })
      } catch (e) {
        results.push({
          reqA: pair.reqA,
          reqB: pair.reqB,
          is_conflict: false,
          raw_response: `检测失败: ${e.message}`,
          error: true
        })
      }
      conflictProgress.value.current++
    }

    conflictResults.value = results
    currentStep.value = 3
    activeTab.value = 'conflict'
  } catch (err) {
    conflictError.value = err.message || '冲突检测失败'
  } finally {
    isDetectingConflict.value = false
  }
}

// 计算冲突统计
const conflictStats = computed(() => {
  if (!conflictResults.value.length) return null
  const conflicts = conflictResults.value.filter((r) => r.is_conflict)
  return {
    total: conflictResults.value.length,
    conflicts: conflicts.length,
    compatible: conflictResults.value.length - conflicts.length
  }
})

// 需求分类 - 对所有需求进行功能/非功能分类
async function runClassification() {
  const allReqs = [
    ...allHighLevelRequirements.value,
    ...lowLevelRequirements.value
  ]

  if (allReqs.length === 0) {
    classificationError.value = '没有需求可供分类'
    return
  }

  isClassifying.value = true
  classificationError.value = null
  classificationResult.value = null

  try {
    const requirements = allReqs.map((r) => r.statement)
    const response = await classifyTexts({ requirements })
    const data = response.data
    
    // 将分类结果与原始需求关联
    classificationResult.value = {
      predictions: data.predictions.map((pred, idx) => ({
        ...pred,
        originalReq: allReqs[idx]
      })),
      label_distribution: data.label_distribution,
      total: data.total
    }
    
    currentStep.value = 4
    activeTab.value = 'classification'
  } catch (err) {
    classificationError.value = err.message || '需求分类失败'
  } finally {
    isClassifying.value = false
  }
}

// ========== 一键分析（追溯 → 冲突 → 分类） ==========
async function runFullAnalysis() {
  if (!canTrace.value) {
    analysisError.value = '请先完成需求获取并加载底层需求'
    return
  }

  isAnalyzing.value = true
  analysisError.value = null
  analysisStep.value = 1

  try {
    // Step 1: 追溯分析
    traceError.value = null
    traceResult.value = null
    
    const highReqs = allHighLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())
    const lowReqs = lowLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())

    if (highReqs.length === 0 || lowReqs.length === 0) {
      throw new Error('顶层需求或底层需求为空')
    }

    const traceApiResult = await traceabilityApi.batchAnalyzeRelation(highReqs, lowReqs)
    traceResult.value = traceApiResult
    currentStep.value = 2

    // Step 2: 冲突检测
    analysisStep.value = 2
    conflictError.value = null
    conflictResults.value = []

    const allReqs = [
      ...allHighLevelRequirements.value.map((r) => ({ ...r, type: 'high' })),
      ...lowLevelRequirements.value.map((r) => ({ ...r, type: 'low' }))
    ]

    if (allReqs.length >= 2) {
      // 选择关键对进行冲突检测（避免组合爆炸）
      const pairs = []
      // 优先检测有追溯关系的对
      if (traceResult.value?.relations) {
        traceResult.value.relations.forEach((rel) => {
          if (rel.has_relation) {
            const highReq = allHighLevelRequirements.value[rel.high_level_index]
            const lowReq = lowLevelRequirements.value[rel.low_level_index]
            if (highReq && lowReq) {
              pairs.push({ reqA: highReq, reqB: lowReq })
            }
          }
        })
      }
      // 限制最多检测10对
      const pairsToCheck = pairs.slice(0, 10)
      conflictProgress.value = { current: 0, total: pairsToCheck.length }

      for (let i = 0; i < pairsToCheck.length; i++) {
        const { reqA, reqB } = pairsToCheck[i]
        conflictProgress.value.current = i + 1
        try {
          const res = await conflictApi.check(
            reqA.statement || reqA.text || '',
            reqB.statement || reqB.text || ''
          )
          conflictResults.value.push({ reqA, reqB, ...res })
        } catch (e) {
          console.warn('冲突检测单对失败:', e)
        }
      }
      currentStep.value = 3
    }

    // Step 3: 需求分类
    analysisStep.value = 3
    classificationError.value = null
    classificationResult.value = null

    const classifyReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]
    if (classifyReqs.length > 0) {
      const requirements = classifyReqs.map((r) => r.statement || r.text || '')
      const response = await classifyTexts({ requirements })
      const data = response.data
      
      classificationResult.value = {
        predictions: data.predictions.map((pred, idx) => ({
          ...pred,
          originalReq: classifyReqs[idx]
        })),
        label_distribution: data.label_distribution,
        total: data.total
      }
      currentStep.value = 4
    }

    // 完成
    analysisStep.value = 4
    activeTab.value = 'network'
    setTimeout(() => updateChart(), 100)
  } catch (err) {
    console.error('[FullAnalysis] Error:', err)
    analysisError.value = err?.response?.data?.error || err?.response?.data?.detail || err.message || '分析失败'
  } finally {
    isAnalyzing.value = false
  }
}

// 分析步骤文本
const analysisStepText = computed(() => {
  switch (analysisStep.value) {
    case 1: return '正在进行追溯分析...'
    case 2: return `正在进行冲突检测 (${conflictProgress.value.current}/${conflictProgress.value.total})...`
    case 3: return '正在进行需求分类...'
    case 4: return '分析完成!'
    default: return ''
  }
})

// 分析进度百分比
const analysisPercent = computed(() => {
  if (analysisStep.value === 0) return 0
  if (analysisStep.value === 4) return 100
  // 追溯 33%, 冲突 66%, 分类 100%
  const basePercent = (analysisStep.value - 1) * 33
  if (analysisStep.value === 2 && conflictProgress.value.total > 0) {
    return basePercent + Math.round((conflictProgress.value.current / conflictProgress.value.total) * 33)
  }
  return basePercent + 16 // 进行中显示中间值
})

// 分类结果按标签分组
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

// 是否可以进行冲突检测
const canDetectConflict = computed(() => {
  return traceResult.value !== null
})

// 是否可以进行分类
const canClassify = computed(() => {
  return conflictResults.value.length > 0 || traceResult.value !== null
})

// ========== 图表相关 ==========
function initChart() {
  if (!chartContainer.value) return
  if (chart) {
    chart.dispose()
  }
  chart = echarts.init(chartContainer.value)
  updateChart()
}

function updateChart() {
  if (!chart) return

  // 如果没有追溯结果，显示空状态
  if (!traceResult.value) {
    const emptyOption = {
      title: {
        text: '追溯网络',
        subtext: '完成需求获取和底层需求提取后，点击"追溯分析"生成网络图',
        left: 'center',
        top: 'center',
        textStyle: { color: '#a1a1aa', fontSize: 16 },
        subtextStyle: { color: '#d4d4d8', fontSize: 12 }
      }
    }
    chart.setOption(emptyOption, true)
    return
  }

  // 二部图布局：左边顶层需求，右边底层需求
  const highNodes = allHighLevelRequirements.value
  const lowNodes = lowLevelRequirements.value

  // 获取图表容器尺寸
  const containerWidth = chartContainer.value?.clientWidth || 900
  const containerHeight = chartContainer.value?.clientHeight || 500

  // 布局参数
  const leftX = containerWidth * 0.18   // 左侧 18% 位置
  const rightX = containerWidth * 0.82  // 右侧 82% 位置
  const topPadding = 80
  const bottomPadding = 60
  const availableHeight = containerHeight - topPadding - bottomPadding

  const categories = [
    { name: 'L1 业务需求', itemStyle: { color: '#3b82f6' } },
    { name: 'L2 利益相关者需求', itemStyle: { color: '#8b5cf6' } },
    { name: 'L3 系统需求', itemStyle: { color: '#f59e0b' } },
    { name: '底层需求', itemStyle: { color: '#10b981' } }
  ]

  const categoryMap = { L1: 0, L2: 1, L3: 2, low: 3 }

  // 计算左侧顶层需求节点位置（垂直均匀分布）
  const leftSpacing = highNodes.length > 1 ? availableHeight / (highNodes.length - 1) : 0
  const nodes = highNodes.map((req, idx) => ({
    id: `high_${idx}`,
    name: req.statement.length > 25 ? req.statement.slice(0, 25) + '...' : req.statement,
    x: leftX,
    y: topPadding + (highNodes.length === 1 ? availableHeight / 2 : idx * leftSpacing),
    category: categoryMap[req.category] ?? 0,
    symbol: 'roundRect',
    symbolSize: [200, 32],
    itemStyle: {
      color: getCategoryColor(req.category),
      borderColor: getCategoryBorderColor(req.category),
      borderWidth: 2,
      borderRadius: 4
    },
    label: {
      show: true,
      position: 'inside',
      fontSize: 11,
      color: '#fff',
      fontWeight: 500,
      formatter: () => {
        const text = req.statement
        return text.length > 22 ? text.slice(0, 22) + '...' : text
      }
    },
    tooltip: {
      formatter: `<div style="max-width:350px; padding: 8px;">
        <div style="font-weight: bold; color: ${getCategoryColor(req.category)}; margin-bottom: 4px;">[${req.category}] 顶层需求</div>
        <div>${req.statement}</div>
      </div>`
    }
  }))

  // 计算右侧底层需求节点位置（垂直均匀分布）
  const rightSpacing = lowNodes.length > 1 ? availableHeight / (lowNodes.length - 1) : 0
  lowNodes.forEach((req, idx) => {
    nodes.push({
      id: `low_${idx}`,
      name: req.statement.length > 25 ? req.statement.slice(0, 25) + '...' : req.statement,
      x: rightX,
      y: topPadding + (lowNodes.length === 1 ? availableHeight / 2 : idx * rightSpacing),
      category: 3,
      symbol: 'roundRect',
      symbolSize: [200, 32],
      itemStyle: {
        color: '#10b981',
        borderColor: '#047857',
        borderWidth: 2,
        borderRadius: 4
      },
      label: {
        show: true,
        position: 'inside',
        fontSize: 11,
        color: '#fff',
        fontWeight: 500,
        formatter: () => {
          const text = req.statement
          return text.length > 22 ? text.slice(0, 22) + '...' : text
        }
      },
      tooltip: {
        formatter: `<div style="max-width:350px; padding: 8px;">
          <div style="font-weight: bold; color: #10b981; margin-bottom: 4px;">底层需求</div>
          <div>${req.statement}</div>
        </div>`
      }
    })
  })

  // 从追溯结果添加边
  const links = []
  if (traceResult.value?.relations) {
    traceResult.value.relations.forEach((rel) => {
      if (rel.has_relation) {
        links.push({
          source: `high_${rel.high_level_index}`,
          target: `low_${rel.low_level_index}`,
          lineStyle: {
            color: getRelationTypeColor(rel.relation_type),
            width: 2 + (rel.confidence || 0.5) * 2,
            curveness: 0.1
          },
          label: {
            show: true,
            formatter: getRelationTypeLabel(rel.relation_type),
            fontSize: 9,
            color: '#666',
            backgroundColor: 'rgba(255,255,255,0.9)',
            padding: [2, 6],
            borderRadius: 3
          }
        })
      }
    })
  }

  const option = {
    title: {
      text: '需求追溯关系图（二部图）',
      subtext: `左侧: ${highNodes.length} 个顶层需求 ─→ 右侧: ${lowNodes.length} 个底层需求`,
      left: 'center',
      top: 8,
      textStyle: { fontSize: 14, fontWeight: 'bold', color: '#374151' },
      subtextStyle: { fontSize: 11, color: '#9ca3af' }
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      textStyle: { color: '#374151' },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.15);'
    },
    legend: {
      bottom: 8,
      left: 'center',
      data: categories.map((c) => c.name),
      textStyle: { fontSize: 11 }
    },
    series: [
      {
        type: 'graph',
        layout: 'none',  // 使用固定位置布局（二部图）
        coordinateSystem: null,
        roam: true,
        categories: categories,
        data: nodes,
        links: links,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 10],
        lineStyle: { opacity: 0.85 },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 5 },
          itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0, 0, 0, 0.25)' }
        }
      }
    ]
  }

  chart.setOption(option, true)
}

// 获取类别边框颜色
function getCategoryBorderColor(category) {
  const colors = {
    L1: '#1d4ed8',
    L2: '#6d28d9',
    L3: '#d97706',
    low: '#047857'
  }
  return colors[category] || '#374151'
}

// 分类标签样式辅助函数
function getLabelClass(label) {
  const styles = {
    '功能性需求': 'bg-blue-50 text-blue-700',
    '非功能性需求': 'bg-purple-50 text-purple-700'
  }
  return styles[label] || 'bg-zinc-50 text-zinc-700'
}

function getLabelDotClass(label) {
  const styles = {
    '功能性需求': 'bg-blue-500',
    '非功能性需求': 'bg-purple-500'
  }
  return styles[label] || 'bg-zinc-500'
}

function getLabelHeaderClass(label) {
  const styles = {
    '功能性需求': 'bg-blue-50 border-blue-100',
    '非功能性需求': 'bg-purple-50 border-purple-100'
  }
  return styles[label] || 'bg-zinc-50 border-zinc-100'
}

function getLabelBadgeClass(label) {
  const styles = {
    '功能性需求': 'bg-blue-100 text-blue-700',
    '非功能性需求': 'bg-purple-100 text-purple-700'
  }
  return styles[label] || 'bg-zinc-100 text-zinc-700'
}

// ========== 生命周期 ==========
watch(activeTab, (val) => {
  if (val === 'network') {
    setTimeout(() => {
      initChart()
    }, 100)
  }
})

watch(
  () => [traceResult.value, allHighLevelRequirements.value, lowLevelRequirements.value],
  () => {
    if (activeTab.value === 'network' && chart) {
      updateChart()
    }
  },
  { deep: true }
)
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 overflow-hidden">
    <!-- Header -->
    <header
      class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between shrink-0"
    >
      <div>
        <h2 class="text-xl font-semibold text-zinc-900 flex items-center gap-2">
          <Network class="w-5 h-5 text-black" />
          需求获取与追溯
        </h2>
        <p class="text-sm text-zinc-500 mt-1">
          从原始文本抽取需求，建立顶层与底层需求间的追溯关系
        </p>
      </div>

      <!-- 步骤指示器 -->
      <div class="flex items-center gap-2">
        <div
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all"
          :class="currentStep >= 1 ? 'bg-black text-white' : 'bg-zinc-100 text-zinc-500'"
        >
          <span class="w-4 h-4 rounded-full flex items-center justify-center text-[10px]"
            :class="currentStep >= 1 ? 'bg-white text-black' : 'bg-zinc-300 text-zinc-600'">1</span>
          获取
        </div>
        <ArrowRight class="w-3 h-3 text-zinc-300" />
        <div
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all"
          :class="currentStep >= 2 ? 'bg-blue-600 text-white' : 'bg-zinc-100 text-zinc-500'"
        >
          <span class="w-4 h-4 rounded-full flex items-center justify-center text-[10px]"
            :class="currentStep >= 2 ? 'bg-white text-blue-600' : 'bg-zinc-300 text-zinc-600'">2</span>
          追溯
        </div>
        <ArrowRight class="w-3 h-3 text-zinc-300" />
        <div
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all"
          :class="currentStep >= 3 ? 'bg-amber-500 text-white' : 'bg-zinc-100 text-zinc-500'"
        >
          <span class="w-4 h-4 rounded-full flex items-center justify-center text-[10px]"
            :class="currentStep >= 3 ? 'bg-white text-amber-600' : 'bg-zinc-300 text-zinc-600'">3</span>
          冲突
        </div>
        <ArrowRight class="w-3 h-3 text-zinc-300" />
        <div
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all"
          :class="currentStep >= 4 ? 'bg-emerald-600 text-white' : 'bg-zinc-100 text-zinc-500'"
        >
          <span class="w-4 h-4 rounded-full flex items-center justify-center text-[10px]"
            :class="currentStep >= 4 ? 'bg-white text-emerald-600' : 'bg-zinc-300 text-zinc-600'">4</span>
          分类
        </div>
      </div>
    </header>

    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧：输入面板 -->
      <div
        class="w-[360px] p-6 flex flex-col border-r border-zinc-200 bg-white min-w-[320px] shrink-0"
      >
        <label class="text-sm font-medium text-zinc-700 mb-2"
          >原始输入文本 (笔记、访谈记录)</label
        >
        <textarea
          v-model="inputText"
          class="flex-1 w-full p-4 rounded-lg border border-zinc-300 resize-none focus:ring-2 focus:ring-black focus:border-black transition-all text-sm leading-relaxed"
          placeholder="在此粘贴原始会议纪要、访谈记录或粗略描述..."
        ></textarea>

        <div class="mt-4 flex flex-col gap-3">
          <!-- 模型设置 -->
          <details class="group">
            <summary
              class="flex items-center justify-between cursor-pointer p-3 bg-zinc-50 rounded-lg border border-zinc-200 hover:bg-zinc-100 transition-colors"
            >
              <div class="flex items-center gap-2">
                <Settings2 class="w-4 h-4 text-zinc-500" />
                <span class="text-xs font-semibold text-zinc-600 uppercase tracking-wider"
                  >模型设置</span
                >
              </div>
              <ChevronDown
                class="w-4 h-4 text-zinc-400 transition-transform group-open:rotate-180"
              />
            </summary>
            <div class="mt-2 p-3 bg-zinc-50 rounded-lg border border-zinc-200 space-y-3">
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1"
                  >推理模型 (抽取)</label
                >
                <select
                  v-model="extractModel"
                  class="w-full text-sm border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="deepseek-reasoner">deepseek-reasoner</option>
                  <option value="deepseek-chat">deepseek-chat</option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1"
                  >聊天模型 (清洗)</label
                >
                <select
                  v-model="cleanModel"
                  class="w-full text-sm border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="deepseek-chat">deepseek-chat</option>
                  <option value="deepseek-reasoner">deepseek-reasoner</option>
                </select>
              </div>
            </div>
          </details>

          <!-- 错误提示 -->
          <div
            v-if="error"
            class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200"
          >
            Error: {{ error }}
          </div>

          <!-- 进度条 -->
          <div
            v-if="isLoading"
            class="p-3 bg-zinc-50 rounded-md border border-zinc-200 space-y-2"
          >
            <div class="flex items-center justify-between text-xs text-zinc-500">
              <span>清洗 & 润色</span>
              <span>{{ progress.clean.current }}/{{ progress.clean.total }}</span>
            </div>
            <div class="h-2 bg-zinc-200 rounded">
              <div
                class="h-2 bg-black rounded transition-all"
                :style="{ width: `${cleanPercent}%` }"
              ></div>
            </div>
            <div class="flex items-center justify-between text-xs text-zinc-500 mt-2">
              <span>抽取</span>
              <span>{{ progress.extract.current }}/{{ progress.extract.total }}</span>
            </div>
            <div class="h-2 bg-zinc-200 rounded">
              <div
                class="h-2 bg-amber-500 rounded transition-all"
                :style="{ width: `${extractPercent}%` }"
              ></div>
            </div>
          </div>

          <!-- 操作按钮组 -->
          <button
            @click="analyzeRequirements"
            :disabled="isLoading || !inputText"
            class="w-full py-2.5 px-4 bg-black hover:bg-zinc-800 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isLoading" class="w-4 h-4 animate-spin" />
            <FileText v-else class="w-4 h-4" />
            <span>{{ isLoading ? '分析中...' : '分析 & 抽取' }}</span>
          </button>

          <button
            @click="extractLowLevelRequirements"
            :disabled="!result || isExtractingLowLevel"
            class="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isExtractingLowLevel" class="w-4 h-4 animate-spin" />
            <Lock v-else class="w-4 h-4" />
            <span>{{ isExtractingLowLevel ? '提取中...' : '提取底层需求' }}</span>
            <span class="text-xs opacity-70">(预留)</span>
          </button>

          <!-- 测试用：加载示例底层需求 -->
          <button
            @click="loadMockLowLevelRequirements"
            :disabled="!result"
            class="w-full py-2 px-4 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors border border-zinc-300 border-dashed text-sm"
          >
            <Layers class="w-4 h-4" />
            <span>加载示例底层需求</span>
            <span class="text-xs text-zinc-500">(测试用)</span>
          </button>

          <!-- 完整模拟数据（离线测试） -->
          <button
            @click="loadFullMockData"
            class="w-full py-2.5 px-4 bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 text-white font-medium rounded-lg flex items-center justify-center gap-2 transition-all shadow-sm text-sm"
          >
            <Network class="w-4 h-4" />
            <span>一键加载完整模拟数据</span>
            <span class="text-xs opacity-80">(离线验证)</span>
          </button>

          <!-- 一键分析按钮 -->
          <button
            @click="runFullAnalysis"
            :disabled="!canTrace || isAnalyzing"
            class="w-full py-3 px-4 bg-gradient-to-r from-blue-600 via-amber-500 to-emerald-500 hover:from-blue-700 hover:via-amber-600 hover:to-emerald-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md text-base"
          >
            <Loader2 v-if="isAnalyzing" class="w-5 h-5 animate-spin" />
            <BarChart3 v-else class="w-5 h-5" />
            <span>{{ isAnalyzing ? '分析中...' : '一键分析 (追溯→冲突→分类)' }}</span>
          </button>

          <!-- 一键分析进度条 -->
          <div
            v-if="isAnalyzing || analysisStep === 4"
            class="p-4 bg-gradient-to-r from-blue-50 via-amber-50 to-emerald-50 rounded-lg border border-zinc-200 space-y-3"
          >
            <!-- 进度条 -->
            <div class="h-3 bg-zinc-200 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-500 ease-out"
                :class="{
                  'bg-blue-500': analysisStep === 1,
                  'bg-amber-500': analysisStep === 2,
                  'bg-emerald-500': analysisStep >= 3
                }"
                :style="{ width: `${analysisPercent}%` }"
              ></div>
            </div>
            
            <!-- 步骤指示 -->
            <div class="flex justify-between text-xs">
              <div class="flex items-center gap-1.5" :class="analysisStep >= 1 ? 'text-blue-600 font-medium' : 'text-zinc-400'">
                <div class="w-5 h-5 rounded-full flex items-center justify-center text-[10px]" 
                     :class="analysisStep >= 1 ? 'bg-blue-500 text-white' : 'bg-zinc-200 text-zinc-500'">
                  <CheckCircle2 v-if="analysisStep > 1" class="w-3 h-3" />
                  <span v-else>1</span>
                </div>
                <span>追溯</span>
              </div>
              <div class="flex items-center gap-1.5" :class="analysisStep >= 2 ? 'text-amber-600 font-medium' : 'text-zinc-400'">
                <div class="w-5 h-5 rounded-full flex items-center justify-center text-[10px]" 
                     :class="analysisStep >= 2 ? 'bg-amber-500 text-white' : 'bg-zinc-200 text-zinc-500'">
                  <CheckCircle2 v-if="analysisStep > 2" class="w-3 h-3" />
                  <span v-else>2</span>
                </div>
                <span>冲突</span>
              </div>
              <div class="flex items-center gap-1.5" :class="analysisStep >= 3 ? 'text-emerald-600 font-medium' : 'text-zinc-400'">
                <div class="w-5 h-5 rounded-full flex items-center justify-center text-[10px]" 
                     :class="analysisStep >= 3 ? 'bg-emerald-500 text-white' : 'bg-zinc-200 text-zinc-500'">
                  <CheckCircle2 v-if="analysisStep > 3" class="w-3 h-3" />
                  <span v-else>3</span>
                </div>
                <span>分类</span>
              </div>
            </div>
            
            <!-- 当前状态文本 -->
            <div class="text-center text-sm font-medium" :class="{
              'text-blue-600': analysisStep === 1,
              'text-amber-600': analysisStep === 2,
              'text-emerald-600': analysisStep >= 3
            }">
              {{ analysisStepText }}
            </div>
          </div>

          <!-- 错误提示 -->
          <div
            v-if="analysisError"
            class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200"
          >
            分析错误: {{ analysisError }}
          </div>

          <!-- 统计信息 -->
          <div
            v-if="result"
            class="p-3 bg-zinc-50 rounded-lg border border-zinc-200 text-xs text-zinc-600 space-y-1"
          >
            <div class="flex justify-between">
              <span>顶层需求</span>
              <span class="font-semibold">{{ allHighLevelRequirements.length }}</span>
            </div>
            <div class="flex justify-between">
              <span>底层需求</span>
              <span class="font-semibold">{{ lowLevelRequirements.length }}</span>
            </div>
            <div v-if="traceResult" class="flex justify-between">
              <span>追溯关系</span>
              <span class="font-semibold text-blue-600">{{
                traceResult.statistics?.relations_found || 0
              }}</span>
            </div>
            <div v-if="conflictStats" class="flex justify-between">
              <span>冲突对数</span>
              <span class="font-semibold" :class="conflictStats.conflicts > 0 ? 'text-red-600' : 'text-green-600'">
                {{ conflictStats.conflicts }} / {{ conflictStats.total }}
              </span>
            </div>
            <div v-if="classificationResult" class="flex justify-between">
              <span>已分类</span>
              <span class="font-semibold text-emerald-600">{{ classificationResult.total }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：输出面板 -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- Tab 切换 -->
        <div class="bg-white border-b border-zinc-200 px-6 py-2 flex gap-1 shrink-0">
          <button
            @click="activeTab = 'board'"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
            :class="activeTab === 'board' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
          >
            <Layers class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
            看板
          </button>
          <button
            @click="activeTab = 'network'"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
            :class="activeTab === 'network' ? 'bg-blue-600 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
          >
            <Network class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
            追溯
          </button>
          <button
            @click="activeTab = 'conflict'"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
            :class="activeTab === 'conflict' ? 'bg-amber-500 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
          >
            <AlertTriangle class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
            冲突
            <span v-if="conflictStats && conflictStats.conflicts > 0" class="ml-1 px-1.5 py-0.5 bg-red-100 text-red-700 rounded-full text-xs">
              {{ conflictStats.conflicts }}
            </span>
          </button>
          <button
            @click="activeTab = 'classification'"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
            :class="activeTab === 'classification' ? 'bg-emerald-600 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
          >
            <Tags class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
            分类
          </button>
        </div>

        <!-- 看板视图 -->
        <div v-show="activeTab === 'board'" class="flex-1 overflow-x-auto bg-zinc-50 p-6">
          <div v-if="!result && !isLoading" class="h-full flex flex-col items-center justify-center text-zinc-400">
            <FileText class="w-12 h-12 mb-3 opacity-20" />
            <p>需求工件将显示在此处</p>
          </div>

          <div v-if="isLoading" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-black mb-4" />
            <p>正在清洗文本、润色语义并抽取需求...</p>
          </div>

          <!-- 看板 -->
          <div v-if="result" class="grid grid-cols-4 gap-4 h-full min-w-[1200px]">
            <div
              v-for="column in boardColumns"
              :key="column.id"
              class="flex flex-col rounded-xl border bg-zinc-100/80 shadow-sm overflow-hidden h-full"
            >
              <div
                class="px-4 py-3 border-b flex items-center justify-between gap-2"
                :class="column.headerClass"
              >
                <div class="flex items-center gap-2">
                  <component :is="column.icon" class="w-4 h-4" :class="column.iconClass" />
                  <h3 class="font-semibold text-zinc-800 text-sm">{{ column.title }}</h3>
                </div>
                <span
                  class="text-[11px] font-semibold px-2 py-0.5 rounded-full border"
                  :class="column.badgeClass"
                >
                  {{ column.items.length }}
                </span>
              </div>
              <div class="flex-1 overflow-y-auto p-3 custom-scrollbar">
                <div class="flex flex-col gap-3">
                  <template v-if="column.items.length > 0">
                    <div
                      v-for="card in column.items"
                      :key="card.id"
                      class="p-3 rounded-lg border border-zinc-200 bg-white shadow-sm hover:shadow-md transition-all"
                    >
                      <p class="text-zinc-900 font-medium text-sm mb-2">{{ card.statement }}</p>
                      <div v-if="card.rationale" class="text-xs text-zinc-500 mb-2">
                        <span class="font-semibold">Rationale:</span> {{ card.rationale }}
                      </div>
                      <div
                        class="flex items-center justify-between mt-2 pt-2 border-t border-zinc-100"
                      >
                        <div
                          v-if="card.evidence"
                          class="flex items-center gap-1 text-xs text-zinc-400 max-w-[70%] truncate"
                          :title="card.evidence"
                        >
                          <Quote class="w-3 h-3 shrink-0" />
                          <span class="truncate">"{{ card.evidence }}"</span>
                        </div>
                        <span
                          v-if="card.confidence !== undefined"
                          class="text-[10px] px-1.5 py-0.5 rounded-full border"
                          :class="getConfidenceColor(card.confidence)"
                        >
                          {{ (card.confidence * 100).toFixed(0) }}%
                        </span>
                      </div>
                    </div>
                  </template>
                  <div
                    v-else
                    class="text-sm text-zinc-400 text-center py-8 border border-dashed border-zinc-200 rounded-lg bg-zinc-50/70"
                  >
                    {{ column.id === 'low' ? '点击"提取底层需求"生成' : '暂无需求' }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 追溯网络视图 -->
        <div v-show="activeTab === 'network'" class="flex-1 p-6 bg-zinc-50">
          <div
            ref="chartContainer"
            class="w-full h-full bg-white rounded-xl border border-zinc-200 shadow-sm"
          ></div>
        </div>

        <!-- 冲突检测视图 -->
        <div v-show="activeTab === 'conflict'" class="flex-1 overflow-y-auto bg-zinc-50 p-6">
          <div v-if="!conflictResults.length && !isDetectingConflict" class="h-full flex flex-col items-center justify-center text-zinc-400">
            <AlertTriangle class="w-12 h-12 mb-3 opacity-20" />
            <p>完成追溯分析后，点击"冲突检测"检查需求冲突</p>
          </div>

          <div v-if="isDetectingConflict" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-amber-500 mb-4" />
            <p>正在检测需求冲突... ({{ conflictProgress.current }}/{{ conflictProgress.total }})</p>
          </div>

          <div v-if="conflictResults.length" class="space-y-4">
            <!-- 冲突统计摘要 -->
            <div class="flex items-center gap-4 p-4 bg-white rounded-xl border border-zinc-200 shadow-sm">
              <div class="flex items-center gap-2">
                <span class="text-sm text-zinc-600">检测对数:</span>
                <span class="font-bold text-zinc-900">{{ conflictStats?.total || 0 }}</span>
              </div>
              <div class="flex items-center gap-2">
                <AlertCircle class="w-4 h-4 text-red-500" />
                <span class="text-sm text-zinc-600">冲突:</span>
                <span class="font-bold text-red-600">{{ conflictStats?.conflicts || 0 }}</span>
              </div>
              <div class="flex items-center gap-2">
                <CheckCircle2 class="w-4 h-4 text-green-500" />
                <span class="text-sm text-zinc-600">兼容:</span>
                <span class="font-bold text-green-600">{{ conflictStats?.compatible || 0 }}</span>
              </div>
            </div>

            <!-- 冲突列表 -->
            <div class="space-y-3">
              <div
                v-for="(item, idx) in conflictResults"
                :key="idx"
                class="p-4 rounded-xl border shadow-sm"
                :class="item.is_conflict ? 'bg-red-50 border-red-200' : 'bg-white border-zinc-200'"
              >
                <div class="flex items-start gap-3">
                  <div class="shrink-0 mt-1">
                    <AlertCircle v-if="item.is_conflict" class="w-5 h-5 text-red-500" />
                    <CheckCircle2 v-else class="w-5 h-5 text-green-500" />
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-2">
                      <span
                        class="px-2 py-0.5 rounded text-xs font-medium"
                        :class="item.is_conflict ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'"
                      >
                        {{ item.is_conflict ? '冲突' : '兼容' }}
                      </span>
                    </div>
                    <div class="grid grid-cols-2 gap-4 mb-3">
                      <div class="p-3 bg-white rounded-lg border border-zinc-200">
                        <div class="text-xs text-zinc-400 mb-1">需求 A [{{ item.reqA.category }}]</div>
                        <p class="text-sm text-zinc-800">{{ item.reqA.statement }}</p>
                      </div>
                      <div class="p-3 bg-white rounded-lg border border-zinc-200">
                        <div class="text-xs text-zinc-400 mb-1">需求 B [{{ item.reqB.category }}]</div>
                        <p class="text-sm text-zinc-800">{{ item.reqB.statement }}</p>
                      </div>
                    </div>
                    <div class="p-3 bg-zinc-50 rounded-lg text-sm text-zinc-600">
                      <span class="font-medium">分析结果：</span>{{ item.raw_response }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 需求分类视图 -->
        <div v-show="activeTab === 'classification'" class="flex-1 overflow-y-auto bg-zinc-50 p-6">
          <div v-if="!classificationResult && !isClassifying" class="h-full flex flex-col items-center justify-center text-zinc-400">
            <Tags class="w-12 h-12 mb-3 opacity-20" />
            <p>完成冲突检测后，点击"需求分类"进行功能/非功能分类</p>
          </div>

          <div v-if="isClassifying" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-emerald-500 mb-4" />
            <p>正在对需求进行分类...</p>
          </div>

          <div v-if="classificationResult" class="space-y-4">
            <!-- 分类统计摘要 -->
            <div class="flex flex-wrap items-center gap-3 p-4 bg-white rounded-xl border border-zinc-200 shadow-sm">
              <div class="flex items-center gap-2">
                <BarChart3 class="w-4 h-4 text-zinc-500" />
                <span class="text-sm text-zinc-600">总计:</span>
                <span class="font-bold text-zinc-900">{{ classificationResult.total }}</span>
              </div>
              <div
                v-for="([label, count]) in Object.entries(classificationResult.label_distribution || {})"
                :key="label"
                class="flex items-center gap-2 px-3 py-1 rounded-full text-sm"
                :class="getLabelClass(label)"
              >
                <span class="w-2 h-2 rounded-full" :class="getLabelDotClass(label)"></span>
                {{ label }}: {{ count }}
              </div>
            </div>

            <!-- 按分类分组显示 -->
            <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              <div
                v-for="([label, items]) in classificationGroups"
                :key="label"
                class="bg-white rounded-xl border border-zinc-200 shadow-sm overflow-hidden"
              >
                <div class="px-4 py-3 border-b flex items-center justify-between" :class="getLabelHeaderClass(label)">
                  <span class="font-semibold text-sm">{{ label }}</span>
                  <span class="text-xs px-2 py-0.5 rounded-full" :class="getLabelBadgeClass(label)">
                    {{ items.length }}
                  </span>
                </div>
                <div class="p-3 space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar">
                  <div
                    v-for="pred in items"
                    :key="pred.index"
                    class="p-3 rounded-lg border border-zinc-100 bg-zinc-50 hover:bg-zinc-100 transition-colors"
                  >
                    <p class="text-sm text-zinc-800 mb-1">{{ pred.requirement }}</p>
                    <div class="flex items-center gap-2 text-xs text-zinc-400">
                      <span v-if="pred.originalReq?.category" class="px-1.5 py-0.5 rounded bg-zinc-200 text-zinc-600">
                        {{ pred.originalReq.category }}
                      </span>
                      <span v-if="pred.originalReq?.confidence">
                        置信度: {{ (pred.originalReq.confidence * 100).toFixed(0) }}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #d4d4d8;
  border-radius: 20px;
}
</style>

