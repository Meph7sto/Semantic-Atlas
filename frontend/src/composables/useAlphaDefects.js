import { computed, ref } from 'vue'
import { manageApi } from '@/api/project'

const SEVERITY_OPTIONS = [
  { value: 'critical', label: '致命' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
]

const PRIORITY_OPTIONS = [
  { value: 'P0', label: 'P0 - 最高' },
  { value: 'P1', label: 'P1 - 高' },
  { value: 'P2', label: 'P2 - 中' },
  { value: 'P3', label: 'P3 - 低' },
]

const STATUS_OPTIONS = [
  { value: 'open', label: '待修复' },
  { value: 'in_progress', label: '修复中' },
  { value: 'resolved', label: '待验证' },
  { value: 'verified', label: '验证通过' },
  { value: 'closed', label: '已关闭' },
  { value: 'rejected', label: '已拒绝' },
]

const UNRESOLVED_STATUSES = new Set(['open', 'in_progress', 'resolved'])

export function useAlphaDefects(projectIdRef) {
  const defects = ref([])
  const loading = ref(false)
  const error = ref('')

  const unresolvedCount = computed(() =>
    defects.value.filter((item) => UNRESOLVED_STATUSES.has(item.status)).length,
  )

  const criticalCount = computed(() =>
    defects.value.filter(
      (item) => item.severity === 'critical' && UNRESOLVED_STATUSES.has(item.status),
    ).length,
  )

  const byAssignee = computed(() => {
    const result = {}
    defects.value
      .filter((item) => UNRESOLVED_STATUSES.has(item.status))
      .forEach((item) => {
        const key = item.current_assignee || item.dev_assignee || '未指派'
        result[key] = (result[key] || 0) + 1
      })
    return Object.entries(result)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  })

  const defectsByRequirementId = computed(() => {
    const map = new Map()
    defects.value.forEach((item) => {
      const rid = item.requirement_id
      if (!rid) return
      if (!map.has(rid)) map.set(rid, [])
      map.get(rid).push(item)
    })
    return map
  })

  async function reload() {
    const projectId = projectIdRef?.value
    if (!projectId) {
      defects.value = []
      return []
    }
    loading.value = true
    error.value = ''
    try {
      const data = await manageApi.listDefects(projectId)
      defects.value = data.defects || []
      return defects.value
    } catch (err) {
      error.value = err?.message || '加载缺陷失败'
      defects.value = []
      throw err
    } finally {
      loading.value = false
    }
  }

  async function createDefect(payload) {
    const projectId = projectIdRef?.value
    if (!projectId) throw new Error('缺少项目ID')
    const created = await manageApi.createDefect(projectId, payload)
    defects.value = [created, ...defects.value.filter((item) => item.defect_id !== created.defect_id)]
    return created
  }

  async function updateDefect(defectId, patch) {
    const updated = await manageApi.updateDefect(defectId, patch)
    const idx = defects.value.findIndex((item) => item.defect_id === defectId)
    if (idx >= 0) {
      defects.value.splice(idx, 1, updated)
    } else {
      defects.value = [updated, ...defects.value]
    }
    return updated
  }

  async function setStatus(defectId, nextStatus) {
    return updateDefect(defectId, { status: nextStatus })
  }

  async function deleteDefect(defectId) {
    await manageApi.deleteDefect(defectId)
    defects.value = defects.value.filter((item) => item.defect_id !== defectId)
  }

  function unresolvedForRequirement(requirementId) {
    return defects.value.filter(
      (item) => item.requirement_id === requirementId && UNRESOLVED_STATUSES.has(item.status),
    )
  }

  return {
    defects,
    loading,
    error,
    unresolvedCount,
    criticalCount,
    byAssignee,
    defectsByRequirementId,
    reload,
    createDefect,
    updateDefect,
    setStatus,
    deleteDefect,
    unresolvedForRequirement,
    severityOptions: SEVERITY_OPTIONS,
    priorityOptions: PRIORITY_OPTIONS,
    statusOptions: STATUS_OPTIONS,
    unresolvedStatuses: UNRESOLVED_STATUSES,
  }
}
