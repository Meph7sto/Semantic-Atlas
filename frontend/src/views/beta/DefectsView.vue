<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="roleType"
        :roleLabel="roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">缺陷与问题 · 全局工作台</span>
          </div>
          <div class="page-actions">
            <button v-if="showBackToRequirement" type="button" class="action-btn ghost sa-button sa-button--secondary" @click="backToRequirement">
              返回需求
            </button>
            <button type="button" class="action-btn ghost sa-button sa-button--secondary" @click="handleReload">
              <RefreshCw class="btn-icon" />
              刷新
            </button>
          </div>
        </section>

        <section class="grid" data-animate style="--delay: 0.12s">
          <article class="card wide sa-card">
            <div class="card-header">
              <h3>项目与看板概览</h3>
            </div>
            <div class="card-body">
              <div class="filter-row">
                <select v-model="selectedProjectId" class="form-select sa-input">
                  <option value="">请选择项目</option>
                  <option v-for="p in projects" :key="p.project_id" :value="p.project_id">{{ p.name }}</option>
                </select>
                <div class="stat-chip">未解决：<strong>{{ unresolvedCount }}</strong></div>
                <div class="stat-chip danger">致命未解决：<strong>{{ criticalCount }}</strong></div>
              </div>
              <p v-if="projectError" class="error-text">{{ projectError }}</p>
              <p v-if="defectsError" class="error-text">{{ defectsError }}</p>

              <div class="assignee-bar">
                <span class="assignee-title">负责人负载</span>
                <span v-if="byAssignee.length === 0" class="assignee-item">无</span>
                <span v-for="item in byAssignee" :key="item.name" class="assignee-item">
                  {{ item.name }}({{ item.count }})
                </span>
              </div>
            </div>
          </article>

          <article v-if="selectedProjectId" class="card wide sa-card">
            <div class="card-header">
              <h3>新增缺陷（标准化录入）</h3>
            </div>
            <div class="card-body">
              <div class="form-grid">
                <input v-model="newForm.title" type="text" class="form-input sa-input" placeholder="缺陷标题（必填）" />
                <select v-model="newForm.requirement_id" class="form-select sa-input">
                  <option value="">关联需求（必选）</option>
                  <option v-for="r in requirementOptions" :key="r.id" :value="r.id">{{ r.title }}</option>
                </select>
                <textarea
                  v-model="newForm.reproduce_steps"
                  rows="3"
                  class="form-input span-2 sa-input"
                  placeholder="复现步骤（必填）"
                ></textarea>
                <select v-model="newForm.severity" class="form-select sa-input">
                  <option v-for="s in severityOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
                <select v-model="newForm.priority" class="form-select sa-input">
                  <option v-for="p in priorityOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
                </select>
                <input v-model="newForm.reporter" type="text" class="form-input sa-input" placeholder="报告人（测试）" />
                <input v-model="newForm.dev_assignee" type="text" class="form-input sa-input" placeholder="指派开发" />
                <input v-model="newForm.tester_assignee" type="text" class="form-input sa-input" placeholder="验证测试" />
              </div>
              <div class="form-actions">
                <button type="button" class="action-btn brown sa-button sa-button--primary" @click="createNewDefect">创建缺陷</button>
              </div>
              <p v-if="reqError" class="error-text">{{ reqError }}</p>
            </div>
          </article>

          <article v-if="selectedProjectId" class="card wide sa-card">
            <div class="card-header">
              <h3>缺陷全局看板</h3>
            </div>
            <div class="card-body">
              <div class="filter-row">
                <label class="check-item">
                  <input v-model="filter.onlyUnresolved" type="checkbox" />
                  仅看未解决
                </label>
                <select v-model="filter.status" class="form-select compact sa-input">
                  <option value="">全部状态</option>
                  <option v-for="s in statusOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
                <select v-model="filter.severity" class="form-select compact sa-input">
                  <option value="">全部严重度</option>
                  <option v-for="s in severityOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
                <input v-model="filter.assignee" type="text" class="form-input compact sa-input" placeholder="按处理人筛选" />
              </div>

              <div class="table-wrap">
                <table class="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>标题</th>
                      <th>关联需求</th>
                      <th>严重度</th>
                      <th>优先级</th>
                      <th>状态</th>
                      <th>开发</th>
                      <th>测试验证</th>
                      <th>当前处理人</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in filteredDefects" :key="item.defect_id">
                      <td class="mono">{{ item.defect_id }}</td>
                      <td>
                        <div class="title">{{ item.title }}</div>
                        <div class="desc">{{ item.reproduce_steps }}</div>
                      </td>
                      <td>
                        <button type="button" class="link-btn" @click="jumpToRequirement(item)">
                          {{ item.requirement_title || item.requirement_id || '-' }}
                        </button>
                      </td>
                      <td>
                        <select
                          :value="item.severity"
                          class="form-select compact sa-input"
                          @change="updateDefectField(item.defect_id, { severity: $event.target.value })"
                        >
                          <option v-for="s in severityOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                        </select>
                      </td>
                      <td>
                        <select
                          :value="item.priority"
                          class="form-select compact sa-input"
                          @change="updateDefectField(item.defect_id, { priority: $event.target.value })"
                        >
                          <option v-for="p in priorityOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
                        </select>
                      </td>
                      <td>
                        <span class="status-chip" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span>
                      </td>
                      <td>
                        <input
                          :value="item.dev_assignee || ''"
                          class="form-input compact sa-input"
                          @change="updateDefectField(item.defect_id, { dev_assignee: $event.target.value })"
                        />
                      </td>
                      <td>
                        <input
                          :value="item.tester_assignee || ''"
                          class="form-input compact sa-input"
                          @change="updateDefectField(item.defect_id, { tester_assignee: $event.target.value })"
                        />
                      </td>
                      <td>{{ item.current_assignee || '-' }}</td>
                      <td>
                        <div class="ops">
                          <select
                            :value="item.status"
                            class="form-select compact sa-input"
                            @change="updateStatus(item.defect_id, $event.target.value)"
                          >
                            <option v-for="s in statusOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                          </select>
                          <button type="button" class="link-btn danger" @click="removeDefect(item.defect_id)">删除</button>
                        </div>
                      </td>
                    </tr>
                    <tr v-if="filteredDefects.length === 0">
                      <td colspan="10" class="empty">{{ loading ? '加载中...' : '暂无缺陷记录' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </article>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import Sidebar from '@/components/beta/Sidebar.vue'
import { manageApi } from '@/api/project'
import { useAlphaDefects } from '@/composables/useAlphaDefects'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const router = useRouter()
const route = useRoute()
const { activePage, handleNavigate, handleExit } = useBetaNavigation('defects')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

const projects = ref([])
const selectedProjectId = ref('')
const requirements = ref([])
const projectError = ref('')
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

const requirementOptions = computed(() =>
  (requirements.value || []).map((item) => ({
    id: item.req_id || item.id,
    title: item.title || item.text || item.req_id || item.id,
  })),
)

const backTargetRoute = computed(() => {
  const candidate = String(route.query.return_route || '').trim()
  return candidate || 'beta-requirements'
})

const backRequirementId = computed(() =>
  String(route.query.focus_requirement_id || route.query.requirement_id || '').trim(),
)

const showBackToRequirement = computed(() => Boolean(backRequirementId.value))

const filteredDefects = computed(() =>
  defects.value.filter((item) => {
    if (filter.value.onlyUnresolved && !unresolvedStatuses.has(item.status)) return false
    if (filter.value.status && item.status !== filter.value.status) return false
    if (filter.value.severity && item.severity !== filter.value.severity) return false
    if (filter.value.assignee && (item.current_assignee || '') !== filter.value.assignee) return false
    return true
  }),
)

function severityLabel(value) {
  return severityOptions.find((item) => item.value === value)?.label || value || '-'
}

function priorityLabel(value) {
  return priorityOptions.find((item) => item.value === value)?.label || value || '-'
}

function statusLabel(value) {
  return statusOptions.find((item) => item.value === value)?.label || value || '-'
}

function statusClass(value) {
  if (value === 'verified' || value === 'closed') return 'ok'
  if (value === 'resolved') return 'wait'
  if (value === 'in_progress') return 'doing'
  if (value === 'open') return 'todo'
  return 'plain'
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
  } catch (error) {
    reqError.value = error?.message || '创建缺陷失败'
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

async function updateStatus(defectId, nextStatus) {
  reqError.value = ''
  try {
    await setStatus(defectId, nextStatus)
  } catch (error) {
    reqError.value = error?.message || '更新缺陷状态失败'
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
    name: backTargetRoute.value,
    query: {
      project_id: selectedProjectId.value,
      focus_requirement_id: defect.requirement_id,
    },
  })
}

function backToRequirement() {
  if (!showBackToRequirement.value) return
  router.push({
    name: backTargetRoute.value,
    query: {
      project_id: selectedProjectId.value || String(route.query.project_id || ''),
      focus_requirement_id: backRequirementId.value,
    },
  })
}

watch(selectedProjectId, async (val) => {
  if (val) {
    localStorage.setItem('lastProjectId', val)
  }
  try {
    await Promise.all([reload(), loadRequirements()])
  } catch {
    // surfaced by UI state
  }
})

onMounted(async () => {
  const qProject = String(route.query.project_id || '')
  if (qProject) selectedProjectId.value = qProject
  const remember = localStorage.getItem('lastProjectId') || ''
  if (!selectedProjectId.value && remember) selectedProjectId.value = remember

  await loadProjects()
  await handleReload()
  await loadRequirements()

  const qReqId = String(route.query.requirement_id || '')
  if (qReqId) newForm.value.requirement_id = qReqId
})
</script>

<style scoped>
.card.wide {
  grid-column: 1 / -1;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.span-2 {
  grid-column: 1 / -1;
}

.form-input,
.form-select {
  border: 1px solid #d7dde5;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
  background: #fff;
}

.form-input.compact,
.form-select.compact {
  padding: 6px 8px;
  font-size: 12px;
}

.stat-chip {
  border: 1px solid #d7dde5;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  color: #334155;
}

.stat-chip.danger {
  border-color: #fecaca;
  color: #b91c1c;
  background: #fef2f2;
}

.assignee-bar {
  font-size: 12px;
  color: #64748b;
}

.assignee-title {
  margin-right: 8px;
  font-weight: 600;
}

.assignee-item {
  margin-right: 8px;
}

.table-wrap {
  overflow: auto;
  border: 1px solid #e6ebf2;
  border-radius: 10px;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.table th,
.table td {
  border-bottom: 1px solid #eef2f7;
  padding: 8px;
  text-align: left;
  vertical-align: top;
}

.table th {
  background: #f8fafc;
  white-space: nowrap;
}

.mono {
  font-family: Consolas, 'Courier New', monospace;
}

.title {
  font-weight: 600;
  color: #111827;
}

.desc {
  color: #64748b;
  margin-top: 4px;
  white-space: pre-wrap;
}

.status-chip {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
}

.status-chip.ok {
  background: #dcfce7;
  color: #166534;
}

.status-chip.wait {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-chip.doing {
  background: #fef3c7;
  color: #92400e;
}

.status-chip.todo {
  background: #fee2e2;
  color: #b91c1c;
}

.status-chip.plain {
  background: #f1f5f9;
  color: #475569;
}

.ops {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.link-btn {
  border: none;
  background: transparent;
  color: #2563eb;
  padding: 0;
  cursor: pointer;
}

.link-btn.danger {
  color: #dc2626;
}

.link-btn:hover {
  text-decoration: underline;
}

.check-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.empty {
  text-align: center;
  color: #64748b;
  padding: 16px;
}

.error-text {
  font-size: 12px;
  color: #dc2626;
}

@media (max-width: 920px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
