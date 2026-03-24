<template>
  <div class="coverage-panel">
    <div class="coverage-cards">
      <div class="coverage-card">
        <p class="card-kicker">Requirements</p>
        <h3>{{ summary.total_requirements }}</h3>
      </div>
      <div class="coverage-card">
        <p class="card-kicker">Covered</p>
        <h3>{{ summary.covered_requirements }}</h3>
      </div>
      <div class="coverage-card">
        <p class="card-kicker">In Progress</p>
        <h3>{{ summary.in_progress_requirements }}</h3>
      </div>
      <div class="coverage-card coverage-card--risk">
        <p class="card-kicker">Orphans</p>
        <h3>{{ summary.orphan_requirements }}</h3>
      </div>
      <div class="coverage-card coverage-card--risk">
        <p class="card-kicker">Unlinked Changes</p>
        <h3>{{ summary.unlinked_changes }}</h3>
      </div>
    </div>

    <div v-if="loading" class="coverage-state">正在加载覆盖检查…</div>
    <div v-else class="coverage-grid">
      <div class="coverage-list">
        <div class="coverage-list-header">
          <p class="card-kicker">Orphan Requirements</p>
          <h3 class="section-title">开发中但未绑测</h3>
        </div>
        <div v-if="!orphanRequirements.length" class="coverage-state">没有发现裸奔需求。</div>
        <div v-for="requirement in orphanRequirements" :key="requirement.req_id" class="coverage-item">
          <strong>{{ requirement.title || requirement.req_id }}</strong>
          <span>{{ requirement.req_id }} · {{ requirement.status }}</span>
        </div>
      </div>

      <div class="coverage-list">
        <div class="coverage-list-header">
          <p class="card-kicker">Unlinked Changes</p>
          <h3 class="section-title">未挂接需求的变更</h3>
        </div>
        <div v-if="!unlinkedChanges.length" class="coverage-state">没有发现游离变更。</div>
        <div v-for="change in unlinkedChanges" :key="change.change_id" class="coverage-item">
          <strong>{{ change.change_type }}</strong>
          <span>{{ change.change_id }} · {{ change.requirement_id || '未指定需求' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const summary = computed(() => props.data?.coverage_summary || {
  total_requirements: 0,
  covered_requirements: 0,
  in_progress_requirements: 0,
  orphan_requirements: 0,
  unlinked_changes: 0,
})

const orphanRequirements = computed(() => props.data?.orphan_requirements || [])
const unlinkedChanges = computed(() => props.data?.unlinked_changes || [])
</script>

<style scoped>
.coverage-panel {
  display: grid;
  gap: 18px;
}

.coverage-cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.coverage-card,
.coverage-list {
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  padding: 16px;
}

.coverage-card--risk h3 {
  color: #a04444;
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.coverage-list {
  display: grid;
  gap: 12px;
}

.coverage-list-header {
  display: grid;
  gap: 4px;
}

.coverage-item {
  display: grid;
  gap: 4px;
  padding: 12px 0;
  border-top: 1px solid rgba(28, 40, 52, 0.08);
}

.coverage-item:first-of-type {
  border-top: none;
}

.coverage-item span,
.coverage-state {
  color: rgba(28, 40, 52, 0.7);
}

@media (max-width: 1100px) {
  .coverage-cards,
  .coverage-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .coverage-cards,
  .coverage-grid {
    grid-template-columns: 1fr;
  }
}
</style>
