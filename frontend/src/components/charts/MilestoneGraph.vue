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
const scale = ref(1)

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

const updateChart = () => {
  if (!chart) return
  const refMap = buildRefMap()
  const orderedNodes = [...props.nodes].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
  const laneMap = buildLaneMap(orderedNodes)
  const xGap = 160
  const yGap = 120

  const nodeData = orderedNodes.map((node, index) => {
    const branchNames = refMap.get(node.milestone_id) || []
    const isBaseline = !!node.is_baseline
    const branchName = resolveBranchName(node)
    const lane = laneMap.get(branchName) || 0
    return {
      id: node.milestone_id,
      name: node.name,
      value: node,
      x: index * xGap,
      y: lane * yGap,
      symbol: isBaseline ? 'diamond' : 'circle',
      symbolSize: isBaseline ? 48 : 36,
      itemStyle: {
        color: isBaseline ? '#f59e0b' : '#3b82f6',
        borderColor: branchNames.length ? '#10b981' : '#1d4ed8',
        borderWidth: branchNames.length ? 3 : 1
      },
      label: {
        show: true,
        position: 'right',
        formatter: () => node.name
      },
      tooltip: {
        formatter: () => {
          const refs = branchNames.length ? `<div>分支: ${branchNames.join(', ')}</div>` : ''
          const baseline = isBaseline ? '<div>Baseline</div>' : ''
          return `
            <div style="padding:6px; max-width:280px;">
              <div style="font-weight:600; margin-bottom:4px;">${node.name}</div>
              ${baseline}
              ${refs}
              <div>分支: ${branchName}</div>
              <div>类型: ${node.milestone_type || '-'} </div>
              <div>创建: ${node.created_at || '-'} </div>
              <div style="margin-top:4px; color:#6b7280;">${node.message || ''}</div>
            </div>
          `
        }
      }
    }
  })

  const linkData = props.edges.map(edge => ({
    source: edge.from_milestone_id,
    target: edge.to_milestone_id,
    lineStyle: {
      color: edge.relation_type === 'commit' ? '#64748b' : '#94a3b8',
      width: 2
    },
    label: {
      show: false
    }
  }))

  const requiredWidth = Math.max(800, orderedNodes.length * xGap + 200)
  const laneCount = Math.max(1, Math.max(...Array.from(laneMap.values()).map(v => Math.abs(v))) * 2 + 1)
  const requiredHeight = Math.max(320, laneCount * yGap + 200)

  if (chartContainer.value) {
    chartContainer.value.style.width = `${requiredWidth}px`
    chartContainer.value.style.height = `${requiredHeight}px`
  }

  const option = {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true,
        data: nodeData,
        links: linkData,
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        label: { color: '#111827', fontSize: 11 },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 4 }
        }
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
  <div ref="outerContainer" class="w-full h-[320px] overflow-auto relative">
    <div class="absolute top-2 right-2 z-10 flex gap-2">
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = Math.min(2, scale.value + 0.1); chart && chart.resize(); }">放大</button>
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = Math.max(0.5, scale.value - 0.1); chart && chart.resize(); }">缩小</button>
      <button class="px-2 py-1 bg-white rounded shadow" @click.prevent="() => { scale.value = 1; chart && chart.resize(); }">重置</button>
    </div>
    <div ref="chartContainer" :style="{ transform: `scale(${scale})`, transformOrigin: '0 0' }" class="w-full"></div>
  </div>
</template>
