<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="roleType"
        :roleLabel="roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <!-- 页面头部 -->
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 需求采集</span>
          </div>
          <div class="nav-center">
            <span class="jama-pill">转录文本 → 需求入库 一键处理</span>
          </div>
          <div class="page-actions">
            <span class="nav-text">自动化流程</span>
          </div>
        </section>

        <!-- 主内容区 -->
        <section class="analysis-container" data-animate style="--delay: 0.1s">
          <div class="analysis-layout">
            <!-- 左侧面板：输入和控制 -->
            <div class="control-panel">
              <!-- Session ID 输入 -->
              <div class="control-section">
                <label class="control-label">Session ID（可空）</label>
                <input
                  v-model="sessionId"
                  type="text"
                  class="control-input"
                  placeholder="留空则后端自动生成"
                />
              </div>

              <!-- 转录文本输入 -->
              <div class="control-section" style="flex: 1; min-height: 200px;">
                <div class="control-header">
                  <label class="control-label">会议转录文本</label>
                  <button
                    type="button"
                    class="refresh-btn"
                    :disabled="isSampleLoading"
                    @click="loadSampleTranscript"
                  >
                    <FileDown class="w-3 h-3" />
                    {{ isSampleLoading ? '加载中...' : '加载示例' }}
                  </button>
                </div>
                <textarea
                  v-model="transcriptText"
                  class="control-input"
                  style="flex: 1; min-height: 180px; resize: none; line-height: 1.6;"
                  placeholder="粘贴会议转写文本（支持 [start-end] speaker text 或 speaker: text）"
                ></textarea>
              </div>

              <!-- 高级选项折叠 -->
              <div class="stats-panel" style="padding: 0;">
                <button
                  type="button"
                  class="stat-row"
                  style="width: 100%; cursor: pointer; border: none; background: transparent;"
                  @click="showAdvanced = !showAdvanced"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    <Settings class="w-4 h-4" />
                    高级选项
                  </span>
                  <ChevronDown class="w-4 h-4" :style="{ transform: showAdvanced ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }" />
                </button>
                <div v-if="showAdvanced" style="padding: 12px; border-top: 1px solid rgba(28, 40, 52, 0.08);">
                  <div class="stat-row">
                    <span>窗口大小</span>
                    <input v-model.number="options.window_size" type="number" min="5" max="10" class="control-input" style="width: 80px; padding: 4px 8px;" />
                  </div>
                  <div class="stat-row">
                    <span>步长</span>
                    <input v-model.number="options.step_size" type="number" min="1" :max="options.window_size - 1" class="control-input" style="width: 80px; padding: 4px 8px;" />
                  </div>
                  <div class="stat-row">
                    <span>置信度阈值</span>
                    <input v-model.number="options.tau" type="number" min="0" max="1" step="0.05" class="control-input" style="width: 80px; padding: 4px 8px;" />
                  </div>
                  <div class="stat-row">
                    <span>Mock 模式</span>
                    <input v-model="options.mock_llm" type="checkbox" style="width: 16px; height: 16px;" />
                  </div>
                </div>
              </div>

              <!-- 开始采集按钮 -->
              <button
                type="button"
                class="analysis-btn"
                :disabled="!canStart || pipelineState.status === 'running'"
                @click="runPipeline"
              >
                <Loader2 v-if="pipelineState.status === 'running'" class="btn-icon animate-spin" />
                <Sparkles v-else class="btn-icon" />
                <span>{{ pipelineState.status === 'running' ? '采集中...' : '开始采集' }}</span>
              </button>

              <!-- 错误信息 -->
              <div v-if="pipelineState.error" class="notice-box error">
                <AlertCircle class="notice-icon" />
                <div style="flex: 1;">
                  {{ pipelineState.error }}
                  <button
                    v-if="pipelineState.currentPhase > 1"
                    type="button"
                    class="refresh-btn"
                    style="margin-top: 8px; width: 100%;"
                    @click="retryFromCurrentPhase"
                  >
                    从此步骤重试
                  </button>
                </div>
              </div>

              <!-- 完成信息 -->
              <div v-if="pipelineState.status === 'completed'" class="notice-box success">
                <CheckCircle2 class="notice-icon" />
                <div style="flex: 1; display: flex; align-items: center; justify-content: space-between;">
                  <span>需求采集完成！</span>
                  <button type="button" class="refresh-btn" @click="goToRequirements">
                    查看需求 →
                  </button>
                </div>
              </div>
            </div>

            <!-- 右侧面板：进度指示器 -->
            <div class="result-panel">
              <!-- 标题 -->
              <div class="result-tabs" style="justify-content: flex-start; gap: 8px;">
                <Zap class="w-5 h-5" style="color: var(--accent);" />
                <span style="font-weight: 600; color: var(--ink-950);">采集进度</span>
              </div>

              <!-- 进度步骤 -->
              <div class="result-content" style="padding: 20px;">
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
                  <div ref="logContainer" style="height: 200px; overflow-y: auto; padding: 12px; font-family: 'SF Mono', 'Monaco', monospace; font-size: 11px; line-height: 1.6; background: rgba(28, 40, 52, 0.02);">
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
                      <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.8); border: 1px solid rgba(34, 197, 94, 0.2);">
                        <div style="font-size: 10px; color: rgba(28, 40, 52, 0.6); text-transform: uppercase;">Spans</div>
                        <div style="font-size: 18px; font-weight: 600; color: #15803d;">{{ pipelineState.phases[1].spanCount }}</div>
                      </div>
                      <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.8); border: 1px solid rgba(34, 197, 94, 0.2);">
                        <div style="font-size: 10px; color: rgba(28, 40, 52, 0.6); text-transform: uppercase;">Bundles</div>
                        <div style="font-size: 18px; font-weight: 600; color: #15803d;">{{ pipelineState.phases[2].bundleCount }}</div>
                      </div>
                      <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.8); border: 1px solid rgba(34, 197, 94, 0.2);">
                        <div style="font-size: 10px; color: rgba(28, 40, 52, 0.6); text-transform: uppercase;">L1/L2/L3</div>
                        <div style="font-size: 18px; font-weight: 600; color: #15803d;">{{ pipelineState.phases[3].l123Count }}</div>
                      </div>
                      <div style="text-align: center; padding: 8px; background: rgba(255,255,255,0.8); border: 1px solid rgba(34, 197, 94, 0.2);">
                        <div style="font-size: 10px; color: rgba(28, 40, 52, 0.6); text-transform: uppercase;">L4</div>
                        <div style="font-size: 18px; font-weight: 600; color: #15803d;">{{ pipelineState.phases[4].l4Count }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, reactive } from "vue";
import { useRouter, useRoute } from "vue-router";
import Sidebar from "../../components/main/Sidebar.vue";
import { requirementsL123Api, l4RequirementsApi } from "../../utils/api";
import {
  Loader2,
  Sparkles,
  FileDown,
  Settings,
  ChevronDown,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Zap,
  FileText
} from "lucide-vue-next";

const router = useRouter();
const route = useRoute();

// 侧边栏状态
const roleType = ref("unified_admin");
const roleLabel = ref("管理员");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);

const routeNameToPageKey = {
  "main-dashboard": "dashboard",
  "main-project": "project-management",
  "main-requirements": "requirements",
  "main-requirements-analysis": "requirements-analysis",
  "main-requirements-collection": "requirements-collection",
};

const pageKeyToRouteName = {
  "dashboard": "main-dashboard",
  "project-management": "main-project",
  "requirements": "main-requirements",
  "requirements-analysis": "main-requirements-analysis",
  "requirements-collection": "main-requirements-collection",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "requirements-collection");

// 输入状态
const sessionId = ref('');
const transcriptText = ref('');
const isSampleLoading = ref(false);
const showAdvanced = ref(false);
const logContainer = ref(null);

// 高级选项
const options = reactive({
  window_size: 8,
  step_size: 7,
  tau: 0.6,
  top_k: 3,
  token_limit_per_bundle: 4000,
  mock_llm: false,
  enable_parallel_windows: false,
  max_concurrent_windows: 5
});

// 流程状态
const pipelineState = reactive({
  status: 'idle',
  currentPhase: 0,
  phases: {
    1: { status: 'pending', sessionId: null, spanCount: 0 },
    2: { status: 'pending', contextRunId: null, bundleCount: 0 },
    3: { status: 'pending', l123Count: 0 },
    4: { status: 'pending', l4Count: 0 }
  },
  error: null
});

// 日志
const logs = ref([]);

// 阶段配置
const phases = [
  { title: '文本解析', desc: '解析转录文本，提取对话片段' },
  { title: '上下文构建', desc: '构建语义关联图，生成 Bundles' },
  { title: '需求抽取', desc: '从 Bundles 中抽取 L1/L2/L3 需求' },
  { title: '底层生成', desc: '基于顶层需求生成 L4 软件需求' }
];

// 计算属性
const canStart = computed(() => {
  return transcriptText.value.trim().length > 0;
});

// 辅助函数
function getPhaseStyle(phaseNum) {
  const status = pipelineState.phases[phaseNum].status;
  if (status === 'running') {
    return { background: 'rgba(196, 105, 47, 0.08)', borderColor: 'rgba(196, 105, 47, 0.3)' };
  }
  if (status === 'completed') {
    return { background: 'rgba(34, 197, 94, 0.06)', borderColor: 'rgba(34, 197, 94, 0.2)' };
  }
  if (status === 'error') {
    return { background: 'rgba(239, 68, 68, 0.06)', borderColor: 'rgba(239, 68, 68, 0.2)' };
  }
  return {};
}

function addLog(phase, message, type = 'info') {
  const now = new Date();
  const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
  logs.value.push({ time, phase, message, type });

  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight;
    }
  });
}

function resetPipelineState() {
  pipelineState.status = 'idle';
  pipelineState.currentPhase = 0;
  pipelineState.error = null;
  pipelineState.phases[1] = { status: 'pending', sessionId: null, spanCount: 0 };
  pipelineState.phases[2] = { status: 'pending', contextRunId: null, bundleCount: 0 };
  pipelineState.phases[3] = { status: 'pending', l123Count: 0 };
  pipelineState.phases[4] = { status: 'pending', l4Count: 0 };
  logs.value = [];
}

// 加载示例文本
async function loadSampleTranscript() {
  if (isSampleLoading.value) return;
  isSampleLoading.value = true;

  try {
    const response = await fetch('/api/analysis/sample_transcript', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`加载示例失败: HTTP ${response.status}`);
    }
    const text = await response.text();
    if (!text.trim()) {
      throw new Error('示例文件为空');
    }
    transcriptText.value = text;
    addLog('系统', '已加载示例文本', 'success');
  } catch (err) {
    addLog('系统', err.message || '加载示例失败', 'error');
  } finally {
    isSampleLoading.value = false;
  }
}

// Phase 1: 文本解析
async function runPhase1() {
  pipelineState.phases[1].status = 'running';
  pipelineState.currentPhase = 1;
  addLog('Phase 1', '开始解析转录文本...');

  const payload = {
    transcript_text: transcriptText.value,
    options: {
      estimate_timestamps_if_missing: true,
      default_span_ms: 8000,
      max_spans_returned: 200
    }
  };
  if (sessionId.value.trim()) {
    payload.session_id = sessionId.value.trim();
  }

  const response = await fetch('/api/analysis/ingest_transcript/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let gotFinal = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let splitIndex = buffer.indexOf('\n\n');
    while (splitIndex !== -1) {
      const rawEvent = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);
      splitIndex = buffer.indexOf('\n\n');

      const lines = rawEvent.split('\n');
      const dataLines = lines.filter((line) => line.startsWith('data:'));
      const dataStr = dataLines.map((line) => line.slice(5).trim()).join('');
      if (!dataStr) continue;

      try {
        const eventData = JSON.parse(dataStr);

        if (eventData.event === 'init') {
          if (eventData.session_id) {
            pipelineState.phases[1].sessionId = eventData.session_id;
          }
          addLog('Phase 1', `接收 ${eventData.received_chars || 0} 字符, ${eventData.received_lines || 0} 行`);
        } else if (eventData.event === 'parsed') {
          addLog('Phase 1', `解析完成: ${eventData.span_total || 0} 个 spans`);
        } else if (eventData.event === 'db_upserted') {
          addLog('Phase 1', `入库: ${eventData.upserted_count || 0} 条记录`);
        } else if (eventData.event === 'final') {
          const data = eventData.data || {};
          if (data.session_id) {
            pipelineState.phases[1].sessionId = data.session_id;
          }
          pipelineState.phases[1].spanCount = data.span_total || 0;
          gotFinal = true;
          addLog('Phase 1', `完成！Session: ${data.session_id?.slice(0, 8)}..., ${data.span_total} spans`, 'success');
          await reader.cancel();
          break;
        }
      } catch {
        // 忽略解析错误
      }
    }
    if (gotFinal) break;
  }

  if (!gotFinal) {
    throw new Error('Phase 1 流结束但未收到 final 事件');
  }

  pipelineState.phases[1].status = 'completed';
}

// Phase 2: 上下文构建
async function runPhase2() {
  pipelineState.phases[2].status = 'running';
  pipelineState.currentPhase = 2;
  addLog('Phase 2', '开始构建上下文...');

  const payload = {
    session_id: pipelineState.phases[1].sessionId,
    options: {
      window_size: options.window_size,
      step_size: options.step_size,
      tau: options.tau,
      top_k: options.top_k,
      token_limit_per_bundle: options.token_limit_per_bundle,
      mock_llm: options.mock_llm,
      enable_parallel_windows: options.enable_parallel_windows,
      max_concurrent_windows: options.max_concurrent_windows,
      llm_model: 'deepseek-chat'
    }
  };

  const response = await fetch('/api/analysis/build_context/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let gotFinal = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const eventData = JSON.parse(line.slice(6));

          if (eventData.event === 'init') {
            addLog('Phase 2', `初始化: ${eventData.span_total} spans`);
          } else if (eventData.event === 'window_start') {
            addLog('Phase 2', `处理窗口 #${eventData.window_index}`);
          } else if (eventData.event === 'window_complete') {
            addLog('Phase 2', `窗口 #${eventData.window_index} 完成: ${eventData.kept_edge_count} 边`);
          } else if (eventData.event === 'bundling_done') {
            addLog('Phase 2', `打包完成: ${eventData.bundle_total} bundles`);
          } else if (eventData.event === 'final') {
            pipelineState.phases[2].contextRunId = eventData.context_run_id;
            pipelineState.phases[2].bundleCount = eventData.bundle_total || 0;
            gotFinal = true;
            addLog('Phase 2', `完成！${eventData.bundle_total} bundles, ${eventData.edge_count} edges`, 'success');
          } else if (eventData.event === 'error') {
            throw new Error(eventData.message);
          }
        } catch (e) {
          if (e.message && !e.message.includes('JSON')) {
            throw e;
          }
        }
      }
    }
  }

  if (!gotFinal) {
    throw new Error('Phase 2 流结束但未收到 final 事件');
  }

  pipelineState.phases[2].status = 'completed';
}

// Phase 3: 需求抽取
async function runPhase3() {
  pipelineState.phases[3].status = 'running';
  pipelineState.currentPhase = 3;
  addLog('Phase 3', '开始抽取 L1/L2/L3 需求...');

  const payload = {
    session_id: pipelineState.phases[1].sessionId,
    context_run_id: pipelineState.phases[2].contextRunId,
    bundle_strategy: 'graph',
    anchor_strategy: 'informative',
    r: 2,
    adaptive_retry_r2: true,
    model: 'deepseek-chat',
    use_toolcall: true,
    max_spans_per_bundle: 12,
    token_limit: 1500,
    top_m_2hop: 5,
    keywords: ['要', '需要', '必须', '应该', '决定', '改成', '提升', '优化', '实现']
  };

  const result = await requirementsL123Api.extract(payload);

  pipelineState.phases[3].l123Count = result.total_inserted || 0;
  addLog('Phase 3', `完成！抽取 ${result.total_inserted} 条需求，处理 ${result.bundles_processed} 个 bundles`, 'success');

  pipelineState.phases[3].status = 'completed';
}

// Phase 4: 底层需求生成
async function runPhase4() {
  pipelineState.phases[4].status = 'running';
  pipelineState.currentPhase = 4;
  addLog('Phase 4', '开始生成 L4 底层需求...');

  const l123Data = await requirementsL123Api.listBySession(
    pipelineState.phases[1].sessionId,
    { page: 1, perPage: 500 }
  );
  const requirements = (l123Data.requirements || []).map(req => ({
    id: req.req_id || req.id,
    text: req.text || req.statement || ''
  }));

  if (requirements.length === 0) {
    addLog('Phase 4', '没有找到顶层需求，跳过 L4 生成', 'warning');
    pipelineState.phases[4].l4Count = 0;
    pipelineState.phases[4].status = 'completed';
    return;
  }

  addLog('Phase 4', `基于 ${requirements.length} 条顶层需求生成 L4...`);

  const l4Response = await l4RequirementsApi.generate(
    pipelineState.phases[1].sessionId,
    requirements,
    {
      config: {
        top_k_pattern: 5,
        top_k_spec: 3,
        top_k_nfr: 3,
        max_l4_per_top_req: 5,
        min_l4_per_top_req: 1,
        confidence_threshold: 0.6
      },
      model: 'deepseek-chat',
      forceRegenerate: false
    }
  );

  const l4Reqs = l4Response.requirements || [];
  pipelineState.phases[4].l4Count = l4Reqs.length;
  addLog('Phase 4', `完成！生成 ${l4Reqs.length} 条 L4 需求`, 'success');

  pipelineState.phases[4].status = 'completed';
}

// 主流程
async function runPipeline() {
  resetPipelineState();
  pipelineState.status = 'running';
  addLog('系统', '开始需求采集流程...');

  try {
    await runPhase1();
    await runPhase2();
    await runPhase3();
    await runPhase4();

    pipelineState.status = 'completed';
    addLog('系统', '需求采集流程完成！', 'success');

    if (pipelineState.phases[1].sessionId) {
      localStorage.setItem('lastSessionId', pipelineState.phases[1].sessionId);

      window.dispatchEvent(new CustomEvent('collection-completed', {
        detail: {
          sessionId: pipelineState.phases[1].sessionId,
          spanCount: pipelineState.phases[1].spanCount,
          bundleCount: pipelineState.phases[2].bundleCount,
          l123Count: pipelineState.phases[3].l123Count,
          l4Count: pipelineState.phases[4].l4Count
        }
      }));
    }

  } catch (err) {
    pipelineState.status = 'error';
    pipelineState.error = err.message || '采集失败';
    pipelineState.phases[pipelineState.currentPhase].status = 'error';
    addLog(`Phase ${pipelineState.currentPhase}`, err.message || '执行失败', 'error');
  }
}

// 从当前步骤重试
async function retryFromCurrentPhase() {
  const startPhase = pipelineState.currentPhase;
  pipelineState.status = 'running';
  pipelineState.error = null;
  addLog('系统', `从 Phase ${startPhase} 重试...`);

  try {
    if (startPhase <= 2) {
      pipelineState.phases[2].status = 'pending';
      await runPhase2();
    }
    if (startPhase <= 3) {
      pipelineState.phases[3].status = 'pending';
      await runPhase3();
    }
    if (startPhase <= 4) {
      pipelineState.phases[4].status = 'pending';
      await runPhase4();
    }

    pipelineState.status = 'completed';
    addLog('系统', '重试完成！', 'success');

  } catch (err) {
    pipelineState.status = 'error';
    pipelineState.error = err.message || '重试失败';
    pipelineState.phases[pipelineState.currentPhase].status = 'error';
    addLog(`Phase ${pipelineState.currentPhase}`, err.message || '执行失败', 'error');
  }
}

// 跳转到需求页面
function goToRequirements() {
  router.push({ name: 'main-requirements' });
}

// 导航处理
function handleNavigate(page) {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
}

function handleExit() {
  router.push({ name: "main-login" });
}
</script>

<style scoped>
/* 分析容器 */
.analysis-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.analysis-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  flex: 1;
  min-height: 0; /* Important for nested scrolling */
}

/* 左侧控制面板 */
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  padding: 24px;
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

/* 统计/高级选项面板 */
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

/* 采集按钮 */
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

.analysis-btn:active:not(:disabled) {
  transform: translateY(0);
}

.analysis-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  filter: grayscale(0.5);
}

/* 提示框 */
.notice-box {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  font-size: 13px;
  border-radius: 4px;
  line-height: 1.5;
}

.notice-box.success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #15803d;
}

.notice-box.error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #b91c1c;
}

.notice-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* 右侧结果面板 */
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
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
  background: rgba(28, 40, 52, 0.02);
}

.result-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* 宽高度工具类兼容 */
.w-3 { width: 12px !important; height: 12px !important; }
.w-4 { width: 16px !important; height: 16px !important; }
.w-5 { width: 20px !important; height: 20px !important; }
.h-3 { height: 12px !important; }
.h-4 { height: 16px !important; }
.h-5 { height: 20px !important; }

.btn-icon {
  width: 20px;
  height: 20px;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 优化原生滚动条 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: rgba(28, 40, 52, 0.02);
}

::-webkit-scrollbar-thumb {
  background: rgba(28, 40, 52, 0.1);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(28, 40, 52, 0.2);
}
</style>
