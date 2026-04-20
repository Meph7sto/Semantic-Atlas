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
      <main class="canvas graph-canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.04s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 需求图谱</span>
          </div>
          <div class="graph-toolbar">
            <select v-model="selectedProjectId" class="project-select" :disabled="isLoadingProjects">
              <option value="">选择项目</option>
              <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
                {{ project.name }}
              </option>
            </select>
            <input
              v-model.trim="sessionId"
              class="session-input"
              placeholder="Session ID"
              spellcheck="false"
            />
            <button type="button" class="action-btn" :disabled="isLoadingGraph" @click="loadGraph">
              {{ isLoadingGraph ? '生成中' : hasGraph ? '刷新图谱' : '生成图谱' }}
            </button>
            <button
              type="button"
              class="action-btn infer-btn"
              :disabled="isLoadingGraph || isInferringGraph"
              @click="inferGraph"
            >
              {{ isInferringGraph ? '推理中' : '推理关系' }}
            </button>
          </div>
        </section>

        <section class="graph-shell" data-animate style="--delay: 0.08s">
          <aside class="graph-side">
            <div class="metric-grid">
              <div class="metric-item">
                <span>需求节点</span>
                <strong>{{ stats.node_counts?.requirement || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>关系边</span>
                <strong>{{ stats.edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>结构关系</span>
                <strong>{{ stats.structural_edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>结构/规则关系</span>
                <strong>{{ stats.strong_edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>推理补强</span>
                <strong>{{ stats.inferred_edge_count || 0 }}</strong>
              </div>
            </div>

            <div class="legend-block">
              <div class="block-title-row">
                <h3>层级分布</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedLevel === '__all__' }"
                  @click="selectLevel('__all__')"
                >
                  全部
                </button>
              </div>
              <div class="source-badge-row">
                <span class="source-badge">统一主源 · manage_requirements</span>
                <span class="source-badge subtle">层级准绳 · source_level</span>
              </div>
              <div v-if="levelLegend.length" class="category-list">
                <button
                  v-for="item in levelLegend"
                  :key="item.label"
                  type="button"
                  class="category-chip"
                  :class="{ active: selectedLevel === item.label }"
                  @click="selectLevel(item.label)"
                >
                  <span class="category-dot" :style="{ background: item.color }"></span>
                  <span class="category-name">{{ item.label }}</span>
                  <b>{{ item.count }}</b>
                </button>
              </div>
              <p v-else class="detail-empty">当前项目暂无需求层级数据。</p>
              <p v-if="levelLegend.length" class="legend-hint">
                点击层级聚焦对应需求及其相邻关系。
              </p>
            </div>

            <div class="legend-block compact-block">
              <div class="block-title-row">
                <h3>关系类型</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedEdgeType === '__all__' }"
                  @click="selectEdgeType('__all__')"
                >
                  全部
                </button>
              </div>
              <button
                v-for="edge in edgeLegend"
                :key="edge.type"
                type="button"
                class="legend-row legend-button"
                :class="{ active: selectedEdgeType === edge.type }"
                @click="selectEdgeType(edge.type)"
              >
                <span class="legend-line" :style="{ background: edge.color }"></span>
                <span>{{ edge.label }}</span>
                <b>{{ stats.edge_counts?.[edge.type] || 0 }}</b>
              </button>
            </div>

            <div class="legend-block compact-block">
              <div class="block-title-row">
                <h3>关系筛选</h3>
                <button type="button" class="clear-filter" @click="resetEdgeFilters">
                  重置
                </button>
              </div>
              <div class="filter-row">
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === '__all__' }"
                  @click="selectSourceScope('__all__')"
                >
                  全部来源
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === 'structural' }"
                  @click="selectSourceScope('structural')"
                >
                  仅结构
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === 'rule' }"
                  @click="selectSourceScope('rule')"
                >
                  仅规则
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === 'llm' }"
                  @click="selectSourceScope('llm')"
                >
                  仅推理关系
                </button>
              </div>
              <p class="legend-hint">默认突出关系类型、方向和来源范围，内部依据只在详情里弱展示。</p>
            </div>

            <div class="detail-block">
              <h3>{{ selectedEdge ? '关系详情' : selectedNode ? '节点详情' : '图谱读取' }}</h3>
              <template v-if="selectedEdge">
                <div class="detail-title">{{ edgeLabel(selectedEdge.type) }}</div>
                <p class="detail-kind">
                  {{ resolveNodeLabel(selectedEdge.source) }} → {{ resolveNodeLabel(selectedEdge.target) }}
                </p>
                <dl>
                  <div v-for="item in selectedEdgeDetails" :key="item.key" class="detail-pair">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </div>
                </dl>
                <details v-if="selectedEdgeInternalDetails.length" class="evidence-panel">
                  <summary>查看内部依据</summary>
                  <dl>
                    <div v-for="item in selectedEdgeInternalDetails" :key="item.key" class="detail-pair">
                      <dt>{{ item.label }}</dt>
                      <dd>{{ item.value }}</dd>
                    </div>
                  </dl>
                </details>
              </template>
              <template v-else-if="selectedNode">
                <div class="detail-title">{{ selectedNode.label }}</div>
                <p class="detail-kind">需求 · {{ levelLabel(normalizeLevel(selectedNode)) }}</p>
                <dl>
                  <div v-for="item in selectedNodeDetails" :key="item.key" class="detail-pair">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  class="detail-action-btn"
                  :disabled="!selectedNode?.properties?.req_id"
                  @click="openAnalysisDrawer"
                >
                  发起变更分析
                </button>
              </template>
              <p v-else class="detail-empty">
                点击图中的节点或关系，查看层级、关系类型、来源范围和简短依据。
              </p>
            </div>
          </aside>

          <div class="graph-stage" :class="{ 'with-analysis': isAnalysisDrawerOpen }">
            <div v-if="graphError" class="state-panel error-state">{{ graphError }}</div>
            <div v-else-if="!hasGraph && !isLoadingGraph" class="state-panel">
              选择项目后，点击“生成图谱”开始生成需求图谱。
            </div>
            <div v-else-if="isLoadingGraph" class="state-panel">
              正在生成结构/规则关系图谱。
            </div>
            <div v-else-if="isInferringGraph" class="state-panel">
              正在基于候选对追加 LLM 补强关系。
            </div>
            <div ref="chartContainer" class="graph-chart"></div>
            <aside v-if="isAnalysisDrawerOpen" class="analysis-drawer">
              <div class="analysis-drawer-header">
                <div>
                  <h3>单需求变更分析</h3>
                  <p>{{ analysisDraft.before.title || selectedNode?.label || '未命名需求' }}</p>
                </div>
                <button type="button" class="clear-filter" @click="closeAnalysisDrawer">关闭</button>
              </div>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>变更输入</h4>
                  <button
                    type="button"
                    class="action-btn analysis-submit-btn"
                    :disabled="analysisLoading"
                    @click="submitAnalysis"
                  >
                    {{ analysisLoading ? '分析中' : '开始分析' }}
                  </button>
                </div>
                <div class="analysis-form">
                  <label class="analysis-field">
                    <span>标题</span>
                    <input v-model="analysisDraft.title" type="text" class="analysis-input" />
                  </label>
                  <label class="analysis-field">
                    <span>描述</span>
                    <textarea v-model="analysisDraft.description" class="analysis-textarea"></textarea>
                  </label>
                  <label class="analysis-field">
                    <span>标签</span>
                    <input
                      v-model="analysisDraft.tagsInput"
                      type="text"
                      class="analysis-input"
                      placeholder="用逗号分隔多个标签"
                    />
                  </label>
                  <div class="analysis-inline-fields">
                    <label class="analysis-field">
                      <span>优先级</span>
                      <select v-model="analysisDraft.priority" class="analysis-input">
                        <option value="">未设置</option>
                        <option v-for="option in priorityOptions" :key="option.value" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </label>
                    <label class="analysis-field">
                      <span>状态</span>
                      <select v-model="analysisDraft.status" class="analysis-input">
                        <option value="">未设置</option>
                        <option v-for="option in requirementStatusOptions" :key="option.value" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </label>
                  </div>
                </div>
                <p v-if="analysisError" class="analysis-state error">{{ analysisError }}</p>
              </section>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>变更摘要</h4>
                  <span v-if="analysisChangedFields.length" class="analysis-chip emphasis">
                    {{ analysisChangedFields.length }} 个字段变化
                  </span>
                </div>
                <div v-if="analysisDiffRows.length" class="analysis-diff-list">
                  <article
                    v-for="row in analysisDiffRows"
                    :key="row.field"
                    class="analysis-diff-card"
                    :class="{ changed: row.changed }"
                  >
                    <div class="analysis-diff-header">
                      <strong>{{ row.label }}</strong>
                      <span v-if="row.changed" class="analysis-chip">已变更</span>
                    </div>
                    <div class="analysis-diff-body">
                      <div>
                        <span>Before</span>
                        <p>{{ row.before || '空' }}</p>
                      </div>
                      <div>
                        <span>After</span>
                        <p>{{ row.after || '空' }}</p>
                      </div>
                    </div>
                  </article>
                </div>
              </section>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>影响结果</h4>
                  <span v-if="analysisResult?.summary" class="analysis-chip">
                    {{ analysisStatusLabel(analysisResult.summary.analysis_status) }}
                  </span>
                </div>
                <p v-if="analysisResult?.summary?.message" class="analysis-state">
                  {{ analysisResult.summary.message }}
                </p>

                <div v-if="analysisSummaryCards.length" class="analysis-summary-grid">
                  <article v-for="item in analysisSummaryCards" :key="item.key" class="analysis-summary-card">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </article>
                </div>

                <div
                  v-if="analysisResultStatus === 'completed' && analysisDisplayedImpacts.length"
                  class="analysis-impact-list"
                >
                  <button
                    v-for="item in analysisDisplayedImpacts"
                    :key="item.requirement_id"
                    type="button"
                    class="analysis-impact-item"
                    :class="{ active: analysisFocusedRequirementId === item.requirement_id }"
                    @click="focusAnalysisItem(item.requirement_id)"
                  >
                    <div class="analysis-impact-top">
                      <strong>{{ item.title }}</strong>
                      <span :class="['risk-badge', item.impact_level]">
                        {{ impactLevelLabel(item.impact_level) }}
                      </span>
                    </div>
                    <div class="analysis-impact-meta">
                      <span>{{ item.source_level || 'UNKNOWN_LEVEL' }}</span>
                      <span>{{ item.trigger_relations.join(' / ') }}</span>
                      <span>{{ item.min_distance }} 跳</span>
                    </div>
                    <p>{{ item.short_reason }}</p>
                  </button>
                </div>

                <p
                  v-else-if="analysisResultStatus === 'completed' && !analysisDisplayedImpacts.length && !analysisAdvisories.length"
                  class="analysis-state"
                >
                  本次变更未命中主影响范围。
                </p>

                <div v-if="analysisFocusedPath" class="analysis-path-block">
                  <div class="analysis-subtitle">最短传播路径</div>
                  <div class="analysis-path-chain">
                    <div v-for="(segment, index) in analysisFocusedPath.path" :key="`${segment.source}-${segment.target}-${index}`" class="analysis-path-segment">
                      <span class="segment-node">{{ resolveRequirementTitle(segment.source) }}</span>
                      <span class="segment-arrow">{{ edgeLabel(segment.type) }}</span>
                      <span class="segment-node">{{ resolveRequirementTitle(segment.target) }}</span>
                    </div>
                  </div>
                  <p>{{ analysisFocusedPath.reason }}</p>
                </div>

                <div v-if="analysisAdvisories.length" class="analysis-advisory-block">
                  <div class="analysis-subtitle">建议关注</div>
                  <div class="analysis-advisory-list">
                    <button
                      v-for="item in analysisAdvisories"
                      :key="item.requirement_id"
                      type="button"
                      class="analysis-advisory-item"
                      @click="focusAnalysisItem(item.requirement_id)"
                    >
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.source_level || 'UNKNOWN_LEVEL' }}</span>
                      <p>{{ item.reason }}</p>
                    </button>
                  </div>
                </div>
              </section>
            </aside>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import Sidebar from '../../components/beta/Sidebar.vue'
import { manageApi, requirementChangeApi, requirementGraphApi } from '@/api'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirement-graph')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

const projects = ref([])
const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
const sessionId = ref(localStorage.getItem('lastSessionId') || '')
const isLoadingProjects = ref(false)
const isLoadingGraph = ref(false)
const isInferringGraph = ref(false)
const graphError = ref('')
const graphData = ref({ nodes: [], edges: [], stats: {} })
const selectedNode = ref(null)
const selectedEdge = ref(null)
const selectedLevel = ref('__all__')
const selectedEdgeType = ref('__all__')
const selectedSourceScope = ref('__all__')
const analysisDraft = ref(createEmptyAnalysisDraft())
const analysisLoading = ref(false)
const analysisResult = ref(null)
const analysisFocusedRequirementId = ref('')
const analysisError = ref('')
const chartContainer = ref(null)
let chart = null
let resizeObserver = null

const levelPalette = {
  L1: { fill: '#dbeafe', border: '#2563eb' },
  L2: { fill: '#dcfce7', border: '#16a34a' },
  L3: { fill: '#fef3c7', border: '#d97706' },
  L4: { fill: '#fee2e2', border: '#dc2626' },
  UNKNOWN_LEVEL: { fill: '#e2e8f0', border: '#64748b' },
}

const edgeLegend = [
  { type: 'REFINES', label: '细化', color: '#0ea5e9' },
  { type: 'DEPENDS_ON', label: '依赖', color: '#f59e0b' },
  { type: 'CONFLICTS_WITH', label: '冲突', color: '#ef4444' },
  { type: 'SIMILAR_TO', label: '同类相似', color: '#22c55e' },
  { type: 'INCLUDES', label: '包含', color: '#0f766e' },
  { type: 'EXTENDS', label: '扩展', color: '#3b82f6' },
  { type: 'IMPACTS', label: '影响', color: '#14b8a6' },
  { type: 'VALIDATES_WITH', label: '验证关联', color: '#65a30d' },
]
const priorityOptions = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
]
const requirementStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'under_review', label: '评审中' },
  { value: 'confirmed', label: '已确认' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'archived', label: '已归档' },
]

const stats = computed(() => graphData.value?.stats || {})
const hasGraph = computed(() => (graphData.value?.nodes || []).length > 0)
const levelCounts = computed(() => stats.value.level_counts || {})
const levelLegend = computed(() =>
  ['L1', 'L2', 'L3', 'L4', 'UNKNOWN_LEVEL']
    .map(label => ({
      label,
      count: levelCounts.value?.[label] || 0,
      color: levelFillColorByLevel(label),
    }))
    .filter(item => item.count > 0),
)
const isAnalysisDrawerOpen = computed(() => Boolean(analysisDraft.value.requirementId))
const analysisPreview = computed(() => {
  const before = analysisDraft.value.before || createAnalysisSnapshot()
  const after = {
    title: analysisDraft.value.title || '',
    description: analysisDraft.value.description || '',
    tags: normalizeTagInput(analysisDraft.value.tagsInput),
    priority: analysisDraft.value.priority || null,
    status: analysisDraft.value.status || null,
  }
  const changedFields = analysisFieldOrder().filter(field => !analysisValueEquals(before[field], after[field]))
  return { before, after, changedFields }
})
const analysisChangedFields = computed(() => analysisResult.value?.changed_fields || analysisPreview.value.changedFields)
const analysisDiffRows = computed(() =>
  analysisFieldOrder().map(field => ({
    field,
    label: analysisFieldLabel(field),
    before: formatAnalysisFieldValue(field, analysisPreview.value.before[field]),
    after: formatAnalysisFieldValue(field, analysisPreview.value.after[field]),
    changed: analysisChangedFields.value.includes(field),
  })),
)
const analysisResultStatus = computed(() => analysisResult.value?.summary?.analysis_status || '')
const analysisDisplayedImpacts = computed(() => analysisResult.value?.impacted_requirements || [])
const analysisAdvisories = computed(() => analysisResult.value?.advisories?.similar_candidates || [])
const analysisSummaryCards = computed(() => {
  const summary = analysisResult.value?.summary
  if (!summary) return []
  return [
    { key: 'impacted', label: '受影响需求', value: summary.impacted_count || 0 },
    { key: 'high', label: '高风险', value: summary.high_risk_count || 0 },
    { key: 'direct', label: '直接影响', value: summary.direct_count || 0 },
    { key: 'advisory', label: '建议关注', value: summary.advisory_count || 0 },
  ]
})
const analysisFocusedPath = computed(() => {
  const paths = analysisResult.value?.propagation_paths || []
  const fallbackTarget = analysisDisplayedImpacts.value[0]?.requirement_id || ''
  const targetRequirementId = analysisFocusedRequirementId.value || fallbackTarget
  return paths.find(item => item.target_requirement_id === targetRequirementId) || null
})
const analysisImpactLookup = computed(() => Object.fromEntries(
  analysisDisplayedImpacts.value.map(item => [item.requirement_id, item]),
))
const analysisSourceRequirementId = computed(() =>
  analysisResult.value?.source_requirement?.requirement_id || analysisDraft.value.requirementId || '',
)
const analysisImpactedRequirementIds = computed(() => new Set(
  analysisDisplayedImpacts.value.map(item => item.requirement_id),
))
const analysisAdvisoryRequirementIds = computed(() => new Set(
  analysisAdvisories.value.map(item => item.requirement_id),
))
const analysisPathEdgeKeys = computed(() => {
  const keys = new Set()
  ;(analysisResult.value?.propagation_paths || []).forEach(item => {
    ;(item.path || []).forEach(segment => keys.add(analysisEdgeKey(segment)))
  })
  return keys
})
const analysisFocusedEdgeKeys = computed(() => {
  const keys = new Set()
  ;(analysisFocusedPath.value?.path || []).forEach(segment => keys.add(analysisEdgeKey(segment)))
  return keys
})

const selectedNodeDetails = computed(() => {
  const props = selectedNode.value?.properties || {}
  const rows = [
    ['source_level', '层级'],
    ['type', '类型'],
    ['status', '状态'],
    ['priority', '优先级'],
    ['assignee', '负责人'],
    ['parent_id', '父需求'],
    ['source_req_id', '来源需求'],
    ['tags', '标签'],
    ['description', '描述'],
    ['custom_fields', '扩展字段'],
  ]
  return rows
    .map(([key, label]) => ({ key, label, value: formatValue(props[key]) }))
    .filter(item => item.value)
})

const selectedEdgeDetails = computed(() => {
  const props = selectedEdge.value?.properties || {}
  const rows = [
    ['type', '关系类型', edgeLabel(selectedEdge.value?.type)],
    ['source_node', '起点', resolveNodeLabel(selectedEdge.value?.source)],
    ['target_node', '终点', resolveNodeLabel(selectedEdge.value?.target)],
    ['source_kind', '来源范围', edgeSourceLabel(selectedEdge.value)],
    ['source_detail', '来源明细', edgeSourceDetailLabel(selectedEdge.value)],
  ]
  return rows
    .map(([key, label, preset]) => ({ key, label, value: preset || '' }))
    .filter(item => item.value)
})

function createAnalysisSnapshot() {
  return {
    title: '',
    description: '',
    tags: [],
    priority: null,
    status: null,
  }
}

function createEmptyAnalysisDraft() {
  return {
    requirementId: '',
    before: createAnalysisSnapshot(),
    title: '',
    description: '',
    tagsInput: '',
    priority: '',
    status: '',
  }
}

function analysisFieldOrder() {
  return ['title', 'description', 'tags', 'priority', 'status']
}

function analysisFieldLabel(field) {
  return {
    title: '标题',
    description: '描述',
    tags: '标签',
    priority: '优先级',
    status: '状态',
  }[field] || field
}

function normalizeTagInput(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  return String(value || '')
    .split(/[，,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function analysisValueEquals(left, right) {
  if (Array.isArray(left) || Array.isArray(right)) {
    return JSON.stringify(left || []) === JSON.stringify(right || [])
  }
  return (left ?? null) === (right ?? null)
}

function formatAnalysisFieldValue(field, value) {
  if (field === 'tags') return (value || []).join('、')
  if (field === 'priority') return priorityLabel(value)
  if (field === 'status') return requirementStatusLabel(value)
  return String(value || '')
}

function buildAnalysisDraftFromNode(node) {
  const props = node?.properties || {}
  return {
    requirementId: props.req_id || '',
    before: {
      title: props.title || node?.label || '',
      description: props.description || '',
      tags: Array.isArray(props.tags) ? props.tags : normalizeTagInput(props.tags),
      priority: props.priority || null,
      status: props.status || null,
    },
    title: props.title || node?.label || '',
    description: props.description || '',
    tagsInput: (Array.isArray(props.tags) ? props.tags : normalizeTagInput(props.tags)).join(', '),
    priority: props.priority || '',
    status: props.status || '',
  }
}

function resetAnalysisState({ closeDrawer = true } = {}) {
  if (closeDrawer) {
    analysisDraft.value = createEmptyAnalysisDraft()
  }
  analysisLoading.value = false
  analysisResult.value = null
  analysisFocusedRequirementId.value = ''
  analysisError.value = ''
}

function clearGraphState() {
  graphError.value = ''
  graphData.value = { nodes: [], edges: [], stats: {} }
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  resetAnalysisState()
  renderGraph()
}

function openAnalysisDrawer() {
  if (!selectedNode.value?.properties?.req_id) return
  selectedLevel.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  analysisDraft.value = buildAnalysisDraftFromNode(selectedNode.value)
  analysisLoading.value = false
  analysisResult.value = null
  analysisFocusedRequirementId.value = analysisDraft.value.requirementId
  analysisError.value = ''
  renderGraph()
}

function closeAnalysisDrawer() {
  resetAnalysisState()
  renderGraph()
}

function buildAnalysisChanges() {
  const { before, after } = analysisPreview.value
  return analysisFieldOrder().reduce((result, field) => {
    if (!analysisValueEquals(before[field], after[field])) {
      result[field] = field === 'tags' ? [...(after[field] || [])] : after[field]
    }
    return result
  }, {})
}

async function submitAnalysis() {
  if (!analysisDraft.value.requirementId) return
  const projectId =
    selectedProjectId.value ||
    selectedNode.value?.properties?.project_id ||
    graphData.value?.nodes?.find(node => node.properties?.req_id === analysisDraft.value.requirementId)?.properties?.project_id
  if (!projectId) {
    analysisError.value = '缺少 project_id，当前无法发起变更分析'
    return
  }
  analysisLoading.value = true
  analysisError.value = ''
  try {
    analysisResult.value = await requirementChangeApi.analyzeRequirementChange({
      projectId,
      requirementId: analysisDraft.value.requirementId,
      changes: buildAnalysisChanges(),
    })
    analysisFocusedRequirementId.value =
      analysisResult.value?.impacted_requirements?.[0]?.requirement_id ||
      analysisResult.value?.source_requirement?.requirement_id ||
      analysisDraft.value.requirementId
    renderGraph()
  } catch (err) {
    analysisResult.value = null
    analysisError.value = err.message || '变更分析失败'
    renderGraph()
  } finally {
    analysisLoading.value = false
  }
}

function focusAnalysisItem(requirementId) {
  analysisFocusedRequirementId.value = requirementId
  const targetNode = graphData.value?.nodes?.find(node => node.properties?.req_id === requirementId)
  if (targetNode) {
    selectedNode.value = targetNode
    selectedEdge.value = null
  }
  renderGraph()
}

const selectedEdgeInternalDetails = computed(() => {
  const props = selectedEdge.value?.properties || {}
  const rows = [
    ['reason', '内部依据', formatValue(props.reason)],
    ['evidence', '触发证据', formatValue(props.evidence)],
    ['confidence', '内部置信度', formatConfidence(props.confidence ?? selectedEdge.value?.weight)],
    ['model', '推理模型', formatValue(props.model)],
  ]
  return rows
    .map(([key, label, preset]) => ({ key, label, value: preset || '' }))
    .filter(item => item.value)
})

async function loadProjects() {
  isLoadingProjects.value = true
  try {
    const data = await manageApi.listProjects()
    projects.value = data?.projects || []
    if (!selectedProjectId.value && projects.value[0]?.project_id) {
      selectedProjectId.value = projects.value[0].project_id
    }
  } catch (err) {
    graphError.value = err.message || '项目列表加载失败'
  } finally {
    isLoadingProjects.value = false
  }
}

async function syncProjectSession() {
  if (!selectedProjectId.value) return
  try {
    const project = await manageApi.getProject(selectedProjectId.value)
    if (project?.current_session_id) {
      sessionId.value = project.current_session_id
    }
  } catch (err) {
    console.warn('加载项目会话失败', err)
  }
}

async function loadGraph() {
  graphError.value = ''
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  resetAnalysisState()
  if (!selectedProjectId.value && !sessionId.value) {
    graphError.value = '请选择项目或填写 Session ID'
    return
  }
  isLoadingGraph.value = true
  try {
    const resp = await requirementGraphApi.getGraph({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 900,
      infer: false,
      inferenceLimit: 48,
      model: 'deepseek-reasoner',
    })
    graphData.value = resp?.data || { nodes: [], edges: [], stats: {} }
    await nextTick()
    renderGraph()
  } catch (err) {
    graphError.value = err.message || '需求图谱生成失败'
    graphData.value = { nodes: [], edges: [], stats: {} }
    renderGraph()
  } finally {
    isLoadingGraph.value = false
  }
}

async function inferGraph() {
  graphError.value = ''
  selectedNode.value = null
  selectedEdge.value = null
  resetAnalysisState()
  if (!selectedProjectId.value && !sessionId.value) {
    graphError.value = '请选择项目或填写 Session ID'
    return
  }
  isInferringGraph.value = true
  try {
    const resp = await requirementGraphApi.inferGraph({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 80,
      inferenceLimit: 48,
      model: 'deepseek-reasoner',
    })
    graphData.value = resp?.data || { nodes: [], edges: [], stats: {} }
    await nextTick()
    renderGraph()
  } catch (err) {
    graphError.value = err.message || '需求图谱推理失败'
  } finally {
    isInferringGraph.value = false
  }
}

function initChart() {
  if (!chartContainer.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartContainer.value)
  chart.on('click', params => {
    if (params.dataType === 'node') {
      selectedNode.value = params.data.raw
      selectedEdge.value = null
      return
    }
    if (params.dataType === 'edge') {
      selectedEdge.value = params.data.raw
      selectedNode.value = null
    }
  })
  resizeObserver = new ResizeObserver(() => {
    chart?.resize()
    patchFullCanvasRoamArea()
  })
  resizeObserver.observe(chartContainer.value)
  renderGraph()
}

function patchFullCanvasRoamArea() {
  const graphView = chart?._chartsViews?.find(view => view?.type === 'graph')
  const controller = graphView?._controller
  if (!controller || !chartContainer.value) return

  // ECharts graph defaults to using the rendered graph bounds as the pan hit-area,
  // which makes the blank edge gutters feel non-draggable. Expand it to the
  // full chart viewport so the canvas can always be dragged from its edges.
  controller.setPointerChecker((_event, x, y) => {
    const width = chartContainer.value?.clientWidth || 0
    const height = chartContainer.value?.clientHeight || 0
    return x >= 0 && y >= 0 && x <= width && y <= height
  })
}

function renderGraph() {
  if (!chart) return
  const allNodes = graphData.value?.nodes || []
  const allEdges = graphData.value?.edges || []
  const { nodes, edges } = filterGraph(allNodes, allEdges)
  if (!nodes.length) {
    chart.clear()
    return
  }

  const visibleCategories = buildChartCategories(nodes)
  const categories = visibleCategories.map(item => ({
    name: item.name,
    itemStyle: { color: item.color },
  }))
  const categoryIndex = Object.fromEntries(categories.map((item, index) => [item.name, index]))

  chart.setOption({
    backgroundColor: '#f8fafc',
    tooltip: {
      trigger: 'item',
      borderWidth: 1,
      borderColor: 'rgba(15, 23, 42, 0.12)',
      backgroundColor: 'rgba(255, 255, 255, 0.96)',
      textStyle: { color: '#0f172a' },
      formatter(params) {
        const raw = params.data?.raw
        if (!raw) return params.name
        if (params.dataType === 'edge') {
          return `${edgeLabel(raw.type)}<br/>${edgeSourceLabel(raw)}`
        }
        return `${levelLabel(normalizeLevel(raw))}<br/>${raw.label}`
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        legendHoverLink: false,
        categories,
        roam: true,
        draggable: true,
        data: nodes.map(node => {
          const chartCategory = chartCategoryName(node)
          const color = categoryIndex[chartCategory] !== undefined
            ? categories[categoryIndex[chartCategory]].itemStyle.color
            : '#64748b'
          const visual = analysisNodeVisual(node)
          return {
            id: node.id,
            name: node.label,
            raw: node,
            category: categoryIndex[chartCategory] ?? 0,
            symbol: 'circle',
            symbolSize: visual.symbolSize ?? nodeSize(node),
            label: {
              show: true,
              position: 'right',
              color: visual.labelColor || '#0f172a',
              fontSize: 12,
              width: 170,
              overflow: 'truncate',
            },
            itemStyle: {
              color: visual.fill || levelFillColor(node),
              borderColor: visual.borderColor || levelBorderColor(node),
              borderWidth: visual.borderWidth ?? 3,
              shadowBlur: visual.shadowBlur ?? 10,
              shadowColor: visual.shadowColor || 'rgba(15, 23, 42, 0.18)',
              opacity: visual.opacity ?? 1,
            },
          }
        }),
        links: edges.map(edge => ({
          source: edge.source,
          target: edge.target,
          label: { show: false },
          raw: edge,
          lineStyle: edgeLineStyle(edge),
        })),
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 9],
        force: {
          repulsion: 260,
          edgeLength: [90, 190],
          gravity: 0.06,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 4, opacity: 1 },
        },
        animationDuration: 900,
        animationEasingUpdate: 'quinticInOut',
      },
    ],
  }, true)
  patchFullCanvasRoamArea()
  focusAnalysisRequirement(analysisFocusedRequirementId.value || analysisSourceRequirementId.value)
}

function normalizeLevel(node) {
  const level = String(node.properties?.source_level || node.properties?.level || node.group || '').toUpperCase()
  if (level.includes('L1')) return 'L1'
  if (level.includes('L2')) return 'L2'
  if (level.includes('L3')) return 'L3'
  if (level.includes('L4')) return 'L4'
  return 'UNKNOWN_LEVEL'
}

function chartCategoryName(node) {
  return normalizeLevel(node)
}

function buildChartCategories(nodes) {
  const labels = []
  nodes.forEach(node => {
    const label = chartCategoryName(node)
    if (!labels.includes(label)) labels.push(label)
  })
  return labels.map(label => ({
    name: label,
    color: levelFillColorByLevel(label),
  }))
}

function levelLabel(level) {
  return {
    L1: 'L1 方向层',
    L2: 'L2 业务层',
    L3: 'L3 方案层',
    L4: 'L4 实现层',
    UNKNOWN_LEVEL: '未知层级',
  }[level] || level || '未知层级'
}

function levelFillColor(node) {
  return levelFillColorByLevel(normalizeLevel(node))
}

function levelFillColorByLevel(level) {
  return levelPalette[level]?.fill || levelPalette.UNKNOWN_LEVEL.fill
}

function levelBorderColor(node) {
  return levelPalette[normalizeLevel(node)]?.border || levelPalette.UNKNOWN_LEVEL.border
}

function filterGraph(nodes, edges) {
  const filteredEdges = edges.filter(edge => edgeMatchesFilters(edge))
  if (selectedLevel.value === '__all__') {
    if (selectedEdgeType.value === '__all__' && selectedSourceScope.value === '__all__') {
      return { nodes, edges: filteredEdges }
    }
    const visibleIds = new Set(filteredEdges.flatMap(edge => [edge.source, edge.target]))
    return {
      nodes: nodes.filter(node => visibleIds.has(node.id)),
      edges: filteredEdges,
    }
  }
  const selectedRequirementIds = new Set(nodes.filter(node => normalizeLevel(node) === selectedLevel.value).map(node => node.id))
  if (!selectedRequirementIds.size) return { nodes: [], edges: [] }

  const includedIds = new Set(selectedRequirementIds)
  filteredEdges.forEach(edge => {
    if (selectedRequirementIds.has(edge.source)) includedIds.add(edge.target)
    if (selectedRequirementIds.has(edge.target)) includedIds.add(edge.source)
  })
  const filteredNodes = nodes.filter(node => includedIds.has(node.id))
  const visibleIds = new Set(filteredNodes.map(node => node.id))
  return {
    nodes: filteredNodes,
    edges: filteredEdges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
  }
}

function selectLevel(label) {
  selectedLevel.value = label
  selectedNode.value = null
  selectedEdge.value = null
  renderGraph()
}

function selectEdgeType(type) {
  selectedEdgeType.value = type
  selectedEdge.value = null
  renderGraph()
}

function selectSourceScope(scope) {
  selectedSourceScope.value = scope
  selectedEdge.value = null
  renderGraph()
}

function resetEdgeFilters() {
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  selectedEdge.value = null
  renderGraph()
}

function nodeSize(node) {
  const priority = Number(node.properties?.priority || 0)
  if (priority >= 4) return 42
  if (priority >= 2) return 36
  return 32
}

function analysisNodeVisual(node) {
  const requirementId = node?.properties?.req_id
  if (!requirementId) return {}
  const focused = analysisFocusedRequirementId.value === requirementId
  if (analysisSourceRequirementId.value === requirementId) {
    return {
      fill: '#ccfbf1',
      borderColor: focused ? '#0f172a' : '#0f766e',
      borderWidth: focused ? 6 : 5,
      shadowBlur: 18,
      shadowColor: 'rgba(15, 118, 110, 0.28)',
      symbolSize: nodeSize(node) + 4,
    }
  }
  if (analysisImpactedRequirementIds.value.has(requirementId)) {
    const impact = analysisImpactLookup.value[requirementId]
    const borderColor = impact?.impact_level === 'high' ? '#dc2626' : '#d97706'
    return {
      borderColor: focused ? '#0f172a' : borderColor,
      borderWidth: focused ? 6 : 4.5,
      shadowBlur: focused ? 16 : 12,
      shadowColor: impact?.impact_level === 'high' ? 'rgba(220, 38, 38, 0.22)' : 'rgba(217, 119, 6, 0.22)',
      symbolSize: nodeSize(node) + (focused ? 4 : 2),
    }
  }
  if (analysisAdvisoryRequirementIds.value.has(requirementId)) {
    return {
      borderColor: focused ? '#0f172a' : '#94a3b8',
      borderWidth: focused ? 5 : 3,
      shadowBlur: focused ? 14 : 6,
      shadowColor: 'rgba(148, 163, 184, 0.18)',
      opacity: 0.76,
    }
  }
  return {}
}

function edgeColor(type) {
  return edgeLegend.find(item => item.type === type)?.color || '#64748b'
}

function edgeLabel(type) {
  return edgeLegend.find(item => item.type === type)?.label || type || ''
}

function resolveNodeLabel(nodeId) {
  if (!nodeId) return ''
  return graphData.value?.nodes?.find(node => node.id === nodeId)?.label || nodeId
}

function edgeSourceType(edge) {
  return edge?.properties?.source_kind || 'rule'
}

function edgeSourceLabel(edge) {
  const kinds = edge?.properties?.source_kinds || [edgeSourceType(edge)]
  return kinds.map(kind => sourceScopeLabel(kind)).join(' + ')
}

function edgeSourceDetailLabel(edge) {
  const details = edge?.properties?.source_details || []
  if (!details.length) return formatValue(edge?.properties?.source_detail || edge?.properties?.source)
  return details.map(item => sourceText(item)).join('、')
}

function sourceScopeLabel(scope) {
  return {
    structural: '结构',
    rule: '规则',
    llm: '推理',
  }[scope] || scope
}

function edgeMatchesFilters(edge) {
  if (selectedEdgeType.value !== '__all__' && edge.type !== selectedEdgeType.value) return false
  const scopes = edge?.properties?.source_kinds || [edgeSourceType(edge)]
  if (selectedSourceScope.value !== '__all__' && !scopes.includes(selectedSourceScope.value)) {
    return false
  }
  return true
}

function edgeLineStyle(edge) {
  const sourceScope = edgeSourceType(edge)
  const edgeKey = analysisEdgeKey({
    source: edge.source.replace(/^req:/, ''),
    target: edge.target.replace(/^req:/, ''),
    type: edge.type,
  })
  const inAnyPath = analysisPathEdgeKeys.value.has(edgeKey)
  const inFocusedPath = analysisFocusedEdgeKeys.value.has(edgeKey)
  return {
    color: edgeColor(edge.type),
    width: inFocusedPath
      ? 5.6
      : inAnyPath
        ? 4.4
        : sourceScope === 'structural'
          ? 3.4
          : sourceScope === 'rule'
            ? 2.8
            : 2.4,
    opacity: inFocusedPath
      ? 1
      : inAnyPath
        ? 0.94
        : edge.type === 'CONFLICTS_WITH'
          ? 0.9
          : sourceScope === 'llm'
            ? 0.84
            : 0.7,
    type: sourceScope === 'llm' ? 'dashed' : 'solid',
    curveness: edge.type === 'CONFLICTS_WITH' ? 0.22 : 0.1,
  }
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === '') return ''
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toFixed(2)
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.filter(Boolean).join('、')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return sourceText(String(value))
}

function sourceText(value) {
  return {
    llm_inference: '大模型补充',
    'manage_requirements.parent_id': '父子结构',
    'manage_requirements.source_req_id': '来源结构',
    rule_dependency_signal_match: '依赖规则',
    rule_conflict_signal_match: '冲突规则',
    rule_validation_overlap: '验证规则',
    rule_similarity_recall: '相似召回',
    manage_requirements: '需求管理',
  }[value] || value
}

function analysisEdgeKey(segment) {
  return `${segment.type}:${toRequirementNodeId(segment.source)}->${toRequirementNodeId(segment.target)}`
}

function toRequirementNodeId(requirementId) {
  const text = String(requirementId || '')
  if (!text) return ''
  return text.startsWith('req:') ? text : `req:${text}`
}

function focusAnalysisRequirement(requirementId) {
  if (!chart || !requirementId) return
  const series = chart.getOption()?.series?.[0]
  const data = series?.data || []
  const dataIndex = data.findIndex(item => item.id === toRequirementNodeId(requirementId))
  if (dataIndex < 0) return
  chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex })
  chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex })
}

function resolveRequirementTitle(requirementId) {
  return graphData.value?.nodes?.find(node => node.properties?.req_id === requirementId)?.label || requirementId
}

function impactLevelLabel(level) {
  return {
    high: '高风险',
    medium: '中风险',
    low: '低风险',
  }[level] || level || '未标记'
}

function analysisStatusLabel(status) {
  return {
    completed: '已完成',
    no_impact: '无影响',
    no_effective_change: '无有效变更',
  }[status] || status || '待分析'
}

function priorityLabel(priority) {
  return {
    low: '低',
    medium: '中',
    high: '高',
  }[priority] || priority || ''
}

function requirementStatusLabel(status) {
  return {
    draft: '草稿',
    under_review: '评审中',
    confirmed: '已确认',
    in_progress: '进行中',
    completed: '已完成',
    archived: '已归档',
  }[status] || status || ''
}

watch(selectedProjectId, async (value) => {
  if (value) {
    localStorage.setItem('lastProjectId', value)
    sessionId.value = ''
    await syncProjectSession()
    clearGraphState()
    return
  }

  localStorage.removeItem('lastProjectId')
  sessionId.value = ''
  clearGraphState()
})

watch(sessionId, (value) => {
  if (value) {
    localStorage.setItem('lastSessionId', value)
    return
  }
  localStorage.removeItem('lastSessionId')
})

watch(levelCounts, () => {
  if (selectedLevel.value !== '__all__' && !levelCounts.value[selectedLevel.value]) {
    selectedLevel.value = '__all__'
  }
}, { deep: true })

watch(analysisFocusedRequirementId, () => {
  if (analysisResult.value) {
    renderGraph()
  }
})

onMounted(async () => {
  initChart()
  await loadProjects()
  if (selectedProjectId.value) {
    await syncProjectSession()
  }
})

onBeforeUnmount(() => {
  if (resizeObserver && chartContainer.value) resizeObserver.unobserve(chartContainer.value)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.graph-canvas {
  min-width: 0;
}

.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: min(760px, 100%);
}

.project-select,
.session-input {
  height: 38px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 6px;
  background: #ffffff;
  color: #0f172a;
  padding: 0 12px;
  outline: none;
}

.project-select {
  min-width: 190px;
}

.session-input {
  flex: 1;
  min-width: 180px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.action-btn {
  height: 38px;
  border: 0;
  border-radius: 6px;
  padding: 0 16px;
  background: #0f766e;
  color: #ffffff;
  font-weight: 700;
  cursor: pointer;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.graph-shell {
  display: grid;
  grid-template-columns: 310px 1fr;
  gap: 16px;
  height: calc(100vh - 150px);
  min-height: 620px;
}

.graph-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.metric-grid,
.legend-block,
.detail-block {
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 14px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.infer-btn {
  background: #1d4ed8;
}

.metric-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 6px;
  padding: 10px;
  background: #f8fafc;
}

.metric-item span,
.legend-row span,
.detail-kind,
.detail-empty,
.legend-hint,
dt {
  color: #64748b;
  font-size: 12px;
}

.metric-item strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  font-size: 22px;
}

.legend-block h3,
.detail-block h3 {
  margin: 0;
  color: #0f172a;
  font-size: 15px;
}

.compact-block h3 {
  margin-bottom: 12px;
}

.detail-block h3 {
  margin-bottom: 12px;
}

.block-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.source-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.source-badge.subtle {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
}

.clear-filter {
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 6px;
  background: #ffffff;
  color: #475569;
  height: 28px;
  padding: 0 10px;
  cursor: pointer;
}

.clear-filter.active {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-chip {
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 999px;
  background: #ffffff;
  color: #475569;
  min-height: 30px;
  padding: 0 12px;
  cursor: pointer;
  font-size: 12px;
}

.filter-chip.active {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.confidence-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  color: #334155;
  font-size: 12px;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-chip {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 6px;
  background: #ffffff;
  color: #0f172a;
  cursor: pointer;
  padding: 0 10px;
  text-align: left;
}

.category-chip.active {
  border-color: rgba(15, 118, 110, 0.45);
  background: rgba(20, 184, 166, 0.08);
}

.category-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.category-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #334155;
  font-size: 13px;
}

.category-chip b {
  color: #0f172a;
  font-size: 12px;
}

.legend-hint {
  margin: 10px 0 0;
  line-height: 1.5;
}

.legend-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 28px;
}

.legend-button {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 6px;
  background: #ffffff;
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
}

.legend-button.active {
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.legend-line {
  height: 3px;
  border-radius: 3px;
}

.legend-row b {
  color: #0f172a;
  font-size: 12px;
}

.detail-title {
  color: #0f172a;
  font-weight: 700;
  line-height: 1.45;
}

.detail-action-btn {
  margin-top: 14px;
  width: 100%;
  min-height: 36px;
  border: 1px solid rgba(15, 118, 110, 0.24);
  border-radius: 8px;
  background: rgba(20, 184, 166, 0.1);
  color: #0f766e;
  font-weight: 700;
  cursor: pointer;
}

.detail-action-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.detail-block dl {
  margin: 12px 0 0;
}

.detail-pair {
  display: contents;
}

.detail-block dt {
  margin-top: 10px;
}

.detail-block dd {
  margin: 4px 0 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.evidence-panel {
  margin-top: 14px;
  border-top: 1px dashed rgba(15, 23, 42, 0.12);
  padding-top: 12px;
}

.evidence-panel summary {
  cursor: pointer;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.evidence-panel dl {
  margin-top: 10px;
}

.graph-stage {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
  min-width: 0;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
}

.graph-stage.with-analysis {
  grid-template-columns: minmax(0, 1fr) 390px;
}

.graph-chart {
  width: 100%;
  height: 100%;
  min-height: 620px;
}

.analysis-drawer {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  overflow: auto;
  background:
    radial-gradient(circle at top, rgba(20, 184, 166, 0.08), transparent 38%),
    linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border-left: 1px solid rgba(15, 23, 42, 0.08);
  padding: 16px;
}

.analysis-drawer-header,
.analysis-block-title,
.analysis-diff-header,
.analysis-impact-top,
.analysis-impact-meta,
.analysis-inline-fields {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.analysis-drawer-header {
  align-items: flex-start;
}

.analysis-drawer-header h3,
.analysis-block h4 {
  margin: 0;
  color: #0f172a;
}

.analysis-drawer-header p,
.analysis-state,
.analysis-impact-item p,
.analysis-advisory-item p,
.analysis-path-block p {
  margin: 6px 0 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.analysis-block {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  padding: 14px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
}

.analysis-submit-btn {
  min-width: 92px;
  padding: 0 14px;
}

.analysis-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.analysis-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #334155;
  font-size: 12px;
}

.analysis-input,
.analysis-textarea {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
  background: #ffffff;
  color: #0f172a;
  padding: 10px 12px;
  outline: none;
}

.analysis-textarea {
  min-height: 96px;
  resize: vertical;
  font-family: inherit;
}

.analysis-chip,
.risk-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.analysis-chip {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
}

.analysis-chip.emphasis {
  background: rgba(20, 184, 166, 0.12);
  color: #0f766e;
}

.analysis-state.error {
  color: #b91c1c;
}

.analysis-diff-list,
.analysis-impact-list,
.analysis-advisory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.analysis-diff-card,
.analysis-impact-item,
.analysis-advisory-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  background: #ffffff;
  padding: 12px;
}

.analysis-impact-item,
.analysis-advisory-item {
  width: 100%;
  cursor: pointer;
  text-align: left;
}

.analysis-impact-item.active,
.analysis-advisory-item:hover {
  border-color: rgba(15, 118, 110, 0.32);
  box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
}

.analysis-diff-card.changed {
  border-color: rgba(20, 184, 166, 0.24);
  background: linear-gradient(180deg, rgba(204, 251, 241, 0.45), #ffffff);
}

.analysis-diff-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.analysis-diff-body span,
.analysis-summary-card span,
.analysis-subtitle,
.analysis-impact-meta span {
  color: #64748b;
  font-size: 11px;
}

.analysis-diff-body p {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.analysis-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.analysis-summary-card {
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
  padding: 12px;
}

.analysis-summary-card strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 22px;
}

.analysis-impact-top strong,
.analysis-advisory-item strong {
  color: #0f172a;
  font-size: 13px;
}

.risk-badge.high {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.risk-badge.medium {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.risk-badge.low {
  background: rgba(148, 163, 184, 0.14);
  color: #475569;
}

.analysis-path-block,
.analysis-advisory-block {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed rgba(15, 23, 42, 0.12);
}

.analysis-path-chain {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.analysis-path-segment {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.segment-node,
.segment-arrow {
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.08);
  padding: 8px 10px;
  color: #0f172a;
  font-size: 12px;
}

.segment-arrow {
  color: #0f766e;
  font-weight: 700;
  white-space: nowrap;
}

.state-panel {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  max-width: 360px;
  padding: 14px 18px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  color: #334155;
  border: 1px solid rgba(15, 23, 42, 0.1);
  text-align: center;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.12);
}

.error-state {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.2);
}

@media (max-width: 1100px) {
  .graph-toolbar {
    justify-content: flex-end;
  }

  .graph-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .graph-side {
    order: 2;
  }

  .graph-stage {
    min-height: 560px;
  }

  .graph-stage.with-analysis {
    grid-template-columns: 1fr;
  }

  .analysis-drawer {
    border-left: 0;
    border-top: 1px solid rgba(15, 23, 42, 0.08);
    max-height: none;
  }

  .analysis-diff-body,
  .analysis-summary-grid,
  .analysis-inline-fields {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
