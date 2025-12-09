<template>
  <div class="trace-chart">
    <div ref="chartContainer" class="chart-container"></div>
    <div class="legend">
      <div class="legend-item">
        <div class="legend-color" style="background-color: #e3f2fd;"></div>
        <span>用户故事</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background-color: #f3e5f5;"></div>
        <span>功能需求</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background-color: #e8f5e8;"></div>
        <span>业务需求</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background-color: #fff3e0;"></div>
        <span>系统需求</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background-color: #fce4ec;"></div>
        <span>战略目标</span>
      </div>
    </div>
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
      if (!this.chart || !this.traceData || !this.traceData.trace_network) {
        return
      }

      const { nodes, links } = this.traceData.trace_network

      // 根据层级排列节点位置
      const processedNodes = nodes.map((node, index) => {
        const level = node.level || 3
        const levelNodes = nodes.filter(n => n.level === level)
        const levelIndex = levelNodes.findIndex(n => n.id === node.id)
        
        return {
          id: node.id,
          name: this.truncateText(node.text, 20),
          category: level - 1,
          symbolSize: node.is_current ? 80 : 60,
          x: levelIndex * 200 + 100,
          y: (6 - level) * 100 + 50,
          itemStyle: {
            color: node.color || this.getLevelColor(level),
            borderColor: node.is_current ? '#ff4757' : '#fff',
            borderWidth: node.is_current ? 3 : 2
          },
          label: {
            show: true,
            position: 'inside',
            fontSize: node.is_current ? 12 : 10,
            fontWeight: node.is_current ? 'bold' : 'normal',
            color: '#333',
            formatter: function(params) {
              return params.name
            }
          },
          tooltip: {
            formatter: `<div style="max-width: 300px;">
              <strong>${node.name}</strong><br/>
              ${node.text}<br/>
              <small>层级: ${node.level}</small>
            </div>`
          }
        }
      })

      // 处理连接线
      const processedLinks = links.map(link => ({
        source: link.source,
        target: link.target,
        lineStyle: {
          color: link.type === 'derives_from' ? '#3742fa' : '#2ed573',
          width: 2,
          type: link.type === 'derives_from' ? 'solid' : 'dashed'
        },
        symbol: ['none', 'arrow'],
        symbolSize: [0, 10],
        label: {
          show: true,
          fontSize: 10,
          color: '#666',
          formatter: link.label
        }
      }))

      // 创建分类
      const categories = [
        { name: '用户故事' },
        { name: '功能需求' },
        { name: '业务需求' },
        { name: '系统需求' },
        { name: '战略目标' }
      ]

      const option = {
        title: {
          text: '需求追溯链网络',
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
        legend: {
          bottom: 20,
          left: 'center',
          data: categories.map(cat => cat.name),
          textStyle: {
            fontSize: 12
          }
        },
        series: [{
          type: 'graph',
          layout: 'none',
          symbolSize: 60,
          roam: true,
          categories: categories,
          label: {
            show: true,
            position: 'inside'
          },
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: [0, 10],
          data: processedNodes,
          links: processedLinks,
          lineStyle: {
            opacity: 0.8,
            width: 2,
            curveness: 0.1
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              width: 4
            },
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0,0,0,0.3)'
            }
          }
        }]
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
      if (text.length <= maxLength) {
        return text
      }
      return text.substring(0, maxLength) + '...'
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
  height: 500px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fff;
}

.legend {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #666;
}

.legend-color {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  border: 1px solid #ddd;
}

@media (max-width: 768px) {
  .chart-container {
    height: 400px;
  }
  
  .legend {
    gap: 10px;
  }
  
  .legend-item {
    font-size: 11px;
  }
}
</style>

