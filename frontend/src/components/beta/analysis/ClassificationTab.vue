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
import { getClassificationLabelStyle } from '@/utils/classificationLabelStyle'

defineProps({
  classificationResult: { type: Object, default: null },
  classificationGroups: { type: Array, default: () => [] },
})

function getLabelClass(label) {
  return getClassificationLabelStyle(label).summaryClass
}

function getLabelDotClass(label) {
  return getClassificationLabelStyle(label).dotClass
}

function getLabelHeaderClass(label) {
  return getClassificationLabelStyle(label).headerClass
}

function getLabelBadgeClass(label) {
  return getClassificationLabelStyle(label).badgeClass
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

.summary-item.tone-sky { color: #0369a1; }
.summary-item.tone-emerald { color: #047857; }
.summary-item.tone-amber { color: #b45309; }
.summary-item.tone-violet { color: #7c3aed; }
.summary-item.tone-rose { color: #be185d; }
.summary-item.tone-cyan { color: #0f766e; }
.summary-item.tone-slate { color: #475569; }
.summary-item.tone-lime { color: #4d7c0f; }

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

.dot-sky { background: #0ea5e9; }
.dot-emerald { background: #10b981; }
.dot-amber { background: #f59e0b; }
.dot-violet { background: #8b5cf6; }
.dot-rose { background: #f43f5e; }
.dot-cyan { background: #06b6d4; }
.dot-slate { background: #64748b; }
.dot-lime { background: #84cc16; }

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

.header-sky { background: rgba(14, 165, 233, 0.1); }
.header-emerald { background: rgba(16, 185, 129, 0.1); }
.header-amber { background: rgba(245, 158, 11, 0.1); }
.header-violet { background: rgba(139, 92, 246, 0.1); }
.header-rose { background: rgba(244, 63, 94, 0.1); }
.header-cyan { background: rgba(6, 182, 212, 0.1); }
.header-slate { background: rgba(100, 116, 139, 0.1); }
.header-lime { background: rgba(132, 204, 22, 0.1); }

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

.badge-sky { background: rgba(14, 165, 233, 0.16); color: #0369a1; }
.badge-emerald { background: rgba(16, 185, 129, 0.16); color: #047857; }
.badge-amber { background: rgba(245, 158, 11, 0.18); color: #b45309; }
.badge-violet { background: rgba(139, 92, 246, 0.16); color: #7c3aed; }
.badge-rose { background: rgba(244, 63, 94, 0.16); color: #be185d; }
.badge-cyan { background: rgba(6, 182, 212, 0.16); color: #0f766e; }
.badge-slate { background: rgba(100, 116, 139, 0.16); color: #475569; }
.badge-lime { background: rgba(132, 204, 22, 0.18); color: #4d7c0f; }

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
