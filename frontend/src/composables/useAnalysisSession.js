import { ref, computed, watch } from 'vue'
import { manageApi } from '@/api/project'
import { requirementsL123Api, l4RequirementsApi, analysisApi } from '@/api/requirements'

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

export function useAnalysisSession() {
  // 项目状态
  const projects = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const isLoadingProjects = ref(false)
  const projectSessionId = ref('')

  const currentProjectName = computed(() => {
    const p = projects.value.find(p => p.project_id === selectedProjectId.value)
    return p ? p.name : '未选择项目'
  })

  async function loadProjects() {
    isLoadingProjects.value = true
    try {
      const data = await manageApi.listProjects()
      projects.value = data?.projects || []
    } catch (err) {
      console.warn('加载项目列表失败', err)
      projects.value = []
    } finally {
      isLoadingProjects.value = false
    }
  }

  async function loadProjectSession() {
    if (!selectedProjectId.value) return
    try {
      const proj = await manageApi.getProject(selectedProjectId.value)
      if (proj?.current_session_id) {
        projectSessionId.value = proj.current_session_id
        if (!sessionId.value) {
          sessionId.value = proj.current_session_id
        }
      }
    } catch (err) {
      console.warn('加载项目 Session 失败', err)
    }
  }

  // Session 与 Context Run 状态
  const sessionId = ref(localStorage.getItem('lastSessionId') || '')
  const contextRunId = ref('')
  const contextRuns = ref([])
  const isLoadingRuns = ref(false)

  // 需求数据（由分析 composable 共享写入）
  const highLevelRequirements = ref([])
  const lowLevelRequirements = ref([])

  watch(sessionId, (newVal) => {
    if (newVal && newVal.trim()) {
      localStorage.setItem('lastSessionId', newVal.trim())
      window.dispatchEvent(new CustomEvent('session-changed', { detail: { sessionId: newVal.trim() } }))
    }
  })

  watch(selectedProjectId, (val) => {
    if (val) {
      localStorage.setItem('lastProjectId', val)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: val } }))
      loadProjectSession()
    }
  })

  async function loadContextRuns() {
    isLoadingRuns.value = true
    try {
      const runs = await analysisApi.listContextRuns(sessionId.value.trim())
      contextRuns.value = Array.isArray(runs) ? runs : []
    } catch {
      contextRuns.value = []
    } finally {
      isLoadingRuns.value = false
    }
  }

  async function loadRequirements() {
    if (!sessionId.value.trim()) return
    try {
      const data = await requirementsL123Api.listBySession(sessionId.value.trim(), { page: 1, perPage: 200 })
      highLevelRequirements.value = (data.requirements || []).map((req) => ({
        ...req,
        level: normalizeLevel(req.level || req.category),
      }))
      try {
        const l4Data = await l4RequirementsApi.getBySession(sessionId.value.trim(), { perPage: 500 })
        lowLevelRequirements.value = (l4Data.requirements || []).map(r => ({
          ...r,
          level: 'L4',
          statement: r.text || r.shall_statement || '',
        }))
      } catch {
        lowLevelRequirements.value = []
      }
    } catch (err) {
      console.error('加载需求失败:', err)
    }
  }

  return {
    projects,
    selectedProjectId,
    isLoadingProjects,
    projectSessionId,
    currentProjectName,
    loadProjects,
    loadProjectSession,
    sessionId,
    contextRunId,
    contextRuns,
    isLoadingRuns,
    highLevelRequirements,
    lowLevelRequirements,
    loadContextRuns,
    loadRequirements,
  }
}

