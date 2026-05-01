<template>
  <div class="card my-work-card sa-card">
    <div class="card-header full-header">
      <div class="header-main">
        <p class="card-kicker">My Work</p>
        <h2>我的工作台</h2>
        <p class="header-desc">把「人要做的事」放到最短路径：待办、待审、需要补齐的条目。</p>
      </div>
      <div class="header-actions">
        <button
          type="button"
          class="filter-btn"
          :class="{ active: filterMode === 'mine' }"
          @click="filterMode = 'mine'"
        >只看我负责</button>
        <button
          type="button"
          class="filter-btn"
          :class="{ active: filterMode === 'all' }"
          @click="filterMode = 'all'"
        >查看全部</button>
      </div>
    </div>

    <!-- 骨架屏 -->
    <div v-if="loading" class="work-grid">
      <div class="work-column">
        <h3 class="column-title">我的待办（To-do）</h3>
        <div v-for="i in 2" :key="'skel-todo-'+i" class="task-card skeleton-card">
          <div class="skeleton-line wide"></div>
          <div class="skeleton-line medium"></div>
          <div class="skeleton-line short"></div>
        </div>
      </div>
      <div class="work-column">
        <h3 class="column-title">评审任务（Reviews）</h3>
        <div v-for="i in 2" :key="'skel-rev-'+i" class="task-card skeleton-card">
          <div class="skeleton-line wide"></div>
          <div class="skeleton-line medium"></div>
          <div class="skeleton-line short"></div>
        </div>
      </div>
    </div>

    <!-- 真实数据 -->
    <div v-else class="work-grid">
      <!-- Left Column: My To-do -->
      <div class="work-column">
        <h3 class="column-title">我的待办（To-do）<span class="column-count">{{ displayedTodos.length }}</span></h3>

        <div v-if="displayedTodos.length === 0" class="empty-hint">
          <p>🎉 暂无待办事项</p>
        </div>

        <div v-for="item in displayedTodos" :key="item.req_id" class="task-card">
          <div class="task-header">
            <h4>{{ item.title || '(无标题)' }}</h4>
            <span class="status-tag" :class="statusClass(item.status)">
              {{ statusLabel(item.status) }}
            </span>
          </div>
          <div class="task-meta">
            <span class="pill">
              优先级：{{ priorityLabel(item.priority) }}
            </span>
            <span v-if="item.due_date" class="pill" :class="{ 'item-warn': item.isOverdue }">
              截止：{{ formatDate(item.due_date) }}
            </span>
            <span class="pill highlight">{{ item.priorityLabel }}</span>
          </div>
          <div class="task-actions">
            <button class="btn-primary" @click="$emit('navigate', 'requirements')">查看详情</button>
          </div>
        </div>
      </div>

      <!-- Right Column: Reviews -->
      <div class="work-column">
        <h3 class="column-title">评审任务（Reviews）<span class="column-count">{{ displayedReviews.length }}</span></h3>

        <div v-if="displayedReviews.length === 0" class="empty-hint">
          <p>✅ 暂无待评审任务</p>
        </div>

        <div v-for="item in displayedReviews" :key="item.req_id" class="task-card">
          <div class="task-header">
            <h4>{{ item.title || '(无标题)' }}</h4>
            <span class="status-tag pending">待审</span>
          </div>
          <div class="task-meta">
            <span v-if="item.due_date" class="pill">
              到期：{{ formatDate(item.due_date) }}
            </span>
            <span v-if="item.dueSoonLabel" class="pill item-warn">
              {{ item.dueSoonLabel }}
            </span>
            <span v-if="item.assignee" class="pill">
              负责人：{{ item.assignee }}
            </span>
          </div>
          <div class="task-actions">
            <button class="btn-primary" @click="$emit('navigate', 'reviews')">进入评审</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  todos: {
    type: Array,
    default: () => [],
  },
  reviews: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  currentUserId: {
    type: String,
    default: '',
  },
})

defineEmits(['navigate'])

const filterMode = ref('mine')

const displayedTodos = computed(() => {
  if (filterMode.value === 'mine' && props.currentUserId) {
    return props.todos.filter(t => t.assignee === props.currentUserId)
  }
  return props.todos
})

const displayedReviews = computed(() => {
  if (filterMode.value === 'mine' && props.currentUserId) {
    return props.reviews.filter(r => r.assignee === props.currentUserId)
  }
  return props.reviews
})

function statusClass(status) {
  const map = {
    draft: 'pending',
    in_progress: 'confirm',
    under_review: 'pending',
    confirmed: 'ok',
    completed: 'ok',
  }
  return map[status] || ''
}

function statusLabel(status) {
  const map = {
    draft: '草稿',
    in_progress: '进行中',
    under_review: '待评审',
    confirmed: '已确认',
    completed: '已完成',
  }
  return map[status] || status || '—'
}

function priorityLabel(priority) {
  const map = { high: '高', medium: '中', low: '低' }
  return map[priority] || priority || '—'
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.my-work-card {
  padding: 32px;
  background: white;
  border-radius: 0;
}

.full-header {
  display: flex !important;
  flex-direction: row;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 30px;
  border-bottom: 1px solid rgba(28,40,52,0.06);
  padding-bottom: 20px;
}

.header-main h2 {
  font-size: 28px;
  margin: 4px 0 10px;
  font-family: serif;
}

.header-desc {
  font-size: 13px;
  color: #9eabb4;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-btn {
  padding: 6px 16px;
  border: 1px solid rgba(28,40,52,0.1);
  background: white;
  border-radius: 0;
  font-size: 12px;
  color: #5d6b76;
  cursor: pointer;
}
.filter-btn.active {
  background: white;
  border-color: #5d6b76;
  color: #1b2730;
}

.work-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

.column-title {
  font-size: 16px;
  font-weight: bold;
  font-family: serif;
  margin-bottom: 20px;
  color: #1b2730;
  display: flex;
  align-items: center;
  gap: 8px;
}

.column-count {
  background: #eee;
  padding: 2px 8px;
  font-size: 12px;
  font-family: sans-serif;
  font-weight: normal;
  color: #5d6b76;
}

.task-card {
  background: #fdfcf9;
  border: 1px solid rgba(28,40,52,0.05);
  border-radius: 0;
  padding: 20px;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.task-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #23323d;
  line-height: 1.4;
}

.status-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 0;
  white-space: nowrap;
  background: #eee;
}
.status-tag.pending { background: #efe6d5; color: #8e7d5e; }
.status-tag.block { background: #ebd5d5; color: #9c5e5e; }
.status-tag.confirm { background: #e0ecf5; color: #456b8a; }
.status-tag.ok { background: #dcece8; color: #5c8a82; }

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  border: 1px solid rgba(28,40,52,0.1);
  padding: 2px 8px;
  border-radius: 0;
  font-size: 11px;
  color: #9eabb4;
}
.pill.highlight { color: #1b2730; border-color: #1b2730; }
.pill.item-warn { background: #fff5f5; color: #c45b60; border-color: #f0c9ca; }

.task-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.btn-primary {
  background: var(--accent);
  color: white;
  border: none;
  padding: 6px 16px;
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
}

.empty-hint {
  padding: 32px 16px;
  text-align: center;
  color: #9eabb4;
  font-size: 14px;
}

/* 骨架屏 */
.skeleton-card {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}
.skeleton-line {
  height: 14px;
  background: #eee;
  border-radius: 4px;
}
.skeleton-line.short { width: 40%; }
.skeleton-line.wide { width: 90%; }
.skeleton-line.medium { width: 65%; }

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@media (max-width: 800px) {
  .work-grid {
    grid-template-columns: 1fr;
  }
}
</style>
