<template>
  <div class="tab-content">
    <div v-if="!classificationResult" class="empty-result">
      <Tags class="empty-icon" />
      <p>点击「一键分析」进行需求分类</p>
    </div>
    <div v-else class="classification-result">
      <!-- 分类统计 -->
      <div class="classification-summary">
        <div class="summary-item">
          <BarChart3 class="summary-icon" />
          <span class="summary-label">总计</span>
          <span class="summary-value">{{ classificationResult.total }}</span>
        </div>
        <div
          v-for="([label, count]) in Object.entries(classificationResult.label_distribution || {})"
          :key="label"
          class="summary-item"
          :class="getLabelClass(label)"
        >
          <span class="label-dot" :class="getLabelDotClass(label)"></span>
          <span class="summary-label">{{ label }}</span>
          <span class="summary-value">{{ count }}</span>
        </div>
      </div>
      <!-- 分类分组列表 -->
      <div class="classification-groups">
        <div
          v-for="([label, items]) in classificationGroups"
          :key="label"
          class="classification-group"
        >
          <div class="group-header" :class="getLabelHeaderClass(label)">
            <span class="group-title">{{ label }}</span>
            <span class="group-count" :class="getLabelBadgeClass(label)">{{ items.length }}</span>
          </div>
          <div class="group-items">
            <div
              v-for="pred in items"
              :key="pred.index"
              class="group-item"
            >
              <p>{{ pred.requirement }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Tags, BarChart3 } from 'lucide-vue-next'

defineProps({
  classificationResult: { type: Object, default: null },
  classificationGroups: { type: Array, default: () => [] },
})

function getLabelClass(label) {
  const styles = { '功能性需求': 'func', '非功能性需求': 'nonfunc' }
  return styles[label] || ''
}

function getLabelDotClass(label) {
  const styles = { '功能性需求': 'dot-func', '非功能性需求': 'dot-nonfunc' }
  return styles[label] || 'dot-default'
}

function getLabelHeaderClass(label) {
  const styles = { '功能性需求': 'header-func', '非功能性需求': 'header-nonfunc' }
  return styles[label] || ''
}

function getLabelBadgeClass(label) {
  const styles = { '功能性需求': 'badge-func', '非功能性需求': 'badge-nonfunc' }
  return styles[label] || ''
}
</script>

<style scoped>
.tab-content {
  height: 100%;
  overflow-y: auto;
}

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: rgba(28, 40, 52, 0.4);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.3;
}

.classification-result {
  padding: 16px;
}

.classification-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  background: rgba(28, 40, 52, 0.04);
  border: 1px solid rgba(28, 40, 52, 0.08);
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.summary-item.func { color: #3b82f6; }
.summary-item.nonfunc { color: #8b5cf6; }

.summary-icon {
  width: 14px;
  height: 14px;
}

.summary-label {
  color: rgba(28, 40, 52, 0.6);
}

.summary-value {
  font-weight: 600;
  color: var(--ink-950);
}

.label-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-func { background: #3b82f6; }
.dot-nonfunc { background: #8b5cf6; }
.dot-default { background: #6b7280; }

.classification-groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.classification-group {
  border: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(255, 255, 255, 0.95);
  overflow: hidden;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.header-func { background: rgba(59, 130, 246, 0.08); }
.header-nonfunc { background: rgba(139, 92, 246, 0.08); }

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-950);
}

.group-count {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
}

.badge-func { background: rgba(59, 130, 246, 0.15); color: #2563eb; }
.badge-nonfunc { background: rgba(139, 92, 246, 0.15); color: #7c3aed; }

.group-items {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-item {
  padding: 10px;
  background: rgba(28, 40, 52, 0.03);
  border: 1px solid rgba(28, 40, 52, 0.06);
}

.group-item p {
  margin: 0;
  font-size: 12px;
  color: var(--ink-950);
  line-height: 1.5;
}
</style>
