<template>
  <div class="trace-chart">
    <div ref="chartContainer" class="chart-container"></div>
  </div>
</template>

<script>
import * as echarts from 'echarts'

export default {
  name: 'TraceChart',
  props: {
    traceData: {
      type: Array,
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
    if (this.chart) {
      this.chart.dispose()
    }
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
      if (!this.chart || !this.traceData || this.traceData.length === 0) {
        return
      }

      const nodes = this.traceData.map((item, index) => ({
        id: index.toString(),
        name: item.stage,
        x: (index % 4) * 200 + 100,
        y: Math.floor(index / 4) * 120 + 80,
        symbolSize: 60,
        itemStyle: {
          color: this.getNodeColor(item.type),
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          position: 'inside',
          fontSize: 12,
          fontWeight: 'bold',
          color: '#fff',
          formatter: function(params) {
            return params.name.length > 6 ? params.name.substring(0, 6) + '...' : params.name
          }
        },
        tooltip: {
          formatter: `<div style="max-width: 300px;">
            <strong>${item.stage}</strong><br/>
            状态: ${this.getStatusText(item.type)}<br/>
            描述: ${item.description}
          </div>`
        }
      }))

      const links = []
      for (let i = 0; i < this.traceData.length - 1; i++) {
        links.push({
          source: i.toString(),
          target: (i + 1).toString(),
          lineStyle: {
            color: '#999',
            width: 2,
            type: 'solid'
          },
          symbol: ['none', 'arrow'],
          symbolSize: [0, 8]
        })
      }

      const option = {
        title: {
          text: '需求追溯链',
          left: 'center',
          textStyle: {
            fontSize: 16,
            fontWeight: 'bold',
            color: '#2c3e50'
          }
        },
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderColor: 'transparent',
          textStyle: {
            color: '#fff'
          }
        },
        series: [{
          type: 'graph',
          layout: 'none',
          symbolSize: 60,
          roam: false,
          label: {
            show: true,
            position: 'inside'
          },
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: [0, 8],
          data: nodes,
          links: links,
          lineStyle: {
            opacity: 0.9,
            width: 2,
            curveness: 0.1
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              width: 4
            }
          }
        }]
      }

      this.chart.setOption(option, true)
    },

    getNodeColor(type) {
      const colors = {
        success: '#67c23a',
        warning: '#e6a23c',
        error: '#f56c6c',
        info: '#409eff'
      }
      return colors[type] || '#909399'
    },

    getStatusText(type) {
      const texts = {
        success: '正常',
        warning: '注意',
        error: '风险',
        info: '信息'
      }
      return texts[type] || '未知'
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
  height: 400px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
}
</style>
