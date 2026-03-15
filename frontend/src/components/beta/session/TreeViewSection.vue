<template>
  <div class="tree-view-container">
    <RequirementTree
      :tree-data="filteredTreeData"
      @hover="$emit('hover', $event)"
      @click-node="$emit('clickNode', $event)"
    />
    <!-- 悬浮详情面板 -->
    <div v-if="hoveredNode" class="hover-detail-panel">
      <div class="detail-title">{{ hoveredNode.title || hoveredNode.text }}</div>
      <div class="detail-row">
        <span class="detail-label">类型:</span>
        <span class="detail-value">{{ getTypeLabel(hoveredNode.requirement_type) }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">状态:</span>
        <span class="detail-value">{{ hoveredNode.status || '-' }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">优先级:</span>
        <span class="detail-value">{{ hoveredNode.priority || '-' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import RequirementTree from '../../charts/RequirementTree.vue'

defineProps({
  filteredTreeData: { type: Array, default: () => [] },
  hoveredNode: { type: Object, default: null },
})

defineEmits(['hover', 'clickNode'])

function getTypeLabel(type) {
  const labels = { 'top_level': '顶层需求', 'low_level': '底层需求', 'task': '任务' }
  return labels[type] || type || '-'
}
</script>

<style scoped>
.tree-view-container {
  position: relative;
  padding: 20px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  min-height: 500px;
}

.hover-detail-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 260px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(28, 40, 52, 0.15);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-950);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 6px;
}

.detail-label { color: rgba(28, 40, 52, 0.6); }
.detail-value { color: var(--ink-950); font-weight: 500; }
</style>
