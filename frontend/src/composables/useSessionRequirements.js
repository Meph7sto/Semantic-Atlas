import { ref, computed, watch } from 'vue'
import { requirementsL123Api, l4RequirementsApi, analysisApi } from '@/api/requirements'
import { manageApi } from '@/api/project'

// ---- 纯工具函数 ----
export function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

export function normalizePriority(raw, fallback = 'medium') {
  const text = String(raw ?? '').trim()
  if (!text) return fallback
  const normalized = text.toLowerCase()
  return ['low', 'medium', 'high'].includes(normalized) ? normalized : fallback
}

export function useSessionRequirements() {
  // 数据状态
  const isLoading = ref(false)
  const highLevelRequirements = ref([])
  const lowLevelRequirements = ref([])
  const requirementTree = ref([])
  const traceRelations = ref([])

  // 项目/Session 状态
  const projects = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const isLoadingProjects = ref(false)
  const projectSessionId = ref('')
  const sessionMismatch = ref(false)
  const sessionId = ref(localStorage.getItem('lastSessionId') || '')
  const sessionIdDraft = ref(sessionId.value)

  // 状态管理相关
  const requirementStatusMap = ref({})
  const backlogRequirements = ref([])
  const inProgressRequirements = ref([])
  const completedRequirements = ref([])
  const isSyncingStatus = ref(false)
  const isImportingToManage = ref(false)
  const manageReqIdMap = ref(new Map())
  const manageStatusMap = ref(new Map())
  const managePriorityMap = ref(new Map())

  // 视图状态
  const activeLevel = ref('all')
  const activeView = ref('tree')
  const hoveredNode = ref(null)

  // 层级标签配置
  const levelTabs = [
    { key: 'all', label: '全部需求' },
    { key: 'L1', label: 'L1' },
    { key: 'L2', label: 'L2' },
    { key: 'L3', label: 'L3' },
    { key: 'L4', label: 'L4' },
  ]

  const requirementStatuses = [
    { id: 'backlog', name: '待处理', color: 'zinc' },
    { id: 'in_progress', name: '进行中', color: 'blue' },
    { id: 'completed', name: '已完成', color: 'emerald' },
  ]

  // ---- 计算属性 ----
  const filteredRequirements = computed(() => {
    const all = [
      ...highLevelRequirements.value.map(r => {
        const id = r.req_id || r.id
        return {
          ...r,
          id,
          level: normalizeLevel(r.level || r.category),
          statement: r.text || r.statement || r.title || '',
          status: requirementStatusMap.value[id] || 'backlog',
        }
      }),
      ...lowLevelRequirements.value.map(r => {
        const id = r.req_id || r.id
        return {
          ...r,
          id,
          level: 'L4',
          statement: r.text || r.statement || r.shall_statement || '',
          status: requirementStatusMap.value[id] || 'backlog',
        }
      }),
    ]
    if (activeLevel.value === 'all') return all
    return all.filter(r => r.level === activeLevel.value)
  })

  const filteredTreeData = computed(() => {
    if (activeLevel.value === 'all') return requirementTree.value
    return filterTreeByLevel(requirementTree.value, activeLevel.value)
  })

  const parentRequirementOptions = computed(() => {
    const all = [
      ...highLevelRequirements.value.map(r => ({
        req_id: r.req_id || r.id,
        title: r.text || r.statement || r.title,
        level: normalizeLevel(r.level || r.category),
      })),
      ...lowLevelRequirements.value.map(r => ({
        req_id: r.req_id || r.id,
        title: r.text || r.statement || r.shall_statement,
        level: 'L4',
      })),
    ]
    return all.filter(r => r.req_id)
  })

  const levelCounts = computed(() => ({
    all: highLevelRequirements.value.length + lowLevelRequirements.value.length,
    L1: highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L1').length,
    L2: highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L2').length,
    L3: highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L3').length,
    L4: lowLevelRequirements.value.length,
  }))

  // ---- 辅助函数 ----
  function getStatusName(statusId) {
    return requirementStatuses.find(s => s.id === statusId)?.name || '待处理'
  }

  function getStatusColorClass(statusId, variant = 'bg') {
    const color = requirementStatuses.find(s => s.id === statusId)?.color || 'zinc'
    const colorMap = {
      zinc:    { bg: 'bg-zinc-100',    text: 'text-zinc-700',    border: 'border-zinc-200',    dot: 'bg-zinc-400' },
      blue:    { bg: 'bg-blue-100',    text: 'text-blue-700',    border: 'border-blue-200',    dot: 'bg-blue-500' },
      emerald: { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' },
    }
    return colorMap[color]?.[variant] || colorMap.zinc[variant]
  }

  function getLevelBadgeClass(level) {
    const map = {
      L1: 'bg-sky-100 text-sky-700 border-sky-200',
      L2: 'bg-violet-100 text-violet-700 border-violet-200',
      L3: 'bg-amber-100 text-amber-700 border-amber-200',
      L4: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    }
    return map[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200'
  }

  function getConfidenceClass(conf) {
    if (conf >= 0.8) return 'conf-high'
    if (conf >= 0.5) return 'conf-medium'
    return 'conf-low'
  }

  function getTypeLabel(type) {
    const labels = { 'top_level': '顶层需求', 'low_level': '底层需求', 'task': '任务' }
    return labels[type] || type || '-'
  }

  function mapManageStatusToLocal(status) {
    if (status === 'completed' || status === 'archived') return 'completed'
    if (['in_progress', 'under_review', 'confirmed'].includes(status)) return 'in_progress'
    return 'backlog'
  }

  function mapLocalStatusToManage(status) {
    if (status === 'completed') return 'completed'
    if (status === 'in_progress') return 'in_progress'
    return 'draft'
  }

  function filterTreeByLevel(nodes, level) {
    if (!nodes || nodes.length === 0) return []
    return nodes.map(node => {
      const req = node.requirement || {}
      const nodeLevel = normalizeLevel(req.requirement_type || req.level || req.category)
      const children = filterTreeByLevel(node.children || [], level)
      if (nodeLevel === level || children.length > 0) return { ...node, children }
      return null
    }).filter(n => n !== null)
  }

  function resolveManageReqId(item) {
    const candidates = [item.manage_req_id, item.req_id, item.id, item.source_req_id, item.source_top_id].filter(Boolean)
    for (const key of candidates) {
      if (manageReqIdMap.value.has(key)) return manageReqIdMap.value.get(key)
    }
    return candidates[0] || ''
  }

  // ---- 项目/Session 操作 ----
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
    if (!selectedProjectId.value) {
      projectSessionId.value = ''
      sessionMismatch.value = false
      return
    }
    try {
      const proj = await manageApi.getProject(selectedProjectId.value)
      projectSessionId.value = proj?.current_session_id || ''
      checkSessionMismatch()
    } catch (err) {
      console.warn('加载项目 Session 失败', err)
    }
  }

  function checkSessionMismatch() {
    if (!selectedProjectId.value || !projectSessionId.value || !sessionId.value) {
      sessionMismatch.value = false
      return
    }
    sessionMismatch.value = sessionId.value !== projectSessionId.value
  }

  function useProjectSession() {
    if (projectSessionId.value) {
      sessionIdDraft.value = projectSessionId.value
      sessionId.value = projectSessionId.value
      sessionMismatch.value = false
    }
  }

  function commitSessionId() {
    const next = String(sessionIdDraft.value || '').trim()
    sessionIdDraft.value = next
    if (next !== sessionId.value) sessionId.value = next
  }

  function clearSessionId() {
    sessionIdDraft.value = ''
    if (sessionId.value) sessionId.value = ''
    localStorage.removeItem('lastSessionId')
  }

  function syncProjectFromStorage() {
    const pid = localStorage.getItem('lastProjectId') || ''
    if (pid && pid !== selectedProjectId.value) selectedProjectId.value = pid
  }

  function syncProjectFromLocation() {
    try {
      const url = new URL(window.location.href)
      const pid = (url.searchParams.get('project_id') || url.searchParams.get('projectId') || '').trim()
      if (pid && pid !== selectedProjectId.value) {
        selectedProjectId.value = pid
        localStorage.setItem('lastProjectId', pid)
        window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: pid } }))
      }
    } catch (_) { /* ignore */ }
  }

  // ---- 需求数据加载 ----
  async function ensureProjectId() {
    if (selectedProjectId.value) return
    try {
      const data = await manageApi.listProjects()
      const list = data?.projects || []
      if (list.length === 1) {
        selectedProjectId.value = list[0].project_id
        localStorage.setItem('lastProjectId', selectedProjectId.value)
      }
    } catch (err) {
      console.warn('加载项目列表失败，无法同步状态到数据库', err)
    }
  }

  async function loadManageRequirementMap() {
    if (!selectedProjectId.value) return
    try {
      const data = await manageApi.listRequirements(selectedProjectId.value)
      const reqs = data?.requirements || []
      const idMap = new Map()
      const statusMap = new Map()
      const priorityMap = new Map()

      reqs.forEach((req) => {
        if (req.req_id) {
          idMap.set(req.req_id, req.req_id)
          statusMap.set(req.req_id, req.status)
          priorityMap.set(req.req_id, normalizePriority(req.priority, null))
        }
        if (req.source_req_id) {
          idMap.set(req.source_req_id, req.req_id)
          statusMap.set(req.source_req_id, req.status)
          priorityMap.set(req.source_req_id, normalizePriority(req.priority, null))
        }
      })

      manageReqIdMap.value = idMap
      manageStatusMap.value = statusMap
      managePriorityMap.value = priorityMap

      statusMap.forEach((status, key) => {
        requirementStatusMap.value[key] = mapManageStatusToLocal(status)
      })
    } catch (err) {
      console.warn('加载管理需求映射失败，状态同步将不可用', err)
    }
  }

  async function loadRequirements() {
    const sid = sessionId.value?.trim()
    if (!sid) {
      highLevelRequirements.value = []
      lowLevelRequirements.value = []
      requirementTree.value = []
      return
    }

    isLoading.value = true
    try {
      const [l123Data, l4Data, traceData] = await Promise.all([
        requirementsL123Api.listBySession(sid, { page: 1, perPage: 500 }).catch(() => ({ requirements: [] })),
        l4RequirementsApi.getBySession(sid, { perPage: 500 }).catch(() => ({ requirements: [] })),
        analysisApi.getLatestTrace(sid).catch(() => null),
      ])

      highLevelRequirements.value = (l123Data.requirements || []).map(req => ({
        ...req,
        priority: normalizePriority(req.priority, null),
        level: normalizeLevel(req.level || req.category),
      }))

      lowLevelRequirements.value = (l4Data.requirements || []).map(r => ({
        ...r,
        priority: normalizePriority(r.priority, null),
        level: 'L4',
        statement: r.text || r.shall_statement || r.statement || '',
      }))

      traceRelations.value = traceData?.relations || []

      requirementTree.value = buildTreeWithRelations(
        highLevelRequirements.value,
        lowLevelRequirements.value,
        traceRelations.value
      )

      await ensureProjectId()
      await loadManageRequirementMap()
    } catch (err) {
      console.error('加载需求失败:', err)
    } finally {
      isLoading.value = false
    }
  }

  // ---- 树形结构构建 ----
  function buildTreeWithRelations(highReqs, lowReqs, relations) {
    const allReqMap = new Map()
    const levelOrder = { L1: 1, L2: 2, L3: 3, L4: 4 }

    highReqs.forEach((req, idx) => {
      const id = req.req_id || req.id || `high_${idx}`
      allReqMap.set(id, {
        id,
        name: req.text || req.statement || req.title || `需求 ${idx + 1}`,
        requirement: { ...req, requirement_type: 'top_level' },
        requirement_type: 'top_level',
        level: normalizeLevel(req.level || req.category),
        parent_id: req.parent_id || null,
        children: [],
      })
    })

    lowReqs.forEach((req, idx) => {
      const id = req.req_id || req.id || `low_${idx}`
      allReqMap.set(id, {
        id,
        name: req.text || req.statement || req.shall_statement || `L4 需求 ${idx + 1}`,
        requirement: { ...req, requirement_type: 'low_level' },
        requirement_type: 'low_level',
        level: 'L4',
        parent_id: req.parent_id || req.source_top_id || null,
        children: [],
      })
    })

    if (relations && relations.length > 0) {
      relations.forEach(rel => {
        if (!rel.has_relation) return
        const lowReq = lowReqs[rel.low_level_index]
        const highReq = highReqs[rel.high_level_index]
        if (lowReq && highReq) {
          const lowId = lowReq.req_id || lowReq.id
          const highId = highReq.req_id || highReq.id
          const lowNode = allReqMap.get(lowId)
          if (lowNode && !lowNode.parent_id) lowNode.parent_id = highId
        }
      })
    }

    const roots = []
    const linkedIds = new Set()

    allReqMap.forEach((node) => {
      if (node.parent_id && allReqMap.has(node.parent_id)) {
        allReqMap.get(node.parent_id).children.push(node)
        linkedIds.add(node.id)
      }
    })

    allReqMap.forEach((node, id) => {
      if (!linkedIds.has(id)) roots.push(node)
    })

    const sortChildren = (node) => {
      node.children.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5))
      node.children.forEach(sortChildren)
    }
    roots.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5))
    roots.forEach(sortChildren)

    return roots
  }

  // ---- 状态管理 ----
  function syncRequirementLists() {
    const all = filteredRequirements.value
    backlogRequirements.value = all.filter(r => r.status === 'backlog')
    inProgressRequirements.value = all.filter(r => r.status === 'in_progress')
    completedRequirements.value = all.filter(r => r.status === 'completed')
  }

  function updateRequirementStatus(reqId, newStatus) {
    requirementStatusMap.value = { ...requirementStatusMap.value, [reqId]: newStatus }
    persistStatusToDb({ id: reqId, req_id: reqId }, newStatus)
  }

  function onDragChange(item, targetStatus) {
    if (item && item.id) {
      requirementStatusMap.value = { ...requirementStatusMap.value, [item.id]: targetStatus }
      persistStatusToDb(item, targetStatus)
    }
  }

  async function persistStatusToDb(item, targetStatus) {
    const manageReqId = resolveManageReqId(item)
    if (!manageReqId) return
    try {
      isSyncingStatus.value = true
      await manageApi.updateRequirement(manageReqId, { status: mapLocalStatusToManage(targetStatus) })
    } catch (err) {
      console.warn('同步状态到数据库失败', err)
    } finally {
      isSyncingStatus.value = false
    }
  }

  async function importSessionRequirementsToManage(router) {
    commitSessionId()
    const sid = String(sessionId.value || '').trim()
    if (!selectedProjectId.value) { alert('请先选择要导入的项目'); return }
    if (!sid) { alert('请先输入 Session ID'); return }

    const targetProject = projects.value.find(p => p.project_id === selectedProjectId.value)
    const projectLabel = targetProject?.name || selectedProjectId.value
    const confirmed = window.confirm(
      `确认将 Session ${sid} 的需求导入到项目「${projectLabel}」吗？\n已存在的需求会自动跳过。`
    )
    if (!confirmed) return

    isImportingToManage.value = true
    try {
      const result = await manageApi.importFromSession(selectedProjectId.value, { session_id: sid, mapping_mode: 'tree' })
      await loadManageRequirementMap()
      localStorage.setItem('lastProjectId', selectedProjectId.value)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: selectedProjectId.value } }))

      const inserted = Number(result?.inserted || 0)
      const insertedL123 = Number(result?.inserted_l123 || 0)
      const insertedL4 = Number(result?.inserted_l4 || 0)
      alert(`导入完成：新增 ${inserted} 条（L1-L3 ${insertedL123} 条，L4 ${insertedL4} 条）`)

      await router.push({ name: 'beta-requirements', query: { project_id: selectedProjectId.value } })
    } catch (err) {
      console.error('导入会话需求失败:', err)
      alert('导入失败: ' + (err.message || '未知错误'))
    } finally {
      isImportingToManage.value = false
    }
  }

  // ---- 全局事件处理 ----
  function handleSessionChanged(event) {
    const newSessionId = event.detail?.sessionId
    if (newSessionId && newSessionId !== sessionId.value) {
      sessionId.value = newSessionId
      sessionIdDraft.value = newSessionId
      loadRequirements()
    }
  }

  function handleAnalysisCompleted(event) {
    const eventSessionId = event.detail?.sessionId
    if (eventSessionId && eventSessionId === sessionId.value) loadRequirements()
  }

  // ---- 事件处理 ----
  function handleNodeHover(req) { hoveredNode.value = req }
  function handleNodeClick(req) { console.log('Clicked:', req) }
  async function refreshData() { await loadRequirements() }

  // ---- Watches ----
  watch(selectedProjectId, async (val) => {
    if (val) {
      localStorage.setItem('lastProjectId', val)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: val } }))
      await loadProjectSession()
      if (projectSessionId.value && projectSessionId.value !== sessionId.value) {
        sessionId.value = projectSessionId.value
        sessionIdDraft.value = projectSessionId.value
      }
      await loadRequirements()
    } else {
      projectSessionId.value = ''
      sessionMismatch.value = false
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: '' } }))
    }
  })

  watch(sessionId, (newVal) => {
    if (newVal !== sessionIdDraft.value) sessionIdDraft.value = newVal
    if (newVal && newVal.trim()) {
      localStorage.setItem('lastSessionId', newVal.trim())
      checkSessionMismatch()
      loadRequirements()
    }
  })

  watch([filteredRequirements, requirementStatusMap], () => {
    syncRequirementLists()
  }, { deep: true, immediate: true })

  return {
    // 数据
    isLoading,
    highLevelRequirements,
    lowLevelRequirements,
    requirementTree,
    projects,
    selectedProjectId,
    isLoadingProjects,
    projectSessionId,
    sessionMismatch,
    sessionId,
    sessionIdDraft,
    requirementStatusMap,
    backlogRequirements,
    inProgressRequirements,
    completedRequirements,
    isSyncingStatus,
    isImportingToManage,
    manageReqIdMap,
    managePriorityMap,
    // 视图
    activeLevel,
    activeView,
    hoveredNode,
    levelTabs,
    requirementStatuses,
    // 计算属性
    filteredRequirements,
    filteredTreeData,
    parentRequirementOptions,
    levelCounts,
    // 辅助函数
    getStatusName,
    getStatusColorClass,
    getLevelBadgeClass,
    getConfidenceClass,
    getTypeLabel,
    resolveManageReqId,
    // 操作
    loadProjects,
    loadProjectSession,
    loadRequirements,
    loadManageRequirementMap,
    commitSessionId,
    clearSessionId,
    useProjectSession,
    syncProjectFromStorage,
    syncProjectFromLocation,
    updateRequirementStatus,
    onDragChange,
    importSessionRequirementsToManage,
    refreshData,
    handleNodeHover,
    handleNodeClick,
    handleSessionChanged,
    handleAnalysisCompleted,
  }
}

