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
              <h3>关系类型</h3>
              <div v-for="edge in edgeLegend" :key="edge.type" class="legend-row">
                <span class="legend-line" :style="{ background: edge.color }"></span>
                <span>{{ edge.label }}</span>
                <b>{{ stats.edge_counts?.[edge.type] || 0 }}</b>
              </div>
            </div>

            <div class="detail-block">
              <h3>{{ selectedNode ? '节点详情' : '图谱读取' }}</h3>
              <template v-if="selectedNode">
                <div class="detail-title">{{ selectedNode.label }}</div>
                <p class="detail-kind">{{ selectedNode.kind === 'stakeholder' ? '利益相关方' : '需求' }}</p>
                <dl>
                  <template v-for="item in selectedDetails" :key="item.key">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </template>
                </dl>
              </template>
              <p v-else class="detail-empty">
                点击图中的节点查看需求内容、分类、验证约束或利益相关方角色。
              </p>
            </div>
          </aside>

          <div class="graph-stage">
            <div v-if="graphError" class="state-panel error-state">{{ graphError }}</div>
            <div v-else-if="!hasGraph && !isLoadingGraph" class="state-panel">
              选择项目后生成需求图谱。
            </div>
            <div v-else-if="isLoadingGraph" class="state-panel">
              正在融合追溯、冲突、分类和利益相关方关系。
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
const graphError = ref('')
const graphData = ref({ nodes: [], edges: [], stats: {} })
const selectedNode = ref(null)
const selectedCategory = ref('__all__')
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
  { type: 'RAISES', label: '提出', color: '#14b8a6' },
  { type: 'OWNS', label: '负责', color: '#6366f1' },
  { type: 'AFFECTED_BY', label: '参与变更', color: '#64748b' },
  { type: 'INTEREST_CONFLICTS_WITH', label: '利益冲突', color: '#e11d48' },
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

const selectedDetails = computed(() => {
  const props = selectedNode.value?.properties || {}
  const rows = [
    ['level', '层级'],
    ['type', '类型'],
    ['category', '分类'],
    ['status', '状态'],
    ['priority', '优先级'],
    ['component', '目标模块'],
    ['role', '角色'],
    ['authority', '权限画像'],
    ['content', '内容'],
  ]
  return rows
    .map(([key, label]) => ({ key, label, value: formatValue(props[key]) }))
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

function initChart() {
  if (!chartContainer.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartContainer.value)
  chart.on('click', params => {
    if (params.dataType === 'node') {
      selectedNode.value = params.data.raw
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
          return `${raw.label}<br/>${raw.type}`
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
          lineStyle: {
            color: edgeColor(edge.type),
            width: Math.max(1.2, (edge.weight || 0.5) * 3),
            opacity: edge.type === 'CONFLICTS_WITH' ? 0.9 : 0.66,
            curveness: edge.type === 'CONFLICTS_WITH' ? 0.22 : 0.1,
          },
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
  if (selectedCategory.value === '__all__') return { nodes, edges }
  const selectedRequirementIds = new Set(
    nodes
      .filter(node => node.kind === 'requirement' && node.properties?.category === selectedCategory.value)
      .map(node => node.id),
  )
  if (!selectedRequirementIds.size) return { nodes: [], edges: [] }

  const includedIds = new Set(selectedRequirementIds)
  edges.forEach(edge => {
    if (selectedRequirementIds.has(edge.source)) includedIds.add(edge.target)
    if (selectedRequirementIds.has(edge.target)) includedIds.add(edge.source)
  })
  const filteredNodes = nodes.filter(node => includedIds.has(node.id))
  const visibleIds = new Set(filteredNodes.map(node => node.id))
  const filteredEdges = edges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target))
  return { nodes: filteredNodes, edges: filteredEdges }
}

function selectCategory(label) {
  selectedCategory.value = label
  selectedNode.value = null
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

function formatValue(value) {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.filter(Boolean).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
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

.detail-block dt {
  margin-top: 10px;
}

.detail-block dd {
  margin: 4px 0 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.55;
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
