<template>
  <div class="project-selector space-y-4">
    <!-- 项目选择 -->
    <div class="flex flex-col space-y-2">
      <label class="text-sm font-medium text-zinc-700">选择项目</label>
      <select
        v-model="selectedProject"
        :disabled="isLoadingProjects"
        class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-zinc-100"
        @change="onProjectChange"
      >
        <option value="">-- 请选择项目 --</option>
        <option
          v-for="project in projects"
          :key="project.project_id"
          :value="project.project_id"
        >
          {{ project.name }}
        </option>
      </select>
    </div>

    <!-- 需求选择 -->
    <div class="flex flex-col space-y-2">
      <label class="text-sm font-medium text-zinc-700">选择需求</label>
      <select
        v-model="selectedRequirement"
        :disabled="!selectedProject || isLoadingRequirements"
        class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-zinc-100"
        @change="onRequirementChange"
      >
        <option value="">-- 请选择需求 --</option>
        <option
          v-for="req in requirements"
          :key="req.req_id"
          :value="req.req_id"
        >
          {{ req.title || req.req_id }}
        </option>
      </select>
    </div>

    <!-- 选中信息 -->
    <div v-if="selectedRequirement" class="mt-2 text-xs text-zinc-500">
      <div>需求ID: {{ selectedRequirement }}</div>
      <div>事件数量: {{ eventCount }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '@/api/request'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ projectId: '', requirementId: '' })
  },
  eventCount: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:modelValue', 'project-selected', 'requirement-selected'])

const projects = ref([])
const requirements = ref([])
const selectedProject = ref('')
const selectedRequirement = ref('')
const isLoadingProjects = ref(false)
const isLoadingRequirements = ref(false)

// 同步 v-model
watch([selectedProject, selectedRequirement], () => {
  emit('update:modelValue', {
    projectId: selectedProject.value,
    requirementId: selectedRequirement.value
  })
})

// 监听外部变化
watch(() => props.modelValue, (newVal) => {
  if (newVal.projectId !== selectedProject.value) {
    selectedProject.value = newVal.projectId
  }
  if (newVal.requirementId !== selectedRequirement.value) {
    selectedRequirement.value = newVal.requirementId
  }
}, { immediate: true, deep: true })

async function loadProjects() {
  isLoadingProjects.value = true
  try {
    const resp = await api.get('/manage/projects')
    projects.value = resp.data.projects || []
  } catch (err) {
    console.error('Failed to load projects:', err)
  } finally {
    isLoadingProjects.value = false
  }
}

async function loadRequirements(projectId) {
  if (!projectId) {
    requirements.value = []
    return
  }

  isLoadingRequirements.value = true
  try {
    const resp = await api.get(`/manage/projects/${projectId}/requirements`)
    requirements.value = resp.data.requirements || []
  } catch (err) {
    console.error('Failed to load requirements:', err)
  } finally {
    isLoadingRequirements.value = false
  }
}

function onProjectChange() {
  selectedRequirement.value = ''
  emit('project-selected', selectedProject.value)
  loadRequirements(selectedProject.value)
}

function onRequirementChange() {
  emit('requirement-selected', selectedRequirement.value)
}

onMounted(() => {
  loadProjects()
})
</script>
