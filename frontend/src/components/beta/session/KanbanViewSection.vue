<template>
  <div class="card-view-container">
    <div class="kanban-header">
      <span class="kanban-total">共 {{ filteredCount }} 条需求</span>
    </div>
    <div class="kanban-grid">
      <!-- 待处理列 -->
      <div class="kanban-column backlog-column">
        <div class="kanban-column-header backlog-header">
          <div class="column-title-group">
            <Circle class="column-status-icon" />
            <h3>待处理</h3>
          </div>
          <span class="column-badge backlog-badge">{{ localBacklog.length }}</span>
        </div>
        <draggable
          v-model="localBacklog"
          :group="{ name: 'requirements', pull: true, put: true }"
          item-key="id"
          :animation="200"
          class="kanban-column-content"
          ghost-class="drag-ghost"
          chosen-class="drag-chosen"
          drag-class="drag-active"
          @change="handleDragChange($event, 'backlog')"
        >
          <template #item="{ element }">
            <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
              <div class="card-drag-handle">
                <GripVertical class="grip-icon" />
              </div>
              <div class="card-content">
                <div class="card-tags">
                  <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                    {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                  </span>
                  <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                    {{ element.level }}
                  </span>
                </div>
                <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                <div class="card-meta">
                  <span class="card-id">{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                  <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                    {{ (element.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>
          </template>
        </draggable>
        <div v-if="localBacklog.length === 0" class="kanban-empty">拖拽需求到此处</div>
      </div>

      <!-- 进行中列 -->
      <div class="kanban-column progress-column">
        <div class="kanban-column-header progress-header">
          <div class="column-title-group">
            <Clock class="column-status-icon" />
            <h3>进行中</h3>
          </div>
          <span class="column-badge progress-badge">{{ localInProgress.length }}</span>
        </div>
        <draggable
          v-model="localInProgress"
          :group="{ name: 'requirements', pull: true, put: true }"
          item-key="id"
          :animation="200"
          class="kanban-column-content"
          ghost-class="drag-ghost"
          chosen-class="drag-chosen"
          drag-class="drag-active"
          @change="handleDragChange($event, 'in_progress')"
        >
          <template #item="{ element }">
            <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
              <div class="card-drag-handle">
                <GripVertical class="grip-icon" />
              </div>
              <div class="card-content">
                <div class="card-tags">
                  <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                    {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                  </span>
                  <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                    {{ element.level }}
                  </span>
                </div>
                <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                <div class="card-meta">
                  <span class="card-id">{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                  <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                    {{ (element.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>
          </template>
        </draggable>
        <div v-if="localInProgress.length === 0" class="kanban-empty">拖拽需求到此处</div>
      </div>

      <!-- 已完成列 -->
      <div class="kanban-column completed-column">
        <div class="kanban-column-header completed-header">
          <div class="column-title-group">
            <CheckCircle class="column-status-icon" />
            <h3>已完成</h3>
          </div>
          <span class="column-badge completed-badge">{{ localCompleted.length }}</span>
        </div>
        <draggable
          v-model="localCompleted"
          :group="{ name: 'requirements', pull: true, put: true }"
          item-key="id"
          :animation="200"
          class="kanban-column-content"
          ghost-class="drag-ghost"
          chosen-class="drag-chosen"
          drag-class="drag-active"
          @change="handleDragChange($event, 'completed')"
        >
          <template #item="{ element }">
            <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
              <div class="card-drag-handle">
                <GripVertical class="grip-icon" />
              </div>
              <div class="card-content">
                <div class="card-tags">
                  <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                    {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                  </span>
                  <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                    {{ element.level }}
                  </span>
                </div>
                <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                <div class="card-meta">
                  <span class="card-id">{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                  <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                    {{ (element.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>
          </template>
        </draggable>
        <div v-if="localCompleted.length === 0" class="kanban-empty">拖拽需求到此处</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { Circle, Clock, CheckCircle, GripVertical } from 'lucide-vue-next'

const props = defineProps({
  backlog: { type: Array, default: () => [] },
  inProgress: { type: Array, default: () => [] },
  completed: { type: Array, default: () => [] },
  filteredCount: { type: Number, default: 0 },
})

const emit = defineEmits(['dragChange'])

// 本地可写副本，供 vuedraggable v-model 使用
const localBacklog = ref([...props.backlog])
const localInProgress = ref([...props.inProgress])
const localCompleted = ref([...props.completed])

watch(() => props.backlog, (val) => { localBacklog.value = [...val] })
watch(() => props.inProgress, (val) => { localInProgress.value = [...val] })
watch(() => props.completed, (val) => { localCompleted.value = [...val] })

function handleDragChange(event, targetStatus) {
  const item = event.added?.element
  if (item) emit('dragChange', item, targetStatus)
}

function getLevelBadgeClass(level) {
  const map = {
    L1: 'bg-sky-100 text-sky-700 border-sky-200',
    L2: 'bg-violet-100 text-violet-700 border-violet-200',
    L3: 'bg-amber-100 text-amber-700 border-amber-200',
    L4: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  }
  return map[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function getConfidenceClass(conf) {
  if (conf >= 0.8) return 'conf-high'
  if (conf >= 0.5) return 'conf-medium'
  return 'conf-low'
}
</script>

<style scoped>
.card-view-container {
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.kanban-header {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.kanban-total {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.6);
}

.kanban-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  padding: 20px;
  min-height: 0;
  overflow: hidden;
}

.kanban-column {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  overflow: hidden;
  min-height: 400px;
}

.kanban-column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.column-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.column-title-group h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--ink-950);
}

.column-status-icon { width: 16px; height: 16px; }

.column-badge {
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 12px;
}

/* 待处理列 */
.backlog-column { background: rgba(250, 250, 250, 0.95); }
.backlog-header { background: rgba(244, 244, 245, 0.9); }
.backlog-header .column-status-icon { color: #71717a; }
.backlog-badge { background: rgba(113, 113, 122, 0.15); color: #52525b; }

/* 进行中列 */
.progress-column { background: rgba(239, 246, 255, 0.5); border-color: rgba(59, 130, 246, 0.2); }
.progress-header { background: rgba(219, 234, 254, 0.6); border-color: rgba(59, 130, 246, 0.2); }
.progress-header .column-status-icon { color: #2563eb; }
.progress-badge { background: rgba(59, 130, 246, 0.15); color: #1d4ed8; }

/* 已完成列 */
.completed-column { background: rgba(236, 253, 245, 0.5); border-color: rgba(16, 185, 129, 0.2); }
.completed-header { background: rgba(209, 250, 229, 0.6); border-color: rgba(16, 185, 129, 0.2); }
.completed-header .column-status-icon { color: #059669; }
.completed-badge { background: rgba(16, 185, 129, 0.15); color: #047857; }

.kanban-column-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.kanban-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(28, 40, 52, 0.35);
  font-size: 13px;
  border: 2px dashed rgba(28, 40, 52, 0.12);
  margin: 12px;
  min-height: 100px;
}

/* 卡片样式 */
.kanban-card {
  display: flex;
  background: #fff;
  border: 1px solid rgba(28, 40, 52, 0.12);
  transition: all 0.2s ease;
  cursor: grab;
}

.kanban-card:hover {
  border-color: rgba(28, 40, 52, 0.25);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.kanban-card:active { cursor: grabbing; }
.kanban-card.card-high { border-left: 3px solid #0ea5e9; }
.kanban-card.card-l4 { border-left: 3px solid #10b981; }

.card-drag-handle {
  display: flex;
  align-items: center;
  padding: 8px 4px;
  background: rgba(28, 40, 52, 0.03);
  color: rgba(28, 40, 52, 0.3);
}

.card-drag-handle:hover {
  background: rgba(28, 40, 52, 0.06);
  color: rgba(28, 40, 52, 0.5);
}

.grip-icon { width: 14px; height: 14px; }

.card-content { flex: 1; padding: 8px; min-width: 0; }

.card-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.card-type-tag { font-size: 10px; padding: 2px 8px; font-weight: 500; }
.card-type-tag.type-high { background: rgba(14, 165, 233, 0.12); color: #0284c7; border: 1px solid rgba(14, 165, 233, 0.25); }
.card-type-tag.type-low { background: rgba(16, 185, 129, 0.12); color: #059669; border: 1px solid rgba(16, 185, 129, 0.25); }

.card-level-tag { font-size: 10px; padding: 2px 8px; font-weight: 600; border: 1px solid; }

.card-statement {
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-950);
  margin: 0 0 10px;
  word-break: break-word;
}

.card-meta { display: flex; justify-content: space-between; align-items: center; font-size: 11px; }

.card-id {
  color: rgba(28, 40, 52, 0.4);
  font-family: monospace;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-confidence { padding: 2px 6px; border: 1px solid; font-weight: 500; }

/* 拖拽状态 */
.drag-ghost { opacity: 0.5; background: rgba(196, 105, 47, 0.1) !important; border: 2px dashed var(--accent) !important; }
.drag-chosen { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); }
.drag-active { opacity: 0.9; }

/* 置信度颜色 */
.conf-high { background: rgba(34, 197, 94, 0.1); color: #15803d; border-color: rgba(34, 197, 94, 0.3); }
.conf-medium { background: rgba(234, 179, 8, 0.1); color: #a16207; border-color: rgba(234, 179, 8, 0.3); }
.conf-low { background: rgba(239, 68, 68, 0.1); color: #b91c1c; border-color: rgba(239, 68, 68, 0.3); }

/* 自定义滚动条 */
.kanban-column-content::-webkit-scrollbar { width: 6px; }
.kanban-column-content::-webkit-scrollbar-track { background: transparent; }
.kanban-column-content::-webkit-scrollbar-thumb { background-color: rgba(28, 40, 52, 0.15); border-radius: 3px; }
.kanban-column-content::-webkit-scrollbar-thumb:hover { background-color: rgba(28, 40, 52, 0.25); }
</style>
