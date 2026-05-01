<template>
  <section class="requirements-toolbar" data-animate style="--delay: 0.1s">
    <!-- 左侧: 层级筛选 -->
    <div class="level-tabs">
      <button
        v-for="tab in levelTabs"
        :key="tab.key"
        type="button"
        class="level-tab"
        :class="{ active: activeLevel === tab.key }"
        @click="$emit('update:activeLevel', tab.key)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ levelCounts[tab.key] || 0 }}</span>
      </button>
    </div>

    <!-- 右侧: 视图切换 -->
    <div class="view-switcher">
      <button type="button" class="view-btn sa-button" :class="{ active: activeView === 'tree' }" title="树状视图" @click="$emit('update:activeView', 'tree')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 3v18M3 9l9-6 9 6M3 15l9 6 9-6" />
        </svg>
      </button>
      <button type="button" class="view-btn sa-button" :class="{ active: activeView === 'table' }" title="表格视图" @click="$emit('update:activeView', 'table')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <line x1="3" y1="9" x2="21" y2="9" />
          <line x1="3" y1="15" x2="21" y2="15" />
          <line x1="9" y1="3" x2="9" y2="21" />
        </svg>
      </button>
      <button type="button" class="view-btn sa-button" :class="{ active: activeView === 'card' }" title="卡片视图" @click="$emit('update:activeView', 'card')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      </button>
    </div>
  </section>
</template>

<script setup>
defineProps({
  activeLevel: { type: String, default: 'all' },
  activeView: { type: String, default: 'tree' },
  levelTabs: { type: Array, default: () => [] },
  levelCounts: { type: Object, default: () => ({}) },
})

defineEmits(['update:activeLevel', 'update:activeView'])
</script>

<style scoped>
.requirements-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  margin-bottom: 12px;
}

.level-tabs {
  display: flex;
  gap: 4px;
  background: rgba(28, 40, 52, 0.06);
  padding: 4px;
}

.level-tab {
  padding: 6px 12px;
  font-size: 13px;
  font-family: "BodyWithTimesDigits", "Noto Sans SC", sans-serif;
  background: transparent;
  border: none;
  color: rgba(28, 40, 52, 0.7);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-tab:hover { color: var(--ink-950); }

.level-tab.active {
  background: rgba(255, 255, 255, 0.95);
  color: var(--ink-950);
  font-weight: 500;
}

.tab-count {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(28, 40, 52, 0.1);
  border-radius: 10px;
  color: rgba(28, 40, 52, 0.6);
}

.level-tab.active .tab-count { background: var(--accent); color: #fff; }

.view-switcher { display: flex; gap: 4px; background: rgba(28, 40, 52, 0.06); padding: 4px; }

.view-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  color: rgba(28, 40, 52, 0.5);
}

.view-btn:hover { color: var(--ink-950); }
.view-btn.active { background: rgba(255, 255, 255, 0.95); color: var(--accent); }
.view-btn svg { width: 18px; height: 18px; }
</style>
