<template>
  <div style="gap: 8px; background: rgba(47, 143, 137, 0.06); padding: 6px 16px; border-radius: 4px; border: 1px solid rgba(47, 143, 137, 0.15);">
    <!-- 项目选择 -->
    <div class="session-indicator">
      <Briefcase class="w-3 h-3" />
      <span class="session-label">项目:</span>
      <select
        :value="selectedProjectId"
        class="session-input sa-input"
        style="width: min(200px, 18vw); padding: 3px 6px;"
        @change="$emit('update:selectedProjectId', $event.target.value)"
      >
        <option value="">未选择</option>
        <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
          {{ p.name }}
        </option>
      </select>
    </div>
    <!-- Session 输入 -->
    <div class="session-indicator">
      <Database class="w-3 h-3" />
      <span class="session-label">Session:</span>
      <input
        :value="sessionIdDraft"
        type="text"
        class="session-input sa-input"
        placeholder="输入 Session ID"
        spellcheck="false"
        autocomplete="off"
        @input="$emit('update:sessionIdDraft', $event.target.value)"
        @keydown.enter.prevent="$emit('commit')"
        @blur="$emit('commit')"
      />
      <button
        v-if="sessionIdDraft"
        type="button"
        class="session-clear"
        title="清空 Session"
        @click="$emit('clear')"
      >
        清空
      </button>
      <button
        v-if="sessionMismatch"
        type="button"
        class="session-clear"
        style="background: rgba(245,158,11,0.12); border-color: rgba(245,158,11,0.3); color: #d97706;"
        title="当前 Session 与项目绑定的不一致"
        @click="$emit('useProjectSession')"
      >
        切换为项目Session
      </button>
    </div>
  </div>
</template>

<script setup>
import { Briefcase, Database } from 'lucide-vue-next'

defineProps({
  projects: { type: Array, default: () => [] },
  selectedProjectId: { type: String, default: '' },
  sessionIdDraft: { type: String, default: '' },
  sessionMismatch: { type: Boolean, default: false },
  projectSessionId: { type: String, default: '' },
})

defineEmits(['update:selectedProjectId', 'update:sessionIdDraft', 'commit', 'clear', 'useProjectSession'])
</script>

<style scoped>
.session-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(47, 143, 137, 0.1);
  border: 1px solid rgba(47, 143, 137, 0.2);
  font-size: 12px;
  color: #2f8f89;
}

.session-label {
  color: rgba(28, 40, 52, 0.6);
}

.session-input {
  width: min(520px, 42vw);
  padding: 4px 8px;
  font-size: 12px;
  font-family: monospace;
  border: 1px solid rgba(47, 143, 137, 0.25);
  background: rgba(255, 255, 255, 0.85);
  color: #134e4a;
  outline: none;
}

.session-input:focus {
  border-color: rgba(47, 143, 137, 0.55);
  box-shadow: 0 0 0 3px rgba(47, 143, 137, 0.12);
}

.session-clear {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid rgba(47, 143, 137, 0.25);
  background: rgba(255, 255, 255, 0.85);
  color: rgba(28, 40, 52, 0.7);
  cursor: pointer;
}

.session-clear:hover {
  color: rgba(28, 40, 52, 0.9);
  border-color: rgba(47, 143, 137, 0.45);
}
</style>
