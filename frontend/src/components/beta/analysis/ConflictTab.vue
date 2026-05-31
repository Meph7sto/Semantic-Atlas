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
          <span class="summary-label">确认冲突</span>
          <span class="summary-value">{{ conflictStats?.conflicts || 0 }}</span>
        </div>
        <div class="summary-item warn">
          <AlertTriangle class="summary-icon" />
          <span class="summary-label">疑似冲突</span>
          <span class="summary-value">{{ conflictStats?.suspected || 0 }}</span>
        </div>
        <div class="summary-item success">
          <CheckCircle2 class="summary-icon" />
          <span class="summary-label">无冲突</span>
          <span class="summary-value">{{ conflictStats?.compatible || 0 }}</span>
        </div>
      </div>
      <!-- 冲突列表 -->
      <div
        v-for="(item, idx) in conflictResults"
        :key="idx"
        class="conflict-item"
        :class="{ 'is-conflict': item.verdict === 'confirmed', 'is-suspected': item.verdict === 'suspected' }"
      >
        <div class="conflict-badge" :class="badgeClass(item.verdict)">
          {{ badgeText(item.verdict) }}
        </div>
        <div class="conflict-content">
          <div class="conflict-pair">
            <div class="conflict-req">
              <span class="req-label">需求 A</span>
              <p>{{ item.requirement_a_text }}</p>
            </div>
            <div class="conflict-req">
              <span class="req-label">需求 B</span>
              <p>{{ item.requirement_b_text }}</p>
            </div>
          </div>
          <div class="conflict-meta">
            <span class="meta-pill">类型：{{ formatType(item.conflict_type) }}</span>
            <span class="meta-pill">置信度：{{ formatConfidence(item.confidence) }}</span>
            <span v-if="item.candidate_reason" class="meta-pill subtle">候选原因：{{ item.candidate_reason }}</span>
          </div>
          <div class="conflict-analysis">
            <span class="analysis-label">说明：</span>
            {{ item.description }}
          </div>
          <div class="evidence-grid">
            <div class="evidence-card">
              <span class="evidence-label">证据 A</span>
              <p>{{ item.evidence_a || '未提供' }}</p>
            </div>
            <div class="evidence-card">
              <span class="evidence-label">证据 B</span>
              <p>{{ item.evidence_b || '未提供' }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { AlertTriangle, AlertCircle, CheckCircle2 } from 'lucide-vue-next'

function badgeText(verdict) {
  if (verdict === 'confirmed') return '确认冲突'
  if (verdict === 'suspected') return '疑似冲突'
  return '无冲突'
}

function badgeClass(verdict) {
  if (verdict === 'confirmed') return 'danger'
  if (verdict === 'suspected') return 'warn'
  return 'success'
}

function formatType(type) {
  const map = {
    object_property: '对象属性',
    logic_timing: '逻辑时序',
    terminology: '术语同指',
    fr_nfr: 'FR-NFR',
    other: '其他',
  }
  return map[type] || '其他'
}

function formatConfidence(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `${Math.round(num * 100)}%`
}

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
.summary-item.warn { color: #d97706; }
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

.conflict-item.is-suspected {
  background: rgba(245, 158, 11, 0.05);
  border-color: rgba(245, 158, 11, 0.2);
}

.conflict-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  align-self: flex-start;
}

.conflict-badge.danger { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
.conflict-badge.warn { background: rgba(245, 158, 11, 0.16); color: #b45309; }
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

.conflict-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  font-size: 11px;
  color: var(--ink-950);
  background: rgba(28, 40, 52, 0.06);
}

.meta-pill.subtle {
  color: rgba(28, 40, 52, 0.7);
}

.evidence-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.evidence-card {
  padding: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.evidence-label {
  font-size: 10px;
  color: rgba(28, 40, 52, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.evidence-card p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-950);
}
</style>
