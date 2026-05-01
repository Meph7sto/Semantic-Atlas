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
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">追踪 · 分支级需求追溯工作台</span>
          </div>
          <div class="page-actions">
            <button type="button" class="action-btn white sa-button sa-button--secondary" @click="refreshContext">刷新上下文</button>
            <button type="button" class="action-btn brown sa-button sa-button--primary" :disabled="triggeringImpact || !selectedBranchId" @click="triggerImpactAnalysis()">
              {{ triggeringImpact ? '分析中…' : '触发影响分析' }}
            </button>
          </div>
        </section>

        <section class="grid" data-animate style="--delay: 0.1s">
          <div class="card wide traceability-shell sa-card">
            <div class="card-header no-border">
              <div>
                <p class="card-kicker">Traceability Context</p>
                <h2 class="section-title">项目与分支上下文</h2>
              </div>
              <span class="chip-neutral small">
                {{ selectedProject?.name || '未选择项目' }} / {{ selectedBranch?.branch_name || '未选择分支' }}
              </span>
            </div>

            <div v-if="overview?.summary" class="traceability-summary">
              <div class="traceability-summary-card">
                <span>需求快照</span>
                <strong>{{ overview.summary.requirement_count }}</strong>
              </div>
              <div class="traceability-summary-card">
                <span>测试用例</span>
                <strong>{{ overview.summary.test_case_count }}</strong>
              </div>
              <div class="traceability-summary-card">
                <span>变更集</span>
                <strong>{{ overview.summary.change_count }}</strong>
              </div>
              <div class="traceability-summary-card">
                <span>审计事件</span>
                <strong>{{ overview.summary.audit_count }}</strong>
              </div>
            </div>

            <div class="traceability-toolbar">
              <label class="traceability-field">
                <span>项目</span>
                <select v-model="selectedProjectId" class="select-clean sa-input">
                  <option value="">选择项目</option>
                  <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
                    {{ project.name }}
                  </option>
                </select>
              </label>

              <label class="traceability-field">
                <span>分支</span>
                <select v-model="selectedBranchId" class="select-clean sa-input" :disabled="!selectedProjectId || loadingBranches">
                  <option value="">{{ loadingBranches ? '加载中…' : '选择分支' }}</option>
                  <option v-for="branch in branches" :key="branch.ref_id" :value="branch.ref_id">
                    {{ branch.branch_name || branch.ref_name }}
                  </option>
                </select>
              </label>
            </div>

            <div v-if="errorMessage" class="traceability-state traceability-state--error">
              {{ errorMessage }}
            </div>

            <div class="traceability-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                type="button"
                class="traceability-tab"
                :class="{ active: tab.key === activeTab }"
                @click="selectTab(tab.key)"
              >
                {{ tab.label }}
              </button>
            </div>

            <div class="traceability-panel">
              <template v-if="loadingProjects || loadingOverview">
                <div class="traceability-state">正在加载追踪工作台上下文…</div>
              </template>
              <template v-else-if="!selectedProjectId">
                <div class="traceability-state">请选择项目以开始追踪分析。</div>
              </template>
              <template v-else-if="!selectedBranchId">
                <div class="traceability-state">当前项目暂无分支，请先创建分支后再进入追踪页。</div>
              </template>
              <template v-else>
                <TraceabilityMatrixPanel
                  v-if="activeTab === 'matrix'"
                  :data="matrixData"
                  :loading="loadingPanel"
                />
                <TraceabilityCoveragePanel
                  v-else-if="activeTab === 'coverage'"
                  :data="coverageData"
                  :loading="loadingPanel"
                />
                <TraceabilityImpactPanel
                  v-else-if="activeTab === 'impact'"
                  :data="impactData"
                  :loading="loadingPanel && !impactData"
                  :triggering="triggeringImpact"
                  @trigger="triggerImpactAnalysis"
                />
                <TraceabilityRiskPanel
                  v-else-if="activeTab === 'risk'"
                  :data="riskData"
                  :loading="loadingPanel"
                />
                <div v-else class="traceability-placeholder">
                  <div>
                    <p class="card-kicker">Active Tab</p>
                    <h3 class="section-title">{{ activeTabLabel }}</h3>
                  </div>
                  <p>当前标签的真实面板会在后续 task 中接入。</p>
                </div>
              </template>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Sidebar from '../../components/beta/Sidebar.vue'
import TraceabilityMatrixPanel from '../../components/beta/traceability/TraceabilityMatrixPanel.vue'
import TraceabilityCoveragePanel from '../../components/beta/traceability/TraceabilityCoveragePanel.vue'
import TraceabilityImpactPanel from '../../components/beta/traceability/TraceabilityImpactPanel.vue'
import TraceabilityRiskPanel from '../../components/beta/traceability/TraceabilityRiskPanel.vue'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'
import { useTraceabilityWorkbench } from '@/composables/useTraceabilityWorkbench'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('tracking')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()
const {
  activeTab,
  branches,
  coverageData,
  errorMessage,
  impactData,
  loadingOverview,
  loadingPanel,
  loadingBranches,
  loadingProjects,
  matrixData,
  overview,
  projects,
  refreshContext,
  riskData,
  selectedBranch,
  selectedBranchId,
  selectedProject,
  selectedProjectId,
  selectTab,
  tabs,
  triggerImpactAnalysis,
  triggeringImpact,
} = useTraceabilityWorkbench()

const activeTabLabel = computed(() =>
  tabs.find((tab) => tab.key === activeTab.value)?.label || '追溯矩阵',
)
</script>

<style scoped>
.traceability-shell {
  display: grid;
  gap: 20px;
}

.traceability-toolbar {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 260px));
  gap: 16px;
}

.traceability-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.traceability-summary-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.88);
}

.traceability-summary-card span {
  color: rgba(28, 40, 52, 0.62);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.traceability-field {
  display: grid;
  gap: 8px;
  color: rgba(28, 40, 52, 0.8);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.traceability-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.traceability-tab {
  border: 1px solid rgba(28, 40, 52, 0.12);
  background: rgba(255, 255, 255, 0.78);
  color: #1c2834;
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
}

.traceability-tab.active {
  background: #1c2834;
  color: #f7f1e8;
}

.traceability-panel {
  min-height: 280px;
  border: 1px dashed rgba(28, 40, 52, 0.14);
  border-radius: 24px;
  background: rgba(255, 252, 247, 0.84);
  padding: 24px;
}

.traceability-state,
.traceability-placeholder {
  display: grid;
  gap: 10px;
  align-content: start;
  color: rgba(28, 40, 52, 0.8);
}

.traceability-state--error {
  color: #a04444;
}

@media (max-width: 900px) {
  .traceability-summary,
  .traceability-toolbar {
    grid-template-columns: 1fr;
  }
}
</style>
