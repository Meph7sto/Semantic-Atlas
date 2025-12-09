<template>
  <div class="analysis-history">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon><Clock /></el-icon>
            <span>分析历史</span>
          </div>
          <el-button 
            type="primary" 
            @click="refreshList"
            :loading="loading"
            size="small"
          >
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <!-- 搜索和筛选 -->
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :lg="8" :md="12" :sm="24">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索需求标题或描述..."
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
          <el-col :lg="6" :md="12" :sm="24">
            <el-select 
              v-model="selectedTimeRange" 
              placeholder="时间范围"
              clearable
              style="width: 100%"
            >
              <el-option label="最近7天" value="7days" />
              <el-option label="最近30天" value="30days" />
              <el-option label="最近3个月" value="3months" />
              <el-option label="全部" value="all" />
            </el-select>
          </el-col>
        </el-row>
      </div>

      <!-- 需求列表 -->
      <div v-loading="loading" class="requirements-list">
        <div v-if="filteredRequirements.length === 0 && !loading" class="empty-state">
          <el-empty description="暂无分析记录" />
        </div>
        
        <div 
          v-for="requirement in paginatedRequirements" 
          :key="requirement.id"
          class="requirement-item"
        >
          <el-card class="requirement-card" shadow="hover">
            <div class="requirement-header">
              <div class="requirement-info">
                <h4 class="requirement-title">{{ requirement.title }}</h4>
                <p class="requirement-description">{{ requirement.description }}</p>
              </div>
              <div class="requirement-actions">
                <el-button 
                  type="primary" 
                  size="small"
                  @click="viewDetail(requirement)"
                >
                  <el-icon><View /></el-icon>
                  查看详情
                </el-button>
                <el-button 
                  type="danger" 
                  size="small"
                  @click="deleteRequirement(requirement)"
                >
                  <el-icon><Delete /></el-icon>
                  删除
                </el-button>
              </div>
            </div>
            
            <div class="requirement-meta">
              <el-tag type="info" size="small">
                <el-icon><Timer /></el-icon>
                {{ formatDate(requirement.created_at) }}
              </el-tag>
              <el-tag type="success" size="small">
                <el-icon><Document /></el-icon>
                ID: {{ requirement.id }}
              </el-tag>
            </div>
          </el-card>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="filteredRequirements.length"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="selectedRequirement?.title"
      width="80%"
      :close-on-click-modal="false"
    >
      <div v-if="selectedRequirement" class="requirement-detail">
        <!-- 基本信息 -->
        <el-descriptions title="基本信息" :column="2" border>
          <el-descriptions-item label="需求ID">
            {{ selectedRequirement.id }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDate(selectedRequirement.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDate(selectedRequirement.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="需求描述" :span="2">
            {{ selectedRequirement.description }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 追溯链分析 -->
        <div v-if="requirementDetail" class="detail-sections">
          <!-- 可视化图表 -->
          <div class="section">
            <h3>追溯链可视化</h3>
            <TraceChart :trace-data="requirementDetail.traceAnalysis" />
          </div>

          <!-- 阶段分析 -->
          <div class="section">
            <h3>阶段分析</h3>
            <el-timeline>
              <el-timeline-item
                v-for="(trace, index) in requirementDetail.traceAnalysis"
                :key="index"
                :type="getTimelineType(trace.type)"
              >
                <el-card class="trace-detail-card">
                  <div class="trace-detail-header">
                    <strong>{{ trace.stage }}</strong>
                    <el-tag :type="getTagType(trace.type)" size="small">
                      {{ getStatusText(trace.type) }}
                    </el-tag>
                  </div>
                  <p>{{ trace.description }}</p>
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </div>

          <!-- 风险分析 -->
          <div v-if="requirementDetail.risks?.length > 0" class="section">
            <h3>风险分析</h3>
            <el-row :gutter="12">
              <el-col 
                v-for="(risk, index) in requirementDetail.risks" 
                :key="index"
                :lg="12" 
                :md="24"
              >
                <el-alert
                  :title="risk.title"
                  :description="risk.description"
                  :type="getRiskType(risk.level)"
                  show-icon
                  :closable="false"
                />
              </el-col>
            </el-row>
          </div>

          <!-- 改进建议 -->
          <div v-if="requirementDetail.suggestions?.length > 0" class="section">
            <h3>改进建议</h3>
            <ul class="suggestions-list">
              <li v-for="(suggestion, index) in requirementDetail.suggestions" :key="index">
                <el-icon><Check /></el-icon>
                {{ suggestion.content }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { ElMessage, ElMessageBox } from 'element-plus'
import { requirementApi } from '../api'
import TraceChart from '../components/TraceChart.vue'
import {
  Clock, Refresh, Search, View, Delete, Timer, Document, Check
} from '@element-plus/icons-vue'

export default {
  name: 'AnalysisHistory',
  components: {
    TraceChart,
    Clock, Refresh, Search, View, Delete, Timer, Document, Check
  },
  data() {
    return {
      loading: false,
      requirements: [],
      searchKeyword: '',
      selectedTimeRange: 'all',
      currentPage: 1,
      pageSize: 10,
      detailDialogVisible: false,
      selectedRequirement: null,
      requirementDetail: null
    }
  },
  computed: {
    filteredRequirements() {
      let filtered = this.requirements

      // 搜索过滤
      if (this.searchKeyword) {
        const keyword = this.searchKeyword.toLowerCase()
        filtered = filtered.filter(req => 
          req.title.toLowerCase().includes(keyword) ||
          req.description.toLowerCase().includes(keyword)
        )
      }

      // 时间范围过滤
      if (this.selectedTimeRange && this.selectedTimeRange !== 'all') {
        const now = new Date()
        const cutoffDate = new Date()
        
        switch (this.selectedTimeRange) {
          case '7days':
            cutoffDate.setDate(now.getDate() - 7)
            break
          case '30days':
            cutoffDate.setDate(now.getDate() - 30)
            break
          case '3months':
            cutoffDate.setMonth(now.getMonth() - 3)
            break
        }

        filtered = filtered.filter(req => 
          new Date(req.created_at) >= cutoffDate
        )
      }

      return filtered
    },

    paginatedRequirements() {
      const start = (this.currentPage - 1) * this.pageSize
      const end = start + this.pageSize
      return this.filteredRequirements.slice(start, end)
    }
  },
  async mounted() {
    await this.loadRequirements()
  },
  methods: {
    // 加载需求列表
    async loadRequirements() {
      this.loading = true
      try {
        const result = await requirementApi.getRequirements(1, 1000) // 加载所有记录
        if (result.success) {
          this.requirements = result.data.requirements
        } else {
          ElMessage.error('加载失败')
        }
      } catch (error) {
        console.error('加载需求列表失败:', error)
        ElMessage.error('加载失败，请重试')
      } finally {
        this.loading = false
      }
    },

    // 刷新列表
    async refreshList() {
      await this.loadRequirements()
      ElMessage.success('刷新成功')
    },

    // 搜索处理
    handleSearch() {
      this.currentPage = 1
    },

    // 查看详情
    async viewDetail(requirement) {
      this.selectedRequirement = requirement
      this.detailDialogVisible = true
      
      try {
        const result = await requirementApi.getRequirementDetail(requirement.id)
        if (result.success) {
          this.requirementDetail = result.data
        }
      } catch (error) {
        console.error('加载详情失败:', error)
        ElMessage.error('加载详情失败')
      }
    },

    // 删除需求
    async deleteRequirement(requirement) {
      try {
        await ElMessageBox.confirm(
          `确定要删除需求"${requirement.title}"吗？此操作不可恢复。`,
          '确认删除',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )

        const result = await requirementApi.deleteRequirement(requirement.id)
        if (result.success) {
          ElMessage.success('删除成功')
          await this.loadRequirements()
        } else {
          ElMessage.error('删除失败')
        }
      } catch (error) {
        if (error !== 'cancel') {
          console.error('删除失败:', error)
          ElMessage.error('删除失败')
        }
      }
    },

    // 分页处理
    handleSizeChange(val) {
      this.pageSize = val
      this.currentPage = 1
    },

    handleCurrentChange(val) {
      this.currentPage = val
    },

    // 格式化日期
    formatDate(dateString) {
      const date = new Date(dateString)
      return date.toLocaleString('zh-CN')
    },

    // 获取时间线类型
    getTimelineType(type) {
      const types = {
        success: 'success',
        warning: 'warning',
        error: 'danger',
        info: 'info'
      }
      return types[type] || 'info'
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

    // 获取风险类型
    getRiskType(level) {
      const types = {
        high: 'error',
        warning: 'warning',
        info: 'info',
        low: 'success'
      }
      return types[level] || 'info'
    }
  }
}
</script>

<style scoped>
.analysis-history {
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

.filter-bar {
  margin-bottom: 20px;
}

.requirements-list {
  min-height: 400px;
}

.requirement-item {
  margin-bottom: 16px;
}

.requirement-card {
  transition: all 0.3s;
}

.requirement-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0,0,0,0.1);
}

.requirement-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.requirement-info {
  flex: 1;
  margin-right: 16px;
}

.requirement-title {
  margin: 0 0 8px 0;
  color: #2c3e50;
  font-size: 16px;
  font-weight: bold;
}

.requirement-description {
  margin: 0;
  color: #606266;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.requirement-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.requirement-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}

.requirement-meta .el-tag {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pagination-container {
  margin-top: 20px;
  text-align: center;
}

.requirement-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.detail-sections {
  margin-top: 20px;
}

.section {
  margin-bottom: 32px;
}

.section h3 {
  margin-bottom: 16px;
  color: #2c3e50;
  font-size: 18px;
  border-bottom: 2px solid #409eff;
  padding-bottom: 8px;
}

.trace-detail-card {
  margin-bottom: 8px;
}

.trace-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.suggestions-list {
  list-style: none;
  padding: 0;
}

.suggestions-list li {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.suggestions-list li:last-child {
  border-bottom: none;
}

.suggestions-list li .el-icon {
  color: #67c23a;
  margin-right: 8px;
  flex-shrink: 0;
}

.empty-state {
  text-align: center;
  padding: 60px 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .requirement-header {
    flex-direction: column;
    align-items: stretch;
  }
  
  .requirement-actions {
    margin-top: 12px;
    justify-content: flex-end;
  }
  
  .requirement-meta {
    flex-wrap: wrap;
  }
}
</style>
