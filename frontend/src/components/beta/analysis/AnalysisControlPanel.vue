<template>
  <div class="control-panel">
    <!-- 项目选择 -->
    <div class="control-section">
      <div class="control-header">
        <label class="control-label">所属项目</label>
        <button
          type="button"
          class="refresh-btn"
          :disabled="isLoadingProjects"
          @click="$emit('loadProjects')"
        >
          <RefreshCw class="w-3 h-3" :class="isLoadingProjects ? 'animate-spin' : ''" />
          刷新
        </button>
      </div>
      <select
        :value="selectedProjectId"
        class="control-select"
        @change="$emit('update:selectedProjectId', $event.target.value)"
      >
        <option value="">（可选：关联项目）</option>
        <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
          {{ p.name }}{{ p.current_session_id ? ' · Session: ' + p.current_session_id.slice(0, 8) + '...' : '' }}
        </option>
      </select>
      <button
        v-if="selectedProjectId && projectSessionId && projectSessionId !== sessionId"
        type="button"
        class="refresh-btn"
        style="margin-top: 4px; width: 100%; justify-content: center;"
        @click="$emit('update:sessionId', projectSessionId)"
      >
        使用项目 Session: {{ projectSessionId.slice(0, 12) }}...
      </button>
    </div>

    <!-- Session ID 输入 -->
    <div class="control-section">
      <label class="control-label">Session ID</label>
      <input
        :value="sessionId"
        type="text"
        class="control-input"
        placeholder="Phase 1 ingest_transcript 返回的 session_id"
        @input="$emit('update:sessionId', $event.target.value)"
      />
    </div>

    <!-- Context Run 选择 -->
    <div class="control-section">
      <div class="control-header">
        <label class="control-label">Context Run (Phase 2)</label>
        <button
          type="button"
          class="refresh-btn"
          :disabled="isLoadingRuns"
          @click="$emit('loadContextRuns')"
        >
          <RefreshCw class="w-3 h-3" :class="isLoadingRuns ? 'animate-spin' : ''" />
          刷新
        </button>
      </div>
      <select
        :value="contextRunId"
        class="control-select"
        @change="$emit('update:contextRunId', $event.target.value)"
      >
        <option value="">（可选：graph 策略需要）</option>
        <option v-for="run in contextRuns" :key="run.context_run_id" :value="run.context_run_id">
          {{ run.context_run_id.slice(0, 8) }}... · {{ run.session_id?.slice(0, 8) || 'N/A' }}... · {{ run.status }}
        </option>
      </select>
    </div>

    <div class="control-section" v-if="sessionId">
      <div class="control-header">
        <label class="control-label">分析记录</label>
        <button
          type="button"
          class="refresh-btn"
          :disabled="isLoadingAnalysisRuns"
          @click="$emit('loadAnalysisRuns')"
        >
          <RefreshCw class="w-3 h-3" :class="isLoadingAnalysisRuns ? 'animate-spin' : ''" />
          刷新
        </button>
      </div>
      <select
        :value="selectedAnalysisRunId"
        class="control-select"
        @change="$emit('update:selectedAnalysisRunId', $event.target.value)"
      >
        <option value="">最新一次完整分析</option>
        <option v-for="run in analysisRuns" :key="run.analysis_run_id" :value="run.analysis_run_id">
          {{ run.created_at?.replace('T', ' ').slice(0, 19) || run.analysis_run_id.slice(0, 8) }}
          · 追溯 {{ run.meta?.summary?.trace_relations_count || 0 }}
          · 冲突 {{ run.meta?.summary?.confirmed_conflict_count || 0 }}
          · 分类 {{ run.meta?.summary?.classification_total || 0 }}
        </option>
      </select>
    </div>

    <div v-if="activeTab === 'conflict'" class="control-section">
      <label class="control-label">冲突检测并发数</label>
      <select
        :value="conflictConcurrency"
        class="control-select"
        @change="$emit('update:conflictConcurrency', Number($event.target.value))"
      >
        <option :value="1">1</option>
        <option :value="2">2</option>
        <option :value="3">3</option>
        <option :value="4">4</option>
        <option :value="6">6</option>
        <option :value="8">8</option>
      </select>
    </div>

    <!-- 统计信息 -->
    <div class="stats-panel" v-if="allHighLevelRequirements.length > 0 || lowLevelRequirements.length > 0">
      <div class="stat-row">
        <span>顶层需求</span>
        <span class="stat-value">{{ allHighLevelRequirements.length }}</span>
      </div>
      <div class="stat-row">
        <span>底层需求</span>
        <span class="stat-value">{{ lowLevelRequirements.length }}</span>
      </div>
      <div v-if="activeTab === 'network' && traceResult" class="stat-row">
        <span>追溯关系</span>
        <span class="stat-value highlight">{{ traceResult.statistics?.relations_found || 0 }}</span>
      </div>
      <div v-if="activeTab === 'conflict' && conflictStats" class="stat-row">
        <span>确认冲突</span>
        <span class="stat-value" :class="conflictStats.conflicts > 0 ? 'danger' : 'success'">
          {{ conflictStats.conflicts }} / {{ conflictStats.total }}
        </span>
      </div>
      <div v-if="activeTab === 'conflict' && conflictStats" class="stat-row">
        <span>疑似冲突</span>
        <span class="stat-value highlight">{{ conflictStats.suspected || 0 }}</span>
      </div>
      <div v-if="activeTab === 'conflict' && conflictStats" class="stat-row">
        <span>实际并发</span>
        <span class="stat-value">{{ conflictStats.appliedConcurrency || 0 }} / {{ conflictStats.requestedConcurrency || 0 }}</span>
      </div>
      <div v-if="activeTab === 'classification' && classificationResult" class="stat-row">
        <span>已分类</span>
        <span class="stat-value success">{{ classificationResult.total }}</span>
      </div>
    </div>

    <!-- 一键分析按钮 -->
    <button
      type="button"
      class="analysis-btn"
      :disabled="!canAnalyze || isAnalyzing"
      @click="$emit('runAnalysis')"
    >
      <Loader2 v-if="isAnalyzing" class="btn-icon animate-spin" />
      <BarChart3 v-else class="btn-icon" />
      <span>{{ isAnalyzing ? '完整分析中...' : '一键分析并保存完整结果' }}</span>
    </button>

    <!-- 分析进度 -->
    <div v-if="isAnalyzing || analysisStep === 5" class="progress-panel">
      <div class="progress-bar">
        <div
          class="progress-fill"
          :class="progressColorClass"
          :style="{ width: `${analysisPercent}%` }"
        ></div>
      </div>
      <div class="progress-steps">
        <div
          class="step"
          :class="{ active: analysisStep >= 1, done: analysisStep > 1 }"
        >
          <span class="step-dot">{{ analysisStep > 1 ? '✓' : '1' }}</span>
          <span>L4生成</span>
        </div>
        <div
          class="step"
          :class="{ active: analysisStep >= 2, done: analysisStep > 2 }"
        >
          <span class="step-dot">{{ analysisStep > 2 ? '✓' : '2' }}</span>
          <span>追溯</span>
        </div>
        <div
          class="step"
          :class="{ active: analysisStep >= 3, done: analysisStep > 3 || analysisStep === 5 }"
        >
          <span class="step-dot">{{ analysisStep > 3 || analysisStep === 5 ? '✓' : '3' }}</span>
          <span>冲突</span>
        </div>
        <div
          class="step"
          :class="{ active: analysisStep >= 4, done: analysisStep === 5 }"
        >
          <span class="step-dot">{{ analysisStep === 5 ? '✓' : '4' }}</span>
          <span>分类</span>
        </div>
      </div>
      <p class="progress-text" :class="progressColorClass">{{ analysisStepText }}</p>
    </div>

    <!-- 提示信息 -->
    <div v-if="analysisNotice" class="notice-box success">
      <CheckCircle2 class="notice-icon" />
      {{ analysisNotice }}
    </div>

    <!-- 错误信息 -->
    <div v-if="analysisError" class="notice-box error">
      <AlertCircle class="notice-icon" />
      {{ analysisError }}
    </div>
  </div>
</template>

<script setup>
import { RefreshCw, Loader2, BarChart3, AlertCircle, CheckCircle2 } from 'lucide-vue-next'

defineProps({
  activeTab: { type: String, default: 'network' },
  activeAnalysisLabel: { type: String, default: '追溯' },
  projects: { type: Array, default: () => [] },
  isLoadingProjects: { type: Boolean, default: false },
  selectedProjectId: { type: String, default: '' },
  projectSessionId: { type: String, default: '' },
  sessionId: { type: String, default: '' },
  contextRuns: { type: Array, default: () => [] },
  isLoadingRuns: { type: Boolean, default: false },
  contextRunId: { type: String, default: '' },
  analysisRuns: { type: Array, default: () => [] },
  isLoadingAnalysisRuns: { type: Boolean, default: false },
  selectedAnalysisRunId: { type: String, default: '' },
  allHighLevelRequirements: { type: Array, default: () => [] },
  lowLevelRequirements: { type: Array, default: () => [] },
  isAnalyzing: { type: Boolean, default: false },
  canAnalyze: { type: Boolean, default: false },
  analysisStep: { type: Number, default: 0 },
  analysisPercent: { type: Number, default: 0 },
  progressColorClass: { type: String, default: '' },
  analysisStepText: { type: String, default: '' },
  traceResult: { type: Object, default: null },
  conflictStats: { type: Object, default: null },
  classificationResult: { type: Object, default: null },
  analysisNotice: { type: String, default: '' },
  analysisError: { type: String, default: null },
  conflictConcurrency: { type: Number, default: 3 },
})

defineEmits([
  'update:selectedProjectId',
  'update:sessionId',
  'update:contextRunId',
  'update:selectedAnalysisRunId',
  'update:conflictConcurrency',
  'loadProjects',
  'loadContextRuns',
  'loadAnalysisRuns',
  'runAnalysis',
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
  gap: 8px;
}

.control-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.control-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink-700);
}

.control-input,
.control-select {
  padding: 10px 12px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink-950);
  border-radius: 0;
  font-family: "BodyWithTimesDigits", "Noto Sans SC", sans-serif;
}

.control-input:focus,
.control-select:focus {
  outline: none;
  border-color: var(--accent);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 11px;
  color: rgba(28, 40, 52, 0.6);
  background: transparent;
  border: none;
  cursor: pointer;
}

.refresh-btn:hover {
  color: var(--ink-950);
}

/* 统计面板 */
.stats-panel {
  padding: 12px;
  background: rgba(28, 40, 52, 0.04);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 6px 0;
  color: rgba(28, 40, 52, 0.7);
}

.stat-value {
  font-weight: 600;
  color: var(--ink-950);
}

.stat-value.highlight { color: #3b82f6; }
.stat-value.success { color: #22c55e; }
.stat-value.danger { color: #ef4444; }

/* 分析按钮 */
.analysis-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px 20px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.analysis-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(196, 105, 47, 0.3);
}

.analysis-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  width: 20px;
  height: 20px;
}

/* 进度面板 */
.progress-panel {
  padding: 16px;
  background: linear-gradient(135deg, rgba(196, 105, 47, 0.08), rgba(47, 143, 137, 0.08));
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.progress-bar {
  height: 8px;
  background: rgba(28, 40, 52, 0.1);
  overflow: hidden;
  margin-bottom: 12px;
}

.progress-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.progress-fill.color-l4gen { background: #8b5cf6; }
.progress-fill.color-trace { background: #3b82f6; }
.progress-fill.color-conflict { background: #f59e0b; }
.progress-fill.color-classify { background: #22c55e; }
.progress-fill.color-complete { background: #10b981; }

.progress-steps {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: rgba(28, 40, 52, 0.4);
}

.step.active { color: var(--ink-950); font-weight: 500; }
.step.done { color: #22c55e; }

.step-dot {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  border-radius: 50%;
  background: rgba(28, 40, 52, 0.1);
}

.step.active .step-dot { background: var(--accent); color: #fff; }
.step.done .step-dot { background: #22c55e; color: #fff; }

.progress-text {
  text-align: center;
  font-size: 12px;
  font-weight: 500;
  margin: 0;
}

.progress-text.color-l4gen { color: #8b5cf6; }
.progress-text.color-trace { color: #3b82f6; }
.progress-text.color-conflict { color: #f59e0b; }
.progress-text.color-classify { color: #22c55e; }
.progress-text.color-complete { color: #10b981; }

/* 提示框 */
.notice-box {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  font-size: 12px;
  border: 1px solid;
}

.notice-box.success {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.3);
  color: #15803d;
}

.notice-box.error {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
  color: #b91c1c;
}

.notice-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
</style>
