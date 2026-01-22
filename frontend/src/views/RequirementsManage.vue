<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { manageApi } from '@/utils/api'
import { Plus, RefreshCw, GitBranch, Flag, Layers, ClipboardList } from 'lucide-vue-next'

const projects = ref([])
const selectedProjectId = ref('')
const projectForm = ref({ name: '', description: '' })
const isLoadingProjects = ref(false)
const projectError = ref('')

const requirements = ref([])
const requirementTree = ref([])
const reqError = ref('')
const isLoadingReqs = ref(false)
const showTree = ref(true)

const requirementForm = ref({
  requirement_type: 'top_level',
  title: '',
  description: '',
  parent_id: '',
  order_index: 0
})

const importForm = ref({ session_id: '' })

const milestones = ref([])
const milestoneForm = ref({ name: '', message: '', is_baseline: false })
const milestoneError = ref('')

const compareForm = ref({ from_milestone_id: '', to_milestone_id: '' })
const compareResult = ref(null)

const branches = ref([])
const branchForm = ref({ name: '', base_milestone_id: '' })
const branchError = ref('')

const audits = ref([])

const requirementTypeOptions = [
  { value: 'top_level', label: '顶层需求' },
  { value: 'low_level', label: '底层需求' },
  { value: 'task', label: '任务' }
]

const selectedProject = computed(() => projects.value.find(p => p.project_id === selectedProjectId.value) || null)

async function loadProjects() {
  projectError.value = ''
  isLoadingProjects.value = true
  try {
    const data = await manageApi.listProjects()
    projects.value = data.projects || []
  } catch (err) {
    projectError.value = err?.message || '加载项目失败'
  } finally {
    isLoadingProjects.value = false
  }
}

async function createProject() {
  projectError.value = ''
  const name = projectForm.value.name.trim()
  if (!name) return
  try {
    const created = await manageApi.createProject(projectForm.value)
    await loadProjects()
    selectedProjectId.value = created.project_id
    projectForm.value = { name: '', description: '' }
  } catch (err) {
    projectError.value = err?.message || '创建项目失败'
  }
}

async function loadRequirements() {
  if (!selectedProjectId.value) return
  reqError.value = ''
  isLoadingReqs.value = true
  try {
    const listData = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = listData.requirements || []
    const treeData = await manageApi.listRequirements(selectedProjectId.value, { tree: true })
    requirementTree.value = treeData.tree || []
  } catch (err) {
    reqError.value = err?.message || '加载需求失败'
  } finally {
    isLoadingReqs.value = false
  }
}

async function createRequirement() {
  if (!selectedProjectId.value) return
  reqError.value = ''
  const payload = { ...requirementForm.value }
  if (!payload.title.trim()) return
  if (!payload.parent_id) delete payload.parent_id
  try {
    await manageApi.createRequirement(selectedProjectId.value, payload)
    await loadRequirements()
    requirementForm.value.title = ''
    requirementForm.value.description = ''
  } catch (err) {
    reqError.value = err?.message || '创建需求失败'
  }
}

async function importFromL123() {
  if (!selectedProjectId.value) return
  reqError.value = ''
  if (!importForm.value.session_id.trim()) return
  try {
    await manageApi.importFromL123(selectedProjectId.value, { session_id: importForm.value.session_id })
    await loadRequirements()
  } catch (err) {
    reqError.value = err?.message || '导入失败'
  }
}

async function loadMilestones() {
  if (!selectedProjectId.value) return
  milestoneError.value = ''
  try {
    const data = await manageApi.listMilestones(selectedProjectId.value)
    milestones.value = data.milestones || []
  } catch (err) {
    milestoneError.value = err?.message || '加载里程碑失败'
  }
}

async function createMilestone() {
  if (!selectedProjectId.value) return
  milestoneError.value = ''
  if (!milestoneForm.value.name.trim()) return
  try {
    await manageApi.createMilestone(selectedProjectId.value, milestoneForm.value)
    milestoneForm.value = { name: '', message: '', is_baseline: false }
    await loadMilestones()
  } catch (err) {
    milestoneError.value = err?.message || '创建里程碑失败'
  }
}

async function setBaseline(milestoneId) {
  milestoneError.value = ''
  try {
    await manageApi.setBaseline(milestoneId)
    await loadMilestones()
  } catch (err) {
    milestoneError.value = err?.message || '设置基线失败'
  }
}

async function compareMilestones() {
  compareResult.value = null
  if (!compareForm.value.from_milestone_id || !compareForm.value.to_milestone_id) return
  try {
    compareResult.value = await manageApi.compareMilestones({
      from_milestone_id: compareForm.value.from_milestone_id,
      to_milestone_id: compareForm.value.to_milestone_id
    })
  } catch (err) {
    milestoneError.value = err?.message || '比较失败'
  }
}

async function loadBranches() {
  if (!selectedProjectId.value) return
  branchError.value = ''
  try {
    const data = await manageApi.listBranches(selectedProjectId.value)
    branches.value = data.branches || []
  } catch (err) {
    branchError.value = err?.message || '加载分支失败'
  }
}

async function createBranch() {
  if (!selectedProjectId.value) return
  branchError.value = ''
  if (!branchForm.value.name.trim() || !branchForm.value.base_milestone_id) return
  try {
    await manageApi.createBranch(selectedProjectId.value, branchForm.value)
    branchForm.value.name = ''
    await loadBranches()
  } catch (err) {
    branchError.value = err?.message || '创建分支失败'
  }
}

async function loadAudits() {
  if (!selectedProjectId.value) return
  const data = await manageApi.listAudits(selectedProjectId.value, 50)
  audits.value = data.logs || []
}

watch(selectedProjectId, async () => {
  if (!selectedProjectId.value) return
  await Promise.all([loadRequirements(), loadMilestones(), loadBranches(), loadAudits()])
})

onMounted(loadProjects)
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <header class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-2 text-zinc-900">
        <ClipboardList class="w-5 h-5" />
        <h2 class="text-xl font-semibold">需求管理监控</h2>
      </div>
      <button
        class="inline-flex items-center gap-2 text-sm text-zinc-700 border border-zinc-300 rounded-md px-3 py-1.5 hover:bg-zinc-50"
        @click="loadProjects"
      >
        <RefreshCw class="w-4 h-4" />
        刷新
      </button>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      <!-- 项目区 -->
      <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-zinc-900">项目</h3>
          <span v-if="isLoadingProjects" class="text-xs text-zinc-500">加载中...</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select v-model="selectedProjectId" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
              {{ p.name }}
            </option>
          </select>
          <input v-model="projectForm.name" placeholder="新项目名称" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createProject">
            <Plus class="w-4 h-4" />
            新建项目
          </button>
        </div>
        <p v-if="projectError" class="text-xs text-red-600">{{ projectError }}</p>
      </section>

      <div v-if="selectedProject" class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <!-- 需求区 -->
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Layers class="w-4 h-4" />
              需求树
            </h3>
            <button class="text-xs text-zinc-600" @click="showTree = !showTree">{{ showTree ? '列表' : '树形' }}</button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <select v-model="requirementForm.requirement_type" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option v-for="opt in requirementTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
            <input v-model="requirementForm.title" placeholder="需求标题" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <input v-model="requirementForm.parent_id" placeholder="父节点ID(可空)" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <input v-model.number="requirementForm.order_index" type="number" placeholder="排序" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <textarea v-model="requirementForm.description" placeholder="描述" class="md:col-span-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm" rows="2" />
          </div>
          <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createRequirement">
            <Plus class="w-4 h-4" />
            新建需求
          </button>

          <div class="flex items-center gap-2">
            <input v-model="importForm.session_id" placeholder="从 L123 导入：session_id" class="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <button class="inline-flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm" @click="importFromL123">
              导入
            </button>
          </div>

          <p v-if="reqError" class="text-xs text-red-600">{{ reqError }}</p>

          <div v-if="showTree" class="max-h-80 overflow-y-auto text-xs text-zinc-700 border border-zinc-200 rounded-lg p-3">
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(requirementTree, null, 2) }}</pre>
          </div>
          <div v-else class="max-h-80 overflow-y-auto text-xs text-zinc-700 border border-zinc-200 rounded-lg p-3">
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(requirements, null, 2) }}</pre>
          </div>
        </section>

        <!-- 里程碑区 -->
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <Flag class="w-4 h-4" />
              里程碑
            </h3>
            <button class="text-xs text-zinc-600" @click="loadMilestones">刷新</button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input v-model="milestoneForm.name" placeholder="里程碑名称" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <input v-model="milestoneForm.message" placeholder="说明" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <label class="flex items-center gap-2 text-xs text-zinc-600">
              <input v-model="milestoneForm.is_baseline" type="checkbox" class="w-4 h-4" />
              设置为 baseline
            </label>
          </div>
          <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createMilestone">
            <Plus class="w-4 h-4" />
            创建里程碑
          </button>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <select v-model="compareForm.from_milestone_id" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option value="">From 里程碑</option>
              <option v-for="m in milestones" :key="m.milestone_id" :value="m.milestone_id">{{ m.name }}</option>
            </select>
            <select v-model="compareForm.to_milestone_id" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option value="">To 里程碑</option>
              <option v-for="m in milestones" :key="m.milestone_id" :value="m.milestone_id">{{ m.name }}</option>
            </select>
          </div>
          <button class="inline-flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm" @click="compareMilestones">
            比较差异
          </button>

          <div v-if="compareResult" class="text-xs text-zinc-700 border border-zinc-200 rounded-lg p-3">
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(compareResult, null, 2) }}</pre>
          </div>

          <div class="space-y-2">
            <div v-for="m in milestones" :key="m.milestone_id" class="flex items-center justify-between text-xs text-zinc-700 border border-zinc-200 rounded-lg px-3 py-2">
              <div>
                <div class="font-medium">{{ m.name }}</div>
                <div class="text-zinc-500">{{ m.milestone_type }} · {{ m.created_at }}</div>
              </div>
              <button class="text-xs text-blue-600" @click="setBaseline(m.milestone_id)">设为 baseline</button>
            </div>
          </div>

          <p v-if="milestoneError" class="text-xs text-red-600">{{ milestoneError }}</p>
        </section>
      </div>

      <div v-if="selectedProject" class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <!-- 分支区 -->
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900 flex items-center gap-2">
              <GitBranch class="w-4 h-4" />
              变更分支与影响分析
            </h3>
            <button class="text-xs text-zinc-600" @click="loadBranches">刷新</button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input v-model="branchForm.name" placeholder="分支名称" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
            <select v-model="branchForm.base_milestone_id" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option value="">基于里程碑</option>
              <option v-for="m in milestones" :key="m.milestone_id" :value="m.milestone_id">{{ m.name }}</option>
            </select>
          </div>
          <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createBranch">
            <Plus class="w-4 h-4" />
            创建分支
          </button>

          <div class="space-y-2">
            <div v-for="b in branches" :key="b.branch_id" class="flex items-center justify-between text-xs text-zinc-700 border border-zinc-200 rounded-lg px-3 py-2">
              <div>
                <div class="font-medium">{{ b.name }}</div>
                <div class="text-zinc-500">{{ b.status }} · {{ b.created_at }}</div>
              </div>
            </div>
          </div>

          <p v-if="branchError" class="text-xs text-red-600">{{ branchError }}</p>
        </section>

        <!-- 审计区 -->
        <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900">审计日志</h3>
            <button class="text-xs text-zinc-600" @click="loadAudits">刷新</button>
          </div>
          <div class="max-h-80 overflow-y-auto text-xs text-zinc-700 border border-zinc-200 rounded-lg p-3">
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(audits, null, 2) }}</pre>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
