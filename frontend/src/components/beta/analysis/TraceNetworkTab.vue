<template>
  <div class="tab-content">
    <div v-if="!traceResult" class="empty-result">
      <Network class="empty-icon" />
      <p>点击「一键分析」生成追溯网络</p>
    </div>
    <div v-else ref="chartContainer" class="chart-container"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Network } from 'lucide-vue-next'
import * as echarts from 'echarts'

const props = defineProps({
  traceResult: { type: Object, default: null },
  allHighLevelRequirements: { type: Array, default: () => [] },
  lowLevelRequirements: { type: Array, default: () => [] },
  isActive: { type: Boolean, default: false },
})

const chartContainer = ref(null)
let chart = null

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

function getRelationTypeColor(type) {
  const colors = {
    'implementation': '#22c55e',
    'support': '#3b82f6',
    'dependency': '#ef4444',
    'decomposition': '#f59e0b',
    'general': '#6b7280',
  }
  return colors[type] || '#6b7280'
}

function getCategoryColor(category) {
  const colors = { L1: '#0ea5e9', L2: '#71717a', L3: '#f59e0b', low: '#10b981' }
  return colors[category] || '#6b7280'
}

function getCategoryBorderColor(category) {
  const colors = { L1: '#1d4ed8', L2: '#6d28d9', L3: '#d97706', low: '#047857' }
  return colors[category] || '#374151'
}

function initChart() {
  if (!chartContainer.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartContainer.value)
  updateChart()
}

function updateChart() {
  if (!chart) return

  if (!props.traceResult) {
    chart.setOption({
      title: {
        text: '追溯网络',
        subtext: '完成分析后显示追溯关系图',
        left: 'center',
        top: 'center',
        textStyle: { color: 'rgba(28, 40, 52, 0.4)', fontSize: 16 },
        subtextStyle: { color: 'rgba(28, 40, 52, 0.3)', fontSize: 12 },
      },
    }, true)
    return
  }

  const highNodes = props.allHighLevelRequirements
  const lowNodes = props.lowLevelRequirements
  const containerWidth = chartContainer.value?.clientWidth || 800
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
    { name: '底层需求', itemStyle: { color: '#10b981' } },
  ]
  const categoryMap = { L1: 0, L2: 1, L3: 2, low: 3 }

  const leftSpacing = highNodes.length > 1 ? availableHeight / (highNodes.length - 1) : 0
  const nodes = highNodes.map((req, idx) => {
    const level = normalizeLevel(req.category || req.level)
    return {
      id: req.req_id || req.id || `high_${idx}`,
      name: (req.statement || '').slice(0, 25) + ((req.statement || '').length > 25 ? '...' : ''),
      x: leftX,
      y: topPadding + (highNodes.length === 1 ? availableHeight / 2 : idx * leftSpacing),
      category: categoryMap[level] ?? 0,
      symbol: 'roundRect',
      symbolSize: [180, 28],
      itemStyle: { color: getCategoryColor(level), borderColor: getCategoryBorderColor(level), borderWidth: 2, borderRadius: 0 },
      label: { show: true, position: 'inside', fontSize: 10, color: '#fff', fontWeight: 500 },
    }
  })

  const rightSpacing = lowNodes.length > 1 ? availableHeight / (lowNodes.length - 1) : 0
  lowNodes.forEach((req, idx) => {
    nodes.push({
      id: req.req_id || req.id || `low_${idx}`,
      name: (req.statement || '').slice(0, 25) + ((req.statement || '').length > 25 ? '...' : ''),
      x: rightX,
      y: topPadding + (lowNodes.length === 1 ? availableHeight / 2 : idx * rightSpacing),
      category: 3,
      symbol: 'roundRect',
      symbolSize: [180, 28],
      itemStyle: { color: '#10b981', borderColor: '#047857', borderWidth: 2, borderRadius: 0 },
      label: { show: true, position: 'inside', fontSize: 10, color: '#fff', fontWeight: 500 },
    })
  })

  const links = []
  if (props.traceResult?.relations) {
    props.traceResult.relations.forEach((rel, idx) => {
      if (!rel.has_relation) return
      const sourceId = rel.high_req_id
      const targetId = rel.low_req_id
      if (!sourceId || !targetId) return
      links.push({
        source: sourceId,
        target: targetId,
        lineStyle: {
          color: getRelationTypeColor(rel.relation_type),
          width: 1.5,
          curveness: ((idx % 5) - 2) * 0.05,
          opacity: 0.7,
        },
      })
    })
  }

  chart.setOption({
    title: {
      text: '需求追溯关系图',
      subtext: `左侧: ${highNodes.length} 个顶层需求 ─→ 右侧: ${lowNodes.length} 个底层需求`,
      left: 'center',
      top: 8,
      textStyle: { fontSize: 14, fontWeight: 'bold', color: 'var(--ink-950)' },
      subtextStyle: { fontSize: 11, color: 'rgba(28, 40, 52, 0.5)' },
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(28, 40, 52, 0.1)',
      borderWidth: 1,
      textStyle: { color: 'var(--ink-950)' },
    },
    legend: {
      bottom: 8,
      left: 'center',
      data: categories.map(c => c.name),
      textStyle: { fontSize: 11 },
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      categories,
      data: nodes,
      links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      lineStyle: { opacity: 0.7 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3, opacity: 0.95 } },
    }],
  }, true)
}

onMounted(() => {
  if (props.isActive) nextTick(() => initChart())
})

watch(() => props.isActive, (val) => {
  if (val) nextTick(() => initChart())
})

watch(() => props.traceResult, () => {
  if (props.isActive && chart) updateChart()
}, { deep: true })

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.tab-content {
  height: 100%;
  overflow-y: auto;
}

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: rgba(28, 40, 52, 0.4);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.3;
}

.chart-container {
  width: 100%;
  height: 100%;
  min-height: 500px;
}
</style>
