import { computed, onMounted, ref, watch } from 'vue'
import { manageApi } from '@/api/project'

const DEFAULT_TAB = 'matrix'

export function useTraceabilityWorkbench() {
  const projects = ref([])
  const branches = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const selectedBranchId = ref('')
  const activeTab = ref(DEFAULT_TAB)
  const loadingProjects = ref(false)
  const loadingBranches = ref(false)
  const errorMessage = ref('')

  const tabs = [
    { key: 'matrix', label: '追溯矩阵' },
    { key: 'coverage', label: '覆盖检查' },
    { key: 'impact', label: '影响分析' },
    { key: 'risk', label: '风险透视' },
  ]

  const selectedProject = computed(() =>
    projects.value.find((project) => project.project_id === selectedProjectId.value) || null,
  )

  const selectedBranch = computed(() =>
    branches.value.find((branch) => branch.ref_id === selectedBranchId.value) || null,
  )

  async function loadProjects() {
    loadingProjects.value = true
    errorMessage.value = ''
    try {
      const resp = await manageApi.listProjects()
      projects.value = resp.projects || []
      if (!selectedProjectId.value && projects.value.length > 0) {
        selectedProjectId.value = projects.value[0].project_id
      }
    } catch (error) {
      console.error('Failed to load traceability projects:', error)
      errorMessage.value = error.message || '加载项目失败'
    } finally {
      loadingProjects.value = false
    }
  }

  async function loadBranches(projectId = selectedProjectId.value) {
    branches.value = []
    selectedBranchId.value = ''
    if (!projectId) return

    loadingBranches.value = true
    errorMessage.value = ''
    try {
      const resp = await manageApi.listBranches(projectId)
      branches.value = resp.branches || []
      if (branches.value.length > 0) {
        selectedBranchId.value = branches.value[0].ref_id
      }
    } catch (error) {
      console.error('Failed to load traceability branches:', error)
      errorMessage.value = error.message || '加载分支失败'
    } finally {
      loadingBranches.value = false
    }
  }

  function selectTab(tabKey) {
    activeTab.value = tabKey
  }

  async function refreshContext() {
    await loadProjects()
    if (selectedProjectId.value) {
      await loadBranches(selectedProjectId.value)
    }
  }

  watch(selectedProjectId, async (projectId) => {
    if (projectId) {
      localStorage.setItem('lastProjectId', projectId)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId } }))
    }
    await loadBranches(projectId)
  })

  onMounted(async () => {
    await refreshContext()
  })

  return {
    activeTab,
    branches,
    errorMessage,
    loadingBranches,
    loadingProjects,
    projects,
    selectedBranch,
    selectedBranchId,
    selectedProject,
    selectedProjectId,
    selectTab,
    refreshContext,
    tabs,
  }
}
