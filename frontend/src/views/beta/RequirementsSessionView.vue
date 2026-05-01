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
            <span class="nav-title">项目管理 · 会话需求</span>
          </div>
          <div class="nav-center">
            <SessionHeaderBar
              :projects="projects"
              :selectedProjectId="selectedProjectId"
              :sessionIdDraft="sessionIdDraft"
              :sessionMismatch="sessionMismatch"
              :projectSessionId="projectSessionId"
              @update:selectedProjectId="selectedProjectId = $event"
              @update:sessionIdDraft="sessionIdDraft = $event"
              @commit="commitSessionId"
              @clear="clearSessionId"
              @useProjectSession="useProjectSession"
            />
          </div>
          <div class="page-actions">
            <button
              type="button"
              class="action-btn white sa-button sa-button--secondary"
              :disabled="!selectedProjectId || !sessionId || isImportingToManage"
              @click="handleImportToManage"
            >
              <Database class="w-4 h-4" :class="{ 'animate-pulse': isImportingToManage }" />
              {{ isImportingToManage ? '导入中...' : '导入到项目需求' }}
            </button>
            <button
              type="button"
              class="action-btn primary sa-button sa-button--primary"
              :disabled="!selectedProjectId"
              @click="openAddRequirementModal"
            >
              <Plus class="w-4 h-4" />
              新增需求
            </button>
            <button
              type="button"
              class="action-btn brown sa-button sa-button--primary"
              :disabled="isLoading"
              @click="refreshData"
            >
              <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
              {{ isLoading ? '加载中' : '刷新' }}
            </button>
          </div>
        </section>

        <!-- 新增需求弹窗 -->
        <AddRequirementModal
          v-if="showAddRequirementModal"
          :form="newRequirement"
          :parentRequirementOptions="parentRequirementOptions"
          :isSubmitting="isSubmitting"
          @close="closeAddRequirementModal"
          @submit="submitNewRequirement"
        />

        <!-- 编辑需求弹窗 -->
        <EditRequirementModal
          v-if="showEditRequirementModal"
          :form="editRequirement"
          :isSubmitting="isEditSubmitting"
          @close="closeEditRequirementModal"
          @submit="submitEditRequirement"
        />

        <!-- 工具栏 -->
        <RequirementsToolbar
          v-model:activeLevel="activeLevel"
          v-model:activeView="activeView"
          :levelTabs="levelTabs"
          :levelCounts="levelCounts"
        />

        <!-- 内容区域 -->
        <section class="requirements-content" data-animate style="--delay: 0.15s">
          <!-- 加载状态 -->
          <div v-if="isLoading" class="loading-state">
            <Loader2 class="animate-spin" />
            <p>正在加载需求数据...</p>
          </div>

          <!-- 空状态 -->
          <div v-else-if="filteredRequirements.length === 0" class="empty-state">
            <FileText class="empty-icon" />
            <p v-if="!sessionId">未选择 Session ID</p>
            <p v-else>暂无需求数据</p>
            <p class="empty-hint">
              {{ !sessionId ? '请先前往「需求分析」界面选择或输入 Session ID' : '请先在「需求分析」界面进行一键分析' }}
            </p>
            <button
              v-if="!sessionId"
              type="button"
              class="action-btn brown mt-4 sa-button sa-button--primary"
              @click="router.push({ name: 'beta-requirements-analysis' })"
            >
              前往需求分析
            </button>
          </div>

          <!-- 树状视图 -->
          <TreeViewSection
            v-else-if="activeView === 'tree'"
            :filteredTreeData="filteredTreeData"
            :hoveredNode="hoveredNode"
            @hover="handleNodeHover"
            @clickNode="handleNodeClick"
          />

          <!-- 表格视图 -->
          <TableViewSection
            v-else-if="activeView === 'table'"
            :filteredRequirements="filteredRequirements"
            :requirementStatuses="requirementStatuses"
            @editRequirement="openEditRequirementModal"
            @updateStatus="updateRequirementStatus"
          />

          <!-- 看板视图 -->
          <KanbanViewSection
            v-else-if="activeView === 'card'"
            :backlog="backlogRequirements"
            :inProgress="inProgressRequirements"
            :completed="completedRequirements"
            :filteredCount="filteredRequirements.length"
            @dragChange="onDragChange"
          />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Loader2, FileText, RefreshCw, Database, Plus } from 'lucide-vue-next'
import Sidebar from '../../components/beta/Sidebar.vue'
import SessionHeaderBar from '../../components/beta/session/SessionHeaderBar.vue'
import AddRequirementModal from '../../components/beta/session/AddRequirementModal.vue'
import EditRequirementModal from '../../components/beta/session/EditRequirementModal.vue'
import RequirementsToolbar from '../../components/beta/session/RequirementsToolbar.vue'
import TreeViewSection from '../../components/beta/session/TreeViewSection.vue'
import TableViewSection from '../../components/beta/session/TableViewSection.vue'
import KanbanViewSection from '../../components/beta/session/KanbanViewSection.vue'
import { useSessionRequirements } from '../../composables/useSessionRequirements'
import { useRequirementModals } from '../../composables/useRequirementModals'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const router = useRouter()
const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirements-session')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

// 需求数据与会话状态
const {
  isLoading,
  projects, selectedProjectId, isLoadingProjects, projectSessionId, sessionMismatch,
  sessionId, sessionIdDraft,
  requirementStatuses, levelTabs,
  backlogRequirements, inProgressRequirements, completedRequirements,
  isImportingToManage,
  manageReqIdMap, managePriorityMap,
  activeLevel, activeView, hoveredNode,
  filteredRequirements, filteredTreeData, parentRequirementOptions, levelCounts,
  loadProjects, loadProjectSession, loadRequirements, loadManageRequirementMap,
  commitSessionId, clearSessionId, useProjectSession,
  updateRequirementStatus, onDragChange, importSessionRequirementsToManage, refreshData,
  handleNodeHover, handleNodeClick,
  handleSessionChanged, handleAnalysisCompleted, syncProjectFromStorage, syncProjectFromLocation,
} = useSessionRequirements()

// 弹窗状态
const {
  showAddRequirementModal, isSubmitting, newRequirement,
  openAddRequirementModal, closeAddRequirementModal, submitNewRequirement,
  showEditRequirementModal, isEditSubmitting, editRequirement,
  openEditRequirementModal, closeEditRequirementModal, submitEditRequirement,
} = useRequirementModals(
  selectedProjectId,
  sessionId,
  manageReqIdMap,
  managePriorityMap,
  { loadRequirements, loadManageRequirementMap, resolveManageReqId }
)

function resolveManageReqId(item) {
  const candidates = [item.manage_req_id, item.req_id, item.id, item.source_req_id, item.source_top_id].filter(Boolean)
  for (const key of candidates) {
    if (manageReqIdMap.value.has(key)) return manageReqIdMap.value.get(key)
  }
  return candidates[0] || ''
}

function handleImportToManage() {
  importSessionRequirementsToManage(router)
}


onMounted(async () => {
  window.addEventListener('session-changed', handleSessionChanged)
  window.addEventListener('analysis-completed', handleAnalysisCompleted)
  window.addEventListener('project-changed', syncProjectFromStorage)

  syncProjectFromLocation()
  syncProjectFromStorage()

  await loadProjects()

  if (selectedProjectId.value) {
    await loadProjectSession()
    if (!sessionId.value && projectSessionId.value) {
      sessionId.value = projectSessionId.value
      sessionIdDraft.value = projectSessionId.value
    }
  }

  loadRequirements()
})

onUnmounted(() => {
  window.removeEventListener('session-changed', handleSessionChanged)
  window.removeEventListener('analysis-completed', handleAnalysisCompleted)
  window.removeEventListener('project-changed', syncProjectFromStorage)
})
</script>

<style scoped>
.requirements-content {
  flex: 1;
  overflow: hidden;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: rgba(28, 40, 52, 0.5);
}

.loading-state svg { width: 48px; height: 48px; margin-bottom: 16px; opacity: 0.3; }
.empty-icon { width: 48px; height: 48px; margin-bottom: 16px; opacity: 0.3; }
.empty-hint { font-size: 13px; margin-top: 8px; color: rgba(28, 40, 52, 0.4); }
</style>
