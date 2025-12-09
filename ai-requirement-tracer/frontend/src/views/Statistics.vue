<template>
  <div class="statistics">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon><DataAnalysis /></el-icon>
            <span>统计数据</span>
          </div>
          <el-button 
            type="primary" 
            @click="refreshStatistics"
            :loading="loading"
            size="small"
          >
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <div v-loading="loading">
        <!-- 概览卡片 -->
        <el-row :gutter="20" class="overview-cards">
          <el-col :lg="6" :md="12" :sm="24">
            <el-card class="stat-card">
              <div class="stat-content">
                <div class="stat-icon requirements">
                  <el-icon><Document /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-number">{{ statistics.total_requirements || 0 }}</div>
                  <div class="stat-label">总需求数</div>
                </div>
              </div>
            </el-card>
          </el-col>
          
          <el-col :lg="6" :md="12" :sm="24">
            <el-card class="stat-card">
              <div class="stat-content">
                <div class="stat-icon traces">
                  <el-icon><Share /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-number">{{ statistics.total_traces || 0 }}</div>
                  <div class="stat-label">追溯记录</div>
                </div>
              </div>
            </el-card>
          </el-col>
          
          <el-col :lg="6" :md="12" :sm="24">
            <el-card class="stat-card">
              <div class="stat-content">
                <div class="stat-icon risks">
                  <el-icon><WarningFilled /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-number">{{ statistics.total_risks || 0 }}</div>
                  <div class="stat-label">风险记录</div>
                </div>
              </div>
            </el-card>
          </el-col>
          
          <el-col :lg="6" :md="12" :sm="24">
            <el-card class="stat-card">
              <div class="stat-content">
                <div class="stat-icon success-rate">
                  <el-icon><TrendCharts /></el-icon>
                </div>
                <div class="stat-info">
                  <div class="stat-number">{{ successRate }}%</div>
                  <div class="stat-label">成功率</div>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 图表区域 -->
        <el-row :gutter="20" class="charts-section">
          <!-- 追溯状态分布 -->
          <el-col :lg="12" :md="24">
            <el-card class="chart-card">
              <template #header>
                <h3>追溯状态分布</h3>
              </template>
              <div ref="traceTypeChart" class="chart-container"></div>
            </el-card>
          </el-col>
          
          <!-- 风险等级分布 -->
          <el-col :lg="12" :md="24">
            <el-card class="chart-card">
              <template #header>
                <h3>风险等级分布</h3>
              </template>
              <div ref="riskLevelChart" class="chart-container"></div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 详细统计表格 -->
        <el-card class="table-card">
          <template #header>
            <h3>详细统计</h3>
          </template>
          
          <el-tabs v-model="activeTab">
            <el-tab-pane label="追溯状态统计" name="trace">
              <el-table :data="traceStatsTable" style="width: 100%">
                <el-table-column prop="type" label="状态类型" width="120">
                  <template #default="{ row }">
                    <el-tag :type="getTagType(row.type)">
                      {{ getStatusText(row.type) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="count" label="记录数" width="100" />
                <el-table-column prop="percentage" label="占比" width="100">
                  <template #default="{ row }">
                    {{ row.percentage }}%
                  </template>
                </el-table-column>
                <el-table-column label="进度条">
                  <template #default="{ row }">
                    <el-progress 
                      :percentage="row.percentage" 
                      :color="getProgressColor(row.type)"
                      :show-text="false"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            
            <el-tab-pane label="风险等级统计" name="risk">
              <el-table :data="riskStatsTable" style="width: 100%">
                <el-table-column prop="level" label="风险等级" width="120">
                  <template #default="{ row }">
                    <el-tag :type="getRiskTagType(row.level)">
                      {{ getRiskLevelText(row.level) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="count" label="记录数" width="100" />
                <el-table-column prop="percentage" label="占比" width="100">
                  <template #default="{ row }">
                    {{ row.percentage }}%
                  </template>
                </el-table-column>
                <el-table-column label="进度条">
                  <template #default="{ row }">
                    <el-progress 
                      :percentage="row.percentage" 
                      :color="getRiskProgressColor(row.level)"
                      :show-text="false"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ElMessage } from 'element-plus'
import { requirementApi } from '../api'
import * as echarts from 'echarts'
import {
  DataAnalysis, Refresh, Document, Share, WarningFilled, TrendCharts
} from '@element-plus/icons-vue'

export default {
  name: 'Statistics',
  components: {
    DataAnalysis, Refresh, Document, Share, WarningFilled, TrendCharts
  },
  data() {
    return {
      loading: false,
      statistics: {},
      activeTab: 'trace',
      traceTypeChart: null,
      riskLevelChart: null
    }
  },
  computed: {
    successRate() {
      if (!this.statistics.trace_type_stats) return 0
      const total = Object.values(this.statistics.trace_type_stats).reduce((sum, count) => sum + count, 0)
      const success = this.statistics.trace_type_stats.success || 0
      return total > 0 ? Math.round((success / total) * 100) : 0
    },

    traceStatsTable() {
      if (!this.statistics.trace_type_stats) return []
      
      const stats = this.statistics.trace_type_stats
      const total = Object.values(stats).reduce((sum, count) => sum + count, 0)
      
      return Object.entries(stats).map(([type, count]) => ({
        type,
        count,
        percentage: total > 0 ? Math.round((count / total) * 100) : 0
      }))
    },

    riskStatsTable() {
      if (!this.statistics.risk_level_stats) return []
      
      const stats = this.statistics.risk_level_stats
      const total = Object.values(stats).reduce((sum, count) => sum + count, 0)
      
      return Object.entries(stats).map(([level, count]) => ({
        level,
        count,
        percentage: total > 0 ? Math.round((count / total) * 100) : 0
      }))
    }
  },
  async mounted() {
    await this.loadStatistics()
    this.initCharts()
  },
  beforeUnmount() {
    if (this.traceTypeChart) {
      this.traceTypeChart.dispose()
    }
    if (this.riskLevelChart) {
      this.riskLevelChart.dispose()
    }
  },
  methods: {
    // 加载统计数据
    async loadStatistics() {
      this.loading = true
      try {
        const result = await requirementApi.getStatistics()
        if (result.success) {
          this.statistics = result.data
          this.updateCharts()
        } else {
          ElMessage.error('加载统计数据失败')
        }
      } catch (error) {
        console.error('加载统计数据失败:', error)
        ElMessage.error('加载失败，请重试')
      } finally {
        this.loading = false
      }
    },

    // 刷新统计数据
    async refreshStatistics() {
      await this.loadStatistics()
      ElMessage.success('刷新成功')
    },

    // 初始化图表
    initCharts() {
      this.traceTypeChart = echarts.init(this.$refs.traceTypeChart)
      this.riskLevelChart = echarts.init(this.$refs.riskLevelChart)
      this.updateCharts()
    },

    // 更新图表
    updateCharts() {
      if (!this.traceTypeChart || !this.riskLevelChart) return

      // 追溯状态分布饼图
      const traceData = Object.entries(this.statistics.trace_type_stats || {}).map(([type, count]) => ({
        name: this.getStatusText(type),
        value: count,
        itemStyle: {
          color: this.getChartColor(type)
        }
      }))

      const traceOption = {
        title: {
          text: '追溯状态分布',
          left: 'center',
          textStyle: {
            fontSize: 14,
            fontWeight: 'bold'
          }
        },
        tooltip: {
          trigger: 'item',
          formatter: '{a} <br/>{b}: {c} ({d}%)'
        },
        legend: {
          bottom: '5%',
          left: 'center'
        },
        series: [{
          name: '追溯状态',
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['50%', '45%'],
          data: traceData,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }]
      }

      // 风险等级分布饼图
      const riskData = Object.entries(this.statistics.risk_level_stats || {}).map(([level, count]) => ({
        name: this.getRiskLevelText(level),
        value: count,
        itemStyle: {
          color: this.getRiskChartColor(level)
        }
      }))

      const riskOption = {
        title: {
          text: '风险等级分布',
          left: 'center',
          textStyle: {
            fontSize: 14,
            fontWeight: 'bold'
          }
        },
        tooltip: {
          trigger: 'item',
          formatter: '{a} <br/>{b}: {c} ({d}%)'
        },
        legend: {
          bottom: '5%',
          left: 'center'
        },
        series: [{
          name: '风险等级',
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['50%', '45%'],
          data: riskData,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }]
      }

      this.traceTypeChart.setOption(traceOption)
      this.riskLevelChart.setOption(riskOption)
    },

    // 获取标签类型
    getTagType(type) {
      const types = {
        success: 'success',
        warning: 'warning',
        error: 'danger',
        info: 'info'
      }
      return types[type] || 'info'
    },

    // 获取状态文本
    getStatusText(type) {
      const texts = {
        success: '正常',
        warning: '注意',
        error: '风险',
        info: '信息'
      }
      return texts[type] || '未知'
    },

    // 获取进度条颜色
    getProgressColor(type) {
      const colors = {
        success: '#67c23a',
        warning: '#e6a23c',
        error: '#f56c6c',
        info: '#409eff'
      }
      return colors[type] || '#909399'
    },

    // 获取图表颜色
    getChartColor(type) {
      return this.getProgressColor(type)
    },

    // 获取风险标签类型
    getRiskTagType(level) {
      const types = {
        high: 'danger',
        warning: 'warning',
        info: 'info',
        low: 'success'
      }
      return types[level] || 'info'
    },

    // 获取风险等级文本
    getRiskLevelText(level) {
      const texts = {
        high: '高风险',
        warning: '中风险',
        info: '低风险',
        low: '极低风险'
      }
      return texts[level] || '未知'
    },

    // 获取风险进度条颜色
    getRiskProgressColor(level) {
      const colors = {
        high: '#f56c6c',
        warning: '#e6a23c',
        info: '#409eff',
        low: '#67c23a'
      }
      return colors[level] || '#909399'
    },

    // 获取风险图表颜色
    getRiskChartColor(level) {
      return this.getRiskProgressColor(level)
    }
  }
}
</script>

<style scoped>
.statistics {
  padding: 20px 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  font-weight: bold;
  color: #2c3e50;
}

.header-left .el-icon {
  margin-right: 8px;
}

.overview-cards {
  margin-bottom: 20px;
}

.stat-card {
  margin-bottom: 16px;
  transition: all 0.3s;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 25px rgba(0,0,0,0.15);
}

.stat-content {
  display: flex;
  align-items: center;
  padding: 10px 0;
}

.stat-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 24px;
  color: white;
}

.stat-icon.requirements {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-icon.traces {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-icon.risks {
  background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
}

.stat-icon.success-rate {
  background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
}

.stat-info {
  flex: 1;
}

.stat-number {
  font-size: 28px;
  font-weight: bold;
  color: #2c3e50;
  line-height: 1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.charts-section {
  margin-bottom: 20px;
}

.chart-card {
  margin-bottom: 16px;
}

.chart-card h3 {
  margin: 0;
  color: #2c3e50;
  font-size: 16px;
  font-weight: bold;
}

.chart-container {
  height: 300px;
  width: 100%;
}

.table-card h3 {
  margin: 0;
  color: #2c3e50;
  font-size: 16px;
  font-weight: bold;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .stat-content {
    flex-direction: column;
    text-align: center;
  }
  
  .stat-icon {
    margin-right: 0;
    margin-bottom: 12px;
  }
  
  .chart-container {
    height: 250px;
  }
}
</style>
