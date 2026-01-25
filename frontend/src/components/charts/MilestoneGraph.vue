<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  branchRefs: { type: Array, default: () => [] }
})

const emit = defineEmits(['select'])

const chartContainer = ref(null)
const outerContainer = ref(null)
let chart = null
let resizeObserver = null
const handleReset = () => {
  if (chart) {
    chart.dispatchAction({ type: 'restore' })
  }
}

const buildRefMap = () => {
  const map = new Map()
  props.branchRefs.forEach(ref => {
    if (!ref?.milestone_id) return
    const arr = map.get(ref.milestone_id) || []
    arr.push(ref.ref_name)
    map.set(ref.milestone_id, arr)
  })
  return map
}

const resolveBranchName = (node) => {
  const meta = node?.metadata || {}
  return meta.branch_name || 'main'
}

const buildLaneMap = (nodes) => {
  const lanes = new Map()
  lanes.set('main', 0)
  let up = 1
  let down = -1
  nodes.forEach(node => {
    const branch = resolveBranchName(node)
    if (lanes.has(branch)) return
    if (up <= Math.abs(down)) {
      lanes.set(branch, up)
      up += 1
    } else {
      lanes.set(branch, down)
      down -= 1
    }
  })
  return lanes
}

const BRANCH_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4'
]

const getBranchColor = (name) => {
  if (name === 'main') return '#3b82f6' // Blue for main
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  const index = Math.abs(hash) % (BRANCH_COLORS.length - 1) + 1
  return BRANCH_COLORS[index]
}

const updateChart = () => {
  if (!chart) return
  const refMap = buildRefMap()
  const orderedNodes = [...props.nodes].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
  const laneMap = buildLaneMap(orderedNodes)
  const xGap = 160
  const yGap = 100

  const nodeData = orderedNodes.map((node, index) => {
    const branchNames = refMap.get(node.milestone_id) || []
    const isBaseline = !!node.is_baseline
    const branchName = resolveBranchName(node)
    const lane = laneMap.get(branchName) || 0
    const color = isBaseline ? '#f59e0b' : getBranchColor(branchName)
    
    return {
      id: node.milestone_id,
      name: node.name,
      value: node,
      x: index * xGap + 50,
      y: lane * yGap,
      symbol: isBaseline ? 'pin' : 'circle',
      symbolSize: isBaseline ? 28 : 16,
      itemStyle: {
        color: isBaseline ? '#fde68a' : 'white', // Light amber fill for baseline
        borderColor: color,
        borderWidth: isBaseline ? 3 : 3,
        shadowColor: 'rgba(0,0,0,0.1)',
        shadowBlur: 10
      },
      label: {
        show: true,
        position: 'bottom',
        offset: [0, 5],
        formatter: (params) => {
           const name = params.data.name || ''
           return name.length > 20 ? name.substring(0, 18) + '...' : name
        },
        fontSize: 12,
        fontWeight: 'bold',
        color: '#475569',
        backgroundColor: 'rgba(255,255,255,0.8)',
        borderRadius: 4,
        padding: [2, 4]
      },
      tooltip: {
        // Inherits global but let's override for node specific
      }
    }
  })

  // Improve logic to curve lines between different lanes
  const linkData = props.edges.map(edge => {
    const sourceNode = nodeData.find(n => n.id === edge.from_milestone_id)
    const targetNode = nodeData.find(n => n.id === edge.to_milestone_id)
    let curveness = 0
    if (sourceNode && targetNode && sourceNode.y !== targetNode.y) {
       // Curve based on distance to avoid overlap? Or just fixed curve
       curveness = 0.2
    }
    
    return {
      source: edge.from_milestone_id,
      target: edge.to_milestone_id,
      lineStyle: {
        color: '#94a3b8',
        width: 2,
        curveness: curveness
      }
    }
  })

  // Dynamic Sizing
  const requiredWidth = Math.max(800, orderedNodes.length * xGap + 200)
  const laneCount = Math.max(1, Math.max(...Array.from(laneMap.values()).map(v => Math.abs(v))) * 2 + 1)
  const requiredHeight = Math.max(400, laneCount * yGap + 200)

  if (chartContainer.value) {
    chartContainer.value.style.width = `${requiredWidth}px`
    chartContainer.value.style.height = `${requiredHeight}px`
  }

  const option = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      textStyle: { color: '#1e293b' },
      extraCssText: 'box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-radius: 0.5rem;',
      formatter: (params) => {
        if (params.dataType !== 'node') return ''
        const node = params.data.value
        const branchNames = refMap.get(node.milestone_id) || []
        const isBaseline = !!node.is_baseline
        const branchName = resolveBranchName(node)
        
        return `
          <div class="font-sans p-1">
            <div class="font-bold text-gray-900 border-b border-gray-100 pb-1 mb-2 flex items-center gap-2">
              ${isBaseline ? '<span class="text-amber-500">★</span>' : ''}
              ${node.name}
            </div>
            <div class="text-xs text-gray-600 space-y-1">
              ${branchNames.length ? `<div><span class="text-gray-400">Heading:</span> <span class="bg-blue-100 text-blue-800 px-1 py-0.5 rounded">${branchNames.join(', ')}</span></div>` : ''}
              <div><span class="text-gray-400">Branch:</span> <span class="font-mono text-xs bg-gray-100 px-1 rounded">${branchName}</span></div>
              <div><span class="text-gray-400">Type:</span> ${node.milestone_type || '-'}</div>
              <div><span class="text-gray-400">Date:</span> ${new Date(node.created_at).toLocaleString()}</div>
              ${node.message ? `<div class="mt-2 pt-2 border-t border-gray-50 italic text-gray-500">${node.message}</div>` : ''}
            </div>
          </div>
        `
      }
    },
    grid: {
      top: 50, bottom: 50
    },
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true, // Allow roam inside the long canvas
        data: nodeData,
        links: linkData,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 10],
        lineStyle: {
           color: '#cbd5e1',
           width: 2
        },
        label: { show: true },
        emphasis: {
          focus: 'adjacency',
          scale: true
        },
        zoom: 1 // Start at 1
      }
    ]
  }

  chart.setOption(option, true)
}

const initChart = () => {
  if (!chartContainer.value) return
  chart = echarts.init(chartContainer.value)
  chart.on('click', params => {
    if (params?.data?.id) {
      emit('select', params.data.id)
    }
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

watch(() => [props.nodes, props.edges, props.branchRefs], () => updateChart(), { deep: true })
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
