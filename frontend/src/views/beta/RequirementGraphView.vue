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
      <main class="canvas graph-canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.04s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 需求图谱</span>
          </div>
          <div class="graph-toolbar">
            <select v-model="selectedProjectId" class="project-select sa-input" :disabled="isLoadingProjects">
              <option value="">选择项目</option>
              <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
                {{ project.name }}
              </option>
            </select>
            <input
              v-model.trim="sessionId"
              class="session-input sa-input"
              placeholder="Session ID"
              spellcheck="false"
            />
            <select
              v-model="selectedSnapshotId"
              class="project-select snapshot-select sa-input"
              :disabled="isLoadingGraph || isInferringGraph || (!selectedProjectId && !sessionId)"
              @focus="refreshSnapshotHistory"
              @change="handleSnapshotSelection"
            >
              <option value="">{{ isLoadingSnapshots ? '快照加载中' : '历史快照' }}</option>
              <option v-for="snapshot in snapshotHistory" :key="snapshot.snapshot_id" :value="snapshot.snapshot_id">
                {{ formatSnapshotOption(snapshot) }}
              </option>
            </select>
            <select v-model="packageSize" class="project-select package-select sa-input" :disabled="isInferringGraph">
              <option v-for="option in packageSizeOptions" :key="option" :value="String(option)">
                每包 {{ option }}
              </option>
            </select>
            <select v-model="reviewConcurrency" class="project-select review-select sa-input" :disabled="isInferringGraph">
              <option v-for="option in reviewConcurrencyOptions" :key="option" :value="String(option)">
                并发 {{ option }}
              </option>
            </select>
            <select v-model="selectedModel" class="project-select review-select sa-input" :disabled="isInferringGraph">
              <option value="deepseek-v4-pro">V4 Pro</option>
              <option value="deepseek-flash">V4.1 Flash</option>
            </select>
            <label class="graph-toggle">
              <input v-model="useThinkingMode" type="checkbox" />
              <span>思考</span>
            </label>
            <button
              type="button"
              class="action-btn infer-btn sa-button sa-button--primary"
              :disabled="isLoadingGraph || isInferringGraph || (!selectedProjectId && !sessionId)"
              @click="generateRequirementGraph"
            >
              {{ isInferringGraph && activeGraphStreamMode === 'review' ? '生成中' : '生成图谱' }}
            </button>
            <button
              type="button"
              class="action-btn discover-btn sa-button sa-button--primary"
              :disabled="isLoadingGraph || isInferringGraph || (!selectedProjectId && !sessionId)"
              @click="discoverRequirementRelations"
            >
              {{ isInferringGraph && activeGraphStreamMode === 'discover' ? '发现中' : 'DeepSeek 发现关系' }}
            </button>
            <button
              type="button"
              class="action-btn danger-btn sa-button sa-button--danger"
              :disabled="isLoadingGraph || isInferringGraph || (!selectedProjectId && !sessionId)"
              @click="deleteAllRelations"
            >
              删除补充关系
            </button>
          </div>
        </section>

        <section class="graph-shell" data-animate style="--delay: 0.08s">
          <aside class="graph-side">
            <div class="metric-grid">
              <div class="metric-item">
                <span>需求节点</span>
                <strong>{{ stats.node_counts?.requirement || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>关系边</span>
                <strong>{{ stats.edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>结构关系</span>
                <strong>{{ stats.structural_edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>已有分析结果</span>
                <strong>{{ stats.analysis_edge_count || 0 }}</strong>
              </div>
              <div class="metric-item">
                <span>补充关系</span>
                <strong>{{ stats.supplemental_edge_count || 0 }}</strong>
              </div>
            </div>

            <div class="legend-block">
              <div class="block-title-row">
                <h3>层级分布</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedLevel === '__all__' }"
                  @click="selectLevel('__all__')"
                >
                  全部
                </button>
              </div>
              <div class="source-badge-row">
                <span class="source-badge">统一主源 · manage_requirements</span>
                <span class="source-badge subtle">已有分析 · 追溯 / 冲突 / 分类</span>
                <span class="source-badge subtle">补充关系 · 本地向量 / DeepSeek</span>
              </div>
              <div v-if="levelLegend.length" class="category-list">
                <button
                  v-for="item in levelLegend"
                  :key="item.label"
                  type="button"
                  class="category-chip"
                  :class="{ active: selectedLevel === item.label }"
                  @click="selectLevel(item.label)"
                >
                  <span class="category-dot" :style="{ background: item.color }"></span>
                  <span class="category-name">{{ item.label }}</span>
                  <b>{{ item.count }}</b>
                </button>
              </div>
              <p v-else class="detail-empty">当前项目暂无需求层级数据。</p>
              <p v-if="levelLegend.length" class="legend-hint">
                点击层级聚焦对应需求及其相邻关系。
              </p>
            </div>

            <div class="legend-block">
              <div class="block-title-row">
                <h3>分类筛选</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedCategory === '__all__' }"
                  @click="selectCategory('__all__')"
                >
                  全部
                </button>
              </div>
              <div v-if="categoryLegend.length" class="category-list">
                <button
                  v-for="item in categoryLegend"
                  :key="item.label"
                  type="button"
                  class="category-chip"
                  :class="{ active: selectedCategory === item.label }"
                  @click="selectCategory(item.label)"
                >
                  <span class="category-dot" :style="{ background: item.color }"></span>
                  <span class="category-name">{{ item.label }}</span>
                  <b>{{ item.count }}</b>
                </button>
              </div>
              <p v-else class="detail-empty">当前项目暂无分类结果。</p>
              <p v-if="categoryLegend.length" class="legend-hint">
                点击分类聚焦对应需求及其相邻关系。
              </p>
            </div>

            <div class="legend-block compact-block">
              <div class="block-title-row">
                <h3>关系类型</h3>
                <button
                  type="button"
                  class="clear-filter"
                  :class="{ active: selectedEdgeType === '__all__' }"
                  @click="selectEdgeType('__all__')"
                >
                  全部
                </button>
              </div>
              <button
                v-for="edge in edgeLegend"
                :key="edge.type"
                type="button"
                class="legend-row legend-button"
                :class="{ active: selectedEdgeType === edge.type }"
                @click="selectEdgeType(edge.type)"
              >
                <span class="legend-line" :style="{ background: edge.color }"></span>
                <span>{{ edge.label }}</span>
                <b>{{ stats.edge_counts?.[edge.type] || 0 }}</b>
              </button>
            </div>

            <div class="legend-block compact-block">
              <div class="block-title-row">
                <h3>关系筛选</h3>
                <button type="button" class="clear-filter" @click="resetEdgeFilters">
                  重置
                </button>
              </div>
              <div class="filter-row">
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === '__all__' }"
                  @click="selectSourceScope('__all__')"
                >
                  全部来源
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === 'structural' }"
                  @click="selectSourceScope('structural')"
                >
                  仅结构
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === '__analysis__' }"
                  @click="selectSourceScope('__analysis__')"
                >
                  仅已有分析
                </button>
                <button
                  type="button"
                  class="filter-chip"
                  :class="{ active: selectedSourceScope === '__extra__' }"
                  @click="selectSourceScope('__extra__')"
                >
                  仅补充关系
                </button>
              </div>
              <p class="legend-hint">来源分为结构、已有分析结果、本地向量召回与 DeepSeek 判断，内部依据只在详情里弱展示。</p>
            </div>

            <div v-if="relationReviewSummary" class="legend-block compact-block">
              <div class="block-title-row">
                <h3>{{ relationReviewSummary.discovery_mode ? '发现进度' : '判断进度' }}</h3>
                <span class="analysis-chip emphasis">{{ relationReviewSummary.model || '未命名模型' }}</span>
              </div>
              <div class="metric-grid">
                <div v-if="relationReviewSummary.discovery_mode" class="metric-item">
                  <span>已处理顶层包</span>
                  <strong>{{ relationReviewSummary.completed_packages || 0 }} / {{ relationReviewSummary.total_packages || relationReviewSummary.package_count || 0 }}</strong>
                </div>
                <div v-else class="metric-item">
                  <span>已判断</span>
                  <strong>{{ relationReviewSummary.completed_pairs || 0 }} / {{ relationReviewSummary.total_pairs || relationReviewSummary.reviewed_pair_count || 0 }}</strong>
                </div>
                <div class="metric-item">
                  <span>{{ relationReviewSummary.discovery_mode ? '已发现关系' : '已确认' }}</span>
                  <strong>{{ relationReviewSummary.discovery_mode ? (relationReviewSummary.added_edges || relationReviewSummary.added_count || 0) : ((relationReviewSummary.added_count || 0) + (relationReviewSummary.updated_count || 0)) }}</strong>
                </div>
                <div v-if="relationReviewSummary.discovery_mode" class="metric-item">
                  <span>已跳过包</span>
                  <strong>{{ relationReviewSummary.skipped_packages || relationReviewSummary.skipped_package_count || 0 }}</strong>
                </div>
                <div v-else class="metric-item">
                  <span>已排除</span>
                  <strong>{{ (relationReviewSummary.deleted_count || 0) + (relationReviewSummary.rejected_count || 0) }}</strong>
                </div>
                <div class="metric-item">
                  <span>并发</span>
                  <strong>{{ relationReviewSummary.applied_concurrency || relationReviewSummary.requested_concurrency || 0 }}</strong>
                </div>
              </div>
            </div>

            <div v-if="localVectorSummary" class="legend-block compact-block">
              <div class="block-title-row">
                <h3>向量产出</h3>
                <span class="analysis-chip">{{ localVectorSummary.model || '本地模型' }}</span>
              </div>
              <div class="metric-grid">
                <div class="metric-item">
                  <span>候选对</span>
                  <strong>{{ localVectorSummary.candidate_pair_count || 0 }}</strong>
                </div>
                <div class="metric-item">
                  <span>入图对</span>
                  <strong>{{ localVectorSummary.reviewed_pair_count || 0 }}</strong>
                </div>
                <div class="metric-item">
                  <span>新增边</span>
                  <strong>{{ localVectorSummary.added_count || 0 }}</strong>
                </div>
              </div>
            </div>

            <div class="detail-block">
              <h3>{{ selectedEdge ? '关系详情' : selectedNode ? '节点详情' : '图谱读取' }}</h3>
              <template v-if="selectedEdge">
                <div class="detail-title">{{ edgeLabel(selectedEdge.type) }}</div>
                <p class="detail-kind">
                  {{ resolveNodeLabel(selectedEdge.source) }} → {{ resolveNodeLabel(selectedEdge.target) }}
                </p>
                <dl>
                  <div v-for="item in selectedEdgeDetails" :key="item.key" class="detail-pair">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </div>
                </dl>
                <details v-if="selectedEdgeInternalDetails.length" class="evidence-panel">
                  <summary>查看内部依据</summary>
                  <dl>
                    <div v-for="item in selectedEdgeInternalDetails" :key="item.key" class="detail-pair">
                      <dt>{{ item.label }}</dt>
                      <dd>{{ item.value }}</dd>
                    </div>
                  </dl>
                </details>
              </template>
              <template v-else-if="selectedNode">
                <div class="detail-title">{{ selectedNode.label }}</div>
                <p class="detail-kind">
                  需求 · {{ levelLabel(normalizeLevel(selectedNode)) }}
                  <template v-if="selectedNode.properties?.category">
                    · {{ selectedNode.properties.category }}
                  </template>
                </p>
                <dl>
                  <div v-for="item in selectedNodeDetails" :key="item.key" class="detail-pair">
                    <dt>{{ item.label }}</dt>
                    <dd>{{ item.value }}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  class="detail-action-btn"
                  :disabled="!selectedNode?.properties?.req_id"
                  @click="openAnalysisDrawer"
                >
                  发起变更分析
                </button>
              </template>
              <p v-else class="detail-empty">
                点击图中的节点或关系，查看层级、关系类型、来源范围和简短依据。
              </p>
            </div>
          </aside>

          <div class="graph-stage" :class="{ 'with-analysis': isAnalysisDrawerOpen }">
            <div v-if="graphError" class="state-panel error-state">{{ graphError }}</div>
            <div v-else-if="!hasGraph && !isLoadingGraph" class="state-panel">
              选择项目后点击“生成图谱”或“DeepSeek 发现关系”，图谱会按流式结果更新。
            </div>
            <div v-else-if="isLoadingGraph" class="state-panel">
              正在生成本地向量关系图谱。
            </div>
            <div v-else-if="isInferringGraph" class="state-panel">
              <template v-if="activeGraphStreamMode === 'discover'">
                正在调用 DeepSeek 主动发现关系：{{ streamProgress.completed_packages }} / {{ streamProgress.total_packages || 0 }}
              </template>
              <template v-else>
                正在调用 DeepSeek 对候选关系做判断：{{ streamProgress.completed_pairs }} / {{ streamProgress.total_pairs || 0 }}
              </template>
            </div>
            <div ref="chartContainer" class="graph-chart"></div>
            <aside v-if="isAnalysisDrawerOpen" class="analysis-drawer">
              <div class="analysis-drawer-header">
                <div>
                  <h3>单需求变更分析</h3>
                  <p>{{ analysisDraft.before.title || selectedNode?.label || '未命名需求' }}</p>
                </div>
                <button type="button" class="clear-filter" @click="closeAnalysisDrawer">关闭</button>
              </div>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>变更输入</h4>
                  <button
                    type="button"
                    class="action-btn analysis-submit-btn sa-button sa-button--primary"
                    :disabled="analysisLoading"
                    @click="submitAnalysis"
                  >
                    {{ analysisLoading ? '分析中' : '开始分析' }}
                  </button>
                </div>
                <div class="analysis-form">
                  <label class="analysis-field">
                    <span>标题</span>
                    <input v-model="analysisDraft.title" type="text" class="analysis-input" />
                  </label>
                  <label class="analysis-field">
                    <span>描述</span>
                    <textarea v-model="analysisDraft.description" class="analysis-textarea"></textarea>
                  </label>
                  <label class="analysis-field">
                    <span>标签</span>
                    <input
                      v-model="analysisDraft.tagsInput"
                      type="text"
                      class="analysis-input"
                      placeholder="用逗号分隔多个标签"
                    />
                  </label>
                  <div class="analysis-inline-fields">
                    <label class="analysis-field">
                      <span>优先级</span>
                      <select v-model="analysisDraft.priority" class="analysis-input">
                        <option value="">未设置</option>
                        <option v-for="option in priorityOptions" :key="option.value" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </label>
                    <label class="analysis-field">
                      <span>状态</span>
                      <select v-model="analysisDraft.status" class="analysis-input">
                        <option value="">未设置</option>
                        <option v-for="option in requirementStatusOptions" :key="option.value" :value="option.value">
                          {{ option.label }}
                        </option>
                      </select>
                    </label>
                  </div>
                </div>
                <p v-if="analysisError" class="analysis-state error">{{ analysisError }}</p>
              </section>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>变更摘要</h4>
                  <span v-if="analysisChangedFields.length" class="analysis-chip emphasis">
                    {{ analysisChangedFields.length }} 个字段变化
                  </span>
                </div>
                <div v-if="analysisDiffRows.length" class="analysis-diff-list">
                  <article
                    v-for="row in analysisDiffRows"
                    :key="row.field"
                    class="analysis-diff-card"
                    :class="{ changed: row.changed }"
                  >
                    <div class="analysis-diff-header">
                      <strong>{{ row.label }}</strong>
                      <span v-if="row.changed" class="analysis-chip">已变更</span>
                    </div>
                    <div class="analysis-diff-body">
                      <div>
                        <span>Before</span>
                        <p>{{ row.before || '空' }}</p>
                      </div>
                      <div>
                        <span>After</span>
                        <p>{{ row.after || '空' }}</p>
                      </div>
                    </div>
                  </article>
                </div>
              </section>

              <section class="analysis-block">
                <div class="analysis-block-title">
                  <h4>影响结果</h4>
                  <span v-if="analysisResult?.summary" class="analysis-chip">
                    {{ analysisStatusLabel(analysisResult.summary.analysis_status) }}
                  </span>
                </div>
                <p v-if="analysisResult?.summary?.message" class="analysis-state">
                  {{ analysisResult.summary.message }}
                </p>

                <div v-if="analysisSummaryCards.length" class="analysis-summary-grid">
                  <article v-for="item in analysisSummaryCards" :key="item.key" class="analysis-summary-card">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                  </article>
                </div>

                <div
                  v-if="analysisResultStatus === 'completed' && analysisDisplayedImpacts.length"
                  class="analysis-impact-list"
                >
                  <button
                    v-for="item in analysisDisplayedImpacts"
                    :key="item.requirement_id"
                    type="button"
                    class="analysis-impact-item"
                    :class="{ active: analysisFocusedRequirementId === item.requirement_id }"
                    @click="focusAnalysisItem(item.requirement_id)"
                  >
                    <div class="analysis-impact-top">
                      <strong>{{ item.title }}</strong>
                      <span :class="['risk-badge', item.impact_level]">
                        {{ impactLevelLabel(item.impact_level) }}
                      </span>
                    </div>
                    <div class="analysis-impact-meta">
                      <span>{{ item.source_level || 'UNKNOWN_LEVEL' }}</span>
                      <span>{{ item.trigger_relations.join(' / ') }}</span>
                      <span>{{ item.min_distance }} 跳</span>
                    </div>
                    <p>{{ item.short_reason }}</p>
                  </button>
                </div>

                <p
                  v-else-if="analysisResultStatus === 'completed' && !analysisDisplayedImpacts.length && !analysisAdvisories.length"
                  class="analysis-state"
                >
                  本次变更未命中主影响范围。
                </p>

                <div v-if="analysisFocusedPath" class="analysis-path-block">
                  <div class="analysis-subtitle">最短传播路径</div>
                  <div class="analysis-path-chain">
                    <div v-for="(segment, index) in analysisFocusedPath.path" :key="`${segment.source}-${segment.target}-${index}`" class="analysis-path-segment">
                      <span class="segment-node">{{ resolveRequirementTitle(segment.source) }}</span>
                      <span class="segment-arrow">{{ edgeLabel(segment.type) }}</span>
                      <span class="segment-node">{{ resolveRequirementTitle(segment.target) }}</span>
                    </div>
                  </div>
                  <p>{{ analysisFocusedPath.reason }}</p>
                </div>

                <div v-if="analysisAdvisories.length" class="analysis-advisory-block">
                  <div class="analysis-subtitle">建议关注</div>
                  <div class="analysis-advisory-list">
                    <button
                      v-for="item in analysisAdvisories"
                      :key="item.requirement_id"
                      type="button"
                      class="analysis-advisory-item"
                      @click="focusAnalysisItem(item.requirement_id)"
                    >
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.source_level || 'UNKNOWN_LEVEL' }}</span>
                      <p>{{ item.reason }}</p>
                    </button>
                  </div>
                </div>
              </section>
            </aside>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import Sidebar from '../../components/beta/Sidebar.vue'
import { manageApi, requirementChangeApi, requirementGraphApi } from '@/api'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirement-graph')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

const projects = ref([])
const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
const sessionId = ref(localStorage.getItem('lastSessionId') || '')
const packageSize = ref(localStorage.getItem('requirementGraphPackageSize') || '6')
const reviewConcurrency = ref(localStorage.getItem('requirementGraphReviewConcurrency') || '3')
const savedGraphModel = localStorage.getItem('requirementGraphModel')
const selectedModel = ref(
  ['deepseek-v4-pro', 'deepseek-flash'].includes(savedGraphModel) ? savedGraphModel : 'deepseek-v4-pro'
)
if (savedGraphModel && savedGraphModel !== selectedModel.value) {
  localStorage.setItem('requirementGraphModel', selectedModel.value)
}
const useThinkingMode = ref(localStorage.getItem('requirementGraphThinking') !== 'false')
const snapshotHistory = ref([])
const selectedSnapshotId = ref('')
const isLoadingProjects = ref(false)
const isLoadingGraph = ref(false)
const isInferringGraph = ref(false)
const isLoadingSnapshots = ref(false)
const activeGraphStreamMode = ref('')
const graphError = ref('')
const graphData = ref({ nodes: [], edges: [], stats: {} })
const lastLocalReviewEdges = ref([])
const streamProgress = ref(createEmptyStreamProgress())
const selectedNode = ref(null)
const selectedEdge = ref(null)
const selectedLevel = ref('__all__')
const selectedCategory = ref('__all__')
const selectedEdgeType = ref('__all__')
const selectedSourceScope = ref('__all__')
const analysisDraft = ref(createEmptyAnalysisDraft())
const analysisLoading = ref(false)
const analysisResult = ref(null)
const analysisFocusedRequirementId = ref('')
const analysisError = ref('')
const chartContainer = ref(null)
let chart = null
let resizeObserver = null
let graphStreamAbortController = null
const packageSizeOptions = [3, 6, 9, 12]
const reviewConcurrencyOptions = [1, 2, 3, 4, 6]
const protectedRelationSourceKinds = new Set([
  'structural',
  'trace_analysis',
  'conflict_analysis',
  'classification_analysis',
])
const supplementalRelationSourceKinds = new Set(['local_vector', 'rule_extra', 'rule', 'llm'])

function createEmptyStreamProgress() {
  return {
    completed_pairs: 0,
    total_pairs: 0,
    completed_packages: 0,
    total_packages: 0,
    added_edges: 0,
    skipped_packages: 0,
    review_concurrency: 0,
  }
}

const levelPalette = {
  L1: { fill: '#dbeafe', border: '#2563eb' },
  L2: { fill: '#dcfce7', border: '#16a34a' },
  L3: { fill: '#fef3c7', border: '#d97706' },
  L4: { fill: '#fee2e2', border: '#dc2626' },
  UNKNOWN_LEVEL: { fill: '#e2e8f0', border: '#64748b' },
}

const edgeLegend = [
  { type: 'REFINES', label: '细化', color: '#0ea5e9' },
  { type: 'DEPENDS_ON', label: '依赖', color: '#f59e0b' },
  { type: 'CONFLICTS_WITH', label: '冲突', color: '#ef4444' },
  { type: 'SIMILAR_TO', label: '同类相似', color: '#22c55e' },
  { type: 'INCLUDES', label: '包含', color: '#0f766e' },
  { type: 'EXTENDS', label: '扩展', color: '#3b82f6' },
  { type: 'IMPACTS', label: '影响', color: '#14b8a6' },
  { type: 'VALIDATES_WITH', label: '验证关联', color: '#65a30d' },
]
const priorityOptions = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
]
const requirementStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'under_review', label: '评审中' },
  { value: 'confirmed', label: '已确认' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'archived', label: '已归档' },
]

const stats = computed(() => graphData.value?.stats || {})
const hasGraph = computed(() => (graphData.value?.nodes || []).length > 0)
const selectedPackageSize = computed(() => {
  const value = Number(packageSize.value)
  if (!Number.isFinite(value)) return 6
  return Math.max(1, Math.min(24, Math.trunc(value)))
})
const selectedReviewConcurrency = computed(() => {
  const value = Number(reviewConcurrency.value)
  if (!Number.isFinite(value)) return 3
  return Math.max(1, Math.min(8, Math.trunc(value)))
})
const levelCounts = computed(() => stats.value.level_counts || {})
const categoryCounts = computed(() => {
  const distribution = stats.value.classification_label_distribution
  if (distribution && typeof distribution === 'object') return distribution
  const counts = {}
  ;(graphData.value?.nodes || []).forEach(node => {
    const label = String(node?.properties?.category || '').trim()
    if (!label) return
    counts[label] = (counts[label] || 0) + 1
  })
  return counts
})
const relationReviewSummary = computed(() => {
  const summary = {
    ...(stats.value.relation_review || {}),
    completed_pairs: streamProgress.value.completed_pairs,
    total_pairs: streamProgress.value.total_pairs,
    completed_packages: streamProgress.value.completed_packages,
    total_packages: streamProgress.value.total_packages,
    added_edges: streamProgress.value.added_edges,
    skipped_packages: streamProgress.value.skipped_packages,
  }
  if (!summary) return null
  if (!(summary.package_count || summary.reviewed_pair_count || summary.total_pairs || summary.total_packages || summary.added_count || summary.updated_count || summary.deleted_count || summary.rejected_count || summary.added_edges || summary.skipped_packages || summary.fallback_used)) {
    return null
  }
  return summary
})
const localVectorSummary = computed(() => {
  const summary = stats.value.local_vector
  if (!summary) return null
  if (!(summary.enabled || summary.error || summary.candidate_pair_count || summary.reviewed_pair_count || summary.added_count)) return null
  return summary
})
const levelLegend = computed(() =>
  ['L1', 'L2', 'L3', 'L4', 'UNKNOWN_LEVEL']
    .map(label => ({
      label,
      count: levelCounts.value?.[label] || 0,
      color: levelFillColorByLevel(label),
    }))
    .filter(item => item.count > 0),
)
const categoryLegend = computed(() =>
  Object.entries(categoryCounts.value || {})
    .map(([label, count]) => ({
      label,
      count,
      color: categoryColor(label),
    }))
    .filter(item => item.count > 0)
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN')),
)
const isAnalysisDrawerOpen = computed(() => Boolean(analysisDraft.value.requirementId))
const analysisPreview = computed(() => {
  const before = analysisDraft.value.before || createAnalysisSnapshot()
  const after = {
    title: analysisDraft.value.title || '',
    description: analysisDraft.value.description || '',
    tags: normalizeTagInput(analysisDraft.value.tagsInput),
    priority: analysisDraft.value.priority || null,
    status: analysisDraft.value.status || null,
  }
  const changedFields = analysisFieldOrder().filter(field => !analysisValueEquals(before[field], after[field]))
  return { before, after, changedFields }
})
const analysisChangedFields = computed(() => analysisResult.value?.changed_fields || analysisPreview.value.changedFields)
const analysisDiffRows = computed(() =>
  analysisFieldOrder().map(field => ({
    field,
    label: analysisFieldLabel(field),
    before: formatAnalysisFieldValue(field, analysisPreview.value.before[field]),
    after: formatAnalysisFieldValue(field, analysisPreview.value.after[field]),
    changed: analysisChangedFields.value.includes(field),
  })),
)
const analysisResultStatus = computed(() => analysisResult.value?.summary?.analysis_status || '')
const analysisDisplayedImpacts = computed(() => analysisResult.value?.impacted_requirements || [])
const analysisAdvisories = computed(() => analysisResult.value?.advisories?.similar_candidates || [])
const analysisSummaryCards = computed(() => {
  const summary = analysisResult.value?.summary
  if (!summary) return []
  return [
    { key: 'impacted', label: '受影响需求', value: summary.impacted_count || 0 },
    { key: 'high', label: '高风险', value: summary.high_risk_count || 0 },
    { key: 'direct', label: '直接影响', value: summary.direct_count || 0 },
    { key: 'advisory', label: '建议关注', value: summary.advisory_count || 0 },
  ]
})
const analysisFocusedPath = computed(() => {
  const paths = analysisResult.value?.propagation_paths || []
  const fallbackTarget = analysisDisplayedImpacts.value[0]?.requirement_id || ''
  const targetRequirementId = analysisFocusedRequirementId.value || fallbackTarget
  return paths.find(item => item.target_requirement_id === targetRequirementId) || null
})
const analysisImpactLookup = computed(() => Object.fromEntries(
  analysisDisplayedImpacts.value.map(item => [item.requirement_id, item]),
))
const analysisSourceRequirementId = computed(() =>
  analysisResult.value?.source_requirement?.requirement_id || analysisDraft.value.requirementId || '',
)
const analysisImpactedRequirementIds = computed(() => new Set(
  analysisDisplayedImpacts.value.map(item => item.requirement_id),
))
const analysisAdvisoryRequirementIds = computed(() => new Set(
  analysisAdvisories.value.map(item => item.requirement_id),
))
const analysisPathEdgeKeys = computed(() => {
  const keys = new Set()
  ;(analysisResult.value?.propagation_paths || []).forEach(item => {
    ;(item.path || []).forEach(segment => keys.add(analysisEdgeKey(segment)))
  })
  return keys
})
const analysisFocusedEdgeKeys = computed(() => {
  const keys = new Set()
  ;(analysisFocusedPath.value?.path || []).forEach(segment => keys.add(analysisEdgeKey(segment)))
  return keys
})

const selectedNodeDetails = computed(() => {
  const props = selectedNode.value?.properties || {}
  const rows = [
    ['source_level', '层级'],
    ['category', '分类'],
    ['type', '类型'],
    ['status', '状态'],
    ['priority', '优先级'],
    ['assignee', '负责人'],
    ['parent_id', '父需求'],
    ['source_req_id', '来源需求'],
    ['tags', '标签'],
    ['description', '描述'],
    ['custom_fields', '扩展字段'],
  ]
  return rows
    .map(([key, label]) => ({ key, label, value: formatValue(props[key]) }))
    .filter(item => item.value)
})

const selectedEdgeDetails = computed(() => {
  const props = selectedEdge.value?.properties || {}
  const rows = [
    ['type', '关系类型', edgeLabel(selectedEdge.value?.type)],
    ['source_node', '起点', resolveNodeLabel(selectedEdge.value?.source)],
    ['target_node', '终点', resolveNodeLabel(selectedEdge.value?.target)],
    ['source_kind', '来源范围', edgeSourceLabel(selectedEdge.value)],
    ['source_detail', '来源明细', edgeSourceDetailLabel(selectedEdge.value)],
    ['review_action', '复核动作', reviewActionLabel(props.review_action)],
    ['review_package_id', '分包编号', formatValue(props.review_package_id)],
  ]
  return rows
    .map(([key, label, preset]) => ({ key, label, value: preset || '' }))
    .filter(item => item.value)
})

function createAnalysisSnapshot() {
  return {
    title: '',
    description: '',
    tags: [],
    priority: null,
    status: null,
  }
}

function createEmptyAnalysisDraft() {
  return {
    requirementId: '',
    before: createAnalysisSnapshot(),
    title: '',
    description: '',
    tagsInput: '',
    priority: '',
    status: '',
  }
}

function analysisFieldOrder() {
  return ['title', 'description', 'tags', 'priority', 'status']
}

function analysisFieldLabel(field) {
  return {
    title: '标题',
    description: '描述',
    tags: '标签',
    priority: '优先级',
    status: '状态',
  }[field] || field
}

function normalizeTagInput(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  return String(value || '')
    .split(/[，,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function analysisValueEquals(left, right) {
  if (Array.isArray(left) || Array.isArray(right)) {
    return JSON.stringify(left || []) === JSON.stringify(right || [])
  }
  return (left ?? null) === (right ?? null)
}

function formatAnalysisFieldValue(field, value) {
  if (field === 'tags') return (value || []).join('、')
  if (field === 'priority') return priorityLabel(value)
  if (field === 'status') return requirementStatusLabel(value)
  return String(value || '')
}

function buildAnalysisDraftFromNode(node) {
  const props = node?.properties || {}
  return {
    requirementId: props.req_id || '',
    before: {
      title: props.title || node?.label || '',
      description: props.description || '',
      tags: Array.isArray(props.tags) ? props.tags : normalizeTagInput(props.tags),
      priority: props.priority || null,
      status: props.status || null,
    },
    title: props.title || node?.label || '',
    description: props.description || '',
    tagsInput: (Array.isArray(props.tags) ? props.tags : normalizeTagInput(props.tags)).join(', '),
    priority: props.priority || '',
    status: props.status || '',
  }
}

function resetAnalysisState({ closeDrawer = true } = {}) {
  if (closeDrawer) {
    analysisDraft.value = createEmptyAnalysisDraft()
  }
  analysisLoading.value = false
  analysisResult.value = null
  analysisFocusedRequirementId.value = ''
  analysisError.value = ''
}

function clearGraphState() {
  graphError.value = ''
  graphData.value = { nodes: [], edges: [], stats: {} }
  lastLocalReviewEdges.value = []
  streamProgress.value = createEmptyStreamProgress()
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  resetAnalysisState()
  renderGraph()
}

function clearSnapshotHistoryState() {
  snapshotHistory.value = []
  selectedSnapshotId.value = ''
}

function applyGraphPayload(graph, { reviewEdges = null } = {}) {
  graphData.value = normalizeGraphPayload(graph)
  refreshGraphStats()
  lastLocalReviewEdges.value = Array.isArray(reviewEdges) ? reviewEdges : extractLocalReviewEdges(graphData.value)
  selectedSnapshotId.value = graphData.value?.meta?.relation_snapshot?.snapshot_id || ''
  const snapshotMeta = graphData.value?.meta?.relation_snapshot || {}
  if (snapshotMeta.saved === false && snapshotMeta.error) {
    graphError.value = `关系快照保存失败：${snapshotMeta.error}`
  }
}

function normalizeGraphPayload(graph) {
  const payload = graph || { nodes: [], edges: [], stats: {} }
  const nodeMap = new Map()
  ;(payload.nodes || []).forEach(node => {
    const normalized = normalizeGraphNode(node)
    if (!normalized) return
    const existing = nodeMap.get(normalized.id)
    nodeMap.set(normalized.id, existing ? mergeGraphNodePayload(existing, normalized) : normalized)
  })

  const edgeMap = new Map()
  ;(payload.edges || []).forEach(edge => {
    const normalized = normalizeGraphEdge(edge)
    if (!normalized) return
    const existing = edgeMap.get(graphEdgeKey(normalized))
    edgeMap.set(graphEdgeKey(normalized), existing ? mergeGraphEdgePayload(existing, normalized) : normalized)
  })

  return {
    ...payload,
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()).filter(edge => nodeMap.has(edge.source) && nodeMap.has(edge.target)),
    stats: { ...(payload.stats || {}) },
  }
}

function normalizeGraphNode(node) {
  const properties = node.properties && typeof node.properties === 'object' ? node.properties : {}
  const kind = node.kind || 'requirement'
  const id = normalizeGraphNodeId(node?.id || properties.req_id, kind, properties.req_id)
  if (!id) return null
  return {
    ...node,
    id,
    label: node.label || properties.title || properties.text || id,
    kind,
    group: node.group || properties.source_level || properties.level || 'UNKNOWN_LEVEL',
    properties: { ...properties },
  }
}

function normalizeGraphNodeId(value, kind = 'requirement', reqId = '') {
  const raw = String(value || '').trim()
  if (!raw) return ''
  if (raw.startsWith('req:') || raw.startsWith('stakeholder:')) return raw
  if (kind === 'requirement' || reqId) return `req:${raw}`
  return raw
}

function mergeGraphNodePayload(existing, incoming) {
  const existingLevel = normalizeLevel(existing)
  const incomingLevel = normalizeLevel(incoming)
  const useIncomingLevel = existingLevel === 'UNKNOWN_LEVEL' && incomingLevel !== 'UNKNOWN_LEVEL'
  return {
    ...existing,
    ...incoming,
    label: chooseGraphNodeLabel(existing, incoming),
    group: useIncomingLevel ? incoming.group : existing.group || incoming.group,
    properties: {
      ...(existing.properties || {}),
      ...(incoming.properties || {}),
      source_level: useIncomingLevel
        ? incoming.properties?.source_level || incoming.group
        : existing.properties?.source_level || incoming.properties?.source_level,
      level: useIncomingLevel
        ? incoming.properties?.level || incoming.group
        : existing.properties?.level || incoming.properties?.level,
    },
  }
}

function chooseGraphNodeLabel(existing, incoming) {
  const labels = [existing?.label, incoming?.label, incoming?.properties?.title, existing?.properties?.title]
    .map(value => String(value || '').trim())
    .filter(Boolean)
  if (!labels.length) return incoming?.id || existing?.id || ''
  return labels.find(label => label !== incoming?.id && label !== existing?.id) || labels[0]
}

function normalizeGraphEdge(edge) {
  let source = normalizeGraphNodeId(edge?.source)
  let target = normalizeGraphNodeId(edge?.target)
  const type = String(edge?.type || '').trim()
  if (!source || !target || !type || source === target) return null
  if (['CONFLICTS_WITH', 'SIMILAR_TO', 'VALIDATES_WITH'].includes(type) && source > target) {
    ;[source, target] = [target, source]
  }
  const properties = edge.properties && typeof edge.properties === 'object' ? edge.properties : {}
  return {
    ...edge,
    id: edge.id || `${type}:${source}->${target}`,
    source,
    target,
    type,
    label: edge.label || edgeLabel(type),
    weight: typeof edge.weight === 'number' ? edge.weight : Number(edge.weight) || 0,
    properties: { ...properties },
  }
}

function mergeGraphEdgePayload(existing, incoming) {
  const existingProps = existing.properties || {}
  const incomingProps = incoming.properties || {}
  const sourceKinds = uniqueList([
    ...asCompactArray(existingProps.source_kinds),
    existingProps.source_kind,
    ...asCompactArray(incomingProps.source_kinds),
    incomingProps.source_kind,
  ])
  return {
    ...existing,
    ...incoming,
    weight: Math.max(Number(existing.weight) || 0, Number(incoming.weight) || 0),
    properties: {
      ...existingProps,
      ...incomingProps,
      source_kind: incomingProps.source_kind || existingProps.source_kind,
      source_kinds: sourceKinds.length ? sourceKinds : incomingProps.source_kinds || existingProps.source_kinds,
    },
  }
}

function asCompactArray(value) {
  return Array.isArray(value) ? value.filter(Boolean) : []
}

function uniqueList(values) {
  return Array.from(new Set(values.map(value => String(value || '').trim()).filter(Boolean)))
}

function normalizeReviewEdgePayload(edge) {
  if (!edge?.source || !edge?.target || !edge?.type) return null
  const props = edge.properties || {}
  if ((props.source_kind || '').trim() !== 'local_vector') return null
  return {
    source: edge.source,
    target: edge.target,
    type: edge.type,
    weight: typeof edge.weight === 'number' ? edge.weight : Number(edge.weight) || 0,
    properties: {
      source_kind: 'local_vector',
      source_detail: props.source_detail || '',
      confidence: props.confidence,
      reason: props.reason || '',
      evidence: Array.isArray(props.evidence) ? props.evidence : [],
      model: props.model || '',
    },
  }
}

function extractLocalReviewEdges(graph) {
  const rawEdges = graph?.edges || []
  const deduped = new Map()
  rawEdges.forEach(edge => {
    const normalized = normalizeReviewEdgePayload(edge)
    if (!normalized) return
    const key = `${normalized.type}:${normalized.source}->${normalized.target}`
    if (!deduped.has(key)) {
      deduped.set(key, normalized)
    }
  })
  return Array.from(deduped.values())
}

function openAnalysisDrawer() {
  if (!selectedNode.value?.properties?.req_id) return
  selectedLevel.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  analysisDraft.value = buildAnalysisDraftFromNode(selectedNode.value)
  analysisLoading.value = false
  analysisResult.value = null
  analysisFocusedRequirementId.value = analysisDraft.value.requirementId
  analysisError.value = ''
  renderGraph()
}

function closeAnalysisDrawer() {
  resetAnalysisState()
  renderGraph()
}

function buildAnalysisChanges() {
  const { before, after } = analysisPreview.value
  return analysisFieldOrder().reduce((result, field) => {
    if (!analysisValueEquals(before[field], after[field])) {
      result[field] = field === 'tags' ? [...(after[field] || [])] : after[field]
    }
    return result
  }, {})
}

async function submitAnalysis() {
  if (!analysisDraft.value.requirementId) return
  const projectId =
    selectedProjectId.value ||
    selectedNode.value?.properties?.project_id ||
    graphData.value?.nodes?.find(node => node.properties?.req_id === analysisDraft.value.requirementId)?.properties?.project_id
  if (!projectId) {
    analysisError.value = '缺少 project_id，当前无法发起变更分析'
    return
  }
  analysisLoading.value = true
  analysisError.value = ''
  try {
    analysisResult.value = await requirementChangeApi.analyzeRequirementChange({
      projectId,
      requirementId: analysisDraft.value.requirementId,
      changes: buildAnalysisChanges(),
    })
    analysisFocusedRequirementId.value =
      analysisResult.value?.impacted_requirements?.[0]?.requirement_id ||
      analysisResult.value?.source_requirement?.requirement_id ||
      analysisDraft.value.requirementId
    renderGraph()
  } catch (err) {
    analysisResult.value = null
    analysisError.value = err.message || '变更分析失败'
    renderGraph()
  } finally {
    analysisLoading.value = false
  }
}

function focusAnalysisItem(requirementId) {
  analysisFocusedRequirementId.value = requirementId
  const targetNode = graphData.value?.nodes?.find(node => node.properties?.req_id === requirementId)
  if (targetNode) {
    selectedNode.value = targetNode
    selectedEdge.value = null
  }
  renderGraph()
}

const selectedEdgeInternalDetails = computed(() => {
  const props = selectedEdge.value?.properties || {}
  const rows = [
    ['reason', '内部依据', formatValue(props.reason)],
    ['evidence', '触发证据', formatValue(props.evidence)],
    ['confidence', '内部置信度', formatConfidence(props.confidence ?? selectedEdge.value?.weight)],
    ['model', '推理模型', formatValue(props.model)],
    ['review_action', '复核动作', reviewActionLabel(props.review_action)],
    ['review_package_id', '分包编号', formatValue(props.review_package_id)],
  ]
  return rows
    .map(([key, label, preset]) => ({ key, label, value: preset || '' }))
    .filter(item => item.value)
})

async function loadProjects() {
  isLoadingProjects.value = true
  try {
    const data = await manageApi.listProjects()
    projects.value = data?.projects || []
    if (!selectedProjectId.value && projects.value[0]?.project_id) {
      selectedProjectId.value = projects.value[0].project_id
    }
  } catch (err) {
    graphError.value = err.message || '项目列表加载失败'
  } finally {
    isLoadingProjects.value = false
  }
}

async function syncProjectSession() {
  if (!selectedProjectId.value) return
  try {
    const project = await manageApi.getProject(selectedProjectId.value)
    if (project?.current_session_id) {
      sessionId.value = project.current_session_id
    }
  } catch (err) {
    console.warn('加载项目会话失败', err)
  }
}

async function refreshSnapshotHistory() {
  if (!selectedProjectId.value && !sessionId.value) {
    snapshotHistory.value = []
    return []
  }
  isLoadingSnapshots.value = true
  try {
    const resp = await requirementGraphApi.listSnapshotHistory({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 20,
    })
    snapshotHistory.value = resp?.data?.items || []
    return snapshotHistory.value
  } catch (err) {
    snapshotHistory.value = []
    console.warn('加载需求图谱快照历史失败', err)
    return []
  } finally {
    isLoadingSnapshots.value = false
  }
}

async function loadLatestSnapshotGraph() {
  if (!selectedProjectId.value && !sessionId.value) return
  isLoadingGraph.value = true
  graphError.value = ''
  try {
    const resp = await requirementGraphApi.getLatestSnapshot({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 900,
    })
    await refreshSnapshotHistory()
    if (!resp?.data) {
      const latestSnapshot = snapshotHistory.value[0]
      if (latestSnapshot?.snapshot_id) {
        await loadSnapshotGraph(latestSnapshot.snapshot_id)
        return
      }
      clearGraphState()
      return
    }
    applyGraphPayload(resp.data)
    await nextTick()
    renderGraph()
  } catch (err) {
    console.warn('加载最新需求图谱快照失败', err)
    const history = await refreshSnapshotHistory()
    const latestSnapshot = history[0]
    if (latestSnapshot?.snapshot_id) {
      try {
        await loadSnapshotGraph(latestSnapshot.snapshot_id)
        graphError.value = ''
        return
      } catch (_) {
        // ignore snapshot fallback error and surface original empty state below
      }
    }
    clearGraphState()
  } finally {
    isLoadingGraph.value = false
  }
}

async function loadSnapshotGraph(snapshotId) {
  if (!snapshotId) return
  isLoadingGraph.value = true
  graphError.value = ''
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  selectedCategory.value = '__all__'
  resetAnalysisState()
  try {
    const resp = await requirementGraphApi.getSnapshot(snapshotId, { limit: 900 })
    applyGraphPayload(resp?.data)
    await nextTick()
    renderGraph()
  } catch (err) {
    graphError.value = err.message || '历史快照加载失败'
  } finally {
    isLoadingGraph.value = false
  }
}

async function handleSnapshotSelection() {
  if (!selectedSnapshotId.value) return
  await loadSnapshotGraph(selectedSnapshotId.value)
}

async function generateRequirementGraph() {
  graphError.value = ''
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  selectedCategory.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  resetAnalysisState()
  if (!selectedProjectId.value && !sessionId.value) {
    graphError.value = '请选择项目或填写 Session ID'
    return
  }
  if (graphStreamAbortController) graphStreamAbortController.abort()
  graphStreamAbortController = new AbortController()
  graphData.value = { nodes: [], edges: [], stats: {} }
  lastLocalReviewEdges.value = []
  streamProgress.value = createEmptyStreamProgress()
  activeGraphStreamMode.value = 'review'
  isInferringGraph.value = true
  try {
    await requirementGraphApi.streamGraph({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 900,
      inferenceLimit: 48,
      packageSize: selectedPackageSize.value,
      reviewConcurrency: selectedReviewConcurrency.value,
      model: selectedModel.value,
      useThinkingMode: useThinkingMode.value,
      signal: graphStreamAbortController.signal,
      onEvent: handleRequirementGraphStreamEvent,
    })
    await refreshSnapshotHistory()
  } catch (err) {
    if (err.name !== 'AbortError') {
      graphError.value = err.message || '需求图谱生成失败'
    }
  } finally {
    isInferringGraph.value = false
    activeGraphStreamMode.value = ''
    graphStreamAbortController = null
  }
}

async function discoverRequirementRelations() {
  graphError.value = ''
  selectedNode.value = null
  selectedEdge.value = null
  selectedLevel.value = '__all__'
  selectedCategory.value = '__all__'
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  resetAnalysisState()
  if (!selectedProjectId.value && !sessionId.value) {
    graphError.value = '请选择项目或填写 Session ID'
    return
  }
  if (graphStreamAbortController) graphStreamAbortController.abort()
  graphStreamAbortController = new AbortController()
  graphData.value = { nodes: [], edges: [], stats: {} }
  lastLocalReviewEdges.value = []
  streamProgress.value = createEmptyStreamProgress()
  activeGraphStreamMode.value = 'discover'
  isInferringGraph.value = true
  try {
    await requirementGraphApi.streamDiscoverGraph({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
      limit: 900,
      reviewConcurrency: selectedReviewConcurrency.value,
      model: selectedModel.value,
      useThinkingMode: useThinkingMode.value,
      signal: graphStreamAbortController.signal,
      onEvent: handleRequirementGraphStreamEvent,
    })
    await refreshSnapshotHistory()
  } catch (err) {
    if (err.name !== 'AbortError') {
      graphError.value = err.message || 'DeepSeek 发现关系失败'
    }
  } finally {
    isInferringGraph.value = false
    activeGraphStreamMode.value = ''
    graphStreamAbortController = null
  }
}

async function deleteAllRelations() {
  if (!selectedProjectId.value && !sessionId.value) {
    graphError.value = '请选择项目或填写 Session ID'
    return
  }
  const confirmed = window.confirm('确定删除当前项目/Session 的补充关系吗？原有结构和追溯分析关系会保留。')
  if (!confirmed) return

  graphError.value = ''
  isLoadingGraph.value = true
  try {
    await requirementGraphApi.deleteAllRelations({
      projectId: selectedProjectId.value,
      sessionId: sessionId.value,
    })
    graphData.value = {
      ...(graphData.value || { nodes: [], edges: [], stats: {} }),
      edges: (graphData.value?.edges || [])
        .filter(isProtectedRelationEdge)
        .map(preserveProtectedRelationEdge),
      stats: {
        ...(graphData.value?.stats || {}),
        local_vector: null,
        relation_review: null,
      },
    }
    refreshGraphEdgeStats()
    lastLocalReviewEdges.value = []
    streamProgress.value = createEmptyStreamProgress()
    selectedEdge.value = null
    selectedSnapshotId.value = ''
    await refreshSnapshotHistory()
    renderGraph()
  } catch (err) {
    graphError.value = err.message || '删除关系失败'
  } finally {
    isLoadingGraph.value = false
  }
}

function handleRequirementGraphStreamEvent({ event, data }) {
  if (event === 'base_graph') {
    applyGraphPayload(data?.graph || { nodes: [], edges: [], stats: {} }, { reviewEdges: [] })
    renderGraph()
    return
  }
  if (event === 'candidate_edges') {
    mergeGraphEdges(data?.edges || [], { candidate: true })
    graphData.value.stats = {
      ...(graphData.value.stats || {}),
      local_vector: data?.stats || {},
    }
    lastLocalReviewEdges.value = extractLocalReviewEdges(graphData.value)
    renderGraph()
    return
  }
  if (event === 'review_progress') {
    streamProgress.value = {
      ...streamProgress.value,
      completed_pairs: data?.completed_pairs || 0,
      total_pairs: data?.total_pairs || 0,
      completed_packages: data?.completed_packages || 0,
      total_packages: data?.total_packages || 0,
    }
    updateRelationReviewStats({})
    return
  }
  if (event === 'discover_progress') {
    streamProgress.value = {
      ...streamProgress.value,
      completed_packages: data?.completed_packages || 0,
      total_packages: data?.total_packages || 0,
      added_edges: data?.added_edges || 0,
      skipped_packages: data?.skipped_packages || 0,
      review_concurrency: data?.review_concurrency || selectedReviewConcurrency.value,
    }
    updateRelationReviewStats({
      discovery_mode: 'top_l4_tool',
      added_edges: 0,
      skipped_packages: 0,
    })
    return
  }
  if (event === 'package_skipped') {
    updateRelationReviewStats({ discovery_mode: 'top_l4_tool' })
    return
  }
  if (event === 'relation_decision') {
    applyRelationDecision(data)
    renderGraph()
    return
  }
  if (event === 'snapshot_saved') {
    selectedSnapshotId.value = data?.snapshot?.snapshot_id || selectedSnapshotId.value
    if (data?.snapshot?.saved === false && data?.snapshot?.error) {
      graphError.value = `关系快照保存失败：${data.snapshot.error}`
    }
    return
  }
  if (event === 'done') {
    updateRelationReviewStats(data?.stats?.relation_review || {})
    return
  }
  if (event === 'error') {
    graphError.value = data?.message || '流式生成失败，已保留当前收到的结果'
  }
}

function applyRelationDecision(decision) {
  const action = String(decision?.action || '').toLowerCase()
  const edge = decision?.edge
  if (!edge?.source || !edge?.target || !edge?.type) return
  if (action === 'add' || action === 'update') {
    mergeGraphEdges([{
      ...edge,
      properties: {
        ...(edge.properties || {}),
        source_kind: 'llm',
        review_action: action,
        confidence: decision?.confidence ?? edge.properties?.confidence,
        reason: decision?.reason || edge.properties?.reason,
        review_package_id: decision?.package_id || edge.properties?.review_package_id,
      },
    }])
    updateRelationReviewStats({ [action === 'add' ? 'added_count' : 'updated_count']: 1 })
    return
  }
  markEdgeForRemoval(edge, action)
  updateRelationReviewStats({ [action === 'delete' ? 'deleted_count' : 'rejected_count']: 1 })
}

function mergeGraphEdges(edges, { candidate = false } = {}) {
  const current = new Map((graphData.value.edges || []).map(edge => [graphEdgeKey(edge), edge]))
  ;(edges || []).forEach(edge => {
    const normalized = normalizeGraphEdge(edge)
    if (!normalized) return
    const nextEdge = {
      ...normalized,
      properties: {
        ...(normalized.properties || {}),
        review_state: candidate ? 'candidate' : normalized.properties?.review_state,
      },
    }
    const existing = current.get(graphEdgeKey(nextEdge))
    current.set(graphEdgeKey(nextEdge), existing ? mergeGraphEdgePayload(existing, nextEdge) : nextEdge)
  })
  graphData.value = {
    ...graphData.value,
    edges: Array.from(current.values()),
  }
  refreshGraphStats()
}

function markEdgeForRemoval(edge, action) {
  const key = graphEdgeKey(edge)
  graphData.value = {
    ...graphData.value,
    edges: (graphData.value.edges || []).map(item =>
      graphEdgeKey(item) === key
        ? { ...item, properties: { ...(item.properties || {}), review_state: action === 'delete' ? 'deleting' : 'rejecting' } }
        : item,
    ),
  }
  setTimeout(() => {
    graphData.value = {
      ...graphData.value,
      edges: (graphData.value.edges || []).filter(item => graphEdgeKey(item) !== key),
    }
    refreshGraphEdgeStats()
    renderGraph()
  }, 380)
}

function updateRelationReviewStats(increment) {
  const current = graphData.value.stats?.relation_review || {}
  const next = {
    model: selectedModel.value,
    package_size: selectedPackageSize.value,
    requested_concurrency: selectedReviewConcurrency.value,
    applied_concurrency: selectedReviewConcurrency.value,
    ...current,
  }
  Object.entries(increment || {}).forEach(([key, value]) => {
    if (typeof value === 'string') {
      next[key] = value
      return
    }
    next[key] = (Number(next[key]) || 0) + (Number(value) || 0)
  })
  if (activeGraphStreamMode.value === 'discover' || next.discovery_mode) {
    next.discovery_mode = next.discovery_mode || 'top_l4_tool'
  }
  next.completed_pairs = streamProgress.value.completed_pairs
  next.total_pairs = streamProgress.value.total_pairs
  next.completed_package_count = streamProgress.value.completed_packages
  next.package_count = streamProgress.value.total_packages || next.package_count
  next.completed_packages = streamProgress.value.completed_packages
  next.total_packages = streamProgress.value.total_packages
  next.added_edges = streamProgress.value.added_edges
  next.skipped_packages = streamProgress.value.skipped_packages
  graphData.value = {
    ...graphData.value,
    stats: {
      ...(graphData.value.stats || {}),
      relation_review: next,
      review_concurrency: selectedReviewConcurrency.value,
    },
  }
}

function refreshGraphStats() {
  const nodes = graphData.value.nodes || []
  const nodeCounts = {}
  const levelCounts = {}
  nodes.forEach(node => {
    const kind = node.kind || 'requirement'
    nodeCounts[kind] = (nodeCounts[kind] || 0) + 1
    if (kind === 'requirement') {
      const level = normalizeLevel(node)
      levelCounts[level] = (levelCounts[level] || 0) + 1
    }
  })
  graphData.value.stats = {
    ...(graphData.value.stats || {}),
    node_count: nodes.length,
    node_counts: nodeCounts,
    level_counts: levelCounts,
  }
  refreshGraphEdgeStats()
}

function refreshGraphEdgeStats() {
  const edges = graphData.value.edges || []
  const edgeCounts = {}
  const edgeSourceCounts = {}
  let structuralEdgeCount = 0
  let analysisEdgeCount = 0
  let supplementalEdgeCount = 0
  edges.forEach(edge => {
    edgeCounts[edge.type] = (edgeCounts[edge.type] || 0) + 1
    const scopes = edgeSourceScopes(edge)
    scopes.forEach(sourceKind => {
      edgeSourceCounts[sourceKind] = (edgeSourceCounts[sourceKind] || 0) + 1
    })
    if (scopes.includes('structural')) structuralEdgeCount += 1
    if (scopes.some(scope => ['trace_analysis', 'conflict_analysis', 'classification_analysis'].includes(scope))) {
      analysisEdgeCount += 1
    }
    if (scopes.some(scope => supplementalRelationSourceKinds.has(scope))) {
      supplementalEdgeCount += 1
    }
  })
  graphData.value.stats = {
    ...(graphData.value.stats || {}),
    edge_count: edges.length,
    edge_counts: edgeCounts,
    edge_source_counts: edgeSourceCounts,
    structural_edge_count: structuralEdgeCount,
    analysis_edge_count: analysisEdgeCount,
    supplemental_edge_count: supplementalEdgeCount,
    inferred_edge_count: edgeSourceCounts.llm || 0,
  }
}

function edgeSourceScopes(edge) {
  const props = edge?.properties || {}
  const scopes = []
  ;(Array.isArray(props.source_kinds) ? props.source_kinds : []).forEach(scope => {
    const normalized = String(scope || '').trim()
    if (normalized && !scopes.includes(normalized)) scopes.push(normalized)
  })
  const primary = String(props.source_kind || 'rule').trim() || 'rule'
  if (!scopes.includes(primary)) scopes.push(primary)
  return scopes
}

function isProtectedRelationEdge(edge) {
  return edgeSourceScopes(edge).some(scope => protectedRelationSourceKinds.has(scope))
}

function preserveProtectedRelationEdge(edge) {
  const props = edge?.properties || {}
  const protectedScopes = edgeSourceScopes(edge).filter(scope => protectedRelationSourceKinds.has(scope))
  const sources = Array.isArray(props.sources)
    ? props.sources.filter(item => protectedRelationSourceKinds.has(String(item?.kind || '').trim()))
    : []
  return {
    ...edge,
    properties: {
      ...props,
      source_kind: protectedScopes[0] || props.source_kind,
      source_kinds: protectedScopes,
      sources: sources.length ? sources : props.sources,
    },
  }
}

function graphEdgeKey(edge) {
  const type = edge?.type || ''
  let source = normalizeGraphNodeId(edge?.source)
  let target = normalizeGraphNodeId(edge?.target)
  if (['CONFLICTS_WITH', 'SIMILAR_TO', 'VALIDATES_WITH'].includes(type) && source > target) {
    ;[source, target] = [target, source]
  }
  return `${type}:${source}->${target}`
}

function initChart() {
  if (!chartContainer.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartContainer.value)
  chart.on('click', params => {
    if (params.dataType === 'node') {
      selectedNode.value = params.data.raw
      selectedEdge.value = null
      return
    }
    if (params.dataType === 'edge') {
      selectedEdge.value = params.data.raw
      selectedNode.value = null
    }
  })
  resizeObserver = new ResizeObserver(() => {
    chart?.resize()
    patchFullCanvasRoamArea()
  })
  resizeObserver.observe(chartContainer.value)
  renderGraph()
}

function patchFullCanvasRoamArea() {
  const graphView = chart?._chartsViews?.find(view => view?.type === 'graph')
  const controller = graphView?._controller
  if (!controller || !chartContainer.value) return

  // ECharts graph defaults to using the rendered graph bounds as the pan hit-area,
  // which makes the blank edge gutters feel non-draggable. Expand it to the
  // full chart viewport so the canvas can always be dragged from its edges.
  controller.setPointerChecker((_event, x, y) => {
    const width = chartContainer.value?.clientWidth || 0
    const height = chartContainer.value?.clientHeight || 0
    return x >= 0 && y >= 0 && x <= width && y <= height
  })
}

function renderGraph() {
  if (!chart) return
  const allNodes = graphData.value?.nodes || []
  const allEdges = graphData.value?.edges || []
  const filteredGraph = filterGraph(allNodes, allEdges)
  const { nodes, edges } = normalizeGraphPayload(filteredGraph)
  if (!nodes.length) {
    chart.clear()
    return
  }

  const visibleCategories = buildChartCategories(nodes)
  const categories = visibleCategories.map(item => ({
    name: item.name,
    itemStyle: { color: item.color },
  }))
  const categoryIndex = Object.fromEntries(categories.map((item, index) => [item.name, index]))
  const initialPositions = buildGraphInitialPositions(nodes, edges)

  chart.setOption({
    backgroundColor: '#f8fafc',
    tooltip: {
      trigger: 'item',
      borderWidth: 1,
      borderColor: 'rgba(15, 23, 42, 0.12)',
      backgroundColor: 'rgba(255, 255, 255, 0.96)',
      textStyle: { color: '#0f172a' },
      formatter(params) {
        const raw = params.data?.raw
        if (!raw) return params.name
        if (params.dataType === 'edge') {
          return `${edgeLabel(raw.type)}<br/>${edgeSourceLabel(raw)}`
        }
        return `${levelLabel(normalizeLevel(raw))}<br/>${raw.label}`
      },
    },
    series: [
      {
        id: 'requirement-graph',
        type: 'graph',
        layout: 'force',
        legendHoverLink: false,
        categories,
        roam: true,
        draggable: true,
        data: nodes.map(node => {
          const chartCategory = chartCategoryName(node)
          const visual = analysisNodeVisual(node)
          const initialPosition = initialPositions.get(node.id) || {}
          return {
            id: node.id,
            name: node.label,
            raw: node,
            x: initialPosition.x,
            y: initialPosition.y,
            category: categoryIndex[chartCategory] ?? 0,
            symbol: 'circle',
            symbolSize: visual.symbolSize ?? nodeSize(node),
            label: {
              show: true,
              position: 'right',
              color: visual.labelColor || '#0f172a',
              fontSize: 12,
              width: 170,
              overflow: 'truncate',
            },
            itemStyle: {
              color: visual.fill || levelFillColor(node),
              borderColor: visual.borderColor || levelBorderColor(node),
              borderWidth: visual.borderWidth ?? 3,
              shadowBlur: visual.shadowBlur ?? 10,
              shadowColor: visual.shadowColor || 'rgba(15, 23, 42, 0.18)',
              opacity: visual.opacity ?? 1,
            },
          }
        }),
        links: edges.map(edge => ({
          source: edge.source,
          target: edge.target,
          label: { show: false },
          raw: edge,
          lineStyle: edgeLineStyle(edge),
        })),
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 9],
        force: {
          repulsion: 520,
          edgeLength: [130, 260],
          gravity: 0.035,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 4, opacity: 1 },
        },
        animationDuration: 900,
        animationEasingUpdate: 'quinticInOut',
      },
    ],
  }, { notMerge: true, lazyUpdate: false, replaceMerge: ['series'] })
  patchFullCanvasRoamArea()
  focusAnalysisRequirement(analysisFocusedRequirementId.value || analysisSourceRequirementId.value)
}

function buildGraphInitialPositions(nodes, edges) {
  const positions = new Map()
  if (!nodes.length) return positions

  const adjacency = new Map(nodes.map(node => [node.id, new Set()]))
  edges.forEach(edge => {
    if (!adjacency.has(edge.source) || !adjacency.has(edge.target)) return
    adjacency.get(edge.source).add(edge.target)
    adjacency.get(edge.target).add(edge.source)
  })

  const components = []
  const visited = new Set()
  nodes.forEach(node => {
    if (visited.has(node.id)) return
    const stack = [node.id]
    const component = []
    visited.add(node.id)
    while (stack.length) {
      const nodeId = stack.pop()
      component.push(nodeId)
      ;(adjacency.get(nodeId) || []).forEach(nextId => {
        if (visited.has(nextId)) return
        visited.add(nextId)
        stack.push(nextId)
      })
    }
    components.push(component)
  })
  components.sort((left, right) => right.length - left.length || String(left[0]).localeCompare(String(right[0])))

  const width = Math.max(chartContainer.value?.clientWidth || 1200, 900)
  const height = Math.max(chartContainer.value?.clientHeight || 700, 600)
  const columns = Math.ceil(Math.sqrt(components.length || 1))
  const rows = Math.ceil((components.length || 1) / columns)
  const cellWidth = width / Math.max(columns, 1)
  const cellHeight = height / Math.max(rows, 1)

  components.forEach((component, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    const centerX = cellWidth * (column + 0.5)
    const centerY = cellHeight * (row + 0.5)
    if (component.length === 1) {
      positions.set(component[0], { x: centerX, y: centerY })
      return
    }
    const radius = Math.max(64, Math.min(cellWidth, cellHeight) * 0.28, Math.sqrt(component.length) * 34)
    component
      .slice()
      .sort((left, right) => String(left).localeCompare(String(right)))
      .forEach((nodeId, nodeIndex) => {
        const angle = (-Math.PI / 2) + (Math.PI * 2 * nodeIndex) / component.length
        positions.set(nodeId, {
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        })
      })
  })

  return positions
}

function normalizeLevel(node) {
  const level = String(node.properties?.source_level || node.properties?.level || node.group || '').toUpperCase()
  if (level.includes('L1')) return 'L1'
  if (level.includes('L2')) return 'L2'
  if (level.includes('L3')) return 'L3'
  if (level.includes('L4')) return 'L4'
  return 'UNKNOWN_LEVEL'
}

function chartCategoryName(node) {
  return normalizeLevel(node)
}

function buildChartCategories(nodes) {
  const labels = []
  nodes.forEach(node => {
    const label = chartCategoryName(node)
    if (!labels.includes(label)) labels.push(label)
  })
  return labels.map(label => ({
    name: label,
    color: levelFillColorByLevel(label),
  }))
}

function categoryColor(label) {
  const palette = ['#0f766e', '#2563eb', '#d97706', '#7c3aed', '#dc2626', '#0891b2', '#65a30d', '#c2410c']
  let hash = 0
  for (const char of String(label || '')) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return palette[hash % palette.length]
}

function levelLabel(level) {
  return {
    L1: 'L1 方向层',
    L2: 'L2 业务层',
    L3: 'L3 方案层',
    L4: 'L4 实现层',
    UNKNOWN_LEVEL: '未知层级',
  }[level] || level || '未知层级'
}

function levelFillColor(node) {
  return levelFillColorByLevel(normalizeLevel(node))
}

function levelFillColorByLevel(level) {
  return levelPalette[level]?.fill || levelPalette.UNKNOWN_LEVEL.fill
}

function levelBorderColor(node) {
  return levelPalette[normalizeLevel(node)]?.border || levelPalette.UNKNOWN_LEVEL.border
}

function filterGraph(nodes, edges) {
  const filteredEdges = edges.filter(edge => edgeMatchesFilters(edge))
  const selectedRequirementIds = new Set(
    nodes
      .filter(node => {
        const levelMatched = selectedLevel.value === '__all__' || normalizeLevel(node) === selectedLevel.value
        const categoryMatched = selectedCategory.value === '__all__' || String(node.properties?.category || '').trim() === selectedCategory.value
        return levelMatched && categoryMatched
      })
      .map(node => node.id),
  )
  if (selectedLevel.value === '__all__' && selectedCategory.value === '__all__') {
    if (selectedEdgeType.value === '__all__' && selectedSourceScope.value === '__all__') {
      return { nodes, edges: filteredEdges }
    }
    const visibleIds = new Set(filteredEdges.flatMap(edge => [edge.source, edge.target]))
    return {
      nodes: nodes.filter(node => visibleIds.has(node.id)),
      edges: filteredEdges,
    }
  }
  if (!selectedRequirementIds.size) return { nodes: [], edges: [] }

  const includedIds = new Set(selectedRequirementIds)
  filteredEdges.forEach(edge => {
    if (selectedRequirementIds.has(edge.source)) includedIds.add(edge.target)
    if (selectedRequirementIds.has(edge.target)) includedIds.add(edge.source)
  })
  const filteredNodes = nodes.filter(node => includedIds.has(node.id))
  const visibleIds = new Set(filteredNodes.map(node => node.id))
  return {
    nodes: filteredNodes,
    edges: filteredEdges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target)),
  }
}

function selectLevel(label) {
  selectedLevel.value = label
  selectedNode.value = null
  selectedEdge.value = null
  renderGraph()
}

function selectCategory(label) {
  selectedCategory.value = label
  selectedNode.value = null
  selectedEdge.value = null
  renderGraph()
}

function selectEdgeType(type) {
  selectedEdgeType.value = type
  selectedEdge.value = null
  renderGraph()
}

function selectSourceScope(scope) {
  selectedSourceScope.value = scope
  selectedEdge.value = null
  renderGraph()
}

function resetEdgeFilters() {
  selectedEdgeType.value = '__all__'
  selectedSourceScope.value = '__all__'
  selectedEdge.value = null
  renderGraph()
}

function nodeSize(node) {
  const priority = Number(node.properties?.priority || 0)
  if (priority >= 4) return 42
  if (priority >= 2) return 36
  return 32
}

function analysisNodeVisual(node) {
  const requirementId = node?.properties?.req_id
  if (!requirementId) return {}
  const focused = analysisFocusedRequirementId.value === requirementId
  if (analysisSourceRequirementId.value === requirementId) {
    return {
      fill: '#ccfbf1',
      borderColor: focused ? '#0f172a' : '#0f766e',
      borderWidth: focused ? 6 : 5,
      shadowBlur: 18,
      shadowColor: 'rgba(15, 118, 110, 0.28)',
      symbolSize: nodeSize(node) + 4,
    }
  }
  if (analysisImpactedRequirementIds.value.has(requirementId)) {
    const impact = analysisImpactLookup.value[requirementId]
    const borderColor = impact?.impact_level === 'high' ? '#dc2626' : '#d97706'
    return {
      borderColor: focused ? '#0f172a' : borderColor,
      borderWidth: focused ? 6 : 4.5,
      shadowBlur: focused ? 16 : 12,
      shadowColor: impact?.impact_level === 'high' ? 'rgba(220, 38, 38, 0.22)' : 'rgba(217, 119, 6, 0.22)',
      symbolSize: nodeSize(node) + (focused ? 4 : 2),
    }
  }
  if (analysisAdvisoryRequirementIds.value.has(requirementId)) {
    return {
      borderColor: focused ? '#0f172a' : '#94a3b8',
      borderWidth: focused ? 5 : 3,
      shadowBlur: focused ? 14 : 6,
      shadowColor: 'rgba(148, 163, 184, 0.18)',
      opacity: 0.76,
    }
  }
  return {}
}

function edgeColor(type) {
  return edgeLegend.find(item => item.type === type)?.color || '#64748b'
}

function edgeLabel(type) {
  return edgeLegend.find(item => item.type === type)?.label || type || ''
}

function resolveNodeLabel(nodeId) {
  if (!nodeId) return ''
  return graphData.value?.nodes?.find(node => node.id === nodeId)?.label || nodeId
}

function edgeSourceType(edge) {
  return edge?.properties?.source_kind || 'rule'
}

function edgeSourceLabel(edge) {
  const kinds = edge?.properties?.source_kinds || [edgeSourceType(edge)]
  return kinds.map(kind => sourceScopeLabel(kind)).join(' + ')
}

function edgeSourceDetailLabel(edge) {
  const details = edge?.properties?.source_details || []
  if (!details.length) return formatValue(edge?.properties?.source_detail || edge?.properties?.source)
  return details.map(item => sourceText(item)).join('、')
}

function reviewActionLabel(value) {
  return {
    add: '新增',
    update: '修改',
    delete: '删除',
    reject: '排除',
  }[String(value || '').trim().toLowerCase()] || formatValue(value)
}

function sourceScopeLabel(scope) {
  return {
    structural: '结构',
    trace_analysis: '追溯结果',
    conflict_analysis: '冲突结果',
    classification_analysis: '分类结果',
    local_vector: '本地向量',
    rule_extra: '规则补充',
    rule: '规则补充',
    llm: 'DeepSeek 判断',
  }[scope] || scope
}

function edgeMatchesFilters(edge) {
  if (isTopLevelSimilarityEdge(edge)) return false
  if (selectedEdgeType.value !== '__all__' && edge.type !== selectedEdgeType.value) return false
  const scopes = edge?.properties?.source_kinds || [edgeSourceType(edge)]
  const matchesSourceScope = (() => {
    if (selectedSourceScope.value === '__all__') return true
    if (selectedSourceScope.value === '__analysis__') {
      return scopes.some(scope => ['trace_analysis', 'conflict_analysis', 'classification_analysis'].includes(scope))
    }
    if (selectedSourceScope.value === '__extra__') {
      return scopes.some(scope => ['local_vector', 'rule_extra', 'rule', 'llm'].includes(scope))
    }
    return scopes.includes(selectedSourceScope.value)
  })()
  if (!matchesSourceScope) {
    return false
  }
  return true
}

function isTopLevelSimilarityEdge(edge) {
  if (edge?.type !== 'SIMILAR_TO') return false
  const nodes = graphData.value?.nodes || []
  const sourceNode = nodes.find(node => node.id === edge.source)
  const targetNode = nodes.find(node => node.id === edge.target)
  const topLevels = new Set(['L1', 'L2', 'L3'])
  return topLevels.has(normalizeLevel(sourceNode || {})) && topLevels.has(normalizeLevel(targetNode || {}))
}

function edgeLineStyle(edge) {
  const sourceScope = edgeSourceType(edge)
  const reviewState = edge?.properties?.review_state || ''
  const edgeKey = analysisEdgeKey({
    source: edge.source.replace(/^req:/, ''),
    target: edge.target.replace(/^req:/, ''),
    type: edge.type,
  })
  const inAnyPath = analysisPathEdgeKeys.value.has(edgeKey)
  const inFocusedPath = analysisFocusedEdgeKeys.value.has(edgeKey)
  return {
    color: reviewState === 'rejecting' || reviewState === 'deleting' ? '#b91c1c' : edgeColor(edge.type),
    width: inFocusedPath
      ? 5.6
      : inAnyPath
        ? 4.4
        : sourceScope === 'structural'
          ? 3.4
          : ['trace_analysis', 'conflict_analysis', 'classification_analysis'].includes(sourceScope)
            ? 3
            : ['rule_extra', 'rule'].includes(sourceScope)
            ? 2.8
            : reviewState === 'candidate'
              ? 2
              : 2.4,
    opacity: inFocusedPath
      ? 1
      : inAnyPath
        ? 0.94
        : edge.type === 'CONFLICTS_WITH'
          ? 0.9
          : sourceScope === 'llm'
            ? 0.84
            : reviewState === 'candidate'
              ? 0.34
              : reviewState === 'rejecting' || reviewState === 'deleting'
                ? 0.2
                : 0.7,
    type: reviewState === 'candidate' ? 'dotted' : sourceScope === 'llm' ? 'solid' : ['rule_extra', 'rule'].includes(sourceScope) ? 'dotted' : 'solid',
    curveness: edge.type === 'CONFLICTS_WITH' ? 0.22 : 0.1,
  }
}

function formatConfidence(value) {
  if (value === null || value === undefined || value === '') return ''
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toFixed(2)
}

function formatSnapshotOption(snapshot) {
  const mode = snapshotModeLabel(snapshot?.relation_mode)
  const status = snapshotStatusLabel(snapshot?.snapshot_status)
  const time = formatSnapshotTime(snapshot?.created_at)
  const edgeCount = Number(snapshot?.edge_count) || 0
  const activity = snapshot?.is_active ? '当前' : '历史'
  return `${time} · ${status} · ${mode} · ${edgeCount} 边 · ${activity}`
}

function formatSnapshotTime(value) {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function snapshotModeLabel(value) {
  return {
    local: '本地向量',
    llm: 'DeepSeek 复核',
    none: '基础图谱',
  }[String(value || '').trim().toLowerCase()] || '未标注'
}

function snapshotStatusLabel(value) {
  return {
    running: '运行中',
    final: '最终',
    failed: '失败',
    interrupted: '中断',
  }[String(value || 'final').trim().toLowerCase()] || '最终'
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.filter(Boolean).join('、')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return sourceText(String(value))
}

function sourceText(value) {
  return {
    llm_inference: '大模型补充',
    llm_tool_review: '工具化复核',
    'manage_requirements.parent_id': '父子结构',
    'manage_requirements.source_req_id': '来源结构',
    trace_analysis: '追溯分析结果',
    conflict_analysis: '冲突分析结果',
    classification_analysis: '分类分析结果',
    rule_dependency_signal_match: '依赖规则',
    rule_conflict_signal_match: '冲突规则',
    rule_validation_overlap: '规则补充',
    rule_similarity_recall: '规则补充',
    semantic_similarity_match: '规则补充',
    manage_requirements: '需求管理',
  }[value] || value
}

function analysisEdgeKey(segment) {
  return `${segment.type}:${toRequirementNodeId(segment.source)}->${toRequirementNodeId(segment.target)}`
}

function toRequirementNodeId(requirementId) {
  const text = String(requirementId || '')
  if (!text) return ''
  return text.startsWith('req:') ? text : `req:${text}`
}

function focusAnalysisRequirement(requirementId) {
  if (!chart || !requirementId) return
  const series = chart.getOption()?.series?.[0]
  const data = series?.data || []
  const dataIndex = data.findIndex(item => item.id === toRequirementNodeId(requirementId))
  if (dataIndex < 0) return
  chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex })
  chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex })
}

function resolveRequirementTitle(requirementId) {
  return graphData.value?.nodes?.find(node => node.properties?.req_id === requirementId)?.label || requirementId
}

function impactLevelLabel(level) {
  return {
    high: '高风险',
    medium: '中风险',
    low: '低风险',
  }[level] || level || '未标记'
}

function analysisStatusLabel(status) {
  return {
    completed: '已完成',
    no_impact: '无影响',
    no_effective_change: '无有效变更',
  }[status] || status || '待分析'
}

function priorityLabel(priority) {
  return {
    low: '低',
    medium: '中',
    high: '高',
  }[priority] || priority || ''
}

function requirementStatusLabel(status) {
  return {
    draft: '草稿',
    under_review: '评审中',
    confirmed: '已确认',
    in_progress: '进行中',
    completed: '已完成',
    archived: '已归档',
  }[status] || status || ''
}

watch(selectedProjectId, async (value) => {
  if (value) {
    localStorage.setItem('lastProjectId', value)
    sessionId.value = ''
    await syncProjectSession()
    clearSnapshotHistoryState()
    clearGraphState()
    await loadLatestSnapshotGraph()
    return
  }

  localStorage.removeItem('lastProjectId')
  sessionId.value = ''
  clearSnapshotHistoryState()
  clearGraphState()
})

watch(sessionId, async (value, oldValue) => {
  if (value) {
    localStorage.setItem('lastSessionId', value)
  } else {
    localStorage.removeItem('lastSessionId')
  }
  if (value !== oldValue) {
    clearSnapshotHistoryState()
    clearGraphState()
    if (value) {
      await loadLatestSnapshotGraph()
    }
  }
})

watch(packageSize, value => {
  const normalized = String(Math.max(1, Math.min(24, Number(value) || 6)))
  if (normalized !== value) {
    packageSize.value = normalized
    return
  }
  localStorage.setItem('requirementGraphPackageSize', normalized)
})

watch(reviewConcurrency, value => {
  const normalized = String(Math.max(1, Math.min(8, Number(value) || 3)))
  if (normalized !== value) {
    reviewConcurrency.value = normalized
    return
  }
  localStorage.setItem('requirementGraphReviewConcurrency', normalized)
})

watch(selectedModel, value => {
  localStorage.setItem('requirementGraphModel', value || 'deepseek-v4-pro')
})

watch(useThinkingMode, value => {
  localStorage.setItem('requirementGraphThinking', value ? 'true' : 'false')
})

watch(levelCounts, () => {
  if (selectedLevel.value !== '__all__' && !levelCounts.value[selectedLevel.value]) {
    selectedLevel.value = '__all__'
  }
}, { deep: true })

watch(analysisFocusedRequirementId, () => {
  if (analysisResult.value) {
    renderGraph()
  }
})

onMounted(async () => {
  initChart()
  await loadProjects()
  if (selectedProjectId.value) {
    await syncProjectSession()
  }
  if (selectedProjectId.value || sessionId.value) {
    await loadLatestSnapshotGraph()
  }
})

onBeforeUnmount(() => {
  if (graphStreamAbortController) {
    graphStreamAbortController.abort()
    graphStreamAbortController = null
  }
  if (resizeObserver && chartContainer.value) resizeObserver.unobserve(chartContainer.value)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.graph-canvas {
  min-width: 0;
}

.page-header.nav-style {
  flex-wrap: wrap;
  align-items: flex-start;
}

.graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex: 1 1 760px;
  flex-wrap: wrap;
  gap: 10px;
  width: auto;
  min-width: 0;
}

.project-select,
.session-input {
  height: 38px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 6px;
  background: #ffffff;
  color: #0f172a;
  padding: 0 12px;
  outline: none;
}

.project-select {
  flex: 1 1 190px;
  min-width: 170px;
  max-width: 240px;
}

.graph-toggle {
  height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 6px;
  padding: 0 10px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.review-select {
  flex: 0 0 120px;
  min-width: 120px;
  max-width: 120px;
}

.package-select {
  flex: 0 0 120px;
  min-width: 120px;
  max-width: 120px;
}

.snapshot-select {
  flex: 1 1 250px;
  min-width: 220px;
  max-width: 360px;
}

.session-input {
  flex: 1 1 220px;
  min-width: 220px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.action-btn {
  height: 38px;
  border: 0;
  border-radius: 6px;
  padding: 0 16px;
  background: #0f766e;
  color: #ffffff;
  font-weight: 700;
  cursor: pointer;
  flex: 0 0 auto;
  white-space: nowrap;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.graph-shell {
  display: grid;
  grid-template-columns: 310px 1fr;
  gap: 16px;
  height: calc(100vh - 150px);
  min-height: 620px;
}

.graph-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.metric-grid,
.legend-block,
.detail-block {
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 14px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.infer-btn {
  background: #1d4ed8;
}

.discover-btn {
  background: #0f766e;
}

.danger-btn {
  background: #b91c1c;
}

.metric-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 6px;
  padding: 10px;
  background: #f8fafc;
}

.metric-item span,
.legend-row span,
.detail-kind,
.detail-empty,
.legend-hint,
dt {
  color: #64748b;
  font-size: 12px;
}

.metric-item strong {
  display: block;
  margin-top: 6px;
  color: #0f172a;
  font-size: 22px;
}

.legend-block h3,
.detail-block h3 {
  margin: 0;
  color: #0f172a;
  font-size: 15px;
}

.compact-block h3 {
  margin-bottom: 12px;
}

.detail-block h3 {
  margin-bottom: 12px;
}

.block-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.source-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
}

.source-badge.subtle {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
}

.clear-filter {
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 6px;
  background: #ffffff;
  color: #475569;
  height: 28px;
  padding: 0 10px;
  cursor: pointer;
}

.clear-filter.active {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-chip {
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 999px;
  background: #ffffff;
  color: #475569;
  min-height: 30px;
  padding: 0 12px;
  cursor: pointer;
  font-size: 12px;
}

.filter-chip.active {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.confidence-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  color: #334155;
  font-size: 12px;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.category-chip {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 6px;
  background: #ffffff;
  color: #0f172a;
  cursor: pointer;
  padding: 0 10px;
  text-align: left;
}

.category-chip.active {
  border-color: rgba(15, 118, 110, 0.45);
  background: rgba(20, 184, 166, 0.08);
}

.category-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.category-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #334155;
  font-size: 13px;
}

.category-chip b {
  color: #0f172a;
  font-size: 12px;
}

.legend-hint {
  margin: 10px 0 0;
  line-height: 1.5;
}

.legend-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 28px;
}

.legend-button {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 6px;
  background: #ffffff;
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
}

.legend-button.active {
  border-color: rgba(15, 118, 110, 0.35);
  background: rgba(20, 184, 166, 0.08);
}

.legend-line {
  height: 3px;
  border-radius: 3px;
}

.legend-row b {
  color: #0f172a;
  font-size: 12px;
}

.detail-title {
  color: #0f172a;
  font-weight: 700;
  line-height: 1.45;
}

.detail-action-btn {
  margin-top: 14px;
  width: 100%;
  min-height: 36px;
  border: 1px solid rgba(15, 118, 110, 0.24);
  border-radius: 8px;
  background: rgba(20, 184, 166, 0.1);
  color: #0f766e;
  font-weight: 700;
  cursor: pointer;
}

.detail-action-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.detail-block dl {
  margin: 12px 0 0;
}

.detail-pair {
  display: contents;
}

.detail-block dt {
  margin-top: 10px;
}

.detail-block dd {
  margin: 4px 0 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.evidence-panel {
  margin-top: 14px;
  border-top: 1px dashed rgba(15, 23, 42, 0.12);
  padding-top: 12px;
}

.evidence-panel summary {
  cursor: pointer;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.evidence-panel dl {
  margin-top: 10px;
}

.graph-stage {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
  min-width: 0;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
}

.graph-stage.with-analysis {
  grid-template-columns: minmax(0, 1fr) 390px;
}

.graph-chart {
  width: 100%;
  height: 100%;
  min-height: 620px;
}

.analysis-drawer {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  overflow: auto;
  background:
    radial-gradient(circle at top, rgba(20, 184, 166, 0.08), transparent 38%),
    linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border-left: 1px solid rgba(15, 23, 42, 0.08);
  padding: 16px;
}

.analysis-drawer-header,
.analysis-block-title,
.analysis-diff-header,
.analysis-impact-top,
.analysis-impact-meta,
.analysis-inline-fields {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.analysis-drawer-header {
  align-items: flex-start;
}

.analysis-drawer-header h3,
.analysis-block h4 {
  margin: 0;
  color: #0f172a;
}

.analysis-drawer-header p,
.analysis-state,
.analysis-impact-item p,
.analysis-advisory-item p,
.analysis-path-block p {
  margin: 6px 0 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.analysis-block {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  padding: 14px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
}

.analysis-submit-btn {
  min-width: 92px;
  padding: 0 14px;
}

.analysis-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.analysis-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #334155;
  font-size: 12px;
}

.analysis-input,
.analysis-textarea {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 8px;
  background: #ffffff;
  color: #0f172a;
  padding: 10px 12px;
  outline: none;
}

.analysis-textarea {
  min-height: 96px;
  resize: vertical;
  font-family: inherit;
}

.analysis-chip,
.risk-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.analysis-chip {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
}

.analysis-chip.emphasis {
  background: rgba(20, 184, 166, 0.12);
  color: #0f766e;
}

.analysis-state.error {
  color: #b91c1c;
}

.analysis-diff-list,
.analysis-impact-list,
.analysis-advisory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.analysis-diff-card,
.analysis-impact-item,
.analysis-advisory-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  background: #ffffff;
  padding: 12px;
}

.analysis-impact-item,
.analysis-advisory-item {
  width: 100%;
  cursor: pointer;
  text-align: left;
}

.analysis-impact-item.active,
.analysis-advisory-item:hover {
  border-color: rgba(15, 118, 110, 0.32);
  box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
}

.analysis-diff-card.changed {
  border-color: rgba(20, 184, 166, 0.24);
  background: linear-gradient(180deg, rgba(204, 251, 241, 0.45), #ffffff);
}

.analysis-diff-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.analysis-diff-body span,
.analysis-summary-card span,
.analysis-subtitle,
.analysis-impact-meta span {
  color: #64748b;
  font-size: 11px;
}

.analysis-diff-body p {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.analysis-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.analysis-summary-card {
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
  padding: 12px;
}

.analysis-summary-card strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 22px;
}

.analysis-impact-top strong,
.analysis-advisory-item strong {
  color: #0f172a;
  font-size: 13px;
}

.risk-badge.high {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.risk-badge.medium {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.risk-badge.low {
  background: rgba(148, 163, 184, 0.14);
  color: #475569;
}

.analysis-path-block,
.analysis-advisory-block {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed rgba(15, 23, 42, 0.12);
}

.analysis-path-chain {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.analysis-path-segment {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.segment-node,
.segment-arrow {
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.08);
  padding: 8px 10px;
  color: #0f172a;
  font-size: 12px;
}

.segment-arrow {
  color: #0f766e;
  font-weight: 700;
  white-space: nowrap;
}

.state-panel {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  max-width: 360px;
  padding: 14px 18px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  color: #334155;
  border: 1px solid rgba(15, 23, 42, 0.1);
  text-align: center;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.12);
}

.error-state {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.2);
}

@media (max-width: 1100px) {
  .graph-toolbar {
    justify-content: flex-start;
  }

  .graph-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .graph-side {
    order: 2;
  }

  .graph-stage {
    min-height: 560px;
  }

  .graph-stage.with-analysis {
    grid-template-columns: 1fr;
  }

  .analysis-drawer {
    border-left: 0;
    border-top: 1px solid rgba(15, 23, 42, 0.08);
    max-height: none;
  }

  .analysis-diff-body,
  .analysis-summary-grid,
  .analysis-inline-fields {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 760px) {
  .project-select,
  .package-select,
  .review-select,
  .snapshot-select,
  .session-input,
  .action-btn {
    width: 100%;
    max-width: none;
  }
}
</style>
