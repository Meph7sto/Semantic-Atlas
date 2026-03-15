import { ref, computed, watch, onMounted } from 'vue'
import { manageApi } from '@/api/project'

export function useCollectionProjects() {
  const projects = ref([])
  const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '')
  const isLoadingProjects = ref(false)

  const selectedProject = computed(() =>
    projects.value.find(p => p.project_id === selectedProjectId.value) || null
  )

  const selectedProjectHasSession = computed(() =>
    !!(selectedProject.value && selectedProject.value.current_session_id)
  )

  const currentProjectName = computed(() => {
    const p = selectedProject.value
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

  watch(selectedProjectId, (val) => {
    if (val) {
      localStorage.setItem('lastProjectId', val)
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: val } }))
    }
  })

  onMounted(() => loadProjects())

  return {
    projects,
    selectedProjectId,
    isLoadingProjects,
    selectedProject,
    selectedProjectHasSession,
    currentProjectName,
    loadProjects,
  }
}

