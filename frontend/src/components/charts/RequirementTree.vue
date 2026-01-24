<script setup>
import { onMounted, onUnmounted, ref, watch, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  treeData: { type: Array, default: () => [] },
  highlightMap: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['hover'])

const chartContainer = ref(null)
const outerContainer = ref(null)
let chart = null
let resizeObserver = null
const scale = ref(1)

const COLOR_MAP = {
  added: '#22c55e',
  deleted: '#ef4444',
  modified: '#f59e0b',
  moved: '#3b82f6',
  mixed: '#a855f7',
  normal: '#94a3b8'
}

const getNodeColor = (reqId) => {
  const types = props.highlightMap?.[reqId]
  if (!types || types.length === 0) return COLOR_MAP.normal
  const uniq = Array.from(new Set(types))
  if (uniq.length > 1) return COLOR_MAP.mixed
  return COLOR_MAP[uniq[0]] || COLOR_MAP.normal
}

const toTreeNode = (node) => {
  const req = node.requirement || {}
  const reqId = req.req_id || req.id || ''
  return {
    name: req.title || req.text || reqId || '未命名需求',
    id: reqId,
    value: req,
    itemStyle: {
      color: getNodeColor(reqId)
    },
    children: (node.children || []).map(toTreeNode)
  }
}

const buildRoots = () => {
  if (!props.treeData || props.treeData.length === 0) return []
  return props.treeData.map(toTreeNode)
}

const computeRequiredHeight = (roots) => {
  // approximate height: per-root segment or depth-based estimate
  const perRoot = 180
  return Math.max(320, roots.length * perRoot)
}

const updateChart = () => {
  if (!chart) return
  const roots = buildRoots()
  if (roots.length === 0) {
    chart.clear()
    return
  }

  const segment = 100 / roots.length
  const series = roots.map((root, index) => {
    const top = Math.max(2, index * segment + 2)
    const height = Math.max(16, segment - 4)
    return {
      type: 'tree',
      data: [root],
      top: `${top}%`,
      height: `${height}%`,
      left: '6%',
      right: '20%',
      symbolSize: 10,
      label: {
        position: 'left',
        verticalAlign: 'middle',
        align: 'right',
        fontSize: 11
      },
      leaves: {
        label: {
          position: 'right',
          verticalAlign: 'middle',
          align: 'left'
        }
      },
      expandAndCollapse: true,
      animationDuration: 200,
      animationDurationUpdate: 300
    }
  })

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const req = params?.data?.value || {}
        if (!req || Object.keys(req).length === 0) return ''
        return `
          <div style="padding:6px; max-width:280px;">
            <div style="font-weight:600; margin-bottom:4px;">${req.title || req.text || '需求'}</div>
            <div>类型: ${req.requirement_type || '-'}</div>
            <div>状态: ${req.status || '-'}</div>
            <div>优先级: ${req.priority || '-'}</div>
            <div>负责人: ${req.assignee || '-'}</div>
            <div>截止: ${req.due_date || '-'}</div>
          </div>
        `
      }
    },
    series
  }

  applyContainerSizing(roots)
  chart.setOption(option, true)
}

const applyContainerSizing = (roots) => {
  const h = computeRequiredHeight(roots)
  if (chartContainer.value) {
    chartContainer.value.style.width = '100%'
    chartContainer.value.style.height = `${h}px`
  }
  // ensure outer can scroll; ResizeObserver will call chart.resize
}

const initChart = () => {
  if (!chartContainer.value) return
  chart = echarts.init(chartContainer.value)
  chart.on('mouseover', params => {
    if (params?.data?.value) emit('hover', params.data.value)
  })
  updateChart()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartContainer.value)
}

onMounted(initChart)
onUnmounted(() => {
  if (resizeObserver && chartContainer.value) resizeObserver.disconnect()
  if (chart) chart.dispose()
  chart = null
})

watch(() => [props.treeData, props.highlightMap], () => updateChart(), { deep: true })
</script>

<template>
  <div ref="outerContainer" class="w-full h-[320px] overflow-auto relative">
    <div class="absolute top-2 right-2 z-10 flex gap-2">
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = Math.min(2, scale.value + 0.1); chart && chart.resize(); }">放大</button>
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = Math.max(0.5, scale.value - 0.1); chart && chart.resize(); }">缩小</button>
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = 1; chart && chart.resize(); }">重置</button>
    </div>
    <div ref="chartContainer" :style="{ transform: `scale(${scale})`, transformOrigin: '0 0' }" class="w-full"></div>
  </div>
</template>
