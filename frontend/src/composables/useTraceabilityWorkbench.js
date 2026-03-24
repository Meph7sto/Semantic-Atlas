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
  const loadingOverview = ref(false)
  const loadingPanel = ref(false)
  const triggeringImpact = ref(false)
  const errorMessage = ref('')
  const overview = ref(null)
  const matrixData = ref(null)
  const coverageData = ref(null)
  const impactData = ref(null)
  const riskData = ref(null)

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

  async function loadOverview(projectId = selectedProjectId.value, branchId = selectedBranchId.value) {
    if (!projectId || !branchId) {
      overview.value = null
      return
    }
    loadingOverview.value = true
    errorMessage.value = ''
    try {
      overview.value = await manageApi.getTraceabilityOverview(projectId, branchId)
    } catch (error) {
      console.error('Failed to load traceability overview:', error)
      errorMessage.value = error.message || '加载追踪总览失败'
    } finally {
      loadingOverview.value = false
    }
  }

  async function loadActiveTabData() {
    if (!selectedProjectId.value || !selectedBranchId.value) return
    loadingPanel.value = true
    errorMessage.value = ''
    try {
      if (activeTab.value === 'matrix') {
        matrixData.value = await manageApi.getTraceabilityMatrix(selectedProjectId.value, selectedBranchId.value)
      } else if (activeTab.value === 'coverage') {
        coverageData.value = await manageApi.getTraceabilityCoverage(selectedProjectId.value, selectedBranchId.value)
      } else if (activeTab.value === 'risk') {
        riskData.value = await manageApi.getTraceabilityRisk(selectedProjectId.value, selectedBranchId.value)
      }
    } catch (error) {
      console.error('Failed to load traceability tab data:', error)
      errorMessage.value = error.message || '加载追踪面板失败'
    } finally {
      loadingPanel.value = false
    }
  }

  async function triggerImpactAnalysis(compareTo = 'baseline', milestoneId = null) {
    if (!selectedProjectId.value || !selectedBranchId.value) return null
    triggeringImpact.value = true
    errorMessage.value = ''
    try {
      impactData.value = await manageApi.createTraceabilityImpact(selectedProjectId.value, {
        branch_id: selectedBranchId.value,
        compare_to: compareTo,
        milestone_id: milestoneId,
      })
      return impactData.value
    } catch (error) {
      console.error('Failed to create traceability impact report:', error)
      errorMessage.value = error.message || '触发影响分析失败'
      return null
    } finally {
      triggeringImpact.value = false
    }
  }

  function selectTab(tabKey) {
    activeTab.value = tabKey
  }

  async function refreshContext() {
    await loadProjects()
    if (selectedProjectId.value) {
      await loadBranches(selectedProjectId.value)
      await loadOverview(selectedProjectId.value, selectedBranchId.value)
      await loadActiveTabData()
    }
  }

  watch(selectedProjectId, async (projectId) => {
    if (projectId) {
      localStorage.setItem('lastProjectId', projectId)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId } }))
    }
    await loadBranches(projectId)
  })

  watch([selectedProjectId, selectedBranchId], async ([projectId, branchId]) => {
    if (!projectId || !branchId) {
      overview.value = null
      matrixData.value = null
      coverageData.value = null
      impactData.value = null
      riskData.value = null
      return
    }
    await loadOverview(projectId, branchId)
    await loadActiveTabData()
  })

  watch(activeTab, async () => {
    await loadActiveTabData()
  })

  onMounted(async () => {
    await refreshContext()
  })

  return {
    activeTab,
    branches,
    errorMessage,
    coverageData,
    impactData,
    loadingBranches,
    loadingOverview,
    loadingPanel,
    loadingProjects,
    matrixData,
    projects,
    overview,
    riskData,
    selectedBranch,
    selectedBranchId,
    selectedProject,
    selectedProjectId,
    selectTab,
    refreshContext,
    tabs,
    triggerImpactAnalysis,
    triggeringImpact,
  }
}
