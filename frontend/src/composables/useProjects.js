import { ref, watch } from 'vue'
import { productApi } from '@/api/product'
import { manageApi } from '@/api/project'
import { useRouter } from 'vue-router'

export function useProjects(selectedProduct, loadProductDetails) {
  const router = useRouter()
  const projects = ref([])
  const loadingProjects = ref(false)
  const editingProject = ref(null)
  const showCreateProjectModal = ref(false)
  const showEditProjectModal = ref(false)

  const loadProjects = async () => {
    if (!selectedProduct.value) return
    loadingProjects.value = true
    try {
      const resp = await productApi.listProjectsByProduct(selectedProduct.value.product_id)
      projects.value = resp.projects || []
    } catch (err) {
      console.error('Failed to load projects:', err)
    } finally {
      loadingProjects.value = false
    }
  }

  const openEditProject = (project) => {
    editingProject.value = project
    showEditProjectModal.value = true
  }

  const handleCreateProject = async (formData) => {
    try {
      const project = await productApi.createProjectUnderProduct(selectedProduct.value.product_id, {
        name: formData.name.trim(),
        description: formData.description,
      })
      showCreateProjectModal.value = false
      await loadProjects()
      await loadProductDetails()

      // 如果用户填了 session_id，自动导入需求
      const sessionId = (formData.sessionId || '').trim()
      if (sessionId && project?.project_id) {
        try {
          const importResult = await manageApi.importFromSession(project.project_id, {
            session_id: sessionId,
            mapping_mode: 'tree',
          })
          const inserted = importResult?.inserted ?? 0
          alert(`项目创建成功，已导入 ${inserted} 条需求`)
        } catch (importErr) {
          console.error('Failed to import requirements from session:', importErr)
          alert('项目已创建成功，但需求导入失败: ' + importErr.message + '\n可稍后在「会话需求」页面手动导入。')
        }
      }
    } catch (err) {
      console.error('Failed to create project:', err)
      alert('创建项目失败: ' + err.message)
    }
  }

  const handleUpdateProject = async (formData) => {
    if (!editingProject.value) return
    try {
      await manageApi.updateProject(editingProject.value.project_id, {
        name: formData.name.trim(),
        description: formData.description,
      })
      showEditProjectModal.value = false
      editingProject.value = null
      await loadProjects()
    } catch (err) {
      console.error('Failed to update project:', err)
      alert('更新项目失败: ' + err.message)
    }
  }

  const handleDeleteProject = async (project) => {
    if (!confirm(`确定要归档项目"${project.name}"吗？归档后项目将不再显示。`)) return
    try {
      await manageApi.deleteProject(project.project_id)
      await loadProjects()
      await loadProductDetails()
    } catch (err) {
      console.error('Failed to archive project:', err)
      alert('归档项目失败: ' + err.message)
    }
  }

  const goToProject = (project) => {
    localStorage.setItem('lastProjectId', project.project_id)
    window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: project.project_id } }))
    router.push({ name: 'beta-requirements' })
  }

  watch(selectedProduct, (val) => {
    if (val) {
      projects.value = []
      loadProjects()
    } else {
      projects.value = []
    }
  })

  return {
    projects,
    loadingProjects,
    editingProject,
    showCreateProjectModal,
    showEditProjectModal,
    loadProjects,
    openEditProject,
    handleCreateProject,
    handleUpdateProject,
    handleDeleteProject,
    goToProject,
  }
}

