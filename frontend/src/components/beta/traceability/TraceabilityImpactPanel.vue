<template>
  <div class="impact-panel">
    <div class="impact-toolbar">
      <label class="impact-filter">
        <span>比较基准</span>
        <select v-model="compareTo" class="select-clean sa-input">
          <option value="baseline">当前基线</option>
          <option value="base">分支起点</option>
        </select>
      </label>
      <button type="button" class="action-btn brown sa-button sa-button--primary" :disabled="triggering" @click="$emit('trigger', compareTo)">
        {{ triggering ? '分析中…' : '重新计算影响分析' }}
      </button>
    </div>

    <div v-if="loading" class="impact-state">正在加载影响分析…</div>
    <div v-else-if="!detail" class="impact-state">尚未生成影响报告，点击上方按钮开始分析。</div>
    <div v-else class="impact-grid">
      <div class="impact-summary">
        <div class="impact-card">
          <p class="card-kicker">Status</p>
          <h3>{{ detail.status || data.status }}</h3>
        </div>
        <div class="impact-card">
          <p class="card-kicker">Changed</p>
          <h3>{{ detail.changed_requirements?.length || 0 }}</h3>
        </div>
        <div class="impact-card">
          <p class="card-kicker">Affected Tests</p>
          <h3>{{ detail.affected_test_cases?.length || 0 }}</h3>
        </div>
        <div class="impact-card">
          <p class="card-kicker">Risk Flags</p>
          <h3>{{ detail.risk_flags?.length || 0 }}</h3>
        </div>
      </div>

      <div class="impact-section">
        <div class="impact-section-header">
          <p class="card-kicker">Diff Summary</p>
          <h3 class="section-title">里程碑差异</h3>
        </div>
        <div class="impact-list impact-list--inline">
          <span>新增 {{ detail.diff_summary?.added || 0 }}</span>
          <span>删除 {{ detail.diff_summary?.deleted || 0 }}</span>
          <span>修改 {{ detail.diff_summary?.modified || 0 }}</span>
          <span>移动 {{ detail.diff_summary?.moved || 0 }}</span>
        </div>
      </div>

      <div class="impact-columns">
        <div class="impact-section">
          <div class="impact-section-header">
            <p class="card-kicker">Changed Requirements</p>
            <h3 class="section-title">直接受影响需求</h3>
          </div>
          <div v-if="!(detail.changed_requirements || []).length" class="impact-state">没有直接变更。</div>
          <div v-for="item in detail.changed_requirements || []" :key="item.requirement_id" class="impact-item">
            <strong>{{ item.current?.title || item.requirement_id }}</strong>
            <span>{{ item.requirement_id }} · {{ (item.change_types || []).join(', ') || 'unknown' }}</span>
          </div>
        </div>

        <div class="impact-section">
          <div class="impact-section-header">
            <p class="card-kicker">Affected Tests</p>
            <h3 class="section-title">受波及测试用例</h3>
          </div>
          <div v-if="!(detail.affected_test_cases || []).length" class="impact-state">没有测试被波及。</div>
          <div v-for="testCase in detail.affected_test_cases || []" :key="testCase.test_case_id" class="impact-item">
            <strong>{{ testCase.title || testCase.test_case_id }}</strong>
            <span>{{ testCase.test_case_id }} · {{ testCase.status || '-' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

defineEmits(['trigger'])

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  triggering: { type: Boolean, default: false },
})

const compareTo = ref('baseline')

const detail = computed(() => props.data?.detail_json || null)
</script>

<style scoped>
.impact-panel {
  display: grid;
  gap: 18px;
}

.impact-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: end;
}

.impact-filter {
  display: grid;
  gap: 8px;
  font-size: 12px;
  color: rgba(28, 40, 52, 0.72);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.impact-summary,
.impact-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.impact-card,
.impact-section {
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  padding: 16px;
}

.impact-section {
  display: grid;
  gap: 12px;
}

.impact-list {
  display: grid;
  gap: 8px;
  color: rgba(28, 40, 52, 0.74);
}

.impact-list--inline {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.impact-item {
  display: grid;
  gap: 4px;
  padding-top: 12px;
  border-top: 1px solid rgba(28, 40, 52, 0.08);
}

.impact-item:first-of-type {
  border-top: none;
  padding-top: 0;
}

.impact-state {
  color: rgba(28, 40, 52, 0.72);
}

@media (max-width: 900px) {
  .impact-summary,
  .impact-columns,
  .impact-list--inline {
    grid-template-columns: 1fr;
  }
}
</style>
