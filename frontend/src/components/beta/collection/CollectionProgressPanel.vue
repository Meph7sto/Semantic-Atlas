<template>
  <div class="result-panel">
    <!-- 标题 -->
    <div class="result-tabs">
      <Zap class="w-5 h-5" style="color: var(--accent);" />
      <span style="font-weight: 600; color: var(--ink-950);">采集进度</span>
    </div>

    <!-- 内容区 -->
    <div class="result-content">
      <!-- 进度步骤 -->
      <div style="display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px;">
        <div
          v-for="(phase, idx) in phases"
          :key="idx"
          class="stats-panel"
          :style="getPhaseStyle(idx + 1)"
        >
          <div style="display: flex; align-items: flex-start; gap: 12px;">
            <div style="width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
              <Loader2 v-if="pipelineState.phases[idx + 1].status === 'running'" class="w-5 h-5 animate-spin" style="color: var(--accent);" />
              <CheckCircle2 v-else-if="pipelineState.phases[idx + 1].status === 'completed'" class="w-5 h-5" style="color: #22c55e;" />
              <XCircle v-else-if="pipelineState.phases[idx + 1].status === 'error'" class="w-5 h-5" style="color: #ef4444;" />
              <span v-else style="width: 24px; height: 24px; border: 2px solid rgba(28, 40, 52, 0.2); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: rgba(28, 40, 52, 0.4);">{{ idx + 1 }}</span>
            </div>
            <div style="flex: 1; min-width: 0;">
              <div style="font-size: 14px; font-weight: 600; color: var(--ink-950);">{{ phase.title }}</div>
              <div style="font-size: 12px; color: rgba(28, 40, 52, 0.6); margin-top: 2px;">{{ phase.desc }}</div>
              <div v-if="pipelineState.phases[idx + 1].status !== 'pending'" style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px;">
                <template v-if="idx === 0">
                  <span v-if="pipelineState.phases[1].sessionId" class="jama-pill" style="font-size: 10px;">
                    Session: {{ pipelineState.phases[1].sessionId.slice(0, 8) }}...
                  </span>
                  <span v-if="pipelineState.phases[1].spanCount > 0" class="jama-pill" style="font-size: 10px;">
                    {{ pipelineState.phases[1].spanCount }} spans
                  </span>
                </template>
                <template v-else-if="idx === 1">
                  <span v-if="pipelineState.phases[2].contextRunId" class="jama-pill" style="font-size: 10px;">
                    Run: {{ pipelineState.phases[2].contextRunId.slice(0, 8) }}...
                  </span>
                  <span v-if="pipelineState.phases[2].bundleCount > 0" class="jama-pill" style="font-size: 10px;">
                    {{ pipelineState.phases[2].bundleCount }} bundles
                  </span>
                </template>
                <template v-else-if="idx === 2">
                  <span v-if="pipelineState.phases[3].l123Count > 0" class="jama-pill" style="font-size: 10px;">
                    {{ pipelineState.phases[3].l123Count }} 条 L1/L2/L3
                  </span>
                </template>
                <template v-else-if="idx === 3">
                  <span v-if="pipelineState.phases[4].l4Count > 0" class="jama-pill" style="font-size: 10px;">
                    {{ pipelineState.phases[4].l4Count }} 条 L4
                  </span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 实时日志 -->
      <div style="border: 1px solid rgba(28, 40, 52, 0.1);">
        <div class="stat-row" style="background: rgba(28, 40, 52, 0.04); padding: 10px 12px; border-bottom: 1px solid rgba(28, 40, 52, 0.08);">
          <span style="display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500;">
            <FileText class="w-4 h-4" />
            实时日志
          </span>
          <span style="font-size: 10px; padding: 2px 6px; background: rgba(28, 40, 52, 0.1); color: rgba(28, 40, 52, 0.6);">{{ logs.length }}</span>
        </div>
        <div
          ref="logContainer"
          style="height: 200px; overflow-y: auto; padding: 12px; font-family: 'SF Mono', 'Monaco', monospace; font-size: 11px; line-height: 1.6; background: rgba(28, 40, 52, 0.02);"
        >
          <div
            v-for="(log, idx) in logs"
            :key="idx"
            style="display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px solid rgba(28, 40, 52, 0.04);"
          >
            <span style="color: rgba(28, 40, 52, 0.4); flex-shrink: 0;">{{ log.time }}</span>
            <span style="color: var(--accent); font-weight: 500; flex-shrink: 0;">[{{ log.phase }}]</span>
            <span :style="{ color: log.type === 'error' ? '#b91c1c' : log.type === 'success' ? '#15803d' : 'rgba(28, 40, 52, 0.8)' }">{{ log.message }}</span>
          </div>
          <div v-if="logs.length === 0" style="color: rgba(28, 40, 52, 0.4); text-align: center; padding: 20px;">
            等待开始采集...
          </div>
        </div>
      </div>

      <!-- 统计汇总 -->
      <div v-if="pipelineState.status === 'completed'" class="notice-box success" style="margin-top: 16px;">
        <div style="width: 100%;">
          <div style="font-weight: 600; margin-bottom: 12px;">采集统计</div>
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
            <div v-for="stat in summaryStats" :key="stat.label" class="stat-card">
              <div class="stat-label">{{ stat.label }}</div>
              <div class="stat-value">{{ stat.value }}</div>
            </div>
          </div>

          <!-- 去重明细 -->
          <div
            v-if="pipelineState.phases[3].deduplication && showPostDedup"
            style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(34, 197, 94, 0.25);"
          >
            <div style="font-weight: 600; margin-bottom: 10px;">抽取后去重（Phase 3）</div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
              <div class="stat-card">
                <div class="stat-label">Groups</div>
                <div class="stat-value">{{ pipelineState.phases[3].deduplication.total_duplicates ?? 0 }}</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Scanned</div>
                <div class="stat-value">{{ pipelineState.phases[3].deduplication.total_requirements_scanned ?? 0 }}</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Merged</div>
                <div class="stat-value">{{ pipelineState.phases[3].deduplication.total_merged ?? '-' }}</div>
              </div>
            </div>

            <div
              v-if="(pipelineState.phases[3].deduplication.duplicate_groups || []).length"
              style="margin-top: 12px; border: 1px solid rgba(28, 40, 52, 0.08); background: rgba(255, 255, 255, 0.7); padding: 10px; max-height: 180px; overflow-y: auto;"
            >
              <div style="font-size: 12px; font-weight: 600; margin-bottom: 8px; color: rgba(28, 40, 52, 0.8);">重复组明细</div>
              <div
                v-for="group in pipelineState.phases[3].deduplication.duplicate_groups"
                :key="group.group_id"
                style="padding: 8px 0; border-bottom: 1px solid rgba(28, 40, 52, 0.06);"
              >
                <div style="display: flex; justify-content: space-between; gap: 8px;">
                  <div style="font-size: 12px; font-weight: 600; color: rgba(28, 40, 52, 0.85);">{{ group.level }} · {{ group.group_id }}</div>
                  <div style="font-size: 11px; color: rgba(28, 40, 52, 0.55);">sim: {{ group.similarity }}</div>
                </div>
                <div style="margin-top: 6px; font-size: 11px; color: rgba(28, 40, 52, 0.75); white-space: pre-wrap;">
                  <span style="color: rgba(28, 40, 52, 0.5);">repr:</span>
                  {{ group.representative_text || '' }}
                </div>
                <div v-if="group.llm_decision" style="margin-top: 6px; font-size: 11px; color: rgba(28, 40, 52, 0.75);">
                  <span style="color: rgba(28, 40, 52, 0.5);">llm:</span>
                  merge={{ group.llm_decision.should_merge }} primary={{ group.llm_decision.primary_req_id || '-' }}
                </div>
                <div v-if="group.merge_result" style="margin-top: 4px; font-size: 11px; color: rgba(28, 40, 52, 0.75);">
                  <span style="color: rgba(28, 40, 52, 0.5);">db:</span>
                  success={{ group.merge_result.success }} deleted={{ group.merge_result.deleted_count ?? 0 }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { Loader2, CheckCircle2, XCircle, Zap, FileText } from 'lucide-vue-next'

const props = defineProps({
  pipelineState: { type: Object, required: true },
  phases: { type: Array, required: true },
  logs: { type: Array, required: true },
  getPhaseStyle: { type: Function, required: true },
  showPostDedup: { type: Boolean, default: false },
})

const logContainer = ref(null)

// 日志新增时自动滚动到底部
watch(() => props.logs.length, () => {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
})

const summaryStats = computed(() => [
  { label: 'Spans', value: props.pipelineState.phases[1].spanCount },
  { label: 'Bundles', value: props.pipelineState.phases[2].bundleCount },
  { label: 'L1/L2/L3', value: props.pipelineState.phases[3].l123Count },
  { label: 'L4', value: props.pipelineState.phases[4].l4Count },
])
</script>

<style scoped>
.result-panel {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 4px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.result-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
  background: rgba(28, 40, 52, 0.02);
}

.result-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
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
  color: var(--ink-700);
}

.notice-box.success {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  font-size: 13px;
  border-radius: 4px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #15803d;
}

.stat-card {
  text-align: center;
  padding: 8px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(34, 197, 94, 0.2);
}

.stat-label {
  font-size: 10px;
  color: rgba(28, 40, 52, 0.6);
  text-transform: uppercase;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #15803d;
}

/* Jama pill (may be defined globally, keep as fallback) */
.jama-pill {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(28, 40, 52, 0.06);
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 12px;
  font-size: 11px;
  color: rgba(28, 40, 52, 0.7);
}

/* Icon size utilities */
.w-4 { width: 16px !important; height: 16px !important; }
.w-5 { width: 20px !important; height: 20px !important; }

.animate-spin { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(28, 40, 52, 0.02); }
::-webkit-scrollbar-thumb { background: rgba(28, 40, 52, 0.1); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(28, 40, 52, 0.2); }
</style>
