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

  // 处理批量分析结果：构建网络图
  let nodes = []
  let links = []

  if (props.traceData.trace_network) {
    // 单对分析结果
    const network = props.traceData.trace_network
    nodes = network.nodes || []
    links = network.links || []
  } else if (props.traceData.relations) {
    // 批量分析结果：从 relations 构建网络
    const nodeMap = new Map()
    const highLevelReqs = props.traceData.high_level_requirements || []
    const lowLevelReqs = props.traceData.low_level_requirements || []

    // 添加顶层需求节点
    highLevelReqs.forEach((req, idx) => {
      const nodeId = `high_${idx}`
      nodeMap.set(nodeId, {
        id: nodeId,
        name: `顶层需求 #${idx + 1}`,
        text: req.length > 30 ? req.substring(0, 30) + '...' : req,
        level: 4,
        type: 'high_level'
      })
    })

    // 添加底层需求节点
    lowLevelReqs.forEach((req, idx) => {
      const nodeId = `low_${idx}`
      nodeMap.set(nodeId, {
        id: nodeId,
        name: `底层需求 #${idx + 1}`,
        text: req.length > 30 ? req.substring(0, 30) + '...' : req,
        level: 2,
        type: 'low_level'
      })
    })

    // 从 relations 构建连接
    props.traceData.relations.forEach(rel => {
      if (rel.has_relation) {
        const sourceId = `high_${rel.high_level_index}`
        const targetId = `low_${rel.low_level_index}`
        links.push({
          source: sourceId,
          target: targetId,
          type: rel.relation_type,
          label: getRelationLabel(rel.relation_type),
          confidence: rel.confidence
        })
      }
    })

    nodes = Array.from(nodeMap.values())
  }

  if (nodes.length === 0) return

  // 处理节点数据
  const processedNodes = nodes.map(node => {
    const level = node.level || 3
    return {
      id: node.id,
      name: node.name || node.text,
      category: Math.min(level - 1, 4),
      symbolSize: 50,
      itemStyle: {
        color: getLevelColor(level),
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: true,
        position: 'inside',
        fontSize: 10,
        color: '#333',
        formatter: (params) => {
          const text = node.text || params.name
          return text.length > 15 ? text.substring(0, 15) + '...' : text
        }
      },
      tooltip: {
        formatter: `<div style="max-width: 300px;">
          <strong>${node.name}</strong><br/>
          ${node.text || ''}<br/>
          <small>层级: ${level}</small>
        </div>`
      }
    }
  })

  // 处理连接数据
  const processedLinks = links.map(link => ({
    source: link.source,
    target: link.target,
    lineStyle: {
      color: getRelationColor(link.type),
      width: 2 + (link.confidence || 0.5) * 2,
      type: 'solid'
    },
    label: {
      show: true,
      fontSize: 10,
      color: '#666',
      formatter: link.label || link.type
    },
    tooltip: {
      formatter: `<div>
        <strong>${link.label || link.type}</strong><br/>
        置信度: ${((link.confidence || 0.5) * 100).toFixed(0)}%
      </div>`
    }
  }))

  const categories = [
    { name: '底层需求' },
    { name: '功能需求' },
    { name: '业务需求' },
    { name: '顶层需求' },
    { name: '战略目标' }
  ]

  const option = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(0,0,0,0.8)',
      borderColor: 'transparent',
      textStyle: { color: '#fff' }
    },
    legend: {
      bottom: 10,
      left: 'center',
      data: categories.map(c => c.name),
      textStyle: { fontSize: 12 }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      force: {
        repulsion: 200,
        gravity: 0.1,
        edgeLength: 100
      },
      roam: true,
      categories: categories,
      data: processedNodes,
      links: processedLinks,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      lineStyle: {
        opacity: 0.8,
        curveness: 0.1
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 4 }
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
  <div class="w-full h-96 border border-zinc-200 rounded-xl bg-white">
    <div ref="chartContainer" class="w-full h-full"></div>
  </div>
</template>

