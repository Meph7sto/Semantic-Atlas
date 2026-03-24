<template>
  <div class="matrix-panel">
    <div class="matrix-toolbar">
      <label class="matrix-filter">
        <span>状态筛选</span>
        <select v-model="statusFilter" class="select-clean">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="under_review">评审中</option>
          <option value="confirmed">已确认</option>
          <option value="in_progress">开发中</option>
          <option value="completed">已完成</option>
          <option value="archived">已归档</option>
        </select>
      </label>

      <label class="matrix-filter matrix-filter--search">
        <span>关键词</span>
        <input v-model="keyword" type="text" class="search-input full-width" placeholder="搜索需求标题 / ID" />
      </label>
    </div>

    <div v-if="loading" class="matrix-state">正在加载追溯矩阵…</div>
    <div v-else-if="!flattenedRows.length" class="matrix-state">当前分支没有可展示的需求快照。</div>
    <div v-else class="matrix-layout">
      <div class="matrix-table">
        <div class="matrix-header">
          <span>需求</span>
          <span>状态</span>
          <span>测试</span>
          <span>变更</span>
          <span>审计</span>
        </div>
        <button
          v-for="row in flattenedRows"
          :key="row.requirement.req_id"
          type="button"
          class="matrix-row"
          :class="{ active: row.requirement.req_id === selectedRequirementId }"
          @click="selectedRequirementId = row.requirement.req_id"
        >
          <div class="matrix-title-cell" :style="{ '--depth': row.depth }">
            <strong>{{ row.requirement.title || row.requirement.req_id }}</strong>
            <span class="matrix-subtitle">{{ row.requirement.req_id }}</span>
          </div>
          <span>{{ row.requirement.status || '-' }}</span>
          <span>{{ row.traceability.test_case_count }}</span>
          <span>{{ row.traceability.change_count }}</span>
          <span>{{ row.traceability.audit_count }}</span>
        </button>
      </div>

      <div class="matrix-detail">
        <template v-if="selectedRequirement">
          <div class="detail-card">
            <p class="card-kicker">Requirement Detail</p>
            <h3 class="section-title">{{ selectedRequirement.title || selectedRequirement.req_id }}</h3>
            <p>{{ selectedRequirement.description || '暂无描述' }}</p>
          </div>

          <div class="detail-grid">
            <div class="detail-card">
              <p class="card-kicker">Traceability</p>
              <div class="detail-list">
                <span>状态：{{ selectedRequirement.status || '-' }}</span>
                <span>测试绑定：{{ selectedTraceability.test_case_count }}</span>
                <span>关联变更：{{ selectedTraceability.change_count }}</span>
                <span>关联审计：{{ selectedTraceability.audit_count }}</span>
              </div>
            </div>

            <div class="detail-card">
              <p class="card-kicker">Bound Tests</p>
              <div class="detail-list">
                <span v-for="testCase in selectedTests" :key="testCase.test_case_id">
                  {{ testCase.title || testCase.test_case_id }}
                </span>
                <span v-if="!selectedTests.length">暂无测试绑定</span>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="matrix-state">选择一条需求以查看右侧追踪明细。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const keyword = ref('')
const statusFilter = ref('')
const selectedRequirementId = ref('')

const testCaseMap = computed(() => {
  const items = props.data?.test_cases || []
  return Object.fromEntries(items.map((item) => [item.test_case_id, item]))
})

const flattenedRows = computed(() => {
  const rows = []
  const search = keyword.value.trim().toLowerCase()

  function visit(node, depth = 0) {
    const requirement = node.requirement || {}
    const traceability = node.traceability || requirement.traceability || {
      test_case_count: 0,
      change_count: 0,
      audit_count: 0,
      test_case_ids: [],
    }
    const haystack = `${requirement.req_id || ''} ${requirement.title || ''}`.toLowerCase()
    const matchStatus = !statusFilter.value || requirement.status === statusFilter.value
    const matchKeyword = !search || haystack.includes(search)

    if (matchStatus && matchKeyword) {
      rows.push({ requirement, traceability, depth })
    }

    ;(node.children || []).forEach((child) => visit(child, depth + 1))
  }

  ;(props.data?.requirements || []).forEach((root) => visit(root, 0))
  return rows
})

const selectedRequirement = computed(() =>
  flattenedRows.value.find((row) => row.requirement.req_id === selectedRequirementId.value)?.requirement || null,
)

const selectedTraceability = computed(() =>
  flattenedRows.value.find((row) => row.requirement.req_id === selectedRequirementId.value)?.traceability || {
    test_case_count: 0,
    change_count: 0,
    audit_count: 0,
    test_case_ids: [],
  },
)

const selectedTests = computed(() =>
  (selectedTraceability.value.test_case_ids || [])
    .map((id) => testCaseMap.value[id])
    .filter(Boolean),
)

watch(flattenedRows, (rows) => {
  if (!rows.length) {
    selectedRequirementId.value = ''
    return
  }
  if (!rows.some((row) => row.requirement.req_id === selectedRequirementId.value)) {
    selectedRequirementId.value = rows[0].requirement.req_id
  }
}, { immediate: true })
</script>

<style scoped>
.matrix-panel {
  display: grid;
  gap: 18px;
}

.matrix-toolbar {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 14px;
}

.matrix-filter {
  display: grid;
  gap: 8px;
  font-size: 12px;
  color: rgba(28, 40, 52, 0.72);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.matrix-filter--search {
  min-width: 0;
}

.matrix-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
  gap: 18px;
}

.matrix-table,
.matrix-detail,
.detail-card {
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
}

.matrix-header,
.matrix-row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) 120px 80px 80px 80px;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
}

.matrix-header {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(28, 40, 52, 0.62);
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.matrix-row {
  width: 100%;
  border: none;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.matrix-row:last-child {
  border-bottom: none;
}

.matrix-row.active {
  background: rgba(28, 40, 52, 0.06);
}

.matrix-title-cell {
  display: grid;
  gap: 4px;
  padding-left: calc(var(--depth, 0) * 16px);
}

.matrix-subtitle {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.54);
}

.matrix-detail {
  padding: 18px;
  display: grid;
  gap: 14px;
}

.detail-grid {
  display: grid;
  gap: 14px;
}

.detail-card {
  padding: 16px;
}

.detail-list {
  display: grid;
  gap: 8px;
  color: rgba(28, 40, 52, 0.74);
}

.matrix-state {
  color: rgba(28, 40, 52, 0.72);
}

@media (max-width: 1100px) {
  .matrix-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .matrix-toolbar {
    grid-template-columns: 1fr;
  }

  .matrix-header,
  .matrix-row {
    grid-template-columns: minmax(0, 1.6fr) repeat(4, minmax(56px, 1fr));
    font-size: 12px;
  }
}
</style>
