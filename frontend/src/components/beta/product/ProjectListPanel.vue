<template>
  <div class="card sa-card">
    <div class="card-header no-border">
      <div>
        <p class="card-kicker">Projects</p>
        <h2 class="section-title">关联项目</h2>
      </div>
      <button type="button" class="action-btn brown small sa-button sa-button--primary" @click="$emit('create')">
        新建项目
      </button>
    </div>

    <div v-if="loading" class="loading-state"><span>加载中...</span></div>

    <div v-else-if="projects.length === 0" class="empty-state">
      <p>暂无关联项目</p>
      <button type="button" class="action-btn brown sa-button sa-button--primary" @click="$emit('create')">
        创建第一个项目
      </button>
    </div>

    <div v-else class="data-table">
      <div class="table-header">
        <span>项目名称</span>
        <span>状态</span>
        <span>创建时间</span>
        <span>操作</span>
      </div>
      <div v-for="project in projects" :key="project.project_id" class="table-row">
        <div class="cell-main">
          <strong>{{ project.name }}</strong>
          <span class="cell-desc">{{ project.description }}</span>
        </div>
        <span>
          <span :class="['status-pill', project.status]">
            {{ project.status === 'active' ? '活跃' : '已归档' }}
          </span>
        </span>
        <span>{{ formatDate(project.created_at) }}</span>
        <span class="row-actions">
          <button type="button" class="ghost-small sa-button sa-button--secondary" @click="$emit('goto', project)">查看</button>
          <button type="button" class="ghost-small sa-button sa-button--secondary" @click="$emit('edit', project)">编辑</button>
          <button type="button" class="ghost-small danger sa-button sa-button--secondary" @click="$emit('delete', project)">归档</button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  projects: { type: Array, required: true },
  loading: { type: Boolean, default: false },
})

defineEmits(['create', 'edit', 'delete', 'goto'])

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.loading-state,
.empty-state {
  padding: 3rem;
  text-align: center;
  color: var(--text-secondary, #6b7280);
}

.empty-state button { margin-top: 1rem; }

.status-pill {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-pill.active { background: #d1fae5; color: #065f46; }
.status-pill.archived { background: #f3f4f6; color: #6b7280; }

.cell-desc {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #6b7280);
  margin-top: 0.25rem;
}

.row-actions {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
  align-items: center;
}

.ghost-small.danger { color: #dc2626; }
.ghost-small.danger:hover { background: #fef2f2; }

.action-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.2s;
}

.action-btn.brown {
  background: var(--primary-color, #c4692f);
  color: white;
}

.action-btn.brown:hover { background: #b35d28; }

.action-btn.small { padding: 0.375rem 0.75rem; font-size: 0.875rem; }
</style>
