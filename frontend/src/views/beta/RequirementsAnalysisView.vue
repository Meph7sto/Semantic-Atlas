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
          <div class="nav-center" style="background: rgba(47, 143, 137, 0.06); padding: 6px 16px; border-radius: 4px; border: 1px solid rgba(47, 143, 137, 0.15); min-width: 200px; display: flex; justify-content: center;">
            <span style="font-weight: 600; color: var(--teal); font-size: 15px;">当前项目：{{ currentProjectName }}</span>
          </div>
          <div class="page-actions">
            <span class="nav-text">分析进度</span>
          </div>
        </section>

        <!-- 主内容区 -->
        <section class="analysis-container" data-animate style="--delay: 0.1s">
          <div class="analysis-layout">
            <AnalysisControlPanel
              :projects="projects"
              :isLoadingProjects="isLoadingProjects"
              :selectedProjectId="selectedProjectId"
              :projectSessionId="projectSessionId"
              :sessionId="sessionId"
              :contextRuns="contextRuns"
              :isLoadingRuns="isLoadingRuns"
              :contextRunId="contextRunId"
              :allHighLevelRequirements="allHighLevelRequirements"
              :lowLevelRequirements="lowLevelRequirements"
              :isAnalyzing="isAnalyzing"
              :canAnalyze="canAnalyze"
              :analysisStep="analysisStep"
              :analysisPercent="analysisPercent"
              :progressColorClass="progressColorClass"
              :analysisStepText="analysisStepText"
              :traceResult="traceResult"
              :conflictStats="conflictStats"
              :classificationResult="classificationResult"
              :analysisNotice="analysisNotice"
              :analysisError="analysisError"
              @update:selectedProjectId="selectedProjectId = $event"
              @update:sessionId="sessionId = $event"
              @update:contextRunId="contextRunId = $event"
              @loadProjects="loadProjects"
              @loadContextRuns="loadContextRuns"
              @runAnalysis="runFullAnalysis"
            />
            <AnalysisResultPanel
              v-model:activeTab="activeTab"
              :traceResult="traceResult"
              :allHighLevelRequirements="allHighLevelRequirements"
              :lowLevelRequirements="lowLevelRequirements"
              :conflictResults="conflictResults"
              :conflictStats="conflictStats"
              :classificationResult="classificationResult"
              :classificationGroups="classificationGroups"
            />
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Sidebar from '../../components/beta/Sidebar.vue'
import AnalysisControlPanel from '../../components/beta/analysis/AnalysisControlPanel.vue'
import AnalysisResultPanel from '../../components/beta/analysis/AnalysisResultPanel.vue'
import { useAnalysisSession } from '../../composables/useAnalysisSession'
import { useRequirementsAnalysis } from '../../composables/useRequirementsAnalysis'

const router = useRouter()
const route = useRoute()

// 侧边栏状态
const roleType = ref('unified_admin')
const roleLabel = ref('管理员')
const timestamp = ref(new Date().toLocaleString())
const notificationCount = ref(3)

const routeNameToPageKey = {
  'beta-dashboard': 'dashboard',
  'beta-products': 'products',
  'beta-project': 'project-management',
  'beta-requirements': 'requirements',
  'beta-requirements-session': 'requirements-session',
  'beta-requirements-analysis': 'requirements-analysis',
  'beta-requirements-collection': 'requirements-collection',
  'beta-asr': 'asr-transcription',
  'beta-user-manage': 'user-management',
}

const pageKeyToRouteName = {
  'dashboard': 'beta-dashboard',
  'products': 'beta-products',
  'project-management': 'beta-project',
  'requirements': 'beta-requirements',
  'requirements-session': 'beta-requirements-session',
  'requirements-analysis': 'beta-requirements-analysis',
  'requirements-collection': 'beta-requirements-collection',
  'asr-transcription': 'beta-asr',
  'user-management': 'beta-user-manage',
}

const activePage = computed(() => routeNameToPageKey[route.name] || 'requirements-analysis')

// 会话与项目状态
const {
  projects, selectedProjectId, isLoadingProjects, projectSessionId, currentProjectName,
  loadProjects, loadProjectSession,
  sessionId, contextRunId, contextRuns, isLoadingRuns,
  highLevelRequirements, lowLevelRequirements,
  loadContextRuns, loadRequirements,
} = useAnalysisSession()

// 分析状态与结果
const {
  isAnalyzing, analysisStep, analysisError, analysisNotice,
  traceResult, conflictResults, classificationResult,
  activeTab, allHighLevelRequirements, canAnalyze, conflictStats, classificationGroups,
  analysisPercent, analysisStepText, progressColorClass,
  runFullAnalysis, loadExistingResults,
} = useRequirementsAnalysis(sessionId, highLevelRequirements, lowLevelRequirements)

function handleNavigate(page) {
  const target = pageKeyToRouteName[page]
  if (target && target !== route.name) {
    router.push({ name: target })
  }
}

function handleExit() {
  router.push({ name: 'beta-login' })
}

onMounted(async () => {
  await loadProjects()
  if (selectedProjectId.value && !sessionId.value) {
    await loadProjectSession()
  }
  if (sessionId.value) {
    await Promise.all([
      loadContextRuns(),
      loadRequirements(),
      loadExistingResults(),
    ])
  }
})
</script>

<style scoped>
.analysis-container {
  flex: 1;
  overflow: hidden;
}

.analysis-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  height: calc(100vh - 180px);
}
</style>
