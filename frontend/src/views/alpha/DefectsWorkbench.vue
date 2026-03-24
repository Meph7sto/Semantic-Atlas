<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'
import { manageApi } from '@/api/project'
import { useAlphaDefects } from '@/composables/useAlphaDefects'

const router = useRouter()
const route = useRoute()

const projects = ref([])
const selectedProjectId = ref('')
const projectError = ref('')
const requirements = ref([])
const reqError = ref('')

const newForm = ref({
  title: '',
  reproduce_steps: '',
  requirement_id: '',
  severity: 'medium',
  priority: 'P2',
  status: 'open',
  reporter: '',
  dev_assignee: '',
  tester_assignee: '',
})

const filter = ref({
  status: '',
  severity: '',
  assignee: '',
  onlyUnresolved: true,
})

const {
  defects,
  loading,
  error: defectsError,
  unresolvedCount,
  criticalCount,
  byAssignee,
  reload,
  createDefect,
  updateDefect,
  setStatus,
  deleteDefect,
  severityOptions,
  priorityOptions,
  statusOptions,
  unresolvedStatuses,
} = useAlphaDefects(selectedProjectId)

const selectedProject = computed(() =>
  projects.value.find((item) => item.project_id === selectedProjectId.value) || null
)

const requirementOptions = computed(() =>
  (requirements.value || []).map((item) => ({
    id: item.req_id || item.id,
    title: item.title || item.text || item.req_id || item.id,
  }))
)

const filteredDefects = computed(() => {
  return defects.value.filter((item) => {
    if (filter.value.onlyUnresolved && !unresolvedStatuses.has(item.status)) return false
    if (filter.value.status && item.status !== filter.value.status) return false
    if (filter.value.severity && item.severity !== filter.value.severity) return false
    if (filter.value.assignee && (item.current_assignee || '') !== filter.value.assignee) return false
    return true
  })
})

function severityLabel(val) {
  return severityOptions.find((item) => item.value === val)?.label || val || '-'
}

function priorityLabel(val) {
  return priorityOptions.find((item) => item.value === val)?.label || val || '-'
}

function statusLabel(val) {
  return statusOptions.find((item) => item.value === val)?.label || val || '-'
}

function statusClass(val) {
  if (val === 'verified' || val === 'closed') return 'bg-emerald-100 text-emerald-700'
  if (val === 'resolved') return 'bg-blue-100 text-blue-700'
  if (val === 'in_progress') return 'bg-amber-100 text-amber-700'
  if (val === 'open') return 'bg-red-100 text-red-700'
  return 'bg-zinc-100 text-zinc-600'
}

async function loadProjects() {
  projectError.value = ''
  try {
    const data = await manageApi.listProjects()
    projects.value = data.projects || []
    if (!selectedProjectId.value && projects.value.length > 0) {
      selectedProjectId.value = projects.value[0].project_id
    }
  } catch (error) {
    projectError.value = error?.message || '加载项目失败'
  }
}

async function loadRequirements() {
  reqError.value = ''
  if (!selectedProjectId.value) {
    requirements.value = []
    return
  }
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = data.requirements || []
  } catch (error) {
    reqError.value = error?.message || '加载需求失败'
    requirements.value = []
  }
}

function resetForm() {
  newForm.value = {
    title: '',
    reproduce_steps: '',
    requirement_id: '',
    severity: 'medium',
    priority: 'P2',
    status: 'open',
    reporter: '',
    dev_assignee: '',
    tester_assignee: '',
  }
}

async function createNewDefect() {
  const title = newForm.value.title.trim()
  const steps = newForm.value.reproduce_steps.trim()
  if (!selectedProjectId.value || !title || !steps || !newForm.value.requirement_id) {
    reqError.value = '请填写缺陷标题、复现步骤，并选择关联需求'
    return
  }

  const req = requirementOptions.value.find((item) => item.id === newForm.value.requirement_id)
  reqError.value = ''
  try {
    await createDefect({
      ...newForm.value,
      title,
      reproduce_steps: steps,
      requirement_title: req?.title || '',
      current_assignee: newForm.value.dev_assignee || '',
    })
    resetForm()
  } catch (error) {
    reqError.value = error?.message || '创建缺陷失败'
  }
}

async function updateStatus(defectId, nextStatus) {
  reqError.value = ''
  try {
    await setStatus(defectId, nextStatus)
  } catch (error) {
    reqError.value = error?.message || '更新缺陷状态失败'
  }
}

async function updateDefectField(defectId, patch) {
  reqError.value = ''
  try {
    await updateDefect(defectId, patch)
  } catch (error) {
    reqError.value = error?.message || '更新缺陷失败'
  }
}

async function removeDefect(defectId) {
  reqError.value = ''
  try {
    await deleteDefect(defectId)
  } catch (error) {
    reqError.value = error?.message || '删除缺陷失败'
  }
}

async function handleReload() {
  reqError.value = ''
  try {
    await reload()
  } catch (error) {
    reqError.value = error?.message || '加载缺陷失败'
  }
}

function jumpToRequirement(defect) {
  if (!defect?.requirement_id) return
  router.push({
    path: '/alpha/requirements-manage',
    query: {
      project_id: selectedProjectId.value,
      focus_requirement_id: defect.requirement_id,
    },
  })
}

watch(selectedProjectId, async () => {
  try {
    await Promise.all([reload(), loadRequirements()])
  } catch {
    // errors are surfaced via reqError / defectsError
  }
})

onMounted(async () => {
  const qProject = String(route.query.project_id || '')
  const qReqId = String(route.query.requirement_id || '')
  const qReqTitle = String(route.query.requirement_title || '')
  if (qProject) selectedProjectId.value = qProject
  await loadProjects()
  await handleReload()
  await loadRequirements()
  if (qReqId) newForm.value.requirement_id = qReqId
  if (qReqTitle && !newForm.value.title) {
    newForm.value.title = `【来源需求】${qReqTitle} 存在缺陷`
  }
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <header class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-2 text-zinc-900">
        <AlertTriangle class="w-5 h-5" />
        <h2 class="text-xl font-semibold">缺陷与问题工作台</h2>
      </div>
      <button
        class="inline-flex items-center gap-2 text-sm text-zinc-700 border border-zinc-300 rounded-md px-3 py-1.5 hover:bg-zinc-50"
        @click="handleReload"
      >
        <RefreshCw class="w-4 h-4" />
        刷新
      </button>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
      <section class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-3">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
          <select v-model="selectedProjectId" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.project_id" :value="p.project_id">{{ p.name }}</option>
          </select>
          <div class="text-sm text-zinc-700">未解决：<span class="font-semibold">{{ unresolvedCount }}</span></div>
          <div class="text-sm text-zinc-700">致命未解决：<span class="font-semibold text-red-600">{{ criticalCount }}</span></div>
        </div>
        <p v-if="projectError" class="text-xs text-red-600">{{ projectError }}</p>
        <p v-if="reqError" class="text-xs text-red-600">{{ reqError }}</p>
        <p v-if="defectsError" class="text-xs text-red-600">{{ defectsError }}</p>
      </section>

      <section v-if="selectedProject" class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-4">
        <h3 class="text-sm font-semibold text-zinc-900">新增缺陷（标准化录入）</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input v-model="newForm.title" placeholder="缺陷标题" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          <select v-model="newForm.requirement_id" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
            <option value="">关联需求（必选）</option>
            <option v-for="req in requirementOptions" :key="req.id" :value="req.id">{{ req.title }}</option>
          </select>
          <textarea v-model="newForm.reproduce_steps" rows="3" placeholder="复现步骤（必填）" class="md:col-span-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm"></textarea>
          <select v-model="newForm.severity" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
            <option v-for="item in severityOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <select v-model="newForm.priority" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm">
            <option v-for="item in priorityOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <input v-model="newForm.reporter" placeholder="报告人（测试）" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          <input v-model="newForm.dev_assignee" placeholder="指派开发人" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
          <input v-model="newForm.tester_assignee" placeholder="回指派测试人（验证）" class="rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
        </div>
        <button class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-3 py-2 text-sm text-white" @click="createNewDefect">
          创建缺陷
        </button>
      </section>

      <section v-if="selectedProject" class="bg-white border border-zinc-200 rounded-xl p-5 shadow-sm space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="text-sm font-semibold text-zinc-900 mr-2">全局看板</h3>
          <label class="text-xs flex items-center gap-1">
            <input v-model="filter.onlyUnresolved" type="checkbox" class="w-3.5 h-3.5" />
            仅看未解决
          </label>
          <select v-model="filter.status" class="text-xs rounded border border-zinc-300 px-2 py-1">
            <option value="">全部状态</option>
            <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <select v-model="filter.severity" class="text-xs rounded border border-zinc-300 px-2 py-1">
            <option value="">全部严重度</option>
            <option v-for="item in severityOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <input v-model="filter.assignee" placeholder="按当前处理人筛选" class="text-xs rounded border border-zinc-300 px-2 py-1" />
        </div>

        <div class="text-xs text-zinc-600">
          负责人负载：
          <span v-if="byAssignee.length === 0">无</span>
          <span v-for="item in byAssignee" :key="item.name" class="mr-2">{{ item.name }}({{ item.count }})</span>
        </div>

        <div class="overflow-auto max-h-[460px] border border-zinc-200 rounded-lg">
          <table class="min-w-full text-xs text-zinc-700">
            <thead class="bg-zinc-50 sticky top-0">
              <tr>
                <th class="text-left px-2 py-2 border-b border-zinc-200">ID</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">标题</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">关联需求</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">严重度</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">优先级</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">状态</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">开发</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">测试验证</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">当前处理人</th>
                <th class="text-left px-2 py-2 border-b border-zinc-200">动作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredDefects" :key="item.defect_id" class="border-b border-zinc-100 align-top">
                <td class="px-2 py-2 font-mono text-[10px] text-zinc-500">{{ item.defect_id }}</td>
                <td class="px-2 py-2">
                  <div class="font-medium text-zinc-800">{{ item.title }}</div>
                  <div class="text-zinc-500 whitespace-pre-wrap mt-1">{{ item.reproduce_steps }}</div>
                </td>
                <td class="px-2 py-2">
                  <button class="text-blue-600 hover:underline" @click="jumpToRequirement(item)">
                    {{ item.requirement_title || item.requirement_id || '-' }}
                  </button>
                </td>
                <td class="px-2 py-2">
                  <select
                    :value="item.severity"
                    class="rounded border border-zinc-300 px-1.5 py-1"
                    @change="updateDefectField(item.defect_id, { severity: $event.target.value })"
                  >
                    <option v-for="s in severityOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                  </select>
                </td>
                <td class="px-2 py-2">
                  <select
                    :value="item.priority"
                    class="rounded border border-zinc-300 px-1.5 py-1"
                    @change="updateDefectField(item.defect_id, { priority: $event.target.value })"
                  >
                    <option v-for="p in priorityOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
                  </select>
                </td>
                <td class="px-2 py-2">
                  <span class="inline-flex px-2 py-0.5 rounded-full" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
                </td>
                <td class="px-2 py-2">
                  <input
                    :value="item.dev_assignee || ''"
                    class="w-[120px] rounded border border-zinc-300 px-1.5 py-1"
                    @change="updateDefectField(item.defect_id, { dev_assignee: $event.target.value })"
                  />
                </td>
                <td class="px-2 py-2">
                  <input
                    :value="item.tester_assignee || ''"
                    class="w-[120px] rounded border border-zinc-300 px-1.5 py-1"
                    @change="updateDefectField(item.defect_id, { tester_assignee: $event.target.value })"
                  />
                </td>
                <td class="px-2 py-2 text-zinc-600">{{ item.current_assignee || '-' }}</td>
                <td class="px-2 py-2">
                  <div class="flex flex-col gap-1">
                    <select
                      :value="item.status"
                      class="rounded border border-zinc-300 px-1.5 py-1"
                      @change="updateStatus(item.defect_id, $event.target.value)"
                    >
                      <option v-for="s in statusOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                    </select>
                    <button class="text-red-600 hover:underline text-left" @click="removeDefect(item.defect_id)">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="filteredDefects.length === 0">
                <td colspan="10" class="px-3 py-4 text-center text-zinc-500">
                  {{ loading ? '加载中...' : '暂无缺陷记录' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
