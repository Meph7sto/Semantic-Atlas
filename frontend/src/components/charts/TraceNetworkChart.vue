<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  traceData: {
    type: Object,
    default: null
  }
})

const chartContainer = ref(null)
let chart = null

const initChart = () => {
  if (!chartContainer.value) return
  chart = echarts.init(chartContainer.value)
  updateChart()
}

const updateChart = () => {
  if (!chart || !props.traceData) return

  // 收集顶层需求和底层需求
  let highLevelNodes = []
  let lowLevelNodes = []
  let links = []

  if (props.traceData.trace_network) {
    // 从 trace_network 结构解析
    const network = props.traceData.trace_network
    const allNodes = network.nodes || []
    const allLinks = network.links || []

    // 根据节点类型或层级分类
    allNodes.forEach(node => {
      if (node.type === 'high_level' || node.level >= 3) {
        highLevelNodes.push(node)
      } else {
        lowLevelNodes.push(node)
      }
    })
    links = allLinks
  } else if (props.traceData.relations) {
    // 批量分析结果
    const highLevelReqs = props.traceData.high_level_requirements || []
    const lowLevelReqs = props.traceData.low_level_requirements || []

    highLevelReqs.forEach((req, idx) => {
      highLevelNodes.push({
        id: `high_${idx}`,
        name: `H${idx + 1}`,
        text: req,
        type: 'high_level'
      })
    })

    lowLevelReqs.forEach((req, idx) => {
      lowLevelNodes.push({
        id: `low_${idx}`,
        name: `L${idx + 1}`,
        text: req,
        type: 'low_level'
      })
    })

    props.traceData.relations.forEach(rel => {
      if (rel.has_relation) {
        links.push({
          source: `high_${rel.high_level_index}`,
          target: `low_${rel.low_level_index}`,
          type: rel.relation_type,
          label: getRelationLabel(rel.relation_type),
          confidence: rel.confidence
        })
      }
    })
  }

  if (highLevelNodes.length === 0 && lowLevelNodes.length === 0) return

  // 二部图布局：计算节点位置
  const chartWidth = chartContainer.value.clientWidth || 800
  const chartHeight = chartContainer.value.clientHeight || 400
  const leftX = chartWidth * 0.15  // 左边 15% 位置
  const rightX = chartWidth * 0.85 // 右边 85% 位置
  const topPadding = 60
  const bottomPadding = 80

  // 计算左侧（顶层需求）节点位置
  const leftSpacing = (chartHeight - topPadding - bottomPadding) / Math.max(highLevelNodes.length - 1, 1)
  const processedHighNodes = highLevelNodes.map((node, idx) => ({
    id: node.id,
    name: node.name,
    x: leftX,
    y: topPadding + (highLevelNodes.length === 1 ? (chartHeight - topPadding - bottomPadding) / 2 : idx * leftSpacing),
    symbolSize: [180, 36],
    symbol: 'roundRect',
    category: 0,
    itemStyle: {
      color: '#3b82f6',
      borderColor: '#1d4ed8',
      borderWidth: 2,
      borderRadius: 6
    },
    label: {
      show: true,
      position: 'inside',
      fontSize: 11,
      color: '#fff',
      fontWeight: 'bold',
      formatter: () => {
        const text = node.text || node.name
        return text.length > 20 ? text.substring(0, 20) + '...' : text
      }
    },
    tooltip: {
      formatter: `<div style="max-width: 350px; padding: 8px;">
        <div style="font-weight: bold; color: #3b82f6; margin-bottom: 4px;">顶层需求</div>
        <div>${node.text || node.name}</div>
      </div>`
    }
  }))

  // 计算右侧（底层需求）节点位置
  const rightSpacing = (chartHeight - topPadding - bottomPadding) / Math.max(lowLevelNodes.length - 1, 1)
  const processedLowNodes = lowLevelNodes.map((node, idx) => ({
    id: node.id,
    name: node.name,
    x: rightX,
    y: topPadding + (lowLevelNodes.length === 1 ? (chartHeight - topPadding - bottomPadding) / 2 : idx * rightSpacing),
    symbolSize: [180, 36],
    symbol: 'roundRect',
    category: 1,
    itemStyle: {
      color: '#10b981',
      borderColor: '#047857',
      borderWidth: 2,
      borderRadius: 6
    },
    label: {
      show: true,
      position: 'inside',
      fontSize: 11,
      color: '#fff',
      fontWeight: 'bold',
      formatter: () => {
        const text = node.text || node.name
        return text.length > 20 ? text.substring(0, 20) + '...' : text
      }
    },
    tooltip: {
      formatter: `<div style="max-width: 350px; padding: 8px;">
        <div style="font-weight: bold; color: #10b981; margin-bottom: 4px;">底层需求</div>
        <div>${node.text || node.name}</div>
      </div>`
    }
  }))

  const allProcessedNodes = [...processedHighNodes, ...processedLowNodes]

  // 处理连接数据
  const processedLinks = links.map(link => ({
    source: link.source,
    target: link.target,
    lineStyle: {
      color: getRelationColor(link.type),
      width: 2 + (link.confidence || 0.5) * 2,
      type: 'solid',
      curveness: 0.15
    },
    label: {
      show: true,
      fontSize: 10,
      color: '#666',
      backgroundColor: 'rgba(255,255,255,0.9)',
      padding: [2, 6],
      borderRadius: 3,
      formatter: link.label || link.type
    },
    tooltip: {
      formatter: `<div style="padding: 6px;">
        <strong>${link.label || link.type}</strong><br/>
        置信度: ${((link.confidence || 0.5) * 100).toFixed(0)}%
      </div>`
    }
  }))

  const categories = [
    { name: '顶层需求', itemStyle: { color: '#3b82f6' } },
    { name: '底层需求', itemStyle: { color: '#10b981' } }
  ]

  const option = {
    title: {
      text: '需求追溯关系图',
      subtext: '左侧: 顶层需求 → 右侧: 底层需求',
      left: 'center',
      top: 5,
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
      bottom: 10,
      left: 'center',
      data: categories.map(c => c.name),
      textStyle: { fontSize: 12 }
    },
    series: [{
      type: 'graph',
      layout: 'none',  // 使用固定位置布局
      coordinateSystem: null,
      roam: true,
      categories: categories,
      data: allProcessedNodes,
      links: processedLinks,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 10],
      lineStyle: {
        opacity: 0.9
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 5 },
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.3)' }
      }
    }]
  }

  chart.setOption(option, true)
}

const getLevelColor = (level) => {
  const colors = {
    1: '#e3f2fd',
    2: '#c8e6c9',
    3: '#fff9c4',
    4: '#ffccbc',
    5: '#f8bbd0'
  }
  return colors[level] || '#f5f5f5'
}

const getRelationColor = (type) => {
  const colors = {
    'implementation': '#67c23a',
    'support': '#409eff',
    'dependency': '#f56c6c',
    'decomposition': '#e6a23c',
    'general': '#909399'
  }
  return colors[type] || '#909399'
}

const getRelationLabel = (type) => {
  const labels = {
    'implementation': '实现关系',
    'support': '支持关系',
    'dependency': '依赖关系',
    'decomposition': '分解关系',
    'general': '追溯关系'
  }
  return labels[type] || '追溯关系'
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', () => {
    if (chart) chart.resize()
  })
})

onUnmounted(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
  window.removeEventListener('resize', () => {
    if (chart) chart.resize()
  })
})

watch(() => props.traceData, () => {
  updateChart()
}, { deep: true })
</script>

<template>
  <div class="w-full h-[500px] border border-zinc-200 rounded-xl bg-gradient-to-br from-slate-50 to-white shadow-sm">
    <div ref="chartContainer" class="w-full h-full"></div>
  </div>
</template>

