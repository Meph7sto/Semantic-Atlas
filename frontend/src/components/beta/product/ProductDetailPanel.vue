<template>
  <div class="card sa-card">
    <div class="card-header no-border">
      <div>
        <button type="button" class="back-btn" @click="$emit('back')">← 返回列表</button>
        <h2 class="section-title">{{ product.name }}</h2>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-small sa-button sa-button--secondary" @click="$emit('edit')">编辑</button>
        <button type="button" class="ghost-small danger sa-button sa-button--secondary" @click="$emit('delete')">归档</button>
      </div>
    </div>

    <div class="product-info">
      <div class="info-row">
        <span class="info-label">状态</span>
        <span :class="['status-pill', product.status]">
          {{ product.status === 'active' ? '活跃' : '已归档' }}
        </span>
      </div>
      <div class="info-row" v-if="product.version">
        <span class="info-label">版本</span>
        <span>{{ product.version }}</span>
      </div>
      <div class="info-row" v-if="product.roadmap">
        <span class="info-label">路线图</span>
        <span>{{ product.roadmap }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">描述</span>
        <span>{{ product.description || '暂无描述' }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">创建时间</span>
        <span>{{ formatDate(product.created_at) }}</span>
      </div>
      <div class="info-row" v-if="product.tags && product.tags.length">
        <span class="info-label">标签</span>
        <div class="product-tags">
          <span v-for="tag in product.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
    </div>

    <div class="stats-section" v-if="overview">
      <h3 class="subsection-title">概览统计</h3>
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-value">{{ overview.stats.projects.total || 0 }}</span>
          <span class="stat-label">项目</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ overview.stats.requirements.total || 0 }}</span>
          <span class="stat-label">需求</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ overview.stats.milestones.total || 0 }}</span>
          <span class="stat-label">里程碑</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ overview.stats.milestones.baselines || 0 }}</span>
          <span class="stat-label">基线</span>
        </div>
      </div>

      <div class="agg-tabs">
        <button
          v-for="tab in aggTabOptions"
          :key="tab.key"
          type="button"
          class="tab"
          :class="{ active: aggTab === tab.key }"
          @click="$emit('switchTab', tab.key)"
        >{{ tab.label }}</button>
      </div>

      <div class="agg-panel">
        <div v-if="loadingAgg" class="loading-state">加载中...</div>

        <div v-else-if="aggTab === 'requirements'">
          <div class="mini-search">
            <input
              type="text"
              :value="aggSearch"
              @input="$emit('update:aggSearch', $event.target.value)"
              placeholder="搜索需求标题/项目..."
              class="search-input full-width sa-input"
            />
          </div>
          <div v-if="aggRequirements.length === 0" class="empty-state">暂无需求</div>
          <div v-else class="agg-table">
            <div class="table-header"><span>项目</span><span>标题</span><span>类型</span><span>状态</span></div>
            <div v-for="r in aggRequirements" :key="r.req_id" class="table-row">
              <span>{{ r.project_name }}</span>
              <span class="cell-main"><strong>{{ r.title }}</strong></span>
              <span>{{ r.requirement_type }}</span>
              <span>{{ r.status }}</span>
            </div>
          </div>
        </div>

        <div v-else-if="aggTab === 'milestones'">
          <div v-if="aggMilestones.length === 0" class="empty-state">暂无里程碑</div>
          <div v-else class="agg-table">
            <div class="table-header"><span>项目</span><span>名称</span><span>类型</span><span>版本</span></div>
            <div v-for="m in aggMilestones" :key="m.milestone_id" class="table-row">
              <span>{{ m.project_name }}</span>
              <span class="cell-main"><strong>{{ m.name }}</strong></span>
              <span>{{ m.milestone_type }}</span>
              <span>{{ m.version || '-' }}</span>
            </div>
          </div>
        </div>

        <div v-else>
          <div v-if="aggBaselines.length === 0" class="empty-state">暂无基线</div>
          <div v-else class="agg-table">
            <div class="table-header"><span>项目</span><span>名称</span><span>版本</span><span>创建时间</span></div>
            <div v-for="b in aggBaselines" :key="b.milestone_id" class="table-row">
              <span>{{ b.project_name }}</span>
              <span class="cell-main"><strong>{{ b.name }}</strong></span>
              <span>{{ b.version || '-' }}</span>
              <span>{{ formatDate(b.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  product: { type: Object, required: true },
  overview: { type: Object, default: null },
  aggTab: { type: String, default: 'requirements' },
  loadingAgg: { type: Boolean, default: false },
  aggRequirements: { type: Array, default: () => [] },
  aggMilestones: { type: Array, default: () => [] },
  aggBaselines: { type: Array, default: () => [] },
  aggSearch: { type: String, default: '' },
})

defineEmits(['back', 'edit', 'delete', 'switchTab', 'update:aggSearch'])

const aggTabOptions = [
  { key: 'requirements', label: '需求' },
  { key: 'milestones', label: '里程碑' },
  { key: 'baselines', label: '基线' },
]

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.back-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #6b7280);
  cursor: pointer;
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
}

.back-btn:hover { color: var(--text-primary, #1f2937); }

.product-info {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.info-row { display: flex; gap: 1rem; align-items: flex-start; }

.info-label {
  min-width: 80px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  font-size: 0.875rem;
}

.stats-section { padding: 1rem 0; }

.subsection-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  margin: 0 0 1rem 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.stat-item {
  text-align: center;
  padding: 0.75rem;
  background: var(--surface-secondary, #f9fafb);
  border-radius: 8px;
}

.stat-value { display: block; font-size: 1.5rem; font-weight: 700; color: var(--text-primary, #1f2937); }
.stat-label { display: block; font-size: 0.75rem; color: var(--text-secondary, #6b7280); margin-top: 0.25rem; }

.agg-tabs { display: flex; gap: 0.5rem; margin-top: 1rem; }

.agg-tabs .tab {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 999px;
  background: white;
  color: var(--text-secondary, #6b7280);
  font-size: 0.875rem;
  cursor: pointer;
}

.agg-tabs .tab.active {
  border-color: var(--primary-color, #c4692f);
  color: var(--text-primary, #1f2937);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
}

.agg-panel { margin-top: 0.75rem; }
.mini-search { margin-bottom: 0.5rem; }

.agg-table {
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
  background: white;
}

.agg-table .table-header,
.agg-table .table-row {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr 1fr;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem 1rem;
}

.agg-table .table-header {
  background: var(--surface-secondary, #f9fafb);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.agg-table .table-row {
  font-size: 0.875rem;
  color: var(--text-primary, #1f2937);
  border-bottom: 1px solid var(--border-color, #f3f4f6);
}

.agg-table .table-row:last-child { border-bottom: none; }

.agg-table .cell-main {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-tags { display: flex; flex-wrap: wrap; gap: 0.5rem; }

.tag {
  background: var(--surface-secondary, #f3f4f6);
  color: var(--text-secondary, #6b7280);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.status-pill {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-pill.active { background: #d1fae5; color: #065f46; }
.status-pill.archived { background: #f3f4f6; color: #6b7280; }

.header-actions { display: flex; gap: 0.5rem; align-items: center; }

.ghost-small.danger { color: #dc2626; }
.ghost-small.danger:hover { background: #fef2f2; }

.search-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  font-size: 0.875rem;
}

.search-input.full-width { width: 100%; box-sizing: border-box; }
.search-input:focus { outline: none; border-color: var(--primary-color, #c4692f); }

.loading-state,
.empty-state {
  padding: 3rem;
  text-align: center;
  color: var(--text-secondary, #6b7280);
}
</style>
