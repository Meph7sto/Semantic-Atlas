<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { manageApi } from '@/utils/api'
import { Plus, RefreshCw, GitBranch, Flag, Layers, ClipboardList } from 'lucide-vue-next'
import MilestoneGraph from '@/components/charts/MilestoneGraph.vue'
import RequirementTree from '@/components/charts/RequirementTree.vue'

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
const requirementHover = ref(null)

const requirementForm = ref({
  requirement_type: 'top_level',
  title: '',
  description: '',
  parent_id: '',
  order_index: 0
})

const importForm = ref({ session_id: '' })

const milestones = ref([])
const milestoneForm = ref({ name: '', message: '', is_baseline: false, parent_milestone_id: '' })
const milestoneError = ref('')
const milestoneGraph = ref({ nodes: [], edges: [] })
const selectedMilestoneId = ref('')
const selectedMilestoneDetail = ref(null)
const milestoneHoverRequirement = ref(null)

const compareForm = ref({ from_milestone_id: '', to_milestone_id: '' })
const compareResult = ref(null)

const branches = ref([])
const branchForm = ref({ name: '', base_milestone_id: '' })
const currentBranch = ref('main')
const branchError = ref('')

const audits = ref([])

const requirementTypeOptions = [
  { value: 'top_level', label: '顶层需求（L1/L2/L3）' },
  { value: 'low_level', label: '底层需求（L4）' },
  { value: 'task', label: '任务（L5）' }
]

const selectedProject = computed(() => projects.value.find(p => p.project_id === selectedProjectId.value) || null)
const branchOptions = computed(() => branches.value.filter(b => b.ref_name !== 'main'))

const filterTopLevelTrees = (trees = []) => {
  return trees.filter(node => node?.requirement?.requirement_type === 'top_level')
}

const filterOtherRoots = (trees = []) => {
  return trees.filter(node => node?.requirement?.requirement_type !== 'top_level')
}

const topLevelRequirementTrees = computed(() => filterTopLevelTrees(requirementTree.value))
const otherRequirementRoots = computed(() => filterOtherRoots(requirementTree.value))

const buildSnapshotTree = (nodes = []) => {
  const nodeMap = new Map()
  nodes.forEach(node => {
    const req = node.snapshot_data || {}
    nodeMap.set(node.requirement_id, {
      requirement: req,
      children: [],
      parent_id: node.parent_id,
      order_index: node.order_index || 0
    })
  })

  const roots = []
  nodeMap.forEach((node, key) => {
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      nodeMap.get(node.parent_id).children.push(node)
    } else {
      roots.push(node)
    }
  })

  const sortChildren = (node) => {
    node.children.sort((a, b) => (a.order_index || 0) - (b.order_index || 0))
    node.children.forEach(sortChildren)
  }
  roots.forEach(sortChildren)
  roots.sort((a, b) => (a.order_index || 0) - (b.order_index || 0))
  return roots
}

const selectedMilestoneTree = computed(() => {
  const nodes = selectedMilestoneDetail.value?.nodes || []
  return buildSnapshotTree(nodes)
})

const selectedMilestoneTopTrees = computed(() => filterTopLevelTrees(selectedMilestoneTree.value))
const selectedMilestoneOtherRoots = computed(() => filterOtherRoots(selectedMilestoneTree.value))

const compareFromTrees = computed(() => filterTopLevelTrees(compareResult.value?.from_tree || []))
const compareToTrees = computed(() => filterTopLevelTrees(compareResult.value?.to_tree || []))

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

async function loadMilestoneGraph() {
  if (!selectedProjectId.value) return
  try {
    const data = await manageApi.listMilestoneGraph(selectedProjectId.value)
    milestoneGraph.value = {
      nodes: data.nodes || [],
      edges: data.edges || []
    }
  } catch (err) {
    milestoneError.value = err?.message || '加载里程碑图失败'
  }
}

async function createMilestone() {
  if (!selectedProjectId.value) return
  milestoneError.value = ''
  if (!milestoneForm.value.name.trim()) return
  try {
    const payload = {
      ...milestoneForm.value,
      branch_name: currentBranch.value || undefined
    }
    if (!payload.parent_milestone_id) delete payload.parent_milestone_id
    await manageApi.createMilestone(selectedProjectId.value, payload)
    milestoneForm.value = { name: '', message: '', is_baseline: false, parent_milestone_id: '' }
    await Promise.all([loadMilestones(), loadMilestoneGraph(), loadBranches()])
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
    if (!currentBranch.value && branches.value.length) {
      currentBranch.value = branches.value[0].ref_name
    }
    if (!branches.value.find(b => b.ref_name === currentBranch.value)) {
      currentBranch.value = 'main'
    }
  } catch (err) {
    branchError.value = err?.message || '加载分支失败'
  }
}

async function createBranch() {
  if (!selectedProjectId.value) return
  branchError.value = ''
  if (!branchForm.value.name.trim() || !branchForm.value.base_milestone_id) return
  try {
    const nextBranch = branchForm.value.name.trim()
    await manageApi.createBranch(selectedProjectId.value, branchForm.value)
    branchForm.value.name = ''
    await Promise.all([loadBranches(), loadMilestoneGraph()])
    currentBranch.value = nextBranch || currentBranch.value
  } catch (err) {
    branchError.value = err?.message || '创建分支失败'
  }
}

async function selectMilestone(milestoneId) {
  selectedMilestoneId.value = milestoneId
  selectedMilestoneDetail.value = null
  if (!milestoneId) return
  try {
    selectedMilestoneDetail.value = await manageApi.getMilestone(milestoneId)
  } catch (err) {
    milestoneError.value = err?.message || '加载里程碑详情失败'
  }
}

async function loadAudits() {
  if (!selectedProjectId.value) return
  const data = await manageApi.listAudits(selectedProjectId.value, 50)
  audits.value = data.logs || []
}

watch(selectedProjectId, async () => {
  if (!selectedProjectId.value) return
  await Promise.all([loadRequirements(), loadMilestones(), loadMilestoneGraph(), loadBranches(), loadAudits()])
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

          <div v-if="showTree" class="border border-zinc-200 rounded-lg p-3 space-y-3">
            <div class="text-xs text-zinc-500">顶层需求树（L1/L2/L3）</div>
            <RequirementTree :tree-data="topLevelRequirementTrees" @hover="(req) => (requirementHover = req)" />
            <div v-if="otherRequirementRoots.length" class="text-xs text-zinc-500 pt-2">未归类根节点</div>
            <RequirementTree v-if="otherRequirementRoots.length" :tree-data="otherRequirementRoots" @hover="(req) => (requirementHover = req)" />
          </div>
          <div v-else class="max-h-80 overflow-y-auto text-xs text-zinc-700 border border-zinc-200 rounded-lg p-3">
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(requirements, null, 2) }}</pre>
          </div>

          <div v-if="requirementHover" class="text-xs text-zinc-600 border border-zinc-200 rounded-lg p-3 bg-zinc-50">
            <div class="font-medium text-zinc-800">悬浮需求</div>
            <div>标题: {{ requirementHover.title || requirementHover.text }}</div>
            <div>类型: {{ requirementHover.requirement_type || '-' }}</div>
            <div>状态: {{ requirementHover.status || '-' }}</div>
            <div>优先级: {{ requirementHover.priority || '-' }}</div>
            <div>负责人: {{ requirementHover.assignee || '-' }}</div>
            <div>截止: {{ requirementHover.due_date || '-' }}</div>
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
            <select v-model="currentBranch" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option value="main">当前分支：main</option>
              <option v-for="b in branchOptions" :key="b.ref_name" :value="b.ref_name">当前分支：{{ b.ref_name }}</option>
            </select>
            <select v-model="milestoneForm.parent_milestone_id" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
              <option value="">父里程碑（可空）</option>
              <option v-for="m in milestones" :key="m.milestone_id" :value="m.milestone_id">{{ m.name }}</option>
            </select>
          </div>
          <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createMilestone">
            <Plus class="w-4 h-4" />
            创建里程碑
          </button>

          <div class="grid grid-cols-1 xl:grid-cols-[2fr,1fr] gap-4">
            <div class="border border-zinc-200 rounded-lg p-3">
              <MilestoneGraph
                :nodes="milestoneGraph.nodes"
                :edges="milestoneGraph.edges"
                :branch-refs="branches"
                @select="selectMilestone"
              />
            </div>
            <div class="border border-zinc-200 rounded-lg p-3 text-xs text-zinc-700 space-y-2">
              <div class="font-medium text-zinc-800">里程碑详情</div>
              <div v-if="!selectedMilestoneDetail" class="text-zinc-500">点击图中节点查看详情</div>
              <div v-else class="space-y-1">
                <div>名称: {{ selectedMilestoneDetail.name }}</div>
                <div>类型: {{ selectedMilestoneDetail.milestone_type }}</div>
                <div>Baseline: {{ selectedMilestoneDetail.is_baseline ? '是' : '否' }}</div>
                <div>创建: {{ selectedMilestoneDetail.created_at }}</div>
                <div>说明: {{ selectedMilestoneDetail.message || '-' }}</div>
              </div>
              <div v-if="selectedMilestoneDetail" class="border-t border-zinc-200 pt-2 space-y-2">
                <div class="font-medium text-zinc-800">该里程碑需求树（按顶层需求分组）</div>
                <RequirementTree :tree-data="selectedMilestoneTopTrees" @hover="(req) => (milestoneHoverRequirement = req)" />
                <RequirementTree v-if="selectedMilestoneOtherRoots.length" :tree-data="selectedMilestoneOtherRoots" @hover="(req) => (milestoneHoverRequirement = req)" />
                <div v-if="milestoneHoverRequirement" class="mt-2 text-zinc-600">
                  <div>标题: {{ milestoneHoverRequirement.title || milestoneHoverRequirement.text }}</div>
                  <div>类型: {{ milestoneHoverRequirement.requirement_type || '-' }}</div>
                  <div>状态: {{ milestoneHoverRequirement.status || '-' }}</div>
                </div>
              </div>
            </div>
          </div>

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

          <div v-if="compareResult" class="border border-zinc-200 rounded-lg p-3 space-y-3">
            <div class="text-xs text-zinc-600">
              变化统计：新增 {{ compareResult.summary?.added || 0 }} · 删除 {{ compareResult.summary?.deleted || 0 }} · 修改 {{ compareResult.summary?.modified || 0 }} · 移动 {{ compareResult.summary?.moved || 0 }}
            </div>
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">
              <div>
                <div class="text-xs text-zinc-500 mb-1">From 里程碑</div>
                <RequirementTree :tree-data="compareFromTrees" :highlight-map="compareResult.change_map" />
              </div>
              <div>
                <div class="text-xs text-zinc-500 mb-1">To 里程碑</div>
                <RequirementTree :tree-data="compareToTrees" :highlight-map="compareResult.change_map" />
              </div>
            </div>
            <div class="flex flex-wrap gap-3 text-xs text-zinc-600">
              <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-full bg-green-500"></span>新增</span>
              <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-full bg-red-500"></span>删除</span>
              <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-full bg-amber-500"></span>修改</span>
              <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-full bg-blue-500"></span>移动</span>
              <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-full bg-purple-500"></span>多重变化</span>
            </div>
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
            <div v-for="b in branches" :key="b.ref_id" class="flex items-center justify-between text-xs text-zinc-700 border border-zinc-200 rounded-lg px-3 py-2">
              <div>
                <div class="font-medium">{{ b.ref_name }}</div>
                <div class="text-zinc-500">指向: {{ b.milestone_name || '未设置' }}</div>
                <div class="text-zinc-500">创建: {{ b.created_at }}</div>
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
