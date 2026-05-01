<template>
  <div class="trace-matrix-panel">
    <div class="trace-matrix-toolbar">
      <label class="trace-matrix-filter">
        <span>状态筛选</span>
        <select v-model="statusFilter" class="select-clean sa-input">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="under_review">评审中</option>
          <option value="confirmed">已确认</option>
          <option value="in_progress">开发中</option>
          <option value="completed">已完成</option>
          <option value="archived">已归档</option>
        </select>
      </label>

      <label class="trace-matrix-filter trace-matrix-filter--search">
        <span>关键词</span>
        <input v-model="keyword" type="text" class="search-input full-width sa-input" placeholder="搜索需求标题 / ID" />
      </label>
    </div>

    <div v-if="loading" class="trace-matrix-state">正在加载追溯矩阵…</div>
    <div v-else-if="!flattenedRows.length" class="trace-matrix-state">当前分支没有可展示的需求快照。</div>
    <div v-else class="trace-matrix-stack">
      <div class="trace-matrix-table">
        <table class="trace-matrix-native-table">
          <colgroup>
            <col class="trace-matrix-col-title" />
            <col class="trace-matrix-col-meta" />
            <col class="trace-matrix-col-flag" />
            <col class="trace-matrix-col-flag" />
            <col class="trace-matrix-col-flag" />
          </colgroup>
          <thead>
            <tr class="trace-matrix-header-row">
              <th scope="col">需求</th>
              <th scope="col" class="trace-matrix-column-label">状态</th>
              <th scope="col" class="trace-matrix-column-label">测试</th>
              <th scope="col" class="trace-matrix-column-label">变更</th>
              <th scope="col" class="trace-matrix-column-label">审计</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in flattenedRows" :key="row.requirement.req_id">
              <tr
                class="trace-matrix-data-row"
                :class="{ active: row.requirement.req_id === selectedRequirementId }"
                tabindex="0"
                @click="toggleRequirement(row.requirement.req_id)"
                @keydown.enter.prevent="toggleRequirement(row.requirement.req_id)"
                @keydown.space.prevent="toggleRequirement(row.requirement.req_id)"
              >
                <td>
                  <div class="trace-matrix-title-cell" :style="{ '--depth': row.depth }">
                    <strong>{{ row.requirement.title || row.requirement.req_id }}</strong>
                    <span class="trace-matrix-subtitle">{{ row.requirement.req_id }}</span>
                  </div>
                </td>
                <td class="trace-matrix-column-value">{{ row.requirement.status || '-' }}</td>
                <td class="trace-matrix-column-value">{{ toBooleanLabel(row.traceability.test_case_count) }}</td>
                <td class="trace-matrix-column-value">{{ toBooleanLabel(row.traceability.change_count) }}</td>
                <td class="trace-matrix-column-value">{{ toBooleanLabel(row.traceability.audit_count) }}</td>
              </tr>
              <tr v-if="row.requirement.req_id === selectedRequirementId" class="trace-matrix-inline-detail-row">
                <td colspan="5" class="trace-matrix-inline-detail-cell">
                  <div class="trace-matrix-detail trace-matrix-detail--inline">
                    <div class="trace-matrix-detail-card">
                      <p class="card-kicker">Requirement Detail</p>
                      <h3 class="section-title">{{ row.requirement.title || row.requirement.req_id }}</h3>
                      <p>{{ row.requirement.description || '暂无描述' }}</p>
                    </div>

                    <div class="trace-matrix-detail-grid">
                      <div class="trace-matrix-detail-card">
                        <p class="card-kicker">Traceability</p>
                        <div class="trace-matrix-detail-list">
                          <span>状态：{{ row.requirement.status || '-' }}</span>
                          <span>测试绑定：{{ toBooleanLabel(row.traceability.test_case_count) }}</span>
                          <span>关联变更：{{ toBooleanLabel(row.traceability.change_count) }}</span>
                          <span>关联审计：{{ toBooleanLabel(row.traceability.audit_count) }}</span>
                        </div>
                      </div>

                      <div class="trace-matrix-detail-card">
                        <p class="card-kicker">Bound Tests</p>
                        <div class="trace-matrix-detail-list">
                          <span
                            v-for="testCase in getTestsForTraceability(row.traceability)"
                            :key="testCase.test_case_id"
                          >
                            {{ testCase.title || testCase.test_case_id }}
                          </span>
                          <span v-if="!getTestsForTraceability(row.traceability).length">暂无测试绑定</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
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

function getTestsForTraceability(traceability) {
  return (traceability?.test_case_ids || [])
    .map((id) => testCaseMap.value[id])
    .filter(Boolean)
}

function toggleRequirement(reqId) {
  selectedRequirementId.value = selectedRequirementId.value === reqId ? '' : reqId
}

function toBooleanLabel(value) {
  return Number(value) > 0 ? 'True' : 'False'
}

watch(flattenedRows, (rows) => {
  if (!rows.length) {
    selectedRequirementId.value = ''
    return
  }
  if (selectedRequirementId.value && !rows.some((row) => row.requirement.req_id === selectedRequirementId.value)) {
    selectedRequirementId.value = ''
  }
}, { immediate: true })
</script>

<style scoped>
.trace-matrix-panel {
  display: grid;
  gap: 18px;
}

.trace-matrix-toolbar {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 14px;
}

.trace-matrix-filter {
  display: grid;
  gap: 8px;
  font-size: 12px;
  color: rgba(28, 40, 52, 0.72);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.trace-matrix-filter--search {
  min-width: 0;
}

.trace-matrix-stack {
  display: grid;
  gap: 18px;
}

.trace-matrix-table,
.trace-matrix-detail,
.trace-matrix-detail-card {
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
}

.trace-matrix-table {
  overflow: hidden;
}

.trace-matrix-native-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.trace-matrix-col-title {
  width: 58%;
}

.trace-matrix-col-meta {
  width: 12%;
}

.trace-matrix-col-flag {
  width: 10%;
}

.trace-matrix-header-row {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(28, 40, 52, 0.62);
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.trace-matrix-header-row th,
.trace-matrix-data-row td {
  padding: 14px 16px;
  vertical-align: top;
}

.trace-matrix-header-row th:first-child {
  text-align: left;
}

.trace-matrix-data-row {
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
  cursor: pointer;
}

.trace-matrix-data-row:last-child {
  border-bottom: none;
}

.trace-matrix-data-row.active {
  background: rgba(28, 40, 52, 0.06);
}

.trace-matrix-data-row:focus-visible {
  outline: 2px solid rgba(28, 40, 52, 0.26);
  outline-offset: -2px;
}

.trace-matrix-title-cell {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding-left: calc(var(--depth, 0) * 16px);
}

.trace-matrix-title-cell strong {
  line-height: 1.5;
  word-break: break-word;
  overflow-wrap: break-word;
}

.trace-matrix-subtitle {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.54);
  word-break: break-all;
}

.trace-matrix-column-label,
.trace-matrix-column-value {
  text-align: center;
}

.trace-matrix-column-label {
  white-space: nowrap;
}

.trace-matrix-column-value {
  padding-top: 1px;
  white-space: nowrap;
}

.trace-matrix-detail {
  padding: 18px;
  display: grid;
  gap: 14px;
}

.trace-matrix-detail--inline {
  padding: 0;
}

.trace-matrix-inline-detail-row {
  background: rgba(28, 40, 52, 0.03);
}

.trace-matrix-inline-detail-cell {
  padding: 0;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
}

.trace-matrix-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.trace-matrix-detail-card {
  padding: 16px;
}

.trace-matrix-detail-list {
  display: grid;
  gap: 8px;
  color: rgba(28, 40, 52, 0.74);
}

.trace-matrix-state {
  color: rgba(28, 40, 52, 0.72);
}

@media (max-width: 780px) {
  .trace-matrix-toolbar {
    grid-template-columns: 1fr;
  }

  .trace-matrix-table {
    overflow-x: auto;
  }

  .trace-matrix-native-table {
    min-width: 620px;
  }

  .trace-matrix-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
