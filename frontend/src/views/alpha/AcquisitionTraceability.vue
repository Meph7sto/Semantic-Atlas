<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import {
  traceabilityApi,
  conflictApi,
  classifyTexts,
  analysisApi,
  requirementsL123Api,
  getLatestClassification,
  l4RequirementsApi,
} from '@/api/requirements'
import draggable from 'vuedraggable'
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
  BarChart3,
  RefreshCw,
  Play,
  Database,
  Table2,
  LayoutGrid,
  Search,
  Filter,
  GripVertical,
  Eye,
  EyeOff,
  ChevronUp,
  Circle,
  Clock,
  CheckCircle
} from 'lucide-vue-next'
import * as echarts from 'echarts'
import { getClassificationLabelStyle } from '@/utils/classificationLabelStyle'

// ========== 状态管理 ==========
const currentStep = ref(1) // 1: 需求获取, 2: 追溯分析, 3: 冲突检测, 4: 需求分类
const activeTab = ref('board') // 'board' | 'network' | 'conflict' | 'classification'

// Session 和 Context Run 相关状态
const sessionId = ref('')
const contextRunId = ref('')
const contextRuns = ref([])
const isLoadingRuns = ref(false)
const runsError = ref('')

// 需求获取相关状态 (从数据库加载)
const isLoading = ref(false)
const error = ref(null)
const highLevelRequirements = ref([]) // L1/L2/L3 需求
const reqStats = ref(null)

// 抽取参数
const extractionForm = ref({
  bundleStrategy: 'graph',
  anchorStrategy: 'informative',
  maxR: 2,
  adaptiveRetryR2: true,
  useToolcall: true,
  model: 'deepseek-v4-pro',
  useThinkingMode: true,
  l4Model: 'deepseek-v4-pro',
  l4UseThinkingMode: true,
  maxSpansPerBundle: 12,
  tokenLimit: 1500,
  topM2Hop: 5,
  keywords: '要,需要,必须,应该,决定,改成,提升,优化,实现'
})
const isExtracting = ref(false)
const extractionError = ref('')
const extractionResult = ref(null)

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
const analysisNotice = ref('')

// ========== 需求管理状态（表格视图+卡片视图） ==========
// 需求状态定义
const requirementStatuses = [
  { id: 'backlog', name: '待处理', color: 'zinc', icon: Circle },
  { id: 'in_progress', name: '进行中', color: 'blue', icon: Clock },
  { id: 'completed', name: '已完成', color: 'emerald', icon: CheckCircle }
]

// 为需求添加状态（响应式状态映射）
const requirementStatusMap = ref({}) // { reqId: 'backlog' | 'in_progress' | 'completed' }

// 表格视图配置
const tableSearchQuery = ref('')
const tableVisibleColumns = ref(['name', 'type', 'level', 'status', 'confidence', 'evidence'])
const tableSortKey = ref('name')
const tableSortOrder = ref('asc') // 'asc' | 'desc'
const availableTableColumns = [
  { key: 'name', label: '需求名称', width: 'flex-1 min-w-[300px]' },
  { key: 'type', label: '类型', width: 'w-28' },
  { key: 'level', label: '层级', width: 'w-20' },
  { key: 'status', label: '状态', width: 'w-28' },
  { key: 'confidence', label: '置信度', width: 'w-24' },
  { key: 'evidence', label: '证据', width: 'w-48' },
  { key: 'rationale', label: '原因', width: 'w-48' }
]
const showColumnSelector = ref(false)

// 图表相关
const chartContainer = ref(null)
let chart = null

// ========== 计算属性 ==========
const selectedRun = computed(() => {
  return contextRuns.value.find((run) => run.context_run_id === contextRunId.value) || null
})

const canLoadRequirements = computed(() => {
  return sessionId.value.trim().length > 0
})

const canExtract = computed(() => {
  if (isExtracting.value) return false
  if (!sessionId.value.trim()) return false
  if (extractionForm.value.bundleStrategy === 'graph' && !contextRunId.value.trim()) return false
  return true
})

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

// 所有顶层需求（L1 + L2 + L3）
const allHighLevelRequirements = computed(() => {
  return highLevelRequirements.value.map((req, idx) => {
    const level = normalizeLevel(req.level || req.category)
    return {
      ...req,
      id: req.req_id || req.id || `${level}-${idx}`,
      category: level,
      level,
      statement: req.text || req.statement || '',
      rationale: '',
      evidence: req.anchor_span_id || '',
      confidence: 0.9,
    }
  })
})

// 是否可以进行追溯分析
const canTrace = computed(() => {
  return allHighLevelRequirements.value.length > 0 && lowLevelRequirements.value.length > 0
})

// 所有需求（顶层+底层）合并
const allRequirements = computed(() => {
  const high = allHighLevelRequirements.value.map(r => ({
    ...r,
    type: '顶层需求',
    typeColor: 'sky'
  }))
  const low = lowLevelRequirements.value.map(r => ({
    ...r,
    type: '底层需求',
    level: 'low',
    category: 'low',
    typeColor: 'emerald'
  }))
  return [...high, ...low].map(r => ({
    ...r,
    status: requirementStatusMap.value[r.id] || 'backlog'
  }))
})

// 筛选后的需求（表格用）
const filteredRequirements = computed(() => {
  let result = allRequirements.value
  
  // 搜索筛选
  if (tableSearchQuery.value.trim()) {
    const query = tableSearchQuery.value.toLowerCase()
    result = result.filter(r => 
      (r.statement || r.text || '').toLowerCase().includes(query) ||
      (r.type || '').toLowerCase().includes(query) ||
      (r.level || r.category || '').toLowerCase().includes(query) ||
      (requirementStatuses.find(s => s.id === r.status)?.name || '').toLowerCase().includes(query)
    )
  }
  
  // 排序
  result = [...result].sort((a, b) => {
    let aVal = a[tableSortKey.value] || ''
    let bVal = b[tableSortKey.value] || ''
    if (tableSortKey.value === 'name') {
      aVal = a.statement || a.text || ''
      bVal = b.statement || b.text || ''
    }
    if (tableSortOrder.value === 'asc') {
      return String(aVal).localeCompare(String(bVal))
    }
    return String(bVal).localeCompare(String(aVal))
  })
  
  return result
})

// 按状态分组的需求列表（卡片视图用 - 使用 ref 以支持拖拽）
const backlogRequirements = ref([])
const inProgressRequirements = ref([])
const completedRequirements = ref([])

// 同步需求到各状态列表
function syncRequirementLists() {
  const all = allRequirements.value
  backlogRequirements.value = all.filter(r => (requirementStatusMap.value[r.id] || 'backlog') === 'backlog')
  inProgressRequirements.value = all.filter(r => requirementStatusMap.value[r.id] === 'in_progress')
  completedRequirements.value = all.filter(r => requirementStatusMap.value[r.id] === 'completed')
}

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
  const l1Items = allHighLevelRequirements.value.filter(r => r.category === 'L1')
  const l2Items = allHighLevelRequirements.value.filter(r => r.category === 'L2')
  const l3Items = allHighLevelRequirements.value.filter(r => r.category === 'L3')

  return baseColumns.map((col) => {
    if (col.id === 'L1') return { ...col, items: l1Items }
    if (col.id === 'L2') return { ...col, items: l2Items }
    if (col.id === 'L3') return { ...col, items: l3Items }
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

function normalizeKeywords(raw) {
  const text = (raw || '').trim()
  if (!text) return null
  return text.split(/[,，;\n|]+/g).map((s) => s.trim()).filter(Boolean)
}

// 切换列排序
function toggleSort(key) {
  if (tableSortKey.value === key) {
    tableSortOrder.value = tableSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    tableSortKey.value = key
    tableSortOrder.value = 'asc'
  }
}

// 切换列可见性
function toggleColumn(key) {
  const idx = tableVisibleColumns.value.indexOf(key)
  if (idx >= 0) {
    tableVisibleColumns.value.splice(idx, 1)
  } else {
    tableVisibleColumns.value.push(key)
  }
}

// 更新需求状态
function updateRequirementStatus(reqId, newStatus) {
  requirementStatusMap.value[reqId] = newStatus
}

// 拖拽改变状态处理
function onDragChange(evt, targetStatus) {
  if (evt.added) {
    const item = evt.added.element
    if (item && item.id) {
      requirementStatusMap.value[item.id] = targetStatus
    }
  }
}

// 获取状态颜色类
function getStatusColorClass(statusId, variant = 'bg') {
  const status = requirementStatuses.find(s => s.id === statusId)
  const color = status?.color || 'zinc'
  const colorMap = {
    zinc: { bg: 'bg-zinc-100', text: 'text-zinc-700', border: 'border-zinc-200', dot: 'bg-zinc-400' },
    blue: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200', dot: 'bg-blue-500' },
    emerald: { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' }
  }
  return colorMap[color]?.[variant] || colorMap.zinc[variant]
}

// 获取层级标签样式
function getLevelBadgeClass(level) {
  const map = {
    L1: 'bg-sky-100 text-sky-700 border-sky-200',
    L2: 'bg-violet-100 text-violet-700 border-violet-200',
    L3: 'bg-amber-100 text-amber-700 border-amber-200',
    low: 'bg-emerald-100 text-emerald-700 border-emerald-200'
  }
  return map[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

// 获取状态对应的需求列表（用于拖拽）
function getRequirementsForStatus(statusId) {
  return allRequirements.value.filter(r => (requirementStatusMap.value[r.id] || 'backlog') === statusId)
}

// ========== API 调用 ==========

// 加载 Context Runs 列表
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

// 从数据库加载已抽取的需求
async function loadRequirementsFromDB() {
  if (!sessionId.value.trim()) {
    error.value = '请先输入 Session ID'
        return
  }

  isLoading.value = true
  error.value = null
  highLevelRequirements.value = []

  try {
    const data = await requirementsL123Api.listBySession(sessionId.value.trim(), {
      page: 1,
      perPage: 200
    })
    highLevelRequirements.value = (data.requirements || []).map((req) => ({
      ...req,
      level: normalizeLevel(req.level || req.category),
    }))
    reqStats.value = await requirementsL123Api.stats(sessionId.value.trim())
    
    if (highLevelRequirements.value.length > 0) {
      currentStep.value = 1
    }
  } catch (err) {
    error.value = err?.message || '加载需求失败'
  } finally {
    isLoading.value = false
  }
}

// 执行 L1-L3 需求抽取
async function startExtraction() {
  extractionError.value = ''
  extractionResult.value = null

  const sid = sessionId.value.trim()
  if (!sid) {
    extractionError.value = '请先填写 session_id'
    return
  }
  if (extractionForm.value.bundleStrategy === 'graph' && !contextRunId.value.trim()) {
    extractionError.value = 'graph 策略需要 context_run_id'
    return
  }

  isExtracting.value = true
  try {
    const payload = {
      session_id: sid,
      context_run_id: contextRunId.value.trim() || null,
      bundle_strategy: extractionForm.value.bundleStrategy,
      anchor_strategy: extractionForm.value.anchorStrategy,
      r: Number(extractionForm.value.maxR) || 2,
      adaptive_retry_r2: !!extractionForm.value.adaptiveRetryR2,
      model: extractionForm.value.model,
      use_thinking_mode: !!extractionForm.value.useThinkingMode,
      use_toolcall: !!extractionForm.value.useToolcall,
      max_spans_per_bundle: Number(extractionForm.value.maxSpansPerBundle) || 12,
      token_limit: Number(extractionForm.value.tokenLimit) || 0,
      top_m_2hop: Number(extractionForm.value.topM2Hop) || 5,
      keywords: normalizeKeywords(extractionForm.value.keywords)
    }

    extractionResult.value = await requirementsL123Api.extract(payload)
    await loadRequirementsFromDB()
  } catch (err) {
    extractionError.value = err?.message || '抽取失败'
  } finally {
    isExtracting.value = false
  }
}

// 提取底层需求（L4）
// 流程：先检查数据库缓存，有则直接加载；否则调用 L4 生成接口
async function extractLowLevelRequirements() {
  if (allHighLevelRequirements.value.length === 0) {
    traceError.value = '请先加载或抽取顶层需求'
    return
  }

  const sid = sessionId.value?.trim()
  if (!sid) {
    traceError.value = '请先填写 Session ID'
    return
  }

  isExtractingLowLevel.value = true
  traceError.value = null
  lowLevelExtractionNotice.value = ''

  try {
    // 准备顶层需求列表
    const topRequirements = allHighLevelRequirements.value.map((req) => ({
      id: req.req_id,
      text: req.text || req.statement || '',
    }))
    if (topRequirements.some((req) => !req.id)) {
      throw new Error('存在顶层需求缺少 req_id，无法建立正确映射关系')
    }

    // 调用 L4 生成 API（内部会检查缓存）
    const result = await l4RequirementsApi.generate(sid, topRequirements, {
      config: {
        top_k_pattern: 5,
        top_k_spec: 3,
        top_k_nfr: 3,
        max_l4_per_top_req: 5,
        min_l4_per_top_req: 1,
        confidence_threshold: 0.6,
      },
      model: extractionForm.value.l4Model,
      useThinkingMode: !!extractionForm.value.l4UseThinkingMode,
    })

    // 获取当前 session 的全部底层需求（缓存 + 新生成）
    const allL4 = await l4RequirementsApi.getBySession(sid, { perPage: 500 })

    // 转换为 lowLevelRequirements 格式
    const l4Reqs = allL4.requirements || result.requirements || []
    lowLevelRequirements.value = l4Reqs.map((req, idx) => ({
      id: req.req_id || `low-${idx + 1}`,
      category: 'low',
      statement: req.text || req.shall_statement || '',
      rationale: req.source_top_text ? `来源: ${req.source_top_text.slice(0, 50)}...` : '',
      evidence: req.acceptance_criteria?.join('; ') || '',
      confidence: req.confidence || 0.8,
      component: req.component,
      test_method: req.test_method,
      source_top_id: req.source_top_id,
    }))

    // 提示
    if (result.from_cache) {
      lowLevelExtractionNotice.value = `已从缓存加载 ${l4Reqs.length} 条底层需求`
    } else {
      lowLevelExtractionNotice.value = `成功生成 ${result.inserted_count || 0} 条底层需求，当前共 ${l4Reqs.length} 条`
    }

    if (lowLevelRequirements.value.length > 0) {
      currentStep.value = 2
    }
  } catch (err) {
    traceError.value = err.message || '提取底层需求失败'
  } finally {
    isExtractingLowLevel.value = false
  }
}

// 底层需求提取提示
const lowLevelExtractionNotice = ref('')

// 加载示例底层需求（用于测试/演示）
// 对应会议记录：员工考勤系统需求讨论
// 会议内容：
// PM: 我们需要开发一个员工考勤系统，支持手机打卡。
// HR: 打卡要支持GPS定位，防止员工在家打卡。定位精度要在50米以内。
// DEV: 那如果GPS信号不好怎么办？
// HR: 可以用WiFi辅助定位，公司WiFi连上了也算有效打卡。
// PM: 系统要能自动生成月度考勤报表，HR每月要统计。
// HR: 对，报表要支持导出Excel，还要能看到迟到早退的明细。
// DEV: 好的，我们一周内出原型。
function loadMockLowLevelRequirements() {
  const mockLowLevel = [
    {
      id: 'low-1',
      category: 'low',
      statement: '开发手机端打卡模块，支持iOS和Android双平台',
      rationale: '实现员工移动端打卡功能',
      evidence: '我们需要开发一个员工考勤系统，支持手机打卡',
      confidence: 0.95
    },
    {
      id: 'low-2',
      category: 'low',
      statement: '集成GPS定位SDK，定位精度控制在50米以内',
      rationale: '防止员工虚假打卡，确保打卡位置真实性',
      evidence: '打卡要支持GPS定位，防止员工在家打卡。定位精度要在50米以内',
      confidence: 0.93
    },
    {
      id: 'low-3',
      category: 'low',
      statement: '实现WiFi辅助定位功能，连接公司WiFi视为有效打卡',
      rationale: '解决GPS信号弱时的定位问题',
      evidence: '可以用WiFi辅助定位，公司WiFi连上了也算有效打卡',
      confidence: 0.91
    },
    {
      id: 'low-4',
      category: 'low',
      statement: '开发月度考勤报表自动生成模块',
      rationale: '满足HR每月统计考勤的需求',
      evidence: '系统要能自动生成月度考勤报表，HR每月要统计',
      confidence: 0.92
    },
    {
      id: 'low-5',
      category: 'low',
      statement: '实现Excel导出功能，包含迟到早退明细数据',
      rationale: '方便HR导出数据进行分析和存档',
      evidence: '报表要支持导出Excel，还要能看到迟到早退的明细',
      confidence: 0.90
    }
  ]

  lowLevelRequirements.value = mockLowLevel
  currentStep.value = 2
}

// 追溯分析
async function runTraceAnalysis() {
  if (!canTrace.value) return

  isTracingLoading.value = true
  traceError.value = null
  traceResult.value = null

  try {
    const highReqs = allHighLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())
    const lowReqs = lowLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim())

    if (highReqs.length === 0 || lowReqs.length === 0) {
      throw new Error('顶层需求或底层需求为空，请先完成需求抽取和底层需求加载')
    }

    const apiResult = await traceabilityApi.batchAnalyzeRelation(highReqs, lowReqs)
    traceResult.value = apiResult
    currentStep.value = 2
    activeTab.value = 'network'
    updateChart()
  } catch (err) {
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
  analysisNotice.value = ''
  analysisStep.value = 1

  // 获取当前 session_id 用于保存到数据库
  const currentSessionId = sessionId.value?.trim() || null

  try {
    // Step 0: 若已有缓存结果，直接读取展示
    if (currentSessionId) {
      try {
        const [traceCache, conflictCache, classificationCache] = await Promise.all([
          analysisApi.getLatestTrace(currentSessionId),
          conflictApi.getLatest(currentSessionId),
          getLatestClassification(currentSessionId),
        ])

        const hasTrace = !!(traceCache && traceCache.data)
        const hasConflict = !!(conflictCache && conflictCache.data && conflictCache.data.items && conflictCache.data.items.length)
        const hasClassification = !!(classificationCache && classificationCache.predictions && classificationCache.predictions.length)

        const traceRelations = traceCache?.data?.relations || []
        const traceHasIds = traceRelations.length === 0
          ? true
          : traceRelations.every((rel) => rel.high_req_id && rel.low_req_id)

        const highReqIds = allHighLevelRequirements.value.map((r) => r.req_id).filter(Boolean)
        const lowSourceTopIds = new Set()
        lowLevelRequirements.value.forEach((req) => {
          const ids = req.source_top_ids || (req.source_top_id ? [req.source_top_id] : [])
          ids.forEach((id) => {
            if (id) lowSourceTopIds.add(id)
          })
        })
        const allTopAnalyzed = highReqIds.length === 0
          ? true
          : highReqIds.every((id) => lowSourceTopIds.has(id))

        if (hasTrace && hasConflict && hasClassification && traceHasIds && allTopAnalyzed) {
          analysisNotice.value = '已加载缓存分析结果，无需重新分析'
          traceResult.value = traceCache.data
          conflictResults.value = conflictCache.data.items.map((item) => ({
            reqA: { statement: item.requirement_a },
            reqB: { statement: item.requirement_b },
            is_conflict: item.is_conflict,
            raw_response: item.raw_response,
            data: item.result_json,
          }))

          const requirements = classificationCache.requirements || []
          classificationResult.value = {
            predictions: classificationCache.predictions.map((pred, idx) => ({
              ...pred,
              originalReq: { statement: requirements[idx] || '' },
            })),
            label_distribution: classificationCache.label_distribution,
            total: classificationCache.total,
          }

          currentStep.value = 4
          analysisStep.value = 4
          activeTab.value = 'network'
          setTimeout(() => updateChart(), 100)
          return
        }
      } catch (cacheErr) {
        // 读取缓存失败不影响正常分析
        console.warn('读取缓存结果失败，继续执行一键分析:', cacheErr)
      }
    }

    // Step 1: 追溯分析（基于数据库映射关系，避免全量笛卡尔积）
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

    // 仅使用基于映射关系的追溯分析（不回退到全量分析）
    const mappingResult = await traceabilityApi.traceByMapping(
      currentSessionId, 
      true,  // save_to_db = true
      800
    )
    const pairsAnalyzed = mappingResult.pairs_analyzed || 0
    const totalPossible = mappingResult.total_possible_pairs || (highReqs.length * lowReqs.length)
    if (pairsAnalyzed < totalPossible) {
      analysisNotice.value = `基于映射关系分析：仅分析 ${pairsAnalyzed} 个有关联的需求对（全量为 ${totalPossible} 个）`
    }
    const traceApiResult = mappingResult.data
    traceResult.value = traceApiResult
    currentStep.value = 2

    // Step 2: 冲突检测（保存到数据库）
    analysisStep.value = 2
    conflictError.value = null
    conflictResults.value = []

    const allReqs = [
      ...allHighLevelRequirements.value.map((r) => ({ ...r, type: 'high' })),
      ...lowLevelRequirements.value.map((r) => ({ ...r, type: 'low' }))
    ]

    if (allReqs.length >= 2) {
      const pairs = []
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
      const pairsToCheck = pairs.slice(0, 10)
      conflictProgress.value = { current: 0, total: pairsToCheck.length }

      // 准备批量检测的数据
      const conflictPairs = pairsToCheck.map(({ reqA, reqB }) => ({
        requirement_a: reqA.statement || reqA.text || '',
        requirement_b: reqB.statement || reqB.text || '',
      }))

      // 尝试批量检测并保存
      if (conflictPairs.length > 0) {
        try {
          const conflictBatchResult = await conflictApi.checkBatch(
            conflictPairs,
            true,  // save_to_db = true
            currentSessionId
          )
          
          if (conflictBatchResult.success && conflictBatchResult.data) {
            conflictResults.value = conflictBatchResult.data.map((result, idx) => ({
              reqA: pairsToCheck[idx].reqA,
              reqB: pairsToCheck[idx].reqB,
              ...result
            }))
            conflictProgress.value.current = pairsToCheck.length
          }
        } catch (e) {
          console.warn('批量冲突检测失败，尝试单对检测:', e)
          // 降级到单对检测
      for (let i = 0; i < pairsToCheck.length; i++) {
        const { reqA, reqB } = pairsToCheck[i]
        conflictProgress.value.current = i + 1
        try {
          const res = await conflictApi.check(
            reqA.statement || reqA.text || '',
                reqB.statement || reqB.text || '',
                true,  // save_to_db = true
                currentSessionId
              )
              conflictResults.value.push({ reqA, reqB, ...(res.data || res) })
            } catch (innerErr) {
              console.warn('冲突检测单对失败:', innerErr)
            }
          }
        }
      }
      currentStep.value = 3
    }

    // Step 3: 需求分类（保存到数据库）
    analysisStep.value = 3
    classificationError.value = null
    classificationResult.value = null

    const classifyReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value]
    if (classifyReqs.length > 0) {
      const requirements = classifyReqs.map((r) => r.statement || r.text || '')
      const response = await classifyTexts(
        { requirements },
        true,  // save_to_db = true
        currentSessionId
      )
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

    analysisStep.value = 4
    activeTab.value = 'network'
    setTimeout(() => updateChart(), 100)
  } catch (err) {
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
  const basePercent = (analysisStep.value - 1) * 33
  if (analysisStep.value === 2 && conflictProgress.value.total > 0) {
    return basePercent + Math.round((conflictProgress.value.current / conflictProgress.value.total) * 33)
  }
  return basePercent + 16
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

  const highNodes = allHighLevelRequirements.value
  const lowNodes = lowLevelRequirements.value

  const containerWidth = chartContainer.value?.clientWidth || 900
  const containerHeight = chartContainer.value?.clientHeight || 500

  const leftX = containerWidth * 0.18
  const rightX = containerWidth * 0.82
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

  const leftSpacing = highNodes.length > 1 ? availableHeight / (highNodes.length - 1) : 0
  const highIndexToNodeId = {}
  const nodes = highNodes.map((req, idx) => {
    const level = normalizeLevel(req.category || req.level)
    const nodeId = req.req_id || req.id || `high_${idx}`
    highIndexToNodeId[idx] = nodeId
    return {
    id: nodeId,
    name: req.statement.length > 25 ? req.statement.slice(0, 25) + '...' : req.statement,
    x: leftX,
    y: topPadding + (highNodes.length === 1 ? availableHeight / 2 : idx * leftSpacing),
    category: categoryMap[level] ?? 0,
    symbol: 'roundRect',
    symbolSize: [200, 32],
    itemStyle: {
      color: getCategoryColor(level),
      borderColor: getCategoryBorderColor(level),
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
        <div style="font-weight: bold; color: ${getCategoryColor(level)}; margin-bottom: 4px;">[${level}] 顶层需求</div>
        <div>${req.statement}</div>
      </div>`
    }
  }
  })

  const rightSpacing = lowNodes.length > 1 ? availableHeight / (lowNodes.length - 1) : 0
  const lowIndexToNodeId = {}
  lowNodes.forEach((req, idx) => {
    const nodeId = req.req_id || req.id || `low_${idx}`
    lowIndexToNodeId[idx] = nodeId
    nodes.push({
      id: nodeId,
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

  const links = []
  if (traceResult.value?.relations) {
    traceResult.value.relations.forEach((rel) => {
      if (!rel.has_relation) return
      const sourceId = rel.high_req_id
      const targetId = rel.low_req_id
      if (!sourceId || !targetId) return
      const curve = ((links.length % 7) - 3) * 0.06
      links.push({
        source: sourceId,
        target: targetId,
        relation_type: rel.relation_type,
        lineStyle: {
          color: getRelationTypeColor(rel.relation_type),
          width: 1.4 + (rel.confidence || 0.5) * 1.2,
          curveness: curve,
          opacity: 0.7
        },
        label: { show: false }
      })
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
        layout: 'none',
        coordinateSystem: null,
        roam: true,
        categories: categories,
        data: nodes,
        links: links,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        lineStyle: { opacity: 0.7 },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3, opacity: 0.95 },
          edgeLabel: {
            show: true,
            formatter: (p) => getRelationTypeLabel(p.data?.relation_type),
            fontSize: 10,
            color: '#666',
            backgroundColor: 'rgba(255,255,255,0.9)',
            padding: [2, 6],
            borderRadius: 3
          },
          itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0, 0, 0, 0.25)' }
        }
      }
    ]
  }

  chart.setOption(option, true)
}

function getCategoryBorderColor(category) {
  const colors = {
    L1: '#1d4ed8',
    L2: '#6d28d9',
    L3: '#d97706',
    low: '#047857'
  }
  return colors[category] || '#374151'
}

function getLabelClass(label) {
  return getClassificationLabelStyle(label).pillClass
}

function getLabelDotClass(label) {
  return getClassificationLabelStyle(label).dotClass
}

function getLabelHeaderClass(label) {
  const style = getClassificationLabelStyle(label)
  return `${style.headerClass} ${style.borderClass}`.trim()
}

function getLabelBadgeClass(label) {
  return getClassificationLabelStyle(label).badgeClass
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

watch(contextRunId, (rid) => {
  const run = contextRuns.value.find((r) => r.context_run_id === rid)
  if (run?.session_id && !sessionId.value.trim()) {
    sessionId.value = run.session_id
  }
})

// 监听需求数据变化，同步到各状态列表
watch(
  () => [allRequirements.value, requirementStatusMap.value],
  () => {
    syncRequirementLists()
  },
  { deep: true, immediate: true }
)

onMounted(async () => {
  await loadContextRuns({ useSessionFilter: false })
  syncRequirementLists()
})
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
          从数据库加载 L1/L2/L3 需求，建立顶层与底层需求间的追溯关系
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
        class="w-[400px] p-6 flex flex-col border-r border-zinc-200 bg-white min-w-[360px] shrink-0 overflow-y-auto"
      >
        <!-- Session 和 Context Run 选择 -->
        <div class="space-y-4 mb-6">
          <div>
            <label class="text-sm font-medium text-zinc-700 mb-2 block">Session ID</label>
            <input
              v-model="sessionId"
              type="text"
              placeholder="Phase 1 ingest_transcript 返回的 session_id"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
            />
          </div>

          <div>
            <div class="flex items-center justify-between gap-2 mb-2">
              <label class="text-sm font-medium text-zinc-700">Context Run (Phase 2)</label>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-xs text-zinc-600 hover:text-zinc-900"
                :disabled="isLoadingRuns"
                @click="loadContextRuns({ useSessionFilter: true })"
              >
                <RefreshCw class="w-3 h-3" :class="isLoadingRuns ? 'animate-spin' : ''" />
                刷新
              </button>
            </div>
            <select
              v-model="contextRunId"
              class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
            >
              <option value="">（可选：graph 策略需要）</option>
              <option v-for="run in contextRuns" :key="run.context_run_id" :value="run.context_run_id">
                {{ run.context_run_id.slice(0, 8) }}... · {{ run.session_id?.slice(0, 8) || 'N/A' }}... · {{ run.status }}
              </option>
            </select>
            <p v-if="runsError" class="mt-1 text-xs text-red-600">{{ runsError }}</p>
          </div>
        </div>

        <!-- 抽取设置 -->
        <details class="group mb-4">
            <summary
              class="flex items-center justify-between cursor-pointer p-3 bg-zinc-50 rounded-lg border border-zinc-200 hover:bg-zinc-100 transition-colors"
            >
              <div class="flex items-center gap-2">
                <Settings2 class="w-4 h-4 text-zinc-500" />
              <span class="text-xs font-semibold text-zinc-600 uppercase tracking-wider">抽取设置</span>
              </div>
            <ChevronDown class="w-4 h-4 text-zinc-400 transition-transform group-open:rotate-180" />
            </summary>
            <div class="mt-2 p-3 bg-zinc-50 rounded-lg border border-zinc-200 space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">bundle_strategy</label>
                <select
                  v-model="extractionForm.bundleStrategy"
                  class="w-full text-xs border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="graph">graph</option>
                  <option value="sequence">sequence</option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">anchor_strategy</label>
                <select
                  v-model="extractionForm.anchorStrategy"
                  class="w-full text-xs border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="informative">informative</option>
                  <option value="keyword">keyword</option>
                  <option value="all">all</option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">model</label>
                <select
                  v-model="extractionForm.model"
                  class="w-full text-xs border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="deepseek-v4-pro">deepseek-v4-pro</option>
                  <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">r (max)</label>
                <select
                  v-model.number="extractionForm.maxR"
                  class="w-full text-xs border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option :value="1">1</option>
                  <option :value="2">2</option>
                </select>
              </div>
            </div>
            <label class="flex items-center gap-2 text-xs text-zinc-600">
              <input v-model="extractionForm.useThinkingMode" type="checkbox" class="w-3 h-3 rounded border-zinc-300" />
              L1-L3 思考模式
            </label>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">L4 model</label>
                <select
                  v-model="extractionForm.l4Model"
                  class="w-full text-xs border-zinc-300 rounded-md focus:ring-black focus:border-black"
                >
                  <option value="deepseek-v4-pro">deepseek-v4-pro</option>
                  <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                </select>
              </div>
              <label class="flex items-center gap-2 text-xs text-zinc-600 pt-6">
                <input v-model="extractionForm.l4UseThinkingMode" type="checkbox" class="w-3 h-3 rounded border-zinc-300" />
                L4 思考模式
              </label>
            </div>
            <label class="flex items-center gap-2 text-xs text-zinc-600">
              <input v-model="extractionForm.useToolcall" type="checkbox" class="w-3 h-3 rounded border-zinc-300" />
              使用 tool-call
            </label>
            </div>
          </details>

          <!-- 错误提示 -->
        <div v-if="error" class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200 mb-4">
            Error: {{ error }}
          </div>
        <div v-if="extractionError" class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200 mb-4">
          抽取错误: {{ extractionError }}
        </div>

        <!-- 操作按钮组 -->
        <div class="space-y-3">
          <div class="flex gap-2">
            <button
              @click="loadRequirementsFromDB"
              :disabled="isLoading || !canLoadRequirements"
              class="flex-1 py-2.5 px-4 bg-zinc-800 hover:bg-zinc-700 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Loader2 v-if="isLoading" class="w-4 h-4 animate-spin" />
              <Database v-else class="w-4 h-4" />
              <span>{{ isLoading ? '加载中...' : '加载已有需求' }}</span>
            </button>
          </div>

          <button
            @click="startExtraction"
            :disabled="!canExtract"
            class="w-full py-2.5 px-4 bg-black hover:bg-zinc-800 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isExtracting" class="w-4 h-4 animate-spin" />
            <Play v-else class="w-4 h-4" />
            <span>{{ isExtracting ? '抽取中...' : '执行 L1-L3 抽取' }}</span>
          </button>

          <button
            @click="extractLowLevelRequirements"
            :disabled="allHighLevelRequirements.length === 0 || isExtractingLowLevel"
            class="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isExtractingLowLevel" class="w-4 h-4 animate-spin" />
            <Layers v-else class="w-4 h-4" />
            <span>{{ isExtractingLowLevel ? '生成中...' : '提取底层需求 (L4)' }}</span>
          </button>

          <!-- 底层需求提取提示 -->
          <div
            v-if="lowLevelExtractionNotice"
            class="p-3 text-sm text-emerald-700 bg-emerald-50 rounded-md border border-emerald-200 flex items-center gap-2"
          >
            <CheckCircle2 class="w-4 h-4 flex-shrink-0" />
            {{ lowLevelExtractionNotice }}
          </div>

          <button
            @click="loadMockLowLevelRequirements"
            :disabled="!canLoadRequirements"
            class="w-full py-2 px-4 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors border border-zinc-300 border-dashed text-sm"
          >
            <Database class="w-4 h-4" />
            <span>加载示例底层需求</span>
            <span class="text-xs text-zinc-500">(测试用)</span>
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
            
            <div class="text-center text-sm font-medium" :class="{
              'text-blue-600': analysisStep === 1,
              'text-amber-600': analysisStep === 2,
              'text-emerald-600': analysisStep >= 3
            }">
              {{ analysisStepText }}
            </div>
          </div>

          <!-- 缓存提示 -->
          <div
            v-if="analysisNotice"
            class="p-3 text-sm text-emerald-700 bg-emerald-50 rounded-md border border-emerald-200"
          >
            {{ analysisNotice }}
          </div>

          <!-- 错误提示 -->
          <div
            v-if="analysisError"
            class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200"
          >
            分析错误: {{ analysisError }}
          </div>

          <!-- 抽取结果 -->
          <div v-if="extractionResult" class="p-3 bg-emerald-50 rounded-lg border border-emerald-200 text-xs">
            <div class="font-medium text-emerald-900 mb-2">本次抽取结果</div>
            <div class="grid grid-cols-2 gap-2 text-emerald-700">
              <div>anchors: {{ extractionResult.total_anchors }}</div>
              <div>bundles: {{ extractionResult.bundles_processed }}</div>
              <div>inserted: {{ extractionResult.total_inserted }}</div>
              <div>duplicates: {{ extractionResult.total_duplicates }}</div>
            </div>
          </div>

          <!-- 统计信息 -->
          <div
            v-if="reqStats || allHighLevelRequirements.length > 0"
            class="p-3 bg-zinc-50 rounded-lg border border-zinc-200 text-xs text-zinc-600 space-y-1"
          >
            <div class="flex justify-between">
              <span>顶层需求</span>
              <span class="font-semibold">{{ allHighLevelRequirements.length }}</span>
            </div>
            <div v-if="reqStats" class="flex justify-between text-zinc-400">
              <span class="ml-2">L1</span>
              <span>{{ reqStats.by_level?.L1 || 0 }}</span>
            </div>
            <div v-if="reqStats" class="flex justify-between text-zinc-400">
              <span class="ml-2">L2</span>
              <span>{{ reqStats.by_level?.L2 || 0 }}</span>
            </div>
            <div v-if="reqStats" class="flex justify-between text-zinc-400">
              <span class="ml-2">L3</span>
              <span>{{ reqStats.by_level?.L3 || 0 }}</span>
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
        <div class="bg-white border-b border-zinc-200 px-6 py-2 flex items-center justify-between shrink-0">
          <div class="flex gap-1">
          <button
            @click="activeTab = 'board'"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
            :class="activeTab === 'board' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
          >
            <Layers class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
            看板
          </button>
            <button
              @click="activeTab = 'table'"
              class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
              :class="activeTab === 'table' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
            >
              <Table2 class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
              表格
            </button>
            <button
              @click="activeTab = 'kanban'"
              class="px-3 py-2 text-sm font-medium rounded-lg transition-colors"
              :class="activeTab === 'kanban' ? 'bg-indigo-600 text-white' : 'text-zinc-600 hover:bg-zinc-100'"
            >
              <LayoutGrid class="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
              卡片
            </button>
            <div class="w-px h-6 bg-zinc-200 mx-1 self-center"></div>
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
          
          <!-- 需求统计 -->
          <div class="flex items-center gap-4 text-xs text-zinc-500">
            <span>共 <span class="font-semibold text-zinc-900">{{ allRequirements.length }}</span> 条需求</span>
          </div>
        </div>

        <!-- 看板视图 -->
        <div v-show="activeTab === 'board'" class="flex-1 overflow-x-auto bg-zinc-50 p-6">
          <div v-if="allHighLevelRequirements.length === 0 && !isLoading" class="h-full flex flex-col items-center justify-center text-zinc-400">
            <FileText class="w-12 h-12 mb-3 opacity-20" />
            <p>需求工件将显示在此处</p>
            <p class="text-sm mt-2">请先输入 Session ID 并点击「加载已有需求」或「执行 L1-L3 抽取」</p>
          </div>

          <div v-if="isLoading" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-black mb-4" />
            <p>正在加载需求数据...</p>
          </div>

          <!-- 看板 -->
          <div v-if="allHighLevelRequirements.length > 0" class="grid grid-cols-4 gap-4 h-full min-w-[1200px]">
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
                      :key="card.id || card.req_id"
                      class="p-3 rounded-lg border border-zinc-200 bg-white shadow-sm hover:shadow-md transition-all"
                    >
                      <p class="text-zinc-900 font-medium text-sm mb-2">{{ card.statement || card.text }}</p>
                      <div v-if="card.rationale" class="text-xs text-zinc-500 mb-2">
                        <span class="font-semibold">Rationale:</span> {{ card.rationale }}
                      </div>
                      <div
                        class="flex items-center justify-between mt-2 pt-2 border-t border-zinc-100"
                      >
                        <div
                          v-if="card.evidence || card.anchor_span_id"
                          class="flex items-center gap-1 text-xs text-zinc-400 max-w-[70%] truncate"
                          :title="card.evidence || card.anchor_span_id"
                        >
                          <Quote class="w-3 h-3 shrink-0" />
                          <span class="truncate">"{{ card.evidence || card.anchor_span_id }}"</span>
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

        <!-- 表格视图 -->
        <div v-show="activeTab === 'table'" class="flex-1 flex flex-col overflow-hidden bg-white">
          <!-- 工具栏 -->
          <div class="px-6 py-3 border-b border-zinc-200 flex items-center justify-between gap-4">
            <!-- 搜索框 -->
            <div class="relative flex-1 max-w-md">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
              <input
                v-model="tableSearchQuery"
                type="text"
                placeholder="搜索需求名称、类型、状态..."
                class="w-full pl-10 pr-4 py-2 text-sm border border-zinc-300 rounded-lg focus:border-black focus:ring-1 focus:ring-black"
              />
            </div>
            
            <!-- 列配置 -->
            <div class="relative">
              <button
                @click="showColumnSelector = !showColumnSelector"
                class="inline-flex items-center gap-2 px-3 py-2 text-sm border border-zinc-300 rounded-lg hover:bg-zinc-50"
              >
                <Filter class="w-4 h-4" />
                设置展示列
                <ChevronDown class="w-4 h-4 transition-transform" :class="showColumnSelector ? 'rotate-180' : ''" />
              </button>
              
              <!-- 列选择下拉框 -->
              <div
                v-if="showColumnSelector"
                class="absolute right-0 top-full mt-1 w-56 bg-white border border-zinc-200 rounded-lg shadow-lg z-50 py-2"
              >
                <div
                  v-for="col in availableTableColumns"
                  :key="col.key"
                  @click="toggleColumn(col.key)"
                  class="flex items-center gap-2 px-3 py-2 hover:bg-zinc-50 cursor-pointer"
                >
                  <div class="w-4 h-4 border rounded flex items-center justify-center"
                       :class="tableVisibleColumns.includes(col.key) ? 'bg-black border-black' : 'border-zinc-300'">
                    <CheckCircle2 v-if="tableVisibleColumns.includes(col.key)" class="w-3 h-3 text-white" />
                  </div>
                  <span class="text-sm">{{ col.label }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 表格 -->
          <div class="flex-1 overflow-auto">
            <table class="w-full">
              <thead class="bg-zinc-50 sticky top-0 z-10">
                <tr>
                  <th
                    v-for="col in availableTableColumns.filter(c => tableVisibleColumns.includes(c.key))"
                    :key="col.key"
                    class="px-4 py-3 text-left text-xs font-semibold text-zinc-600 uppercase tracking-wider border-b border-zinc-200 cursor-pointer hover:bg-zinc-100"
                    :class="col.width"
                    @click="toggleSort(col.key)"
                  >
                    <div class="flex items-center gap-1">
                      {{ col.label }}
                      <div class="flex flex-col -space-y-1">
                        <ChevronUp class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'asc' ? 'text-black' : 'text-zinc-300'" />
                        <ChevronDown class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'desc' ? 'text-black' : 'text-zinc-300'" />
                      </div>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-100">
                <tr
                  v-for="req in filteredRequirements"
                  :key="req.id"
                  class="hover:bg-zinc-50 transition-colors"
                >
                  <!-- 需求名称 -->
                  <td v-if="tableVisibleColumns.includes('name')" class="px-4 py-3">
                    <p class="text-sm text-zinc-900 font-medium">{{ req.statement || req.text }}</p>
                  </td>
                  
                  <!-- 类型 -->
                  <td v-if="tableVisibleColumns.includes('type')" class="px-4 py-3">
                    <span class="text-xs px-2 py-1 rounded-full" :class="req.typeColor === 'sky' ? 'bg-sky-100 text-sky-700' : 'bg-emerald-100 text-emerald-700'">
                      {{ req.type }}
                    </span>
                  </td>
                  
                  <!-- 层级 -->
                  <td v-if="tableVisibleColumns.includes('level')" class="px-4 py-3">
                    <span class="text-xs px-2 py-0.5 rounded border font-medium" :class="getLevelBadgeClass(req.level || req.category)">
                      {{ req.level || req.category }}
                    </span>
                  </td>
                  
                  <!-- 状态 -->
                  <td v-if="tableVisibleColumns.includes('status')" class="px-4 py-3">
                    <select
                      :value="req.status"
                      @change="updateRequirementStatus(req.id, $event.target.value)"
                      class="text-xs px-2 py-1 rounded-lg border border-zinc-200 focus:border-black focus:ring-1 focus:ring-black"
                      :class="getStatusColorClass(req.status, 'bg')"
                    >
                      <option v-for="s in requirementStatuses" :key="s.id" :value="s.id">
                        {{ s.name }}
                      </option>
                    </select>
                  </td>
                  
                  <!-- 置信度 -->
                  <td v-if="tableVisibleColumns.includes('confidence')" class="px-4 py-3">
                    <span v-if="req.confidence" class="text-xs px-2 py-0.5 rounded-full border" :class="getConfidenceColor(req.confidence)">
                      {{ (req.confidence * 100).toFixed(0) }}%
                    </span>
                    <span v-else class="text-zinc-400">-</span>
                  </td>
                  
                  <!-- 证据 -->
                  <td v-if="tableVisibleColumns.includes('evidence')" class="px-4 py-3">
                    <p class="text-xs text-zinc-500 truncate max-w-[200px]" :title="req.evidence || req.anchor_span_id">
                      {{ req.evidence || req.anchor_span_id || '-' }}
                    </p>
                  </td>
                  
                  <!-- 原因 -->
                  <td v-if="tableVisibleColumns.includes('rationale')" class="px-4 py-3">
                    <p class="text-xs text-zinc-500 truncate max-w-[200px]" :title="req.rationale">
                      {{ req.rationale || '-' }}
                    </p>
                  </td>
                </tr>
                
                <tr v-if="filteredRequirements.length === 0">
                  <td :colspan="tableVisibleColumns.length" class="px-4 py-12 text-center text-zinc-400">
                    <FileText class="w-10 h-10 mx-auto mb-2 opacity-20" />
                    <p>暂无需求数据</p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <!-- 分页信息 -->
          <div class="px-6 py-3 border-t border-zinc-200 flex items-center justify-between text-sm text-zinc-600">
            <span>共 {{ filteredRequirements.length }} 条</span>
          </div>
        </div>

        <!-- 卡片视图（可拖拽看板） -->
        <div v-show="activeTab === 'kanban'" class="flex-1 overflow-x-auto bg-zinc-100 p-6">
          <div class="flex gap-4 h-full min-w-[900px]">
            <!-- 待处理列 -->
            <div class="flex-1 min-w-[300px] flex flex-col bg-zinc-50 rounded-xl border border-zinc-200 shadow-sm overflow-hidden">
              <div class="px-4 py-3 border-b bg-zinc-100 border-zinc-200 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <Circle class="w-4 h-4 text-zinc-500" />
                  <h3 class="font-semibold text-zinc-800 text-sm">待处理</h3>
                </div>
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700">
                  {{ backlogRequirements.length }}
                </span>
              </div>
              <draggable
                v-model="backlogRequirements"
                :group="{ name: 'requirements', pull: true, put: true }"
                item-key="id"
                :animation="200"
                class="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar min-h-[200px]"
                ghost-class="drag-ghost"
                chosen-class="drag-chosen"
                drag-class="drag-active"
                @change="onDragChange($event, 'backlog')"
              >
                <template #item="{ element }">
                  <div
                    class="p-3 rounded-lg border bg-white shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing group"
                    :class="element.type === '顶层需求' ? 'border-sky-100 hover:border-sky-200' : 'border-emerald-100 hover:border-emerald-200'"
                  >
                    <div class="flex items-start gap-2">
                      <GripVertical class="w-4 h-4 text-zinc-300 shrink-0 mt-0.5 group-hover:text-zinc-400" />
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-2">
                          <span class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                                :class="element.type === '顶层需求' ? 'bg-sky-100 text-sky-700' : 'bg-emerald-100 text-emerald-700'">
                            {{ element.type }}
                          </span>
                          <span v-if="element.level && element.level !== 'low'" 
                                class="text-[10px] px-1.5 py-0.5 rounded border font-medium"
                                :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="text-sm text-zinc-900 font-medium leading-snug">
                          {{ (element.statement || element.text).length > 80 
                             ? (element.statement || element.text).slice(0, 80) + '...' 
                             : (element.statement || element.text) }}
                        </p>
                        <div class="flex items-center justify-between mt-2 pt-2 border-t border-zinc-100">
                          <div v-if="element.evidence || element.anchor_span_id" 
                               class="flex items-center gap-1 text-xs text-zinc-400 max-w-[60%] truncate">
                            <Quote class="w-3 h-3 shrink-0" />
                            <span class="truncate">"{{ element.evidence || element.anchor_span_id }}"</span>
                          </div>
                          <span v-if="element.confidence" 
                                class="text-[10px] px-1.5 py-0.5 rounded-full border"
                                :class="getConfidenceColor(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #footer>
                  <div v-if="!backlogRequirements.length" 
                       class="text-center py-8 text-zinc-400 text-sm border-2 border-dashed border-zinc-200 rounded-lg">
                    拖拽需求到此处
                  </div>
                </template>
              </draggable>
            </div>

            <!-- 进行中列 -->
            <div class="flex-1 min-w-[300px] flex flex-col bg-blue-50/50 rounded-xl border border-blue-200 shadow-sm overflow-hidden">
              <div class="px-4 py-3 border-b bg-blue-100/50 border-blue-200 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <Clock class="w-4 h-4 text-blue-600" />
                  <h3 class="font-semibold text-zinc-800 text-sm">进行中</h3>
                </div>
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                  {{ inProgressRequirements.length }}
                </span>
              </div>
              <draggable
                v-model="inProgressRequirements"
                :group="{ name: 'requirements', pull: true, put: true }"
                item-key="id"
                :animation="200"
                class="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar min-h-[200px]"
                ghost-class="drag-ghost"
                chosen-class="drag-chosen"
                drag-class="drag-active"
                @change="onDragChange($event, 'in_progress')"
              >
                <template #item="{ element }">
                  <div
                    class="p-3 rounded-lg border bg-white shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing group"
                    :class="element.type === '顶层需求' ? 'border-sky-100 hover:border-sky-200' : 'border-emerald-100 hover:border-emerald-200'"
                  >
                    <div class="flex items-start gap-2">
                      <GripVertical class="w-4 h-4 text-zinc-300 shrink-0 mt-0.5 group-hover:text-zinc-400" />
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-2">
                          <span class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                                :class="element.type === '顶层需求' ? 'bg-sky-100 text-sky-700' : 'bg-emerald-100 text-emerald-700'">
                            {{ element.type }}
                          </span>
                          <span v-if="element.level && element.level !== 'low'" 
                                class="text-[10px] px-1.5 py-0.5 rounded border font-medium"
                                :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="text-sm text-zinc-900 font-medium leading-snug">
                          {{ (element.statement || element.text).length > 80 
                             ? (element.statement || element.text).slice(0, 80) + '...' 
                             : (element.statement || element.text) }}
                        </p>
                        <div class="flex items-center justify-between mt-2 pt-2 border-t border-zinc-100">
                          <div v-if="element.evidence || element.anchor_span_id" 
                               class="flex items-center gap-1 text-xs text-zinc-400 max-w-[60%] truncate">
                            <Quote class="w-3 h-3 shrink-0" />
                            <span class="truncate">"{{ element.evidence || element.anchor_span_id }}"</span>
                          </div>
                          <span v-if="element.confidence" 
                                class="text-[10px] px-1.5 py-0.5 rounded-full border"
                                :class="getConfidenceColor(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #footer>
                  <div v-if="!inProgressRequirements.length" 
                       class="text-center py-8 text-zinc-400 text-sm border-2 border-dashed border-blue-200 rounded-lg">
                    拖拽需求到此处
                  </div>
                </template>
              </draggable>
            </div>

            <!-- 已完成列 -->
            <div class="flex-1 min-w-[300px] flex flex-col bg-emerald-50/50 rounded-xl border border-emerald-200 shadow-sm overflow-hidden">
              <div class="px-4 py-3 border-b bg-emerald-100/50 border-emerald-200 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <CheckCircle class="w-4 h-4 text-emerald-600" />
                  <h3 class="font-semibold text-zinc-800 text-sm">已完成</h3>
                </div>
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                  {{ completedRequirements.length }}
                </span>
              </div>
              <draggable
                v-model="completedRequirements"
                :group="{ name: 'requirements', pull: true, put: true }"
                item-key="id"
                :animation="200"
                class="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar min-h-[200px]"
                ghost-class="drag-ghost"
                chosen-class="drag-chosen"
                drag-class="drag-active"
                @change="onDragChange($event, 'completed')"
              >
                <template #item="{ element }">
                  <div
                    class="p-3 rounded-lg border bg-white shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing group"
                    :class="element.type === '顶层需求' ? 'border-sky-100 hover:border-sky-200' : 'border-emerald-100 hover:border-emerald-200'"
                  >
                    <div class="flex items-start gap-2">
                      <GripVertical class="w-4 h-4 text-zinc-300 shrink-0 mt-0.5 group-hover:text-zinc-400" />
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-2">
                          <span class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                                :class="element.type === '顶层需求' ? 'bg-sky-100 text-sky-700' : 'bg-emerald-100 text-emerald-700'">
                            {{ element.type }}
                          </span>
                          <span v-if="element.level && element.level !== 'low'" 
                                class="text-[10px] px-1.5 py-0.5 rounded border font-medium"
                                :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="text-sm text-zinc-900 font-medium leading-snug line-through opacity-70">
                          {{ (element.statement || element.text).length > 80 
                             ? (element.statement || element.text).slice(0, 80) + '...' 
                             : (element.statement || element.text) }}
                        </p>
                        <div class="flex items-center justify-between mt-2 pt-2 border-t border-zinc-100">
                          <div v-if="element.evidence || element.anchor_span_id" 
                               class="flex items-center gap-1 text-xs text-zinc-400 max-w-[60%] truncate">
                            <Quote class="w-3 h-3 shrink-0" />
                            <span class="truncate">"{{ element.evidence || element.anchor_span_id }}"</span>
                          </div>
                          <span v-if="element.confidence" 
                                class="text-[10px] px-1.5 py-0.5 rounded-full border"
                                :class="getConfidenceColor(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template #footer>
                  <div v-if="!completedRequirements.length" 
                       class="text-center py-8 text-zinc-400 text-sm border-2 border-dashed border-emerald-200 rounded-lg">
                    拖拽需求到此处
                  </div>
                </template>
              </draggable>
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
            <p>完成追溯分析后，点击"一键分析"检查需求冲突</p>
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
            <p>完成追溯分析后，点击"一键分析"进行功能/非功能分类</p>
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

/* 拖拽样式 */
.drag-ghost {
  opacity: 0.5;
}
.drag-chosen {
  box-shadow: 0 0 0 2px #3b82f6;
  border-radius: 8px;
}
.drag-active {
  transform: rotate(2deg) scale(1.05);
}
</style>
