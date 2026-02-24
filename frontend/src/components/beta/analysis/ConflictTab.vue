<template>
  <div class="tab-content">
    <div v-if="!conflictResults.length" class="empty-result">
      <AlertTriangle class="empty-icon" />
      <p>点击「一键分析」检测需求冲突</p>
    </div>
    <div v-else class="conflict-list">
      <!-- 冲突统计 -->
      <div class="conflict-summary">
        <div class="summary-item">
          <span class="summary-label">检测对数</span>
          <span class="summary-value">{{ conflictStats?.total || 0 }}</span>
        </div>
        <div class="summary-item danger">
          <AlertCircle class="summary-icon" />
          <span class="summary-label">冲突</span>
          <span class="summary-value">{{ conflictStats?.conflicts || 0 }}</span>
        </div>
        <div class="summary-item success">
          <CheckCircle2 class="summary-icon" />
          <span class="summary-label">兼容</span>
          <span class="summary-value">{{ conflictStats?.compatible || 0 }}</span>
        </div>
      </div>
      <!-- 冲突列表 -->
      <div
        v-for="(item, idx) in conflictResults"
        :key="idx"
        class="conflict-item"
        :class="{ 'is-conflict': item.is_conflict }"
      >
        <div class="conflict-badge" :class="item.is_conflict ? 'danger' : 'success'">
          {{ item.is_conflict ? '冲突' : '兼容' }}
        </div>
        <div class="conflict-content">
          <div class="conflict-pair">
            <div class="conflict-req">
              <span class="req-label">需求 A</span>
              <p>{{ item.reqA?.statement || item.reqA?.text }}</p>
            </div>
            <div class="conflict-req">
              <span class="req-label">需求 B</span>
              <p>{{ item.reqB?.statement || item.reqB?.text }}</p>
            </div>
          </div>
          <div class="conflict-analysis">
            <span class="analysis-label">分析结果：</span>
            {{ item.raw_response }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { AlertTriangle, AlertCircle, CheckCircle2 } from 'lucide-vue-next'

defineProps({
  conflictResults: { type: Array, default: () => [] },
  conflictStats: { type: Object, default: null },
})
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

.conflict-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conflict-summary {
  display: flex;
  gap: 16px;
  padding: 12px;
  background: rgba(28, 40, 52, 0.04);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.summary-item.danger { color: #ef4444; }
.summary-item.success { color: #22c55e; }

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

.conflict-item {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.conflict-item.is-conflict {
  background: rgba(239, 68, 68, 0.04);
  border-color: rgba(239, 68, 68, 0.2);
}

.conflict-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  align-self: flex-start;
}

.conflict-badge.danger { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
.conflict-badge.success { background: rgba(34, 197, 94, 0.15); color: #15803d; }

.conflict-content {
  flex: 1;
  min-width: 0;
}

.conflict-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 10px;
}

.conflict-req {
  padding: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.req-label {
  font-size: 10px;
  color: rgba(28, 40, 52, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.conflict-req p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-950);
}

.conflict-analysis {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.7);
  padding: 10px;
  background: rgba(28, 40, 52, 0.04);
}

.analysis-label {
  font-weight: 500;
  color: var(--ink-950);
}
</style>
