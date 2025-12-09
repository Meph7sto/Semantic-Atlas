<template>
  <div class="model-status">
    <el-card class="status-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <el-icon><Connection /></el-icon>
          <span>AI模型状态</span>
          <el-button 
            type="primary" 
            size="small"
            @click="refreshStatus"
            :loading="loading"
          >
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <div v-if="loading" class="loading-container">
        <el-skeleton :rows="3" animated />
      </div>

      <div v-else class="status-content">
        <!-- 连接状态总览 -->
        <div class="status-overview">
          <el-tag 
            :type="getOverallStatusType()" 
            size="large"
            class="status-tag"
          >
            <el-icon><component :is="getStatusIcon()" /></el-icon>
            {{ getOverallStatusText() }}
          </el-tag>
          
          <div class="model-info">
            <span class="model-name">{{ getCurrentModelName() }}</span>
            <span class="model-version">{{ status?.model_info?.model_used || '未知' }}</span>
          </div>
        </div>

        <!-- AutoDL连接详情 -->
        <div v-if="status?.autodl_config" class="autodl-info">
          <h4>
            <el-icon><Server /></el-icon>
            AutoDL服务器信息
          </h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="服务器">
              {{ status.autodl_config.host }}:{{ status.autodl_config.port }}
            </el-descriptions-item>
            <el-descriptions-item label="模型">
              {{ status.autodl_config.model_name }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 连接状态详情 -->
        <div v-if="status?.connection_status" class="connection-details">
          <h4>
            <el-icon><Link /></el-icon>
            连接状态详情
          </h4>
          
          <div class="status-items">
            <div class="status-item">
              <span class="status-label">模型可用:</span>
              <el-tag 
                :type="status.connection_status.model_available ? 'success' : 'danger'"
                size="small"
              >
                {{ status.connection_status.model_available ? '是' : '否' }}
              </el-tag>
            </div>
            
            <div class="status-item">
              <span class="status-label">GPU推理API:</span>
              <el-tag 
                :type="status.connection_status.gpu_inference_api ? 'success' : 'info'"
                size="small"
              >
                {{ status.connection_status.gpu_inference_api ? '已连接' : '未连接' }}
              </el-tag>
            </div>
            
            <div class="status-item">
              <span class="status-label">后端API:</span>
              <el-tag 
                :type="status.connection_status.backend_api ? 'success' : 'info'"
                size="small"
              >
                {{ status.connection_status.backend_api ? '已连接' : '未连接' }}
              </el-tag>
            </div>
          </div>
        </div>

        <!-- 性能指标 -->
        <div v-if="performanceData" class="performance-section">
          <h4>
            <el-icon><TrendCharts /></el-icon>
            性能指标
          </h4>
          <div class="performance-metrics">
            <div class="metric-item">
              <span class="metric-label">响应时间:</span>
              <span class="metric-value">{{ performanceData.responseTime }}ms</span>
            </div>
            <div class="metric-item">
              <span class="metric-label">成功率:</span>
              <span class="metric-value">{{ performanceData.successRate }}%</span>
            </div>
          </div>
        </div>

        <!-- 连接建议 -->
        <div v-if="!status?.connection_status?.model_available" class="connection-help">
          <el-alert
            title="AutoDL模型连接指南"
            type="info"
            :closable="false"
            show-icon
          >
            <template #default>
              <div class="help-content">
                <p><strong>设置SSH端口转发:</strong></p>
                <el-code class="ssh-command">
                  ssh -p 29250 -L 11434:localhost:11434 root@connect.westc.gpuhub.com
                </el-code>
                <p><strong>密码:</strong> xbKhX2bHw4GO</p>
                <p>设置完成后点击刷新按钮</p>
              </div>
            </template>
          </el-alert>
        </div>

        <!-- 重连按钮 -->
        <div class="action-buttons">
          <el-button 
            type="warning" 
            @click="reconnectModel"
            :loading="reconnecting"
          >
            <el-icon><RefreshRight /></el-icon>
            重新连接
          </el-button>
          
          <el-button 
            type="info" 
            @click="testConnection"
            :loading="testing"
          >
            <el-icon><Lightning /></el-icon>
            测试连接
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ElMessage } from 'element-plus'
import { requirementApi } from '../api'
import {
  Connection, Refresh, Server, Link, TrendCharts,
  RefreshRight, Lightning, SuccessFilled, WarningFilled, 
  CircleCloseFilled, InfoFilled
} from '@element-plus/icons-vue'

export default {
  name: 'ModelStatus',
  components: {
    Connection, Refresh, Server, Link, TrendCharts,
    RefreshRight, Lightning, SuccessFilled, WarningFilled,
    CircleCloseFilled, InfoFilled
  },
  data() {
    return {
      status: null,
      loading: false,
      reconnecting: false,
      testing: false,
      performanceData: null
    }
  },
  async mounted() {
    await this.loadStatus()
  },
  methods: {
    async loadStatus() {
      this.loading = true
      try {
        const response = await requirementApi.getModelStatus()
        if (response.success) {
          this.status = response.data
        } else {
          // 尝试从health接口获取状态
          const healthResponse = await requirementApi.healthCheck()
          if (healthResponse.autodl_connection) {
            this.status = healthResponse.autodl_connection
          }
        }
      } catch (error) {
        console.error('获取模型状态失败:', error)
        ElMessage.error('获取模型状态失败')
      } finally {
        this.loading = false
      }
    },

    async refreshStatus() {
      await this.loadStatus()
      ElMessage.success('状态已刷新')
    },

    async reconnectModel() {
      this.reconnecting = true
      try {
        const response = await requirementApi.reconnectModel()
        if (response.success) {
          this.status = response.status
          ElMessage.success('重新连接成功')
        } else {
          ElMessage.error('重新连接失败')
        }
      } catch (error) {
        console.error('重新连接失败:', error)
        ElMessage.error('重新连接失败')
      } finally {
        this.reconnecting = false
      }
    },

    async testConnection() {
      this.testing = true
      const startTime = Date.now()
      
      try {
        const response = await requirementApi.analyzeRequirement('测试连接', false)
        const responseTime = Date.now() - startTime
        
        if (response.success) {
          this.performanceData = {
            responseTime,
            successRate: 100
          }
          ElMessage.success(`连接测试成功 (${responseTime}ms)`)
        } else {
          ElMessage.warning('连接测试失败，但服务器响应正常')
        }
      } catch (error) {
        console.error('连接测试失败:', error)
        ElMessage.error('连接测试失败')
      } finally {
        this.testing = false
      }
    },

    getOverallStatusType() {
      if (!this.status?.connection_status) return 'info'
      
      if (this.status.connection_status.model_available) {
        return 'success'
      } else if (this.status.connection_status.gpu_inference_api || this.status.connection_status.backend_api) {
        return 'warning'
      } else {
        return 'danger'
      }
    },

    getOverallStatusText() {
      if (!this.status?.connection_status) return '状态未知'
      
      if (this.status.connection_status.model_available) {
        return 'AutoDL GPU推理已连接'
      } else if (this.status.connection_status.gpu_inference_api || this.status.connection_status.backend_api) {
        return '部分连接可用'
      } else {
        return '使用本地规则引擎'
      }
    },

    getStatusIcon() {
      const type = this.getOverallStatusType()
      const icons = {
        success: SuccessFilled,
        warning: WarningFilled, 
        danger: CircleCloseFilled,
        info: InfoFilled
      }
      return icons[type] || InfoFilled
    },

    getCurrentModelName() {
      if (this.status?.connection_status?.model_available) {
        return this.status.autodl_config?.model_name || 'SU模型'
      } else {
        return '本地规则引擎'
      }
    }
  }
}
</script>

<style scoped>
.model-status {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  color: #2c3e50;
}

.card-header .el-icon {
  margin-right: 8px;
}

.loading-container {
  padding: 20px 0;
}

.status-content {
  space-y: 20px;
}

.status-overview {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
}

.status-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: bold;
}

.model-info {
  text-align: right;
}

.model-name {
  display: block;
  font-size: 16px;
  font-weight: bold;
  color: #2c3e50;
}

.model-version {
  display: block;
  font-size: 12px;
  color: #666;
  margin-top: 2px;
}

.autodl-info,
.connection-details,
.performance-section {
  margin-bottom: 20px;
}

.autodl-info h4,
.connection-details h4,
.performance-section h4 {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  color: #2c3e50;
  font-size: 14px;
}

.autodl-info h4 .el-icon,
.connection-details h4 .el-icon,
.performance-section h4 .el-icon {
  margin-right: 6px;
  color: #409eff;
}

.status-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
}

.status-label {
  font-size: 14px;
  color: #606266;
}

.performance-metrics {
  display: flex;
  gap: 20px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  flex: 1;
}

.metric-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: bold;
  color: #2c3e50;
}

.connection-help {
  margin: 20px 0;
}

.help-content p {
  margin: 8px 0;
}

.ssh-command {
  display: block;
  padding: 8px 12px;
  background: #f1f1f1;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  margin: 8px 0;
  word-break: break-all;
}

.action-buttons {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .status-overview {
    flex-direction: column;
    gap: 10px;
    text-align: center;
  }
  
  .performance-metrics {
    flex-direction: column;
  }
  
  .action-buttons {
    flex-direction: column;
  }
}
</style>
