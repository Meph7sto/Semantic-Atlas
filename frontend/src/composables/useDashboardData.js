/**
 * useDashboardData — Dashboard 数据获取与聚合
 *
 * 从已有后端 API 组合计算仪表盘所需的统计数据。
 * 不修改任何后端接口，所有聚合在前端完成。
 */

import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { manageApi } from '@/api/project'
import { useAuthStore } from '@/stores/auth'

// ─── 常量 ───

const UNRESOLVED_DEFECT_STATUSES = new Set(['open', 'in_progress', 'resolved'])
const OVERDUE_DEFECT_DAYS = 7
const REVIEW_DUE_SOON_DAYS = 3

// ─── 辅助函数 ───

function isWithinDays(dateStr, days) {
  if (!dateStr) return false
  const target = new Date(dateStr)
  const now = new Date()
  const diff = target.getTime() - now.getTime()
  return diff >= 0 && diff <= days * 24 * 60 * 60 * 1000
}

function isOverdueDays(dateStr, days) {
  if (!dateStr) return false
  const created = new Date(dateStr)
  const now = new Date()
  return (now.getTime() - created.getTime()) > days * 24 * 60 * 60 * 1000
}

function hasRequiredFields(req) {
  return Boolean(req.title && req.description && req.priority)
}

function formatRelativeTime(isoString) {
  if (!isoString) return '—'
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / (1000 * 60))
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr} 小时前`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay} 天前`
}

// ─── Composable ───

export function useDashboardData() {
  const authStore = useAuthStore()

  // ---- 原始数据 ----
  const projects = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const requirements = ref([])
  const defects = ref([])
  const milestones = ref([])
  const auditLogs = ref([])

  // ---- 状态 ----
  const isLoadingProjects = ref(false)
  const isLoadingData = ref(false)
  const loadError = ref(null)
  const lastRefreshedAt = ref(null)
  const isSyncingProjectFromEvent = ref(false)

  // ========================
  // 计算属性：需求统计
  // ========================

  const reqStats = computed(() => {
    const reqs = requirements.value
    const total = reqs.length
    const draft = reqs.filter(r => r.status === 'draft').length
    const underReview = reqs.filter(r => r.status === 'under_review').length
    const confirmed = reqs.filter(r => r.status === 'confirmed').length
    const inProgress = reqs.filter(r => r.status === 'in_progress').length
    const completed = reqs.filter(r => r.status === 'completed').length
    return { total, draft, underReview, confirmed, inProgress, completed }
  })

  // ========================
  // 计算属性：评审队列
  // ========================

  const reviewStats = computed(() => {
    const userId = authStore.userId
    const reviewReqs = requirements.value.filter(r => r.status === 'under_review')
    const total = reviewReqs.length
    const dueSoon = reviewReqs.filter(r => isWithinDays(r.due_date, REVIEW_DUE_SOON_DAYS)).length
    const myParticipation = userId
      ? reviewReqs.filter(r => r.assignee === userId).length
      : 0
    return { total, dueSoon, myParticipation }
  })

  // ========================
  // 计算属性：缺陷统计
  // ========================

  const defectStats = computed(() => {
    const defs = defects.value
    const unresolved = defs.filter(d => UNRESOLVED_DEFECT_STATUSES.has(d.status))
    const total = unresolved.length
    const overdue = unresolved.filter(d => isOverdueDays(d.created_at, OVERDUE_DEFECT_DAYS)).length
    const unassigned = unresolved.filter(d => !d.current_assignee).length
    return { total, overdue, unassigned }
  })

  // ========================
  // 计算属性：基线状态
  // ========================

  const baselineInfo = computed(() => {
    const ms = milestones.value
    if (ms.length === 0) return { status: 'N/A', diffCount: 0, candidateCount: 0 }
    return {
      status: 'Ready',
      diffCount: ms.length,
      candidateCount: ms.filter(m => !m.baseline_at).length,
    }
  })

  // ========================
  // 计算属性：门禁指标
  // ========================

  const gateMetrics = computed(() => {
    const reqs = requirements.value
    if (reqs.length === 0) {
      return { completeness: 0, pendingClarification: 0, highRiskCount: 0 }
    }
    const completeCount = reqs.filter(hasRequiredFields).length
    const completeness = Math.round((completeCount / reqs.length) * 100)
    const pendingClarification = reqs.filter(r => r.status === 'clarification').length
    const highRiskCount = reqs.filter(
      r => r.priority === 'high' && r.status !== 'completed'
    ).length
    return { completeness, pendingClarification, highRiskCount }
  })

  // ========================
  // 计算属性：最近活动
  // ========================

  const latestActivityTime = computed(() => {
    if (auditLogs.value.length === 0) return null
    return auditLogs.value[0]?.created_at || null
  })

  const latestActivityLabel = computed(() => {
    return formatRelativeTime(latestActivityTime.value)
  })

  // ========================
  // 计算属性：我的工作台
  // ========================

  const myTodos = computed(() => {
    const userId = authStore.userId
    if (!userId) return []
    return requirements.value
      .filter(r =>
        r.assignee === userId &&
        (r.status === 'draft' || r.status === 'in_progress')
      )
      .map(r => ({
        ...r,
        priorityLabel: r.priority === 'high' ? 'P1' : r.priority === 'medium' ? 'P2' : 'P3',
        isOverdue: r.due_date ? new Date(r.due_date) < new Date() : false,
      }))
      .sort((a, b) => {
        const order = { high: 0, medium: 1, low: 2 }
        return (order[a.priority] ?? 2) - (order[b.priority] ?? 2)
      })
  })

  const myReviews = computed(() => {
    return requirements.value
      .filter(r => r.status === 'under_review')
      .map(r => ({
        ...r,
        dueSoonLabel: isWithinDays(r.due_date, REVIEW_DUE_SOON_DAYS) ? '即将到期' : '',
      }))
      .sort((a, b) => {
        if (!a.due_date) return 1
        if (!b.due_date) return -1
        return new Date(a.due_date) - new Date(b.due_date)
      })
  })

  // ========================
  // 数据加载
  // ========================

  async function loadProjects() {
    isLoadingProjects.value = true
    try {
      const resp = await manageApi.listProjects()
      projects.value = resp.projects || []
      if (!projects.value.length) {
        selectedProjectId.value = ''
        return
      }

      const hasSelectedProject = projects.value.some(
        (project) => project.project_id === selectedProjectId.value,
      )
      if (!hasSelectedProject) {
        selectedProjectId.value = projects.value[0].project_id
      }
    } catch (err) {
      console.error('Failed to load projects:', err)
      projects.value = []
    } finally {
      isLoadingProjects.value = false
    }
  }

  async function loadDashboardData() {
    const projectId = selectedProjectId.value
    if (!projectId) {
      requirements.value = []
      defects.value = []
      milestones.value = []
      auditLogs.value = []
      loadError.value = null
      return
    }

    isLoadingData.value = true
    loadError.value = null

    try {
      const [reqResp, defResp, msResp, auditResp] = await Promise.allSettled([
        manageApi.listRequirements(projectId),
        manageApi.listDefects(projectId),
        manageApi.listMilestones(projectId),
        manageApi.listAudits(projectId, 20),
      ])

      requirements.value = reqResp.status === 'fulfilled'
        ? (reqResp.value.requirements || [])
        : []
      defects.value = defResp.status === 'fulfilled'
        ? (defResp.value.defects || [])
        : []
      milestones.value = msResp.status === 'fulfilled'
        ? (msResp.value.milestones || msResp.value || [])
        : []
      auditLogs.value = auditResp.status === 'fulfilled'
        ? (auditResp.value.logs || [])
        : []

      // 收集加载失败的部分
      const failures = [reqResp, defResp, msResp, auditResp]
        .filter(r => r.status === 'rejected')
        .map(r => r.reason?.message || '未知错误')
      if (failures.length > 0) {
        loadError.value = `部分数据加载失败: ${failures.join('; ')}`
      }

      lastRefreshedAt.value = new Date().toLocaleString('zh-CN')
    } catch (err) {
      loadError.value = `加载失败: ${err.message}`
      console.error('Dashboard data load error:', err)
    } finally {
      isLoadingData.value = false
    }
  }

  async function refresh() {
    await loadDashboardData()
  }

  function syncProjectFromStorage() {
    const nextProjectId = localStorage.getItem('lastProjectId') || ''
    if (nextProjectId === selectedProjectId.value) return
    isSyncingProjectFromEvent.value = true
    selectedProjectId.value = nextProjectId
  }

  function handleProjectChanged(event) {
    const nextProjectId = String(
      event?.detail?.projectId ?? localStorage.getItem('lastProjectId') ?? '',
    ).trim()
    if (nextProjectId === selectedProjectId.value) return
    isSyncingProjectFromEvent.value = true
    selectedProjectId.value = nextProjectId
  }

  // 切换项目时自动加载
  watch(selectedProjectId, (val) => {
    const shouldBroadcast = !isSyncingProjectFromEvent.value
    isSyncingProjectFromEvent.value = false

    if (val) {
      localStorage.setItem('lastProjectId', val)
    } else {
      localStorage.removeItem('lastProjectId')
    }

    if (shouldBroadcast) {
      window.dispatchEvent(
        new CustomEvent('project-changed', { detail: { projectId: val } }),
      )
    }

    loadDashboardData()
  })

  onMounted(() => {
    window.addEventListener('project-changed', handleProjectChanged)
    syncProjectFromStorage()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('project-changed', handleProjectChanged)
  })

  return {
    // 原始数据
    projects,
    selectedProjectId,
    requirements,
    defects,
    milestones,
    auditLogs,

    // 状态
    isLoadingProjects,
    isLoadingData,
    loadError,
    lastRefreshedAt,

    // 计算属性
    reqStats,
    reviewStats,
    defectStats,
    baselineInfo,
    gateMetrics,
    latestActivityLabel,
    myTodos,
    myReviews,

    // 方法
    loadProjects,
    loadDashboardData,
    refresh,
  }
}
