<template>
  <div class="result-panel">
    <!-- Tab 切换 -->
    <div class="result-tabs">
      <button
        type="button"
        class="result-tab"
        :class="{ active: activeTab === 'network' }"
        @click="$emit('update:activeTab', 'network')"
      >
        <Network class="tab-icon" />
        追溯图
      </button>
      <button
        type="button"
        class="result-tab"
        :class="{ active: activeTab === 'conflict' }"
        @click="$emit('update:activeTab', 'conflict')"
      >
        <AlertTriangle class="tab-icon" />
        冲突
        <span v-if="conflictStats && conflictStats.conflicts > 0" class="tab-badge danger">
          {{ conflictStats.conflicts }}
        </span>
      </button>
      <button
        type="button"
        class="result-tab"
        :class="{ active: activeTab === 'classification' }"
        @click="$emit('update:activeTab', 'classification')"
      >
        <Tags class="tab-icon" />
        分类
      </button>
    </div>

    <!-- 结果内容 -->
    <div class="result-content">
      <TraceNetworkTab
        v-show="activeTab === 'network'"
        :traceResult="traceResult"
        :allHighLevelRequirements="allHighLevelRequirements"
        :lowLevelRequirements="lowLevelRequirements"
        :isActive="activeTab === 'network'"
      />
      <ConflictTab
        v-show="activeTab === 'conflict'"
        :conflictResults="conflictResults"
        :conflictStats="conflictStats"
      />
      <ClassificationTab
        v-show="activeTab === 'classification'"
        :classificationResult="classificationResult"
        :classificationGroups="classificationGroups"
      />
    </div>
  </div>
</template>

<script setup>
import { Network, AlertTriangle, Tags } from 'lucide-vue-next'
import TraceNetworkTab from './TraceNetworkTab.vue'
import ConflictTab from './ConflictTab.vue'
import ClassificationTab from './ClassificationTab.vue'

defineProps({
  activeTab: { type: String, default: 'network' },
  traceResult: { type: Object, default: null },
  allHighLevelRequirements: { type: Array, default: () => [] },
  lowLevelRequirements: { type: Array, default: () => [] },
  conflictResults: { type: Array, default: () => [] },
  conflictStats: { type: Object, default: null },
  classificationResult: { type: Object, default: null },
  classificationGroups: { type: Array, default: () => [] },
})

defineEmits(['update:activeTab'])
</script>

<style scoped>
.result-panel {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  overflow: hidden;
}

.result-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(28, 40, 52, 0.02);
}

.result-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(28, 40, 52, 0.6);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.result-tab:hover {
  color: var(--ink-950);
}

.result-tab.active {
  background: rgba(255, 255, 255, 0.95);
  color: var(--ink-950);
}

.tab-icon {
  width: 16px;
  height: 16px;
}

.tab-badge {
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
}

.tab-badge.danger {
  background: rgba(239, 68, 68, 0.15);
  color: #dc2626;
}

.result-content {
  flex: 1;
  overflow: hidden;
}
</style>
