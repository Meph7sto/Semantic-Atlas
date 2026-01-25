<script setup>
import { onMounted, onUnmounted, ref, watch, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  treeData: { type: Array, default: () => [] },
  highlightMap: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['hover', 'click-node'])

const chartContainer = ref(null)
const outerContainer = ref(null)
let chart = null
let resizeObserver = null
const handleReset = () => {
  if (chart) {
    chart.dispatchAction({
      type: 'restore'
    })
  }
}

const COLOR_MAP = {
  added: '#22c55e',
  deleted: '#ef4444',
  modified: '#f59e0b',
  moved: '#3b82f6',
  mixed: '#a855f7',
  normal: '#94a3b8'
}

const TYPE_COLORS = {
  top_level: '#6366f1', // Indigo
  low_level: '#06b6d4', // Cyan
  task: '#8b5cf6'       // Violet
}

const getNodeColor = (reqId, reqType) => {
  const types = props.highlightMap?.[reqId]
  if (types && types.length > 0) {
    const uniq = Array.from(new Set(types))
    if (uniq.length > 1) return COLOR_MAP.mixed
    return COLOR_MAP[uniq[0]] || COLOR_MAP.normal
  }
  return TYPE_COLORS[reqType] || COLOR_MAP.normal
}

const getNodeSymbol = (reqType) => {
  switch (reqType) {
    case 'top_level': return 'circle'
    case 'low_level': return 'roundRect'
    case 'task': return 'diamond'
    default: return 'circle'
  }
}

const getNodeSize = (reqType) => {
  switch (reqType) {
    case 'top_level': return 20 
    case 'low_level': return 16
    case 'task': return 14
    default: return 14
  }
}

const toTreeNode = (node) => {
  const req = node.requirement || {}
  const reqId = req.req_id || req.id || ''
  const reqType = req.requirement_type || ''
  const isInSprint = req.status === 'in_progress'
  return {
    name: '',
    id: reqId,
    value: req,
    itemStyle: {
      color: getNodeColor(reqId, reqType),
      borderColor: isInSprint ? '#f59e0b' : '#fff',
      borderWidth: isInSprint ? 4 : 1.5,
      shadowColor: 'rgba(0,0,0,0.1)',
      shadowBlur: 3
    },
    symbol: getNodeSymbol(reqType),
    symbolSize: getNodeSize(reqType),
    children: (node.children || []).map(toTreeNode)
  }
}


const buildRoots = () => {
  if (!props.treeData || props.treeData.length === 0) return []
  const roots = props.treeData.map(toTreeNode)
  return [
    {
      id: '__root__',
      name: '',
      value: {},
      symbolSize: 0,
      itemStyle: { color: 'transparent' },
      label: { show: false },
      children: roots
    }
  ]
}

const countNodes = (nodes = []) => {
  let total = 0
  const walk = (n) => {
    total += 1
    ;(n.children || []).forEach(walk)
  }
  nodes.forEach(walk)
  return total
}

const computeRequiredHeight = (roots) => {
  const total = countNodes(roots)
  // Removed strict upper bound to prevent overlap in dense trees
  return Math.max(400, total * 35)
}

  const updateChart = () => {
  if (!chart) return
  const roots = buildRoots()
  if (roots.length === 0) {
    chart.clear()
    return
  }

  const option = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      textStyle: {
        color: '#1e293b'
      },
      extraCssText: 'box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); border-radius: 0.5rem;',
      formatter: (params) => {
        const req = params?.data?.value || {}
        if (!req || Object.keys(req).length === 0) return ''
        const typeLabel = {
          'top_level': '顶层需求',
          'low_level': '底层需求',
          'task': '任务'
        }[req.requirement_type] || req.requirement_type || '-'
        const levelLabel = req.source_level || '-'
        const isInSprint = req.status === 'in_progress'
        
        return `
          <div class="font-sans">
            <div class="font-bold text-gray-900 border-b border-gray-200 pb-1 mb-2">
              ${req.title || req.text || '需求'}
              ${isInSprint ? '<span class="ml-2 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded border border-amber-200">Sprint</span>' : ''}
            </div>
            <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
              <div><span class="text-gray-400">ID:</span> ${req.req_id || req.id || '-'}</div>
              <div><span class="text-gray-400">级别:</span> ${levelLabel}</div>
              <div><span class="text-gray-400">类型:</span> ${typeLabel}</div>
              <div><span class="text-gray-400">状态:</span> <span class="font-medium ${req.status === 'completed' ? 'text-green-600' : ''}">${req.status || '-'}</span></div>
              <div><span class="text-gray-400">优先级:</span> ${req.priority || '-'}</div>
              <div class="col-span-2"><span class="text-gray-400">负责人:</span> ${req.assignee || '-'}</div>
            </div>
          </div>
        `
      }
    },
    series: [
      {
        type: 'tree',
        data: roots,
        top: '10%',
        bottom: '10%',
        left: '10%',
        right: '10%',
        symbolSize: (value, params) => getNodeSize(params.data.value?.requirement_type),
        edgeShape: 'curve',
        roam: true,
        initialTreeDepth: 3,
        lineStyle: {
          width: 2,
          color: '#cbd5e1',
          curveness: 0.5
        },
        label: {
          show: true,
          position: 'right',
          verticalAlign: 'middle',
          align: 'left',
          fontSize: 12,
          formatter: (params) => {
             const title = params.data.value?.title || params.data.value?.text || ''
             return title.length > 10 ? title.substring(0, 10) + '...' : title
          }
        },
        leaves: {
          label: {
            position: 'right',
            verticalAlign: 'middle',
            align: 'left'
          }
        },
        emphasis: {
          focus: 'descendant'
        },
        expandAndCollapse: true,
        animationDuration: 550,
        animationDurationUpdate: 750
      }
    ]
  }
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
  chart.on('click', params => {
    if (params?.data?.value) emit('click-node', params.data.value)
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
  <div ref="outerContainer" class="w-full h-[500px] overflow-hidden relative border border-gray-100 rounded-lg bg-slate-50">
    <div class="absolute top-3 right-3 z-10 flex gap-2">
      <button 
        class="flex items-center gap-1 px-3 py-1.5 bg-white text-sm font-medium text-slate-600 rounded-md shadow-sm border border-slate-200 hover:bg-slate-50 transition-colors"
        @click.prevent="handleReset"
      >
        <span>还原视图</span>
      </button>
    </div>
    <div ref="chartContainer" class="w-full h-full"></div>
  </div>
</template>
