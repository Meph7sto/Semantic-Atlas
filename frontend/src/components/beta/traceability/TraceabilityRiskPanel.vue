<template>
  <div class="risk-panel">
    <div v-if="loading" class="risk-state">正在加载风险透视…</div>
    <template v-else>
      <div class="risk-summary">
        <div class="risk-card">
          <p class="card-kicker">In Progress Without Tests</p>
          <h3>{{ uncovered.length }}</h3>
        </div>
        <div class="risk-card">
          <p class="card-kicker">Active Audit Targets</p>
          <h3>{{ audits.length }}</h3>
        </div>
        <div class="risk-card">
          <p class="card-kicker">Changed Requirements</p>
          <h3>{{ changed.length }}</h3>
        </div>
        <div class="risk-card risk-card--accent">
          <p class="card-kicker">High Risk Chains</p>
          <h3>{{ highRisk.length }}</h3>
        </div>
      </div>

      <div class="risk-columns">
        <div class="risk-section">
          <div class="risk-section-header">
            <p class="card-kicker">Status Distribution</p>
            <h3 class="section-title">状态分布</h3>
          </div>
          <div class="risk-list">
            <span v-for="entry in statusEntries" :key="entry.key">{{ entry.key }} · {{ entry.value }}</span>
            <span v-if="!statusEntries.length">暂无状态数据</span>
          </div>
        </div>

        <div class="risk-section">
          <div class="risk-section-header">
            <p class="card-kicker">High Risk Chains</p>
            <h3 class="section-title">高风险链路</h3>
          </div>
          <div class="risk-item" v-for="item in highRisk" :key="item.requirement_id">
            <strong>{{ item.title || item.requirement_id }}</strong>
            <span>{{ item.requirement_id }} · score {{ item.risk_score }}</span>
          </div>
          <div v-if="!highRisk.length" class="risk-state">暂无高风险链路。</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const statusEntries = computed(() =>
  Object.entries(props.data?.status_distribution || {}).map(([key, value]) => ({ key, value })),
)
const uncovered = computed(() => props.data?.uncovered_in_progress || [])
const audits = computed(() => props.data?.active_audit_targets || [])
const changed = computed(() => props.data?.frequently_changed_requirements || [])
const highRisk = computed(() => props.data?.high_risk_chains || [])
</script>

<style scoped>
.risk-panel {
  display: grid;
  gap: 18px;
}

.risk-summary,
.risk-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.risk-card,
.risk-section {
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  padding: 16px;
}

.risk-card--accent h3 {
  color: #a04444;
}

.risk-section {
  display: grid;
  gap: 12px;
}

.risk-list {
  display: grid;
  gap: 8px;
  color: rgba(28, 40, 52, 0.74);
}

.risk-item {
  display: grid;
  gap: 4px;
  padding-top: 12px;
  border-top: 1px solid rgba(28, 40, 52, 0.08);
}

.risk-item:first-of-type {
  border-top: none;
  padding-top: 0;
}

.risk-state {
  color: rgba(28, 40, 52, 0.72);
}

@media (max-width: 900px) {
  .risk-summary,
  .risk-columns {
    grid-template-columns: 1fr;
  }
}
</style>
