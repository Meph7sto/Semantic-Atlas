<template>
  <div class="trace-chart">
    <div ref="chartContainer" class="chart-container"></div>
  </div>
</template>

<script>
import * as echarts from 'echarts'

export default {
  name: 'RequirementTraceChart',
  props: {
    traceData: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      chart: null
    }
  },
  mounted() {
    this.initChart()
  },
  beforeUnmount() {
    if (this.chart) this.chart.dispose()
  },
  watch: {
    traceData: {
      handler() {
        this.updateChart()
      },
      deep: true
    }
  },
  methods: {
    initChart() {
      this.chart = echarts.init(this.$refs.chartContainer)
      this.updateChart()
    },
    updateChart() {
      if (!this.chart || !this.traceData || !this.traceData.trace_network) return

      const { nodes = [], links = [] } = this.traceData.trace_network

      // 将节点按 level 分层摆放（level 越大越靠上）
      const levelGroups = {}
      nodes.forEach(n => {
        const lv = Number(n.level || 3)
        if (!levelGroups[lv]) levelGroups[lv] = []
        levelGroups[lv].push(n)
      })

      const sortedLevels = Object.keys(levelGroups)
        .map(v => Number(v))
        .sort((a, b) => b - a)

      const processedNodes = []
      sortedLevels.forEach((lv, levelRow) => {
        const group = levelGroups[lv]
        group.forEach((node, idx) => {
          processedNodes.push({
            id: node.id,
            name: this.truncateText(node.text || node.name || node.id, 18),
            symbolSize: 70,
            x: idx * 240 + 140,
            y: levelRow * 130 + 90,
            itemStyle: {
              color: this.getLevelColor(lv),
              borderColor: '#fff',
              borderWidth: 2
            },
            label: {
              show: true,
              position: 'inside',
              fontSize: 11,
              color: '#333'
            },
            tooltip: {
              formatter: `<div style="max-width: 340px;">
                <strong>${node.name || node.id}</strong><br/>
                ${this.escapeHtml(node.text || '')}<br/>
                <small>level: ${lv}</small>
              </div>`
            }
          })
        })
      })

      const processedLinks = links.map(link => ({
        source: link.source,
        target: link.target,
        lineStyle: {
          color: '#409eff',
          width: 2,
          type: 'solid'
        },
        symbol: ['none', 'arrow'],
        symbolSize: [0, 10],
        label: {
          show: !!link.label,
          fontSize: 10,
          color: '#666',
          formatter: link.label || ''
        },
        tooltip: {
          formatter: link.label ? `${link.label}${link.confidence != null ? `（${Math.round(link.confidence * 100)}%）` : ''}` : ''
        }
      }))

      const option = {
        title: {
          text: '需求追溯关系网络',
          left: 'center',
          textStyle: { fontSize: 16, fontWeight: 'bold', color: '#2c3e50' }
        },
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderColor: 'transparent',
          textStyle: { color: '#fff' }
        },
        series: [
          {
            type: 'graph',
            layout: 'none',
            roam: true,
            label: { show: true, position: 'inside' },
            edgeSymbol: ['none', 'arrow'],
            edgeSymbolSize: [0, 10],
            data: processedNodes,
            links: processedLinks,
            lineStyle: { opacity: 0.85, width: 2, curveness: 0.1 },
            emphasis: {
              focus: 'adjacency',
              lineStyle: { width: 4 },
              itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' }
            }
          }
        ]
      }

      this.chart.setOption(option, true)
    },
    getLevelColor(level) {
      const colors = {
        1: '#e3f2fd',
        2: '#f3e5f5',
        3: '#e8f5e8',
        4: '#fff3e0',
        5: '#fce4ec'
      }
      return colors[level] || '#f5f5f5'
    },
    truncateText(text, maxLength) {
      const s = String(text || '')
      return s.length <= maxLength ? s : s.substring(0, maxLength) + '...'
    },
    escapeHtml(str) {
      return String(str)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;')
    }
  }
}
</script>

<style scoped>
.trace-chart {
  width: 100%;
  margin: 16px 0;
}

.chart-container {
  width: 100%;
  height: 520px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
}

@media (max-width: 768px) {
  .chart-container {
    height: 420px;
  }
}
</style>


