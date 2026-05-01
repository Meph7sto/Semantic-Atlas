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
          <div class="nav-center" style="background: rgba(47, 143, 137, 0.06); padding: 6px 16px; border-radius: 4px; border: 1px solid rgba(47, 143, 137, 0.15); min-width: 200px; display: flex; justify-content: center;">
            <span style="font-weight: 600; color: var(--teal); font-size: 15px;">当前项目：{{ currentProjectName }}</span>
          </div>
          <div class="page-actions">
            <button
              type="button"
              class="action-btn secondary sa-button sa-button--secondary"
              @click="router.push({ name: 'beta-requirements-session' })"
            >
              查看会话需求
            </button>
            <span class="nav-text">自动化流程</span>
          </div>
        </section>

        <!-- 主内容区 -->
        <section class="analysis-container" data-animate style="--delay: 0.1s">
          <div class="analysis-layout">
            <CollectionControlPanel
              v-model:selectedProjectId="selectedProjectId"
              v-model:sessionId="sessionId"
              v-model:transcriptText="transcriptText"
              :projects="projects"
              :isLoadingProjects="isLoadingProjects"
              :selectedProject="selectedProject"
              :selectedProjectHasSession="selectedProjectHasSession"
              :isSampleLoading="isSampleLoading"
              :options="options"
              :canStart="canStart"
              :pipelineState="pipelineState"
              @loadProjects="loadProjects"
              @loadSample="loadSampleTranscript"
              @run="runPipeline(selectedProjectId)"
              @retry="retryFromCurrentPhase"
              @goToRequirements="goToRequirements"
              @openAdvanced="openAdvanced"
            />
            <CollectionProgressPanel
              :pipelineState="pipelineState"
              :phases="phases"
              :logs="logs"
              :getPhaseStyle="getPhaseStyle"
              :showPostDedup="options.post_dedup"
            />
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Sidebar from '../../components/beta/Sidebar.vue'
import CollectionControlPanel from '../../components/beta/collection/CollectionControlPanel.vue'
import CollectionProgressPanel from '../../components/beta/collection/CollectionProgressPanel.vue'
import { useCollectionProjects } from '../../composables/useCollectionProjects'
import { useCollectionPipeline } from '../../composables/useCollectionPipeline'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const router = useRouter()
const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirements-collection')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

// ---- Composables ----
const {
  projects,
  selectedProjectId,
  isLoadingProjects,
  selectedProject,
  selectedProjectHasSession,
  currentProjectName,
  loadProjects,
} = useCollectionProjects()

const {
  sessionId,
  transcriptText,
  isSampleLoading,
  options,
  pipelineState,
  phases,
  logs,
  getPhaseStyle,
  runPipeline,
  retryFromCurrentPhase,
  loadSampleTranscript,
  goToRequirements,
} = useCollectionPipeline()

const canStart = computed(() =>
  transcriptText.value.trim().length > 0
  && !!selectedProjectId.value
  && !selectedProjectHasSession.value
)

function openAdvanced() {
  router.push({ name: 'beta-collection-advanced' })
}
</script>

<style scoped>
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
  gap: 16px;
  flex: 1;
  min-height: 0;
}
</style>
