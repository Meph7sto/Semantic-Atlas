import { ref } from 'vue'
import { manageApi } from '@/api/project'
import { normalizeLevel, normalizePriority } from './useSessionRequirements'

/**
 * @param {import('vue').Ref<string>} selectedProjectId
 * @param {import('vue').Ref<string>} sessionId
 * @param {import('vue').Ref<Map>} manageReqIdMap
 * @param {import('vue').Ref<Map>} managePriorityMap
 * @param {{ loadRequirements: Function, loadManageRequirementMap: Function, resolveManageReqId: Function }} callbacks
 */
export function useRequirementModals(
  selectedProjectId,
  sessionId,
  manageReqIdMap,
  managePriorityMap,
  { loadRequirements, loadManageRequirementMap, resolveManageReqId }
) {
  // ---- 新增需求弹窗 ----
  const showAddRequirementModal = ref(false)
  const isSubmitting = ref(false)
  const newRequirement = ref({
    title: '', description: '', requirement_type: 'top_level',
    level: 'L1', priority: 'medium', status: 'draft', parent_id: '', tags: '',
  })

  function openAddRequirementModal() {
    if (!selectedProjectId.value) { alert('请先选择项目'); return }
    newRequirement.value = {
      title: '', description: '', requirement_type: 'top_level',
      level: 'L1', priority: 'medium', status: 'draft', parent_id: '', tags: '',
    }
    showAddRequirementModal.value = true
  }

  function closeAddRequirementModal() {
    showAddRequirementModal.value = false
  }

  async function submitNewRequirement() {
    if (!selectedProjectId.value) { alert('请先选择项目'); return }
    if (!newRequirement.value.title.trim()) { alert('请输入需求标题'); return }

    isSubmitting.value = true
    try {
      const payload = {
        title: newRequirement.value.title.trim(),
        description: newRequirement.value.description.trim(),
        requirement_type: newRequirement.value.requirement_type,
        status: newRequirement.value.status,
        priority: normalizePriority(newRequirement.value.priority, 'medium'),
      }

      if (newRequirement.value.requirement_type === 'top_level') {
        payload.source_level = normalizeLevel(newRequirement.value.level || 'L1')
      } else if (newRequirement.value.requirement_type === 'low_level') {
        payload.source_level = 'L4'
      }

      if (newRequirement.value.parent_id) payload.parent_id = newRequirement.value.parent_id

      if (newRequirement.value.tags.trim()) {
        payload.tags = newRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean)
      }

      await manageApi.createRequirement(selectedProjectId.value, payload)
      closeAddRequirementModal()
      await loadRequirements()
      await loadManageRequirementMap()
    } catch (err) {
      console.error('新增需求失败:', err)
      alert('新增需求失败: ' + (err.message || '未知错误'))
    } finally {
      isSubmitting.value = false
    }
  }

  // ---- 编辑需求弹窗 ----
  const showEditRequirementModal = ref(false)
  const isEditSubmitting = ref(false)
  const editRequirementId = ref('')
  const editRequirement = ref({
    title: '', description: '', priority: 'medium', status: 'draft', tags: '',
  })

  async function openEditRequirementModal(req) {
    if (!selectedProjectId.value) { alert('请先选择项目'); return }

    let reqId = resolveManageReqId(req)
    const hasManageEntry = manageReqIdMap.value.has(req.req_id || req.id)

    if (!hasManageEntry && sessionId.value) {
      try {
        await manageApi.importFromSession(selectedProjectId.value, { session_id: sessionId.value, mapping_mode: 'tree' })
        await loadManageRequirementMap()
        reqId = resolveManageReqId(req)
      } catch (err) {
        console.warn('自动导入失败:', err)
      }
    }

    if (!reqId || !manageReqIdMap.value.has(req.req_id || req.id)) {
      alert('无法关联到项目需求，请确认项目和 Session 已正确绑定')
      return
    }

    editRequirementId.value = reqId
    const sourceKey = req.req_id || req.id
    const mappedPriority = managePriorityMap.value.get(sourceKey) || managePriorityMap.value.get(reqId)
    editRequirement.value = {
      title: req.title || req.text || req.statement || '',
      description: req.description || '',
      priority: normalizePriority(mappedPriority ?? req.priority, 'medium'),
      status: req.status || 'draft',
      tags: Array.isArray(req.tags) ? req.tags.join(', ') : (req.tags || ''),
    }
    showEditRequirementModal.value = true
  }

  function closeEditRequirementModal() {
    showEditRequirementModal.value = false
    editRequirementId.value = ''
  }

  async function submitEditRequirement() {
    if (!editRequirementId.value) { alert('需求 ID 丢失'); return }
    if (!editRequirement.value.title.trim()) { alert('请输入需求标题'); return }

    isEditSubmitting.value = true
    try {
      const payload = {
        title: editRequirement.value.title.trim(),
        description: editRequirement.value.description.trim(),
        priority: normalizePriority(editRequirement.value.priority, 'medium'),
        status: editRequirement.value.status,
        tags: editRequirement.value.tags.trim()
          ? editRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean)
          : [],
      }

      await manageApi.updateRequirement(editRequirementId.value, payload)
      closeEditRequirementModal()
      await loadRequirements()
      await loadManageRequirementMap()
    } catch (err) {
      console.error('编辑需求失败:', err)
      alert('编辑需求失败: ' + (err.message || '未知错误'))
    } finally {
      isEditSubmitting.value = false
    }
  }

  return {
    // 新增弹窗
    showAddRequirementModal,
    isSubmitting,
    newRequirement,
    openAddRequirementModal,
    closeAddRequirementModal,
    submitNewRequirement,
    // 编辑弹窗
    showEditRequirementModal,
    isEditSubmitting,
    editRequirement,
    openEditRequirementModal,
    closeEditRequirementModal,
    submitEditRequirement,
  }
}

