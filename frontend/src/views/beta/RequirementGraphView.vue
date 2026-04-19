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
              {{ isLoadingGraph ? '生成中' : '刷新图谱' }}
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
                <span>利益相关方</span>
                <strong>{{ stats.node_counts?.stakeholder || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>关系边</span>
                <strong>{{ stats.edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>已有分析关系</span>
                <strong>{{ stats.strong_edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>推理关系</span>
                <strong>{{ stats.inferred_edge_count || 0 }}</strong>
              </div>
            </div>

            <div class="legend-block">
              <div class="block-title-row">
                <h3>需求分类</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedCategory === '__all__' }"
                  @click="selectCategory('__all__')"
                >
                  全部
                </button>
              </div>
              <div v-if="classificationLegend.length" class="category-list">
                <button
                  v-for="item in classificationLegend"
                  :key="item.label"
                  type="button"
                  class="category-chip"
                  :class="{ active: selectedCategory === item.label }"
                  @click="selectCategory(item.label)"
                >
                  <span class="category-dot" :style="{ background: item.color }"></span>
                  <span class="category-name">{{ item.label }}</span>
                  <b>{{ item.count }}</b>
                </button>
              </div>
              <p v-else class="detail-empty">暂无已保存的分类结果。</p>
              <p v-if="classificationLegend.length" class="legend-hint">
                点击分类聚焦对应需求及相邻关系。
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
                  :class="{ active: selectedSourceScope === 'analysis' }"
                  @click="selectSourceScope('analysis')"
                >
                  仅已有分析
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === 'inferred' }"
                  @click="selectSourceScope('inferred')"
                >
                  仅推理关系
                </button>
              </div>
              <label class="confidence-toggle">
                <input v-model="highConfidenceOnly" type="checkbox" />
                <span>仅看高置信度关系（>= 0.75）</span>
              </label>
              <p class="legend-hint">支持按来源、关系类型和置信度快速聚焦图谱。</p>
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
              </template>
              <template v-else-if="selectedNode">
                <div class="detail-title">{{ selectedNode.label }}</div>
                <p class="detail-kind">{{ selectedNode.kind === 'stakeholder' ? '利益相关方' : '需求' }}</p>
                <dl>
                  <div v-for="item in selectedNodeDetails" :key="item.key" class="detail-pair">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </div>
                </dl>
              </template>
              <p v-else class="detail-empty">
                点击图中的节点或关系，查看需求内容、验证约束、角色信息和推理依据。
              </p>
            </div>
          </aside>

          <div class="graph-stage">
            <div v-if="graphError" class="state-panel error-state">{{ graphError }}</div>
            <div v-else-if="!hasGraph && !isLoadingGraph" class="state-panel">
              选择项目后生成需求图谱。
            </div>
            <div v-else-if="isLoadingGraph" class="state-panel">
              正在生成需求图谱关系（含大模型推理）。
            </div>
            <div v-else-if="isInferringGraph" class="state-panel">
              正在使用大模型推理需求图谱关系。
            </div>
            <div ref="chartContainer" class="graph-chart"></div>
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
import { manageApi, requirementGraphApi } from '@/api'
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
const selectedCategory = ref('__all__')
const selectedEdgeType = ref('__all__')
const selectedSourceScope = ref('__all__')
const highConfidenceOnly = ref(false)
const chartContainer = ref(null)
let chart = null
let resizeObserver = null

const categoryPalette = [
  '#2563eb',
  '#16a34a',
  '#dc2626',
  '#9333ea',
  '#0891b2',
  '#ca8a04',
  '#db2777',
  '#4f46e5',
  '#059669',
  '#ea580c',
  '#475569',
  '#7c3aed',
]

const edgeLegend = [
  { type: 'REFINES', label: '细化', color: '#0ea5e9' },
  { type: 'DEPENDS_ON', label: '依赖', color: '#f59e0b' },
  { type: 'CONFLICTS_WITH', label: '冲突', color: '#ef4444' },
  { type: 'SIMILAR_TO', label: '同类相似', color: '#22c55e' },
  { type: 'INCLUDES', label: '包含', color: '#0f766e' },
  { type: 'EXTENDS', label: '扩展', color: '#3b82f6' },
  { type: 'IMPACTS', label: '影响', color: '#14b8a6' },
  { type: 'VALIDATES_WITH', label: '验证关联', color: '#65a30d' },
  { type: 'RAISES', label: '提出', color: '#14b8a6' },
  { type: 'OWNS', label: '负责', color: '#6366f1' },
  { type: 'AFFECTED_BY', label: '受影响', color: '#64748b' },
  { type: 'APPROVES', label: '审批', color: '#2f6fed' },
  { type: 'BENEFITS_FROM', label: '受益', color: '#22c55e' },
  { type: 'OPPOSES', label: '反对', color: '#f97316' },
  { type: 'INTEREST_CONFLICTS_WITH', label: '利益冲突', color: '#e11d48' },
  { type: 'COLLABORATES_WITH', label: '协作', color: '#0ea5e9' },
]

const stats = computed(() => graphData.value?.stats || {})
const hasGraph = computed(() => (graphData.value?.nodes || []).length > 0)
const classificationCounts = computed(() => stats.value.classification_counts || {})
const classificationLegend = computed(() =>
  Object.entries(classificationCounts.value)
    .map(([label, count], index) => ({
      label,
      count,
      color: categoryColor(label, index),
    }))
    .sort((a, b) => b.count - a.count),
)

const selectedNodeDetails = computed(() => {
  const props = selectedNode.value?.properties || {}
  const rows = [
    ['level', '层级'],
    ['type', '类型'],
    ['category', '分类'],
    ['status', '状态'],
    ['priority', '优先级'],
    ['source', '来源'],
    ['component', '目标模块'],
    ['target_modules', '目标模块'],
    ['validation_rules', '验证约束'],
    ['role', '角色'],
    ['roles', '角色集合'],
    ['department', '部门'],
    ['title', '岗位'],
    ['inference_reason', '推理依据'],
    ['inference_model', '推理模型'],
    ['content', '内容'],
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
    ['source_kind', '关系来源', edgeSourceLabel(selectedEdge.value)],
    ['confidence', '置信度', formatConfidence(selectedEdge.value?.weight)],
    ['reason', '推理依据', formatValue(props.reason)],
    ['source', '来源明细', formatValue(props.source)],
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
  selectedCategory.value = '__all__'
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
      infer: true,
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
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartContainer.value)
  renderGraph()
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
          return `${edgeLabel(raw.type)}<br/>${edgeSourceLabel(raw)}<br/>置信度 ${formatConfidence(raw.weight)}`
        }
        const kind = raw.kind === 'stakeholder' ? '利益相关方' : '需求'
        const level = raw.properties?.level || raw.group || ''
        return `${kind} ${level}<br/>${raw.label}`
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
          return {
            id: node.id,
            name: node.label,
            raw: node,
            category: categoryIndex[chartCategory] ?? 0,
            symbol: node.kind === 'stakeholder' ? 'diamond' : 'circle',
            symbolSize: node.kind === 'stakeholder' ? 48 : nodeSize(node),
            label: {
              show: true,
              position: node.kind === 'stakeholder' ? 'bottom' : 'right',
              color: '#0f172a',
              fontSize: 12,
              width: 170,
              overflow: 'truncate',
            },
            itemStyle: {
              color,
              borderColor: levelBorderColor(node),
              borderWidth: node.kind === 'stakeholder' ? 2 : 3,
              shadowBlur: node.kind === 'stakeholder' ? 12 : 8,
              shadowColor: 'rgba(15, 23, 42, 0.18)',
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
}

function normalizeLevel(node) {
  if (node.kind === 'stakeholder') return 'stakeholder'
  const level = String(node.properties?.level || node.group || '').toUpperCase()
  if (level.includes('L1')) return 'L1'
  if (level.includes('L2')) return 'L2'
  if (level.includes('L3')) return 'L3'
  if (level.includes('L4')) return 'L4'
  return 'managed'
}

function chartCategoryName(node) {
  if (node.kind === 'stakeholder') return '__stakeholder__'
  return node.properties?.category || '未分类'
}

function buildChartCategories(nodes) {
  const labels = []
  nodes.forEach(node => {
    const label = chartCategoryName(node)
    if (!labels.includes(label)) labels.push(label)
  })
  return labels.map((label, index) => ({
    name: label,
    color: label === '__stakeholder__' ? '#6366f1' : categoryColor(label, index),
  }))
}

function categoryColor(label, fallbackIndex = 0) {
  if (!label) return '#64748b'
  const labels = Object.keys(classificationCounts.value)
  const index = labels.indexOf(label)
  const paletteIndex = index >= 0 ? index : fallbackIndex
  return categoryPalette[paletteIndex % categoryPalette.length]
}

function levelBorderColor(node) {
  const colors = {
    L1: '#0f172a',
    L2: '#06b6d4',
    L3: '#f59e0b',
    L4: '#22c55e',
    managed: '#64748b',
    stakeholder: '#ffffff',
  }
  return colors[normalizeLevel(node)] || '#ffffff'
}

function filterGraph(nodes, edges) {
  const filteredEdges = edges.filter(edge => edgeMatchesFilters(edge))
  if (selectedCategory.value === '__all__') {
    if (
      selectedEdgeType.value === '__all__'
      && selectedSourceScope.value === '__all__'
      && !highConfidenceOnly.value
    ) {
      return { nodes, edges: filteredEdges }
    }
    const visibleIds = new Set(filteredEdges.flatMap(edge => [edge.source, edge.target]))
    return {
      nodes: nodes.filter(node => visibleIds.has(node.id)),
      edges: filteredEdges,
    }
  }
  const selectedRequirementIds = new Set(
    nodes
      .filter(node => node.kind === 'requirement' && node.properties?.category === selectedCategory.value)
      .map(node => node.id),
  )
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

function selectCategory(label) {
  selectedCategory.value = label
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
  highConfidenceOnly.value = false
  selectedEdge.value = null
  renderGraph()
}

function nodeSize(node) {
  const priority = Number(node.properties?.priority || 0)
  if (priority >= 4) return 42
  if (priority >= 2) return 36
  return 32
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
  return edge?.properties?.source === 'llm_inference' ? 'inferred' : 'analysis'
}

function edgeSourceLabel(edge) {
  return edgeSourceType(edge) === 'inferred' ? '推理关系' : '已有分析关系'
}

function edgeMatchesFilters(edge) {
  if (selectedEdgeType.value !== '__all__' && edge.type !== selectedEdgeType.value) return false
  if (selectedSourceScope.value !== '__all__' && edgeSourceType(edge) !== selectedSourceScope.value) {
    return false
  }
  if (highConfidenceOnly.value && Number(edge.weight || 0) < 0.75) return false
  return true
}

function edgeLineStyle(edge) {
  const inferred = edgeSourceType(edge) === 'inferred'
  return {
    color: edgeColor(edge.type),
    width: Math.max(1.4, (edge.weight || 0.5) * (inferred ? 3.4 : 2.8)),
    opacity: inferred ? 0.84 : edge.type === 'CONFLICTS_WITH' ? 0.9 : 0.66,
    type: inferred ? 'dashed' : 'solid',
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
    'project_members/auth_users': '项目成员候选',
    requirement_people_evidence: '需求人员证据',
    manage_requirements: '需求管理',
    requirements_l123: 'L1-L3 需求',
    low_level_requirements: 'L4 需求',
    trace_analysis: '追溯分析',
    conflict_analysis: '冲突分析',
    classification_analysis: '分类分析',
  }[value] || value
}

watch(selectedProjectId, async (value) => {
  if (value) {
    localStorage.setItem('lastProjectId', value)
    sessionId.value = ''
    await syncProjectSession()
    await loadGraph()
  }
})

watch(sessionId, (value) => {
  if (value) localStorage.setItem('lastSessionId', value)
})

watch(classificationCounts, () => {
  if (selectedCategory.value !== '__all__' && !classificationCounts.value[selectedCategory.value]) {
    selectedCategory.value = '__all__'
  }
}, { deep: true })

watch(highConfidenceOnly, () => {
  selectedEdge.value = null
  renderGraph()
})

onMounted(async () => {
  initChart()
  await loadProjects()
  await syncProjectSession()
  if (selectedProjectId.value || sessionId.value) {
    await loadGraph()
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

.graph-stage {
  position: relative;
  overflow: hidden;
  min-width: 0;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
}

.graph-chart {
  width: 100%;
  height: 100%;
  min-height: 620px;
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
}
</style>
