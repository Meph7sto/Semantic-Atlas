<template>
  <div class="table-view-container">
    <!-- 工具栏 -->
    <div class="table-toolbar">
      <div class="table-search">
        <Search class="table-search-icon" />
        <input
          v-model="tableSearchQuery"
          type="text"
          placeholder="搜索需求名称、层级、状态..."
          class="table-search-input"
        />
      </div>
      <div class="table-column-config">
        <button type="button" class="column-config-btn" @click="showColumnSelector = !showColumnSelector">
          <Filter class="w-4 h-4" />
          设置展示列
          <ChevronDown class="w-4 h-4 transition-transform" :class="showColumnSelector ? 'rotate-180' : ''" />
        </button>
        <div v-if="showColumnSelector" class="column-selector">
          <div
            v-for="col in availableTableColumns"
            :key="col.key"
            class="column-selector-item"
            @click="toggleColumn(col.key)"
          >
            <div class="column-selector-check" :class="tableVisibleColumns.includes(col.key) ? 'checked' : ''">
              <CheckCircle2 v-if="tableVisibleColumns.includes(col.key)" class="w-3 h-3" />
            </div>
            <span>{{ col.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 表格 -->
    <div class="table-scroll">
      <table class="requirements-table">
        <thead>
          <tr>
            <th
              v-for="col in availableTableColumns.filter(c => tableVisibleColumns.includes(c.key))"
              :key="col.key"
              :class="col.width"
              @click="toggleSort(col.key)"
            >
              <div class="th-content">
                {{ col.label }}
                <div class="sort-icons">
                  <ChevronUp class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'asc' ? 'active' : ''" />
                  <ChevronDown class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'desc' ? 'active' : ''" />
                </div>
              </div>
            </th>
            <th class="w-16">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="req in tableRequirements" :key="req.id || req.req_id">
            <td v-if="tableVisibleColumns.includes('name')">
              <p class="cell-title">{{ req.title || req.text || req.statement }}</p>
            </td>
            <td v-if="tableVisibleColumns.includes('type')">
              <span class="cell-type" :class="req.level === 'L4' ? 'type-low' : 'type-high'">
                {{ req.level === 'L4' ? '底层需求' : '顶层需求' }}
              </span>
            </td>
            <td v-if="tableVisibleColumns.includes('level')">
              <span class="cell-level" :class="getLevelBadgeClass(req.level || req.category)">
                {{ req.level || req.category || '-' }}
              </span>
            </td>
            <td v-if="tableVisibleColumns.includes('status')">
              <select
                :value="req.status"
                class="cell-status"
                :class="getStatusColorClass(req.status, 'bg')"
                @change="$emit('updateStatus', req.id || req.req_id, $event.target.value)"
              >
                <option v-for="s in requirementStatuses" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </td>
            <td v-if="tableVisibleColumns.includes('confidence')">
              <span v-if="req.confidence" class="cell-confidence" :class="getConfidenceClass(req.confidence)">
                {{ (req.confidence * 100).toFixed(0) }}%
              </span>
              <span v-else class="cell-muted">-</span>
            </td>
            <td v-if="tableVisibleColumns.includes('evidence')">
              <span class="cell-truncate" :title="req.evidence || req.anchor_span_id">
                {{ req.evidence || req.anchor_span_id || '-' }}
              </span>
            </td>
            <td v-if="tableVisibleColumns.includes('rationale')">
              <span class="cell-truncate" :title="req.rationale">{{ req.rationale || '-' }}</span>
            </td>
            <td>
              <button type="button" class="edit-btn" title="编辑需求" @click="$emit('editRequirement', req)">
                <Pencil class="w-3.5 h-3.5" />
              </button>
            </td>
          </tr>
          <tr v-if="tableRequirements.length === 0">
            <td :colspan="tableVisibleColumns.length + 1" class="table-empty">暂无需求数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="table-footer">共 {{ tableRequirements.length }} 条</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Search, Filter, ChevronDown, ChevronUp, CheckCircle2, Pencil } from 'lucide-vue-next'

const props = defineProps({
  filteredRequirements: { type: Array, default: () => [] },
  requirementStatuses: { type: Array, default: () => [] },
})

defineEmits(['editRequirement', 'updateStatus'])

// 内部表格状态
const tableSearchQuery = ref('')
const tableVisibleColumns = ref(['name', 'type', 'level', 'status', 'confidence', 'evidence'])
const tableSortKey = ref('name')
const tableSortOrder = ref('asc')
const showColumnSelector = ref(false)

const availableTableColumns = [
  { key: 'name', label: '需求名称', width: 'flex-1 min-w-[280px]' },
  { key: 'type', label: '类型', width: 'w-24' },
  { key: 'level', label: '层级', width: 'w-20' },
  { key: 'status', label: '状态', width: 'w-28' },
  { key: 'confidence', label: '置信度', width: 'w-24' },
  { key: 'evidence', label: '证据', width: 'w-40' },
  { key: 'rationale', label: '原因', width: 'w-40' },
]

const tableRequirements = computed(() => {
  let result = [...props.filteredRequirements]

  if (tableSearchQuery.value.trim()) {
    const query = tableSearchQuery.value.toLowerCase()
    result = result.filter(r =>
      (r.statement || r.text || r.title || '').toLowerCase().includes(query) ||
      (r.level || r.category || '').toLowerCase().includes(query) ||
      (getStatusName(r.status) || '').toLowerCase().includes(query)
    )
  }

  result.sort((a, b) => {
    let aVal = tableSortKey.value === 'name' ? (a.statement || a.text || a.title || '') : (a[tableSortKey.value] || '')
    let bVal = tableSortKey.value === 'name' ? (b.statement || b.text || b.title || '') : (b[tableSortKey.value] || '')
    return tableSortOrder.value === 'asc'
      ? String(aVal).localeCompare(String(bVal))
      : String(bVal).localeCompare(String(aVal))
  })

  return result
})

function getStatusName(statusId) {
  return props.requirementStatuses.find(s => s.id === statusId)?.name || '待处理'
}

function getStatusColorClass(statusId, variant = 'bg') {
  const color = props.requirementStatuses.find(s => s.id === statusId)?.color || 'zinc'
  const colorMap = {
    zinc:    { bg: 'bg-zinc-100' },
    blue:    { bg: 'bg-blue-100' },
    emerald: { bg: 'bg-emerald-100' },
  }
  return colorMap[color]?.[variant] || colorMap.zinc[variant]
}

function getLevelBadgeClass(level) {
  const map = {
    L1: 'bg-sky-100 text-sky-700 border-sky-200',
    L2: 'bg-violet-100 text-violet-700 border-violet-200',
    L3: 'bg-amber-100 text-amber-700 border-amber-200',
    L4: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  }
  return map[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function getConfidenceClass(conf) {
  if (conf >= 0.8) return 'conf-high'
  if (conf >= 0.5) return 'conf-medium'
  return 'conf-low'
}

function toggleSort(key) {
  if (tableSortKey.value === key) {
    tableSortOrder.value = tableSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    tableSortKey.value = key
    tableSortOrder.value = 'asc'
  }
}

function toggleColumn(key) {
  const idx = tableVisibleColumns.value.indexOf(key)
  tableVisibleColumns.value = idx >= 0
    ? tableVisibleColumns.value.filter(k => k !== key)
    : [...tableVisibleColumns.value, key]
}
</script>

<style scoped>
.table-view-container {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(255, 255, 255, 0.95);
}

.table-search { position: relative; flex: 1; max-width: 360px; }

.table-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  width: 14px;
  height: 14px;
  transform: translateY(-50%);
  color: rgba(28, 40, 52, 0.5);
}

.table-search-input {
  width: 100%;
  padding: 8px 12px 8px 32px;
  font-size: 12px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
}

.table-column-config { position: relative; }

.column-config-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
  color: rgba(28, 40, 52, 0.8);
}

.column-selector {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  width: 200px;
  background: #fff;
  border: 1px solid rgba(28, 40, 52, 0.12);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
  z-index: 20;
  padding: 6px 0;
}

.column-selector-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.column-selector-item:hover { background: rgba(28, 40, 52, 0.04); }

.column-selector-check {
  width: 14px;
  height: 14px;
  border: 1px solid rgba(28, 40, 52, 0.3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.column-selector-check.checked { background: #111; color: #fff; border-color: #111; }

.table-scroll { flex: 1; overflow: auto; }

.requirements-table { width: 100%; border-collapse: collapse; }

.requirements-table thead th {
  position: sticky;
  top: 0;
  background: #f8f9fb;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(28, 40, 52, 0.6);
  padding: 10px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  cursor: pointer;
  text-align: left;
}

.requirements-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
  font-size: 12px;
  color: rgba(28, 40, 52, 0.85);
}

.requirements-table tbody tr:hover { background: rgba(28, 40, 52, 0.02); }

.th-content { display: flex; align-items: center; gap: 6px; }
.sort-icons { display: flex; flex-direction: column; margin-top: -2px; }
.sort-icons .active { color: #111; }

.cell-title { font-weight: 600; color: var(--ink-950); }

.cell-type {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  border: 1px solid transparent;
}

.cell-type.type-high { background: rgba(14, 165, 233, 0.1); color: #0284c7; border-color: rgba(14, 165, 233, 0.2); }
.cell-type.type-low { background: rgba(16, 185, 129, 0.1); color: #059669; border-color: rgba(16, 185, 129, 0.2); }

.cell-level { display: inline-block; padding: 2px 6px; font-size: 10px; border: 1px solid transparent; }

.cell-status { padding: 4px 8px; font-size: 11px; border: 1px solid rgba(28, 40, 52, 0.15); background: #fff; }

.cell-confidence { padding: 2px 6px; font-size: 10px; border: 1px solid rgba(28, 40, 52, 0.1); }
.cell-muted { color: rgba(28, 40, 52, 0.4); }

.cell-truncate {
  display: inline-block;
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(28, 40, 52, 0.6);
}

.edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid rgba(28, 40, 52, 0.15);
  color: rgba(28, 40, 52, 0.5);
  cursor: pointer;
  transition: all 0.2s ease;
}

.edit-btn:hover { background: rgba(47, 143, 137, 0.08); border-color: rgba(47, 143, 137, 0.3); color: #2f8f89; }

.table-empty { text-align: center; padding: 24px 12px; color: rgba(28, 40, 52, 0.45); }

.table-footer { padding: 10px 16px; border-top: 1px solid rgba(28, 40, 52, 0.1); font-size: 12px; color: rgba(28, 40, 52, 0.6); }

.conf-high { background: rgba(34, 197, 94, 0.1); color: #15803d; border-color: rgba(34, 197, 94, 0.3); }
.conf-medium { background: rgba(234, 179, 8, 0.1); color: #a16207; border-color: rgba(234, 179, 8, 0.3); }
.conf-low { background: rgba(239, 68, 68, 0.1); color: #b91c1c; border-color: rgba(239, 68, 68, 0.3); }
</style>
