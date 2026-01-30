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
            <span class="nav-title">项目管理 · 需求分析</span>
          </div>
          <div class="nav-center">
            <span class="jama-pill">追溯 · 冲突 · 分类 一键分析</span>
          </div>
          <div class="page-actions">
            <span class="nav-text">分析进度</span>
          </div>
        </section>

        <!-- 主内容区 -->
        <section class="analysis-container" data-animate style="--delay: 0.1s">
          <div class="analysis-layout">
            <!-- 左侧面板：输入和控制 -->
            <div class="control-panel">
              <!-- Session ID 输入 -->
              <div class="control-section">
                <label class="control-label">Session ID</label>
                <input
                  v-model="sessionId"
                  type="text"
                  class="control-input"
                  placeholder="Phase 1 ingest_transcript 返回的 session_id"
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
                    @click="loadContextRuns"
                  >
                    <RefreshCw class="w-3 h-3" :class="isLoadingRuns ? 'animate-spin' : ''" />
                    刷新
                  </button>
                </div>
                <select v-model="contextRunId" class="control-select">
                  <option value="">（可选：graph 策略需要）</option>
                  <option v-for="run in contextRuns" :key="run.context_run_id" :value="run.context_run_id">
                    {{ run.context_run_id.slice(0, 8) }}... · {{ run.session_id?.slice(0, 8) || 'N/A' }}... · {{ run.status }}
                  </option>
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
                <div v-if="traceResult" class="stat-row">
                  <span>追溯关系</span>
                  <span class="stat-value highlight">{{ traceResult.statistics?.relations_found || 0 }}</span>
                </div>
                <div v-if="conflictStats" class="stat-row">
                  <span>冲突对数</span>
                  <span class="stat-value" :class="conflictStats.conflicts > 0 ? 'danger' : 'success'">
                    {{ conflictStats.conflicts }} / {{ conflictStats.total }}
                  </span>
                </div>
                <div v-if="classificationResult" class="stat-row">
                  <span>已分类</span>
                  <span class="stat-value success">{{ classificationResult.total }}</span>
                </div>
              </div>

              <!-- 一键分析按钮 -->
              <button
                type="button"
                class="analysis-btn"
                :disabled="!canAnalyze || isAnalyzing"
                @click="runFullAnalysis"
              >
                <Loader2 v-if="isAnalyzing" class="btn-icon animate-spin" />
                <BarChart3 v-else class="btn-icon" />
                <span>{{ isAnalyzing ? '分析中...' : '一键分析 (追溯→冲突→分类)' }}</span>
              </button>

              <!-- 分析进度 -->
              <div v-if="isAnalyzing || analysisStep === 4" class="progress-panel">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :class="progressColorClass"
                    :style="{ width: `${analysisPercent}%` }"
                  ></div>
                </div>
                <div class="progress-steps">
                  <div class="step" :class="{ active: analysisStep >= 1, done: analysisStep > 1 }">
                    <span class="step-dot">{{ analysisStep > 1 ? '✓' : '1' }}</span>
                    <span>L4生成</span>
                  </div>
                  <div class="step" :class="{ active: analysisStep >= 2, done: analysisStep > 2 }">
                    <span class="step-dot">{{ analysisStep > 2 ? '✓' : '2' }}</span>
                    <span>追溯</span>
                  </div>
                  <div class="step" :class="{ active: analysisStep >= 3, done: analysisStep > 3 }">
                    <span class="step-dot">{{ analysisStep > 3 ? '✓' : '3' }}</span>
                    <span>冲突</span>
                  </div>
                  <div class="step" :class="{ active: analysisStep >= 4, done: analysisStep > 4 }">
                    <span class="step-dot">{{ analysisStep > 4 ? '✓' : '4' }}</span>
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

            <!-- 右侧面板：结果展示 -->
            <div class="result-panel">
              <!-- Tab 切换 -->
              <div class="result-tabs">
                <button
                  type="button"
                  class="result-tab"
                  :class="{ active: activeTab === 'network' }"
                  @click="activeTab = 'network'"
                >
                  <Network class="tab-icon" />
                  追溯图
                </button>
                <button
                  type="button"
                  class="result-tab"
                  :class="{ active: activeTab === 'conflict' }"
                  @click="activeTab = 'conflict'"
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
                  @click="activeTab = 'classification'"
                >
                  <Tags class="tab-icon" />
                  分类
                </button>
              </div>

              <!-- 结果内容 -->
              <div class="result-content">
                <!-- 追溯网络 -->
                <div v-show="activeTab === 'network'" class="tab-content">
                  <div v-if="!traceResult" class="empty-result">
                    <Network class="empty-icon" />
                    <p>点击「一键分析」生成追溯网络</p>
                  </div>
                  <div v-else ref="chartContainer" class="chart-container"></div>
                </div>

                <!-- 冲突检测 -->
                <div v-show="activeTab === 'conflict'" class="tab-content">
                  <div v-if="!conflictResults.length" class="empty-result">
                    <AlertTriangle class="empty-icon" />
                    <p>点击「一键分析」检测需求冲突</p>
                  </div>
                  <div v-else class="conflict-list">
                    <!-- 冲突统计 -->
                    <div class="conflict-summary">
                      <div class="summary-item">
                        <span class="summary-label">检测对数</span>
                        <span class="summary-value">{{ conflictStats?.total || 0 }}</span>
                      </div>
                      <div class="summary-item danger">
                        <AlertCircle class="summary-icon" />
                        <span class="summary-label">冲突</span>
                        <span class="summary-value">{{ conflictStats?.conflicts || 0 }}</span>
                      </div>
                      <div class="summary-item success">
                        <CheckCircle2 class="summary-icon" />
                        <span class="summary-label">兼容</span>
                        <span class="summary-value">{{ conflictStats?.compatible || 0 }}</span>
                      </div>
                    </div>
                    <!-- 冲突列表 -->
                    <div
                      v-for="(item, idx) in conflictResults"
                      :key="idx"
                      class="conflict-item"
                      :class="{ 'is-conflict': item.is_conflict }"
                    >
                      <div class="conflict-badge" :class="item.is_conflict ? 'danger' : 'success'">
                        {{ item.is_conflict ? '冲突' : '兼容' }}
                      </div>
                      <div class="conflict-content">
                        <div class="conflict-pair">
                          <div class="conflict-req">
                            <span class="req-label">需求 A</span>
                            <p>{{ item.reqA?.statement || item.reqA?.text }}</p>
                          </div>
                          <div class="conflict-req">
                            <span class="req-label">需求 B</span>
                            <p>{{ item.reqB?.statement || item.reqB?.text }}</p>
                          </div>
                        </div>
                        <div class="conflict-analysis">
                          <span class="analysis-label">分析结果：</span>
                          {{ item.raw_response }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 需求分类 -->
                <div v-show="activeTab === 'classification'" class="tab-content">
                  <div v-if="!classificationResult" class="empty-result">
                    <Tags class="empty-icon" />
                    <p>点击「一键分析」进行需求分类</p>
                  </div>
                  <div v-else class="classification-result">
                    <!-- 分类统计 -->
                    <div class="classification-summary">
                      <div class="summary-item">
                        <BarChart3 class="summary-icon" />
                        <span class="summary-label">总计</span>
                        <span class="summary-value">{{ classificationResult.total }}</span>
                      </div>
                      <div
                        v-for="([label, count]) in Object.entries(classificationResult.label_distribution || {})"
                        :key="label"
                        class="summary-item"
                        :class="getLabelClass(label)"
                      >
                        <span class="label-dot" :class="getLabelDotClass(label)"></span>
                        <span class="summary-label">{{ label }}</span>
                        <span class="summary-value">{{ count }}</span>
                      </div>
                    </div>
                    <!-- 分类列表 -->
                    <div class="classification-groups">
                      <div
                        v-for="([label, items]) in classificationGroups"
                        :key="label"
                        class="classification-group"
                      >
                        <div class="group-header" :class="getLabelHeaderClass(label)">
                          <span class="group-title">{{ label }}</span>
                          <span class="group-count" :class="getLabelBadgeClass(label)">{{ items.length }}</span>
                        </div>
                        <div class="group-items">
                          <div
                            v-for="pred in items"
                            :key="pred.index"
                            class="group-item"
                          >
                            <p>{{ pred.requirement }}</p>
                          </div>
                        </div>
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
import { ref, computed, watch, onMounted, nextTick } from "vue";
import { useRouter, useRoute } from "vue-router";
import Sidebar from "../../components/main/Sidebar.vue";
import {
  traceabilityApi,
  conflictApi,
  classifyTexts,
  analysisApi,
  requirementsL123Api,
  getLatestClassification,
  l4RequirementsApi
} from "../../utils/api";
import * as echarts from "echarts";
import {
  Loader2,
  RefreshCw,
  BarChart3,
  Network,
  AlertTriangle,
  Tags,
  AlertCircle,
  CheckCircle2
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
};

const pageKeyToRouteName = {
  "dashboard": "main-dashboard",
  "project-management": "main-project",
  "requirements": "main-requirements",
  "requirements-analysis": "main-requirements-analysis",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "requirements-analysis");

// Session 和 Context Run
const sessionId = ref(localStorage.getItem('lastSessionId') || '');
const contextRunId = ref('');
const contextRuns = ref([]);
const isLoadingRuns = ref(false);

// 当 sessionId 变化时保存到 localStorage 并广播事件
watch(sessionId, (newVal) => {
  if (newVal && newVal.trim()) {
    localStorage.setItem('lastSessionId', newVal.trim());
    // 广播事件通知其他组件
    window.dispatchEvent(new CustomEvent('session-changed', { detail: { sessionId: newVal.trim() } }));
  }
});

// 需求数据
const highLevelRequirements = ref([]);
const lowLevelRequirements = ref([]);

// 分析状态
const isAnalyzing = ref(false);
const analysisStep = ref(0); // 0: 未开始, 1: 生成L4, 2: 追溯, 3: 冲突检测, 4: 分类, 5: 完成
const analysisError = ref(null);
const analysisNotice = ref('');
const l4GenerationProgress = ref({ current: 0, total: 0 }); // L4生成进度

// 分析结果
const traceResult = ref(null);
const conflictResults = ref([]);
const classificationResult = ref(null);
const conflictProgress = ref({ current: 0, total: 0 });

// 视图状态
const activeTab = ref('network');
const chartContainer = ref(null);
let chart = null;

// 计算属性
const allHighLevelRequirements = computed(() => {
  return highLevelRequirements.value.map((req, idx) => {
    const level = normalizeLevel(req.level || req.category);
    return {
      ...req,
      id: req.req_id || req.id || `${level}-${idx}`,
      category: level,
      level,
      statement: req.text || req.statement || '',
    };
  });
});

const canAnalyze = computed(() => {
  return sessionId.value.trim().length > 0;
});

const conflictStats = computed(() => {
  if (!conflictResults.value.length) return null;
  const conflicts = conflictResults.value.filter((r) => r.is_conflict);
  return {
    total: conflictResults.value.length,
    conflicts: conflicts.length,
    compatible: conflictResults.value.length - conflicts.length
  };
});

const classificationGroups = computed(() => {
  if (!classificationResult.value?.predictions) return [];
  const groups = {};
  classificationResult.value.predictions.forEach((pred) => {
    const label = pred.predicted_label || '未分类';
    if (!groups[label]) groups[label] = [];
    groups[label].push(pred);
  });
  return Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
});

const analysisPercent = computed(() => {
  if (analysisStep.value === 0) return 0;
  if (analysisStep.value === 5) return 100;
  // 5 个步骤: L4生成(20%), 追溯(20%), 冲突检测(30%), 分类(20%), 完成(10%)
  const stepPercents = [0, 20, 40, 70, 90, 100];
  const basePercent = stepPercents[analysisStep.value - 1] || 0;
  const stepWidth = (stepPercents[analysisStep.value] || 100) - basePercent;
  
  if (analysisStep.value === 1 && l4GenerationProgress.value.total > 0) {
    return basePercent + Math.round((l4GenerationProgress.value.current / l4GenerationProgress.value.total) * stepWidth);
  }
  if (analysisStep.value === 3 && conflictProgress.value.total > 0) {
    return basePercent + Math.round((conflictProgress.value.current / conflictProgress.value.total) * stepWidth);
  }
  return basePercent + Math.round(stepWidth / 2);
});

const analysisStepText = computed(() => {
  switch (analysisStep.value) {
    case 1: return l4GenerationProgress.value.total > 0 
      ? `正在生成底层需求 (${l4GenerationProgress.value.current}/${l4GenerationProgress.value.total})...` 
      : '正在生成底层需求...';
    case 2: return '正在进行追溯分析...';
    case 3: return `正在进行冲突检测 (${conflictProgress.value.current}/${conflictProgress.value.total})...`;
    case 4: return '正在进行需求分类...';
    case 5: return '分析完成!';
    default: return '';
  }
});

const progressColorClass = computed(() => {
  switch (analysisStep.value) {
    case 1: return 'color-l4gen';
    case 2: return 'color-trace';
    case 3: return 'color-conflict';
    case 4: return 'color-classify';
    case 5: return 'color-complete';
    default: return '';
  }
});

// 辅助函数
function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase();
  if (!text) return 'L1';
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1';
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2';
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3';
  return 'L1';
}

function getLabelClass(label) {
  const styles = {
    '功能性需求': 'func',
    '非功能性需求': 'nonfunc'
  };
  return styles[label] || '';
}

function getLabelDotClass(label) {
  const styles = {
    '功能性需求': 'dot-func',
    '非功能性需求': 'dot-nonfunc'
  };
  return styles[label] || 'dot-default';
}

function getLabelHeaderClass(label) {
  const styles = {
    '功能性需求': 'header-func',
    '非功能性需求': 'header-nonfunc'
  };
  return styles[label] || '';
}

function getLabelBadgeClass(label) {
  const styles = {
    '功能性需求': 'badge-func',
    '非功能性需求': 'badge-nonfunc'
  };
  return styles[label] || '';
}

function getRelationTypeColor(type) {
  const colors = {
    'implementation': '#22c55e',
    'support': '#3b82f6',
    'dependency': '#ef4444',
    'decomposition': '#f59e0b',
    'general': '#6b7280'
  };
  return colors[type] || '#6b7280';
}

function getCategoryColor(category) {
  const colors = {
    L1: '#0ea5e9',
    L2: '#71717a',
    L3: '#f59e0b',
    low: '#10b981'
  };
  return colors[category] || '#6b7280';
}

function getCategoryBorderColor(category) {
  const colors = {
    L1: '#1d4ed8',
    L2: '#6d28d9',
    L3: '#d97706',
    low: '#047857'
  };
  return colors[category] || '#374151';
}

// 数据加载
async function loadContextRuns() {
  isLoadingRuns.value = true;
  try {
    const runs = await analysisApi.listContextRuns(sessionId.value.trim());
    contextRuns.value = Array.isArray(runs) ? runs : [];
  } catch {
    contextRuns.value = [];
  } finally {
    isLoadingRuns.value = false;
  }
}

async function loadRequirements() {
  if (!sessionId.value.trim()) return;
  
  try {
    const data = await requirementsL123Api.listBySession(sessionId.value.trim(), { page: 1, perPage: 200 });
    highLevelRequirements.value = (data.requirements || []).map((req) => ({
      ...req,
      level: normalizeLevel(req.level || req.category),
    }));
    
    try {
      const l4Data = await l4RequirementsApi.getBySession(sessionId.value.trim(), { perPage: 500 });
      lowLevelRequirements.value = (l4Data.requirements || []).map(r => ({
        ...r,
        level: 'L4',
        statement: r.text || r.shall_statement || '',
      }));
    } catch {
      lowLevelRequirements.value = [];
    }
  } catch (err) {
    console.error('加载需求失败:', err);
  }
}

// 一键分析（包含 L4 生成）
async function runFullAnalysis() {
  if (!canAnalyze.value) return;
  
  isAnalyzing.value = true;
  analysisError.value = null;
  analysisNotice.value = '';
  analysisStep.value = 1;
  l4GenerationProgress.value = { current: 0, total: 0 };
  conflictProgress.value = { current: 0, total: 0 };
  
  const currentSessionId = sessionId.value.trim();
  localStorage.setItem('lastSessionId', currentSessionId);
  
  try {
    // 先加载高层需求数据 (L1-L3)
    const l123Data = await requirementsL123Api.listBySession(currentSessionId, { page: 1, perPage: 500 });
    highLevelRequirements.value = (l123Data.requirements || []).map((req) => ({
      ...req,
      level: normalizeLevel(req.level || req.category),
    }));
    
    if (highLevelRequirements.value.length === 0) {
      throw new Error('未找到顶层需求，请先在需求分析流程中抽取需求');
    }
    
    // Step 1: 生成 L4 底层需求
    analysisNotice.value = '正在基于顶层需求生成底层需求...';
    l4GenerationProgress.value = { current: 0, total: highLevelRequirements.value.length };
    
    // 准备顶层需求数据用于 L4 生成
    const reqsForL4 = highLevelRequirements.value.map(req => ({
      id: req.req_id || req.id,
      text: req.text || req.statement || ''
    }));
    
    try {
      // 调用 L4 生成 API
      const l4Response = await l4RequirementsApi.generate(
        currentSessionId,
        reqsForL4,
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
          forceRegenerate: false // 如果已有缓存，直接使用
        }
      );
      
      // 处理 L4 结果
      const l4Reqs = l4Response.requirements || [];
      lowLevelRequirements.value = l4Reqs.map((r, idx) => ({
        ...r,
        id: r.req_id || r.id || `l4_${idx}`,
        level: 'L4',
        statement: r.text || r.shall_statement || '',
        text: r.text || r.shall_statement || '',
      }));
      
      l4GenerationProgress.value = { current: l4Reqs.length, total: l4Reqs.length };
      analysisNotice.value = `已生成 ${l4Reqs.length} 条底层需求`;
    } catch (l4Err) {
      console.warn('L4 生成失败，尝试加载已有数据:', l4Err);
      // 如果 L4 生成失败，尝试加载已有的 L4 数据
      try {
        const existingL4 = await l4RequirementsApi.getBySession(currentSessionId, { perPage: 500 });
        lowLevelRequirements.value = (existingL4.requirements || []).map(r => ({
          ...r,
          level: 'L4',
          statement: r.text || r.shall_statement || '',
        }));
        if (lowLevelRequirements.value.length > 0) {
          analysisNotice.value = `使用已有的 ${lowLevelRequirements.value.length} 条底层需求`;
        }
      } catch {
        lowLevelRequirements.value = [];
      }
    }
    
    // Step 2: 追溯分析
    analysisStep.value = 2;
    traceResult.value = null;
    analysisNotice.value = '';
    
    const highReqs = allHighLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim());
    const lowReqs = lowLevelRequirements.value
      .map((r) => r.statement || r.text || '')
      .filter((s) => s && s.trim());
    
    if (highReqs.length > 0 && lowReqs.length > 0) {
      const mappingResult = await traceabilityApi.traceByMapping(currentSessionId, true, 800);
      traceResult.value = mappingResult.data;
    }
    
    // Step 3: 冲突检测
    analysisStep.value = 3;
    conflictResults.value = [];
    
    const allReqs = [
      ...allHighLevelRequirements.value.map((r) => ({ ...r, type: 'high' })),
      ...lowLevelRequirements.value.map((r) => ({ ...r, type: 'low' }))
    ];
    
    if (allReqs.length >= 2 && traceResult.value?.relations) {
      const pairs = [];
      traceResult.value.relations.forEach((rel) => {
        if (rel.has_relation) {
          const highReq = allHighLevelRequirements.value[rel.high_level_index];
          const lowReq = lowLevelRequirements.value[rel.low_level_index];
          if (highReq && lowReq) {
            pairs.push({ reqA: highReq, reqB: lowReq });
          }
        }
      });
      
      const pairsToCheck = pairs.slice(0, 10);
      conflictProgress.value = { current: 0, total: pairsToCheck.length };
      
      for (const { reqA, reqB } of pairsToCheck) {
        try {
          const res = await conflictApi.check(
            reqA.statement || reqA.text || '',
            reqB.statement || reqB.text || '',
            true,
            currentSessionId
          );
          conflictResults.value.push({ reqA, reqB, ...(res.data || res) });
        } catch {
          // 忽略单个失败
        }
        conflictProgress.value.current++;
      }
    }
    
    // Step 4: 需求分类
    analysisStep.value = 4;
    classificationResult.value = null;
    
    const classifyReqs = [...allHighLevelRequirements.value, ...lowLevelRequirements.value];
    if (classifyReqs.length > 0) {
      const requirements = classifyReqs.map((r) => r.statement || r.text || '');
      const response = await classifyTexts({ requirements }, true, currentSessionId);
      const data = response.data;
      
      classificationResult.value = {
        predictions: data.predictions.map((pred, idx) => ({
          ...pred,
          originalReq: classifyReqs[idx]
        })),
        label_distribution: data.label_distribution,
        total: data.total
      };
    }
    
    analysisStep.value = 5;
    activeTab.value = 'network';
    
    // 广播分析完成事件，通知其他视图刷新
    window.dispatchEvent(new CustomEvent('analysis-completed', { 
      detail: { 
        sessionId: currentSessionId,
        hasTrace: !!traceResult.value,
        hasConflict: conflictResults.value.length > 0,
        hasClassification: !!classificationResult.value,
        l4Count: lowLevelRequirements.value.length
      } 
    }));
    
    await nextTick();
    updateChart();
    
  } catch (err) {
    analysisError.value = err?.response?.data?.error || err?.response?.data?.detail || err.message || '分析失败';
  } finally {
    isAnalyzing.value = false;
  }
}

// 图表
function initChart() {
  if (!chartContainer.value) return;
  if (chart) {
    chart.dispose();
  }
  chart = echarts.init(chartContainer.value);
  updateChart();
}

function updateChart() {
  if (!chart) return;
  
  if (!traceResult.value) {
    chart.setOption({
      title: {
        text: '追溯网络',
        subtext: '完成分析后显示追溯关系图',
        left: 'center',
        top: 'center',
        textStyle: { color: 'rgba(28, 40, 52, 0.4)', fontSize: 16 },
        subtextStyle: { color: 'rgba(28, 40, 52, 0.3)', fontSize: 12 }
      }
    }, true);
    return;
  }
  
  const highNodes = allHighLevelRequirements.value;
  const lowNodes = lowLevelRequirements.value;
  
  const containerWidth = chartContainer.value?.clientWidth || 800;
  const containerHeight = chartContainer.value?.clientHeight || 500;
  
  const leftX = containerWidth * 0.18;
  const rightX = containerWidth * 0.82;
  const topPadding = 80;
  const bottomPadding = 60;
  const availableHeight = containerHeight - topPadding - bottomPadding;
  
  const categories = [
    { name: 'L1 业务需求', itemStyle: { color: '#3b82f6' } },
    { name: 'L2 利益相关者需求', itemStyle: { color: '#8b5cf6' } },
    { name: 'L3 系统需求', itemStyle: { color: '#f59e0b' } },
    { name: '底层需求', itemStyle: { color: '#10b981' } }
  ];
  
  const categoryMap = { L1: 0, L2: 1, L3: 2, low: 3 };
  
  const leftSpacing = highNodes.length > 1 ? availableHeight / (highNodes.length - 1) : 0;
  const nodes = highNodes.map((req, idx) => {
    const level = normalizeLevel(req.category || req.level);
    return {
      id: req.req_id || req.id || `high_${idx}`,
      name: (req.statement || '').slice(0, 25) + ((req.statement || '').length > 25 ? '...' : ''),
      x: leftX,
      y: topPadding + (highNodes.length === 1 ? availableHeight / 2 : idx * leftSpacing),
      category: categoryMap[level] ?? 0,
      symbol: 'roundRect',
      symbolSize: [180, 28],
      itemStyle: {
        color: getCategoryColor(level),
        borderColor: getCategoryBorderColor(level),
        borderWidth: 2,
        borderRadius: 0
      },
      label: {
        show: true,
        position: 'inside',
        fontSize: 10,
        color: '#fff',
        fontWeight: 500,
      }
    };
  });
  
  const rightSpacing = lowNodes.length > 1 ? availableHeight / (lowNodes.length - 1) : 0;
  lowNodes.forEach((req, idx) => {
    nodes.push({
      id: req.req_id || req.id || `low_${idx}`,
      name: (req.statement || '').slice(0, 25) + ((req.statement || '').length > 25 ? '...' : ''),
      x: rightX,
      y: topPadding + (lowNodes.length === 1 ? availableHeight / 2 : idx * rightSpacing),
      category: 3,
      symbol: 'roundRect',
      symbolSize: [180, 28],
      itemStyle: {
        color: '#10b981',
        borderColor: '#047857',
        borderWidth: 2,
        borderRadius: 0
      },
      label: {
        show: true,
        position: 'inside',
        fontSize: 10,
        color: '#fff',
        fontWeight: 500,
      }
    });
  });
  
  const links = [];
  if (traceResult.value?.relations) {
    traceResult.value.relations.forEach((rel, idx) => {
      if (!rel.has_relation) return;
      const sourceId = rel.high_req_id;
      const targetId = rel.low_req_id;
      if (!sourceId || !targetId) return;
      links.push({
        source: sourceId,
        target: targetId,
        lineStyle: {
          color: getRelationTypeColor(rel.relation_type),
          width: 1.5,
          curveness: ((idx % 5) - 2) * 0.05,
          opacity: 0.7
        }
      });
    });
  }
  
  chart.setOption({
    title: {
      text: '需求追溯关系图',
      subtext: `左侧: ${highNodes.length} 个顶层需求 ─→ 右侧: ${lowNodes.length} 个底层需求`,
      left: 'center',
      top: 8,
      textStyle: { fontSize: 14, fontWeight: 'bold', color: 'var(--ink-950)' },
      subtextStyle: { fontSize: 11, color: 'rgba(28, 40, 52, 0.5)' }
    },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: 'rgba(28, 40, 52, 0.1)',
      borderWidth: 1,
      textStyle: { color: 'var(--ink-950)' }
    },
    legend: {
      bottom: 8,
      left: 'center',
      data: categories.map((c) => c.name),
      textStyle: { fontSize: 11 }
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      categories: categories,
      data: nodes,
      links: links,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      lineStyle: { opacity: 0.7 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, opacity: 0.95 }
      }
    }]
  }, true);
}

// 导航
function handleNavigate(page) {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
}

function handleExit() {
  router.push({ name: "main-login" });
}

// 监听
watch(activeTab, (val) => {
  if (val === 'network') {
    nextTick(() => initChart());
  }
});

watch(traceResult, () => {
  if (activeTab.value === 'network' && chart) {
    updateChart();
  }
}, { deep: true });

// 加载已有的分析结果（追溯、冲突、分类）
async function loadExistingResults() {
  if (!sessionId.value.trim()) return;
  
  const sid = sessionId.value.trim();
  
  try {
    // 加载追溯结果
    const traceData = await analysisApi.getLatestTrace(sid);
    if (traceData && traceData.relations) {
      traceResult.value = traceData;
    }
  } catch {
    // 无缓存数据，忽略
  }
  
  try {
    // 加载冲突检测结果
    const conflictData = await conflictApi.getLatest(sid);
    if (conflictData?.data?.results) {
      conflictResults.value = conflictData.data.results.map(r => ({
        reqA: { statement: r.requirement_a },
        reqB: { statement: r.requirement_b },
        is_conflict: r.is_conflict,
        raw_response: r.raw_response
      }));
    }
  } catch {
    // 无缓存数据，忽略
  }
  
  try {
    // 加载分类结果
    const classData = await getLatestClassification(sid);
    if (classData?.predictions) {
      classificationResult.value = {
        predictions: classData.predictions,
        label_distribution: classData.label_distribution,
        total: classData.total
      };
    }
  } catch {
    // 无缓存数据，忽略
  }
}

onMounted(async () => {
  if (sessionId.value) {
    await Promise.all([
      loadContextRuns(),
      loadRequirements(),
      loadExistingResults()
    ]);
    
    // 如果有追溯结果，初始化图表
    if (traceResult.value && activeTab.value === 'network') {
      await nextTick();
      initChart();
    }
  }
});
</script>

<style scoped>
/* 分析容器 */
.analysis-container {
  flex: 1;
  overflow: hidden;
}

.analysis-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 24px;
  height: calc(100vh - 180px);
}

/* 左侧控制面板 */
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  padding: 20px;
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

/* 右侧结果面板 */
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
  padding: 12px 16px;
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

.tab-content {
  height: 100%;
  overflow-y: auto;
}

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: rgba(28, 40, 52, 0.4);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.3;
}

.chart-container {
  width: 100%;
  height: 100%;
  min-height: 500px;
}

/* 冲突列表 */
.conflict-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.conflict-summary {
  display: flex;
  gap: 16px;
  padding: 12px;
  background: rgba(28, 40, 52, 0.04);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.summary-item.danger { color: #ef4444; }
.summary-item.success { color: #22c55e; }

.summary-icon {
  width: 14px;
  height: 14px;
}

.summary-label {
  color: rgba(28, 40, 52, 0.6);
}

.summary-value {
  font-weight: 600;
  color: var(--ink-950);
}

.conflict-item {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.conflict-item.is-conflict {
  background: rgba(239, 68, 68, 0.04);
  border-color: rgba(239, 68, 68, 0.2);
}

.conflict-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  align-self: flex-start;
}

.conflict-badge.danger { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
.conflict-badge.success { background: rgba(34, 197, 94, 0.15); color: #15803d; }

.conflict-content {
  flex: 1;
  min-width: 0;
}

.conflict-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 10px;
}

.conflict-req {
  padding: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.08);
}

.req-label {
  font-size: 10px;
  color: rgba(28, 40, 52, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.conflict-req p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ink-950);
}

.conflict-analysis {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.7);
  padding: 10px;
  background: rgba(28, 40, 52, 0.04);
}

.analysis-label {
  font-weight: 500;
  color: var(--ink-950);
}

/* 分类结果 */
.classification-result {
  padding: 16px;
}

.classification-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  background: rgba(28, 40, 52, 0.04);
  border: 1px solid rgba(28, 40, 52, 0.08);
  margin-bottom: 16px;
}

.label-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-func { background: #3b82f6; }
.dot-nonfunc { background: #8b5cf6; }
.dot-default { background: #6b7280; }

.classification-groups {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.classification-group {
  border: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(255, 255, 255, 0.95);
  overflow: hidden;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.header-func { background: rgba(59, 130, 246, 0.08); }
.header-nonfunc { background: rgba(139, 92, 246, 0.08); }

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-950);
}

.group-count {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
}

.badge-func { background: rgba(59, 130, 246, 0.15); color: #2563eb; }
.badge-nonfunc { background: rgba(139, 92, 246, 0.15); color: #7c3aed; }

.group-items {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-item {
  padding: 10px;
  background: rgba(28, 40, 52, 0.03);
  border: 1px solid rgba(28, 40, 52, 0.06);
}

.group-item p {
  margin: 0;
  font-size: 12px;
  color: var(--ink-950);
  line-height: 1.5;
}
</style>

