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
              :activeTab="activeTab"
              :activeAnalysisLabel="activeAnalysisLabel"
              :projects="projects"
              :isLoadingProjects="isLoadingProjects"
              :selectedProjectId="selectedProjectId"
              :projectSessionId="projectSessionId"
              :sessionId="sessionId"
              :contextRuns="contextRuns"
              :isLoadingRuns="isLoadingRuns"
              :contextRunId="contextRunId"
              :analysisRuns="analysisRuns"
              :isLoadingAnalysisRuns="isLoadingAnalysisRuns"
              :selectedAnalysisRunId="selectedAnalysisRunId"
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
              :conflictConcurrency="conflictConcurrency"
              @update:selectedProjectId="selectedProjectId = $event"
              @update:sessionId="sessionId = $event"
              @update:contextRunId="contextRunId = $event"
              @update:selectedAnalysisRunId="selectedAnalysisRunId = $event"
              @update:conflictConcurrency="conflictConcurrency = $event"
              @loadProjects="loadProjects"
              @loadContextRuns="loadContextRuns"
              @loadAnalysisRuns="loadAnalysisRuns"
              @runAnalysis="runActiveAnalysis"
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
import { onMounted, watch } from 'vue'
import Sidebar from '../../components/beta/Sidebar.vue'
import AnalysisControlPanel from '../../components/beta/analysis/AnalysisControlPanel.vue'
import AnalysisResultPanel from '../../components/beta/analysis/AnalysisResultPanel.vue'
import { useAnalysisSession } from '../../composables/useAnalysisSession'
import { useRequirementsAnalysis } from '../../composables/useRequirementsAnalysis'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirements-analysis')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

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
  activeTab, activeAnalysisLabel, allHighLevelRequirements, canAnalyze, conflictStats, classificationGroups,
  analysisPercent, analysisStepText, progressColorClass,
  analysisRuns, selectedAnalysisRunId, isLoadingAnalysisRuns,
  conflictConcurrency,
  runActiveAnalysis, loadExistingResults, loadAnalysisRuns, loadAnalysisRunDetail,
} = useRequirementsAnalysis(sessionId, highLevelRequirements, lowLevelRequirements)

onMounted(async () => {
  await loadProjects()
  if (selectedProjectId.value && !sessionId.value) {
    await loadProjectSession()
  }
  if (sessionId.value) {
    await Promise.all([
      loadContextRuns(),
      loadRequirements(),
      loadAnalysisRuns(),
      loadExistingResults(),
    ])
  }
})

watch(sessionId, async (newSessionId) => {
  if (!newSessionId?.trim()) return
  selectedAnalysisRunId.value = ''
  await Promise.all([
    loadRequirements(),
    loadAnalysisRuns(),
    loadExistingResults(),
  ])
})

watch(selectedAnalysisRunId, async (newRunId) => {
  if (!newRunId) {
    await loadExistingResults()
    return
  }
  await loadAnalysisRunDetail(newRunId)
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
