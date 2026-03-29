<template>
  <div class="control-panel">
    <!-- 项目选择 -->
    <div class="control-section">
      <div class="control-header">
        <label class="control-label">所属项目</label>
        <button type="button" class="refresh-btn" :disabled="isLoadingProjects" @click="$emit('loadProjects')">
          <RefreshCw class="w-3 h-3" :class="isLoadingProjects ? 'animate-spin' : ''" />
          刷新
        </button>
      </div>
      <select
        :value="selectedProjectId"
        class="control-select"
        @change="$emit('update:selectedProjectId', $event.target.value)"
      >
        <option value="">请选择项目（必选）</option>
        <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
          {{ p.current_session_id ? '[已导入] ' : '[未导入] ' }}{{ p.name }}{{ p.current_session_id ? ' · ' + p.current_session_id.slice(0, 8) + '...' : '' }}
        </option>
      </select>
      <div v-if="!selectedProjectId" class="notice-box notice-warn">
        <AlertCircle class="notice-icon" />
        请先选择项目，采集结果将绑定到该项目
      </div>
      <div v-else-if="selectedProjectHasSession" class="notice-box notice-danger">
        <AlertCircle class="notice-icon" />
        该项目已完成需求导入（Session: {{ selectedProject.current_session_id.slice(0, 8) }}...），暂不支持重复导入
      </div>
      <div v-else class="notice-box notice-teal">
        <CheckCircle2 class="notice-icon" />
        该项目尚未导入需求，可以开始采集
      </div>
    </div>

    <!-- Session ID 输入 -->
    <div class="control-section">
      <label class="control-label">Session ID（可空）</label>
      <input
        :value="sessionId"
        type="text"
        class="control-input"
        placeholder="留空则后端自动生成"
        @input="$emit('update:sessionId', $event.target.value)"
      />
    </div>

    <!-- 转录文本输入 -->
    <div class="control-section" style="flex: 1; min-height: 200px;">
      <div class="control-header">
        <label class="control-label">会议转录文本</label>
        <button type="button" class="refresh-btn" :disabled="isSampleLoading" @click="$emit('loadSample')">
          <FileDown class="w-3 h-3" />
          {{ isSampleLoading ? '加载中...' : '加载示例' }}
        </button>
      </div>
      <textarea
        :value="transcriptText"
        class="control-input"
        style="flex: 1; min-height: 180px; resize: none; line-height: 1.6;"
        placeholder="粘贴会议转写文本（支持 [start-end] speaker text 或 speaker: text）"
        @input="$emit('update:transcriptText', $event.target.value)"
      ></textarea>
    </div>

    <!-- 高级选项入口 -->
    <div class="stats-panel" style="padding: 0;">
      <button
        type="button"
        class="stat-row adv-nav-btn"
        @click="$emit('openAdvanced')"
      >
        <span style="display: flex; align-items: center; gap: 6px;">
          <Settings class="w-4 h-4" />
          高级选项
        </span>
        <ChevronRight class="w-4 h-4" />
      </button>
    </div>

    <!-- 开始采集按钮 -->
    <button
      type="button"
      class="analysis-btn"
      :disabled="!canStart || pipelineState.status === 'running'"
      @click="$emit('run')"
    >
      <Loader2 v-if="pipelineState.status === 'running'" class="btn-icon animate-spin" />
      <Sparkles v-else class="btn-icon" />
      <span>{{ pipelineState.status === 'running' ? '采集中...' : '开始采集' }}</span>
    </button>

    <!-- 错误信息 -->
    <div v-if="pipelineState.error" class="notice-box notice-error">
      <AlertCircle class="notice-icon" />
      <div style="flex: 1;">
        {{ pipelineState.error }}
        <button
          v-if="pipelineState.currentPhase > 1"
          type="button"
          class="refresh-btn"
          style="margin-top: 8px; width: 100%;"
          @click="$emit('retry')"
        >
          从此步骤重试
        </button>
      </div>
    </div>

    <!-- 完成信息 -->
    <div v-if="pipelineState.status === 'completed'" class="notice-box notice-success">
      <CheckCircle2 class="notice-icon" />
      <div style="flex: 1; display: flex; align-items: center; justify-content: space-between;">
        <span>需求采集完成！</span>
        <button type="button" class="refresh-btn" @click="$emit('goToRequirements')">查看需求 →</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  Loader2, Sparkles, FileDown, Settings, ChevronRight,
  AlertCircle, CheckCircle2, RefreshCw
} from 'lucide-vue-next'

defineProps({
  projects: { type: Array, required: true },
  selectedProjectId: { type: String, required: true },
  isLoadingProjects: { type: Boolean, required: true },
  selectedProject: { type: Object, default: null },
  selectedProjectHasSession: { type: Boolean, required: true },
  sessionId: { type: String, required: true },
  transcriptText: { type: String, required: true },
  isSampleLoading: { type: Boolean, required: true },

  options: { type: Object, required: true },
  canStart: { type: Boolean, required: true },
  pipelineState: { type: Object, required: true },
})

defineEmits([
  'update:selectedProjectId',
  'update:sessionId',
  'update:transcriptText',
  'openAdvanced',
  'loadProjects',
  'loadSample',
  'run',
  'retry',
  'goToRequirements',
])
</script>

<style scoped>
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  padding: 16px;
  overflow-y: auto;
}

.control-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.control-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.control-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700);
  letter-spacing: 0.5px;
}

.control-input,
.control-select {
  width: 100%;
  padding: 12px 14px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
  color: var(--ink-950);
  border-radius: 4px;
  transition: all 0.2s ease;
}

.control-input:focus,
.control-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(196, 105, 47, 0.1);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--accent);
  background: rgba(196, 105, 47, 0.05);
  border: 1px solid rgba(196, 105, 47, 0.1);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(196, 105, 47, 0.1);
  color: var(--accent-strong);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.stats-panel {
  padding: 14px;
  background: rgba(28, 40, 52, 0.03);
  border: 1px solid rgba(28, 40, 52, 0.08);
  border-radius: 4px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 8px 0;
  color: var(--ink-700);
}

.analysis-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.analysis-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(196, 105, 47, 0.25);
}

.analysis-btn:active:not(:disabled) { transform: translateY(0); }

.analysis-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  filter: grayscale(0.5);
}

.notice-box {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  font-size: 12px;
  border-radius: 4px;
  line-height: 1.5;
}

.notice-box.notice-warn {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  color: #d97706;
}

.notice-box.notice-danger {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #b91c1c;
}

.notice-box.notice-teal {
  background: rgba(47, 143, 137, 0.06);
  border: 1px solid rgba(47, 143, 137, 0.15);
  color: var(--teal);
}

.notice-box.notice-success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #15803d;
  padding: 14px;
  font-size: 13px;
}

.notice-box.notice-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #b91c1c;
  padding: 14px;
  font-size: 13px;
}

.notice-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.notice-box.notice-success .notice-icon,
.notice-box.notice-error .notice-icon {
  width: 20px;
  height: 20px;
}

/* Tooltip */
.tooltip-container {
  position: relative;
  display: inline-flex;
  cursor: help;
}

.text-muted { color: rgba(28, 40, 52, 0.4); }

.tooltip-text {
  visibility: hidden;
  width: 200px;
  background-color: #333;
  color: #fff;
  text-align: center;
  border-radius: 4px;
  padding: 5px;
  position: absolute;
  z-index: 10;
  bottom: 125%;
  left: 50%;
  margin-left: -100px;
  opacity: 0;
  transition: opacity 0.3s;
  font-size: 11px;
  font-weight: normal;
}

.tooltip-container:hover .tooltip-text {
  visibility: visible;
  opacity: 1;
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.toggle-switch input { opacity: 0; width: 0; height: 0; }

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(28, 40, 52, 0.2);
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.toggle-switch input:checked + .toggle-slider { background-color: var(--accent); }
.toggle-switch input:checked + .toggle-slider:before { transform: translateX(20px); }
.toggle-switch input:focus + .toggle-slider { box-shadow: 0 0 0 3px rgba(196, 105, 47, 0.1); }

/* Advanced nav button */
.adv-nav-btn {
  width: 100%;
  cursor: pointer;
  border: none;
  background: transparent;
  transition: background 0.2s ease;
}

.adv-nav-btn:hover {
  background: rgba(196, 105, 47, 0.06);
}

/* Icon size utilities */
.w-3 { width: 12px !important; height: 12px !important; }
.w-4 { width: 16px !important; height: 16px !important; }
.btn-icon { width: 20px; height: 20px; }

.animate-spin { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
