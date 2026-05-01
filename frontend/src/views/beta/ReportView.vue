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
        <!-- Header -->
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">报告 · 项目数据总览</span>
          </div>
          <div class="nav-center">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              class="tab-btn"
              :class="{ active: activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              <component :is="tab.icon" class="tab-icon" />
              {{ tab.label }}
            </button>
          </div>
          <div class="page-actions">
            <select v-model="selectedProjectId" class="project-select sa-input">
              <option value="">选择项目</option>
              <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
                {{ p.name }}
              </option>
            </select>
            <button type="button" class="action-btn ghost sa-button sa-button--secondary" @click="refreshAll" :disabled="isLoading">
              <RefreshCw class="btn-icon" :class="{ spin: isLoading }" />
              刷新
            </button>
            <button
              type="button"
              class="action-btn brown sa-button sa-button--primary"
              :disabled="!selectedProjectId"
              @click="exportMarkdown"
            >
              <Download class="btn-icon" />
              导出 MD
            </button>
          </div>
        </section>

        <!-- Tab: 项目总览 -->
        <section v-if="activeTab === 'overview'" class="tab-content" data-animate style="--delay: 0.12s">
          <div v-if="!selectedProjectId" class="empty-state">请先选择一个项目</div>
          <template v-else>
            <div class="kpi-grid">
              <div class="kpi-card">
                <span class="kpi-label">需求总数</span>
                <strong class="kpi-value">{{ requirementStats.total }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">草稿</span>
                <strong class="kpi-value muted">{{ requirementStats.draft }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">已审核</span>
                <strong class="kpi-value teal">{{ requirementStats.reviewed }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">已发布</span>
                <strong class="kpi-value accent">{{ requirementStats.published }}</strong>
              </div>
            </div>

            <div class="kpi-grid">
              <div class="kpi-card">
                <span class="kpi-label">缺陷总数</span>
                <strong class="kpi-value">{{ defectStats.total }}</strong>
              </div>
              <div class="kpi-card danger">
                <span class="kpi-label">未解决</span>
                <strong class="kpi-value">{{ defectStats.unresolved }}</strong>
              </div>
              <div class="kpi-card danger">
                <span class="kpi-label">致命级</span>
                <strong class="kpi-value">{{ defectStats.critical }}</strong>
              </div>
              <div class="kpi-card ok">
                <span class="kpi-label">已关闭</span>
                <strong class="kpi-value">{{ defectStats.closed }}</strong>
              </div>
            </div>

            <!-- 需求状态分布 -->
            <div class="report-card">
              <h3 class="card-title">需求状态分布</h3>
              <div class="bar-chart">
                <div v-for="item in requirementDistribution" :key="item.label" class="bar-row">
                  <span class="bar-label">{{ item.label }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: item.percent + '%', background: item.color }" />
                  </div>
                  <span class="bar-count">{{ item.count }}</span>
                </div>
              </div>
            </div>

            <!-- 缺陷严重度分布 -->
            <div class="report-card">
              <h3 class="card-title">缺陷严重度分布</h3>
              <div class="bar-chart">
                <div v-for="item in defectSeverityDistribution" :key="item.label" class="bar-row">
                  <span class="bar-label">{{ item.label }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: item.percent + '%', background: item.color }" />
                  </div>
                  <span class="bar-count">{{ item.count }}</span>
                </div>
              </div>
            </div>
          </template>
        </section>

        <!-- Tab: 缺陷报告 -->
        <section v-if="activeTab === 'defects'" class="tab-content" data-animate style="--delay: 0.12s">
          <div v-if="!selectedProjectId" class="empty-state">请先选择一个项目</div>
          <template v-else>
            <div class="kpi-grid">
              <div class="kpi-card">
                <span class="kpi-label">总缺陷</span>
                <strong class="kpi-value">{{ defectStats.total }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">打开</span>
                <strong class="kpi-value warn">{{ defectStats.open }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">进行中</span>
                <strong class="kpi-value">{{ defectStats.inProgress }}</strong>
              </div>
              <div class="kpi-card">
                <span class="kpi-label">已解决</span>
                <strong class="kpi-value teal">{{ defectStats.resolved }}</strong>
              </div>
              <div class="kpi-card ok">
                <span class="kpi-label">已验证</span>
                <strong class="kpi-value">{{ defectStats.verified }}</strong>
              </div>
              <div class="kpi-card ok">
                <span class="kpi-label">已关闭</span>
                <strong class="kpi-value">{{ defectStats.closed }}</strong>
              </div>
            </div>

            <!-- 缺陷状态分布 -->
            <div class="report-card">
              <h3 class="card-title">缺陷状态分布</h3>
              <div class="bar-chart">
                <div v-for="item in defectStatusDistribution" :key="item.label" class="bar-row">
                  <span class="bar-label">{{ item.label }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: item.percent + '%', background: item.color }" />
                  </div>
                  <span class="bar-count">{{ item.count }}</span>
                </div>
              </div>
            </div>

            <!-- 按负责人统计 -->
            <div class="report-card">
              <h3 class="card-title">按负责人统计</h3>
              <div v-if="defectByAssignee.length === 0" class="empty-hint">暂无负责人数据</div>
              <div v-else class="bar-chart">
                <div v-for="item in defectByAssignee" :key="item.name" class="bar-row">
                  <span class="bar-label">{{ item.name || '未指派' }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: item.percent + '%', background: '#c4692f' }" />
                  </div>
                  <span class="bar-count">{{ item.count }}</span>
                </div>
              </div>
            </div>
          </template>
        </section>

        <!-- Tab: 追踪覆盖 -->
        <section v-if="activeTab === 'traceability'" class="tab-content" data-animate style="--delay: 0.12s">
          <div v-if="!selectedProjectId" class="empty-state">请先选择一个项目</div>
          <template v-else>
            <div v-if="isLoadingTrace" class="loading-state">
              <RefreshCw class="spin loading-icon" />
            </div>
            <template v-else-if="traceOverview">
              <div class="kpi-grid">
                <div class="kpi-card">
                  <span class="kpi-label">需求快照</span>
                  <strong class="kpi-value">{{ traceOverview.requirement_count ?? '-' }}</strong>
                </div>
                <div class="kpi-card">
                  <span class="kpi-label">测试用例</span>
                  <strong class="kpi-value">{{ traceOverview.test_case_count ?? '-' }}</strong>
                </div>
                <div class="kpi-card">
                  <span class="kpi-label">变更集</span>
                  <strong class="kpi-value">{{ traceOverview.change_count ?? '-' }}</strong>
                </div>
                <div class="kpi-card">
                  <span class="kpi-label">审计事件</span>
                  <strong class="kpi-value">{{ traceOverview.audit_count ?? '-' }}</strong>
                </div>
              </div>

              <!-- 覆盖率 -->
              <div v-if="traceCoverage" class="report-card">
                <h3 class="card-title">需求覆盖率</h3>
                <div class="coverage-meter">
                  <div class="coverage-bar">
                    <div
                      class="coverage-fill"
                      :style="{ width: coveragePercent + '%' }"
                    />
                  </div>
                  <span class="coverage-label">{{ coveragePercent }}%</span>
                </div>
                <p class="coverage-hint">
                  {{ traceCoverage.covered ?? 0 }} / {{ traceCoverage.total ?? 0 }} 需求已关联测试用例
                </p>
              </div>
            </template>
            <div v-else class="empty-state">暂无追踪数据，请先在追踪模块配置分支</div>
          </template>
        </section>

        <!-- Tab: 审计日志 -->
        <section v-if="activeTab === 'audit'" class="tab-content" data-animate style="--delay: 0.12s">
          <div v-if="!selectedProjectId" class="empty-state">请先选择一个项目</div>
          <template v-else>
            <div v-if="isLoadingAudits" class="loading-state">
              <RefreshCw class="spin loading-icon" />
            </div>
            <div v-else-if="audits.length === 0" class="empty-state">暂无审计日志</div>
            <div v-else class="audit-list">
              <div v-for="(entry, idx) in audits" :key="idx" class="audit-row">
                <div class="audit-time">{{ formatTime(entry.created_at || entry.timestamp) }}</div>
                <div class="audit-body">
                  <span class="audit-action tag" :class="auditActionClass(entry.action)">
                    {{ entry.action || entry.event_type || '-' }}
                  </span>
                  <span class="audit-detail">
                    {{ entry.description || entry.detail || entry.summary || '-' }}
                  </span>
                </div>
                <div class="audit-actor">{{ entry.actor || entry.created_by || '-' }}</div>
              </div>
            </div>
          </template>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import Sidebar from '@/components/beta/Sidebar.vue'
import { manageApi } from '@/api/project'
import {
  RefreshCw, BarChart3, Bug, Shield, ScrollText, Download,
} from 'lucide-vue-next'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('reports')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

// ─── Tabs ───
const tabs = [
  { key: 'overview', label: '项目总览', icon: BarChart3 },
  { key: 'defects', label: '缺陷报告', icon: Bug },
  { key: 'traceability', label: '追踪覆盖', icon: Shield },
  { key: 'audit', label: '审计日志', icon: ScrollText },
]
const activeTab = ref('overview')

// ─── Project selection ───
const projects = ref([])
const selectedProjectId = ref('')
const isLoading = ref(false)

// ─── Data stores ───
const requirements = ref([])
const defects = ref([])
const traceOverview = ref(null)
const traceCoverage = ref(null)
const audits = ref([])
const isLoadingTrace = ref(false)
const isLoadingAudits = ref(false)

// ─── Computed: requirement stats ───
const requirementStats = computed(() => {
  const list = requirements.value
  const total = list.length
  const draft = list.filter(r => r.status === 'draft' || !r.status).length
  const reviewed = list.filter(r => r.status === 'reviewed' || r.status === 'approved').length
  const published = list.filter(r => r.status === 'published' || r.status === 'released').length
  return { total, draft, reviewed, published }
})

const requirementDistribution = computed(() => {
  const s = requirementStats.value
  const max = Math.max(s.draft, s.reviewed, s.published, 1)
  return [
    { label: '草稿', count: s.draft, percent: (s.draft / max) * 100, color: '#9eabb4' },
    { label: '已审核', count: s.reviewed, percent: (s.reviewed / max) * 100, color: '#2f8f89' },
    { label: '已发布', count: s.published, percent: (s.published / max) * 100, color: '#c4692f' },
  ]
})

// ─── Computed: defect stats ───
const UNRESOLVED = new Set(['open', 'in_progress', 'reopen'])

const defectStats = computed(() => {
  const list = defects.value
  const total = list.length
  const open = list.filter(d => d.status === 'open').length
  const inProgress = list.filter(d => d.status === 'in_progress').length
  const resolved = list.filter(d => d.status === 'resolved').length
  const verified = list.filter(d => d.status === 'verified').length
  const closed = list.filter(d => d.status === 'closed').length
  const unresolved = list.filter(d => UNRESOLVED.has(d.status)).length
  const critical = list.filter(d =>
    UNRESOLVED.has(d.status) && (d.severity === 'critical' || d.severity === 'blocker'),
  ).length
  return { total, open, inProgress, resolved, verified, closed, unresolved, critical }
})

const defectSeverityDistribution = computed(() => {
  const list = defects.value
  const groups = [
    { label: '致命', key: 'critical', color: '#b91c1c' },
    { label: '严重', key: 'major', color: '#dc2626' },
    { label: '一般', key: 'medium', color: '#f59e0b' },
    { label: '轻微', key: 'minor', color: '#16a34a' },
  ]
  const max = Math.max(...groups.map(g => list.filter(d => d.severity === g.key).length), 1)
  return groups.map(g => {
    const count = list.filter(d => d.severity === g.key).length
    return { ...g, count, percent: (count / max) * 100 }
  })
})

const defectStatusDistribution = computed(() => {
  const s = defectStats.value
  const groups = [
    { label: '打开', count: s.open, color: '#dc2626' },
    { label: '进行中', count: s.inProgress, color: '#f59e0b' },
    { label: '已解决', count: s.resolved, color: '#2563eb' },
    { label: '已验证', count: s.verified, color: '#16a34a' },
    { label: '已关闭', count: s.closed, color: '#9eabb4' },
  ]
  const max = Math.max(...groups.map(g => g.count), 1)
  return groups.map(g => ({ ...g, percent: (g.count / max) * 100 }))
})

const defectByAssignee = computed(() => {
  const map = {}
  for (const d of defects.value) {
    const name = d.current_assignee || d.dev_assignee || ''
    if (!map[name]) map[name] = 0
    map[name]++
  }
  const entries = Object.entries(map)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
  const max = Math.max(...entries.map(e => e.count), 1)
  return entries.map(e => ({ ...e, percent: (e.count / max) * 100 }))
})

// ─── Computed: coverage ───
const coveragePercent = computed(() => {
  if (!traceCoverage.value) return 0
  const { covered = 0, total = 0 } = traceCoverage.value
  if (total === 0) return 0
  return Math.round((covered / total) * 100)
})

// ─── Data loaders ───
async function loadProjects() {
  try {
    const data = await manageApi.listProjects()
    projects.value = data.projects || []
    if (!selectedProjectId.value && projects.value.length > 0) {
      selectedProjectId.value = projects.value[0].project_id
    }
  } catch (e) {
    console.error('加载项目列表失败', e)
  }
}

async function loadRequirements() {
  if (!selectedProjectId.value) { requirements.value = []; return }
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value)
    requirements.value = data.requirements || []
  } catch (e) {
    console.error('加载需求失败', e)
    requirements.value = []
  }
}

async function loadDefects() {
  if (!selectedProjectId.value) { defects.value = []; return }
  try {
    const data = await manageApi.listDefects(selectedProjectId.value)
    defects.value = data.defects || []
  } catch (e) {
    console.error('加载缺陷失败', e)
    defects.value = []
  }
}

async function loadTraceability() {
  if (!selectedProjectId.value) {
    traceOverview.value = null
    traceCoverage.value = null
    return
  }
  isLoadingTrace.value = true
  try {
    const [ov, cov] = await Promise.allSettled([
      manageApi.getTraceabilityOverview(selectedProjectId.value),
      manageApi.getTraceabilityCoverage(selectedProjectId.value),
    ])
    traceOverview.value = ov.status === 'fulfilled' ? (ov.value?.summary || ov.value) : null
    traceCoverage.value = cov.status === 'fulfilled' ? (cov.value?.coverage || cov.value) : null
  } catch (e) {
    console.error('加载追踪数据失败', e)
  } finally {
    isLoadingTrace.value = false
  }
}

async function loadAudits() {
  if (!selectedProjectId.value) { audits.value = []; return }
  isLoadingAudits.value = true
  try {
    const data = await manageApi.listAudits(selectedProjectId.value, 50)
    audits.value = data.audits || data.events || []
  } catch (e) {
    console.error('加载审计日志失败', e)
    audits.value = []
  } finally {
    isLoadingAudits.value = false
  }
}

async function refreshAll() {
  isLoading.value = true
  try {
    await Promise.all([loadRequirements(), loadDefects(), loadTraceability(), loadAudits()])
  } finally {
    isLoading.value = false
  }
}

// ─── Utilities ───
function formatTime(isoString) {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function auditActionClass(action) {
  if (!action) return ''
  const a = action.toLowerCase()
  if (a.includes('create') || a.includes('add')) return 'tag-create'
  if (a.includes('update') || a.includes('change')) return 'tag-update'
  if (a.includes('delete') || a.includes('remove')) return 'tag-delete'
  return 'tag-neutral'
}

// ─── Markdown Export ───
function buildMarkdown() {
  const project = projects.value.find(p => p.project_id === selectedProjectId.value)
  const projectName = project?.name || selectedProjectId.value
  const now = new Date().toLocaleString('zh-CN')
  const lines = []

  lines.push(`# 项目报告：${projectName}`)
  lines.push(`\n> 导出时间：${now}\n`)

  // 需求统计
  const rs = requirementStats.value
  lines.push('## 一、需求统计\n')
  lines.push('| 指标 | 数量 |')
  lines.push('| --- | ---: |')
  lines.push(`| 需求总数 | ${rs.total} |`)
  lines.push(`| 草稿 | ${rs.draft} |`)
  lines.push(`| 已审核 | ${rs.reviewed} |`)
  lines.push(`| 已发布 | ${rs.published} |`)

  // 缺陷统计
  const ds = defectStats.value
  lines.push('\n## 二、缺陷统计\n')
  lines.push('| 指标 | 数量 |')
  lines.push('| --- | ---: |')
  lines.push(`| 总缺陷 | ${ds.total} |`)
  lines.push(`| 未解决 | ${ds.unresolved} |`)
  lines.push(`| 致命级（未解决） | ${ds.critical} |`)
  lines.push(`| 打开 | ${ds.open} |`)
  lines.push(`| 进行中 | ${ds.inProgress} |`)
  lines.push(`| 已解决 | ${ds.resolved} |`)
  lines.push(`| 已验证 | ${ds.verified} |`)
  lines.push(`| 已关闭 | ${ds.closed} |`)

  // 缺陷严重度分布
  lines.push('\n### 缺陷严重度分布\n')
  lines.push('| 严重度 | 数量 |')
  lines.push('| --- | ---: |')
  for (const item of defectSeverityDistribution.value) {
    lines.push(`| ${item.label} | ${item.count} |`)
  }

  // 按负责人
  if (defectByAssignee.value.length > 0) {
    lines.push('\n### 按负责人统计\n')
    lines.push('| 负责人 | 缺陷数 |')
    lines.push('| --- | ---: |')
    for (const item of defectByAssignee.value) {
      lines.push(`| ${item.name || '未指派'} | ${item.count} |`)
    }
  }

  // 追踪覆盖
  if (traceOverview.value) {
    const to = traceOverview.value
    lines.push('\n## 三、追踪覆盖\n')
    lines.push('| 指标 | 数量 |')
    lines.push('| --- | ---: |')
    lines.push(`| 需求快照 | ${to.requirement_count ?? '-'} |`)
    lines.push(`| 测试用例 | ${to.test_case_count ?? '-'} |`)
    lines.push(`| 变更集 | ${to.change_count ?? '-'} |`)
    lines.push(`| 审计事件 | ${to.audit_count ?? '-'} |`)
    if (traceCoverage.value) {
      const tc = traceCoverage.value
      lines.push(`\n**需求覆盖率**：${coveragePercent.value}%（${tc.covered ?? 0} / ${tc.total ?? 0}）`)
    }
  }

  // 审计日志
  if (audits.value.length > 0) {
    lines.push('\n## 四、审计日志（最近 50 条）\n')
    lines.push('| 时间 | 操作 | 描述 | 执行人 |')
    lines.push('| --- | --- | --- | --- |')
    for (const e of audits.value) {
      const time = formatTime(e.created_at || e.timestamp)
      const action = e.action || e.event_type || '-'
      const desc = (e.description || e.detail || e.summary || '-').replace(/\|/g, '\\|')
      const actor = e.actor || e.created_by || '-'
      lines.push(`| ${time} | ${action} | ${desc} | ${actor} |`)
    }
  }

  return lines.join('\n')
}

function exportMarkdown() {
  if (!selectedProjectId.value) return
  const md = buildMarkdown()
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const project = projects.value.find(p => p.project_id === selectedProjectId.value)
  const safeName = (project?.name || 'report').replace(/[^\w\u4e00-\u9fa5-]/g, '_')
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeName}_报告_${new Date().toISOString().slice(0, 10)}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ─── Watchers ───
watch(selectedProjectId, () => {
  refreshAll()
})

// ─── Init ───
onMounted(async () => {
  await loadProjects()
  if (selectedProjectId.value) {
    await refreshAll()
  }
})
</script>

<style scoped>
/* ── Tabs ── */
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid rgba(28, 40, 52, 0.1);
  background: white;
  border-radius: 0;
  font-size: 13px;
  color: #5d6b76;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn.active {
  background: #1b2730;
  color: #fff;
  border-color: #1b2730;
}
.tab-icon { width: 14px; height: 14px; }

/* ── Tab Content ── */
.tab-content {
  padding: 24px 0 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Project Selector ── */
.project-select {
  padding: 6px 10px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 0;
  font-size: 12px;
  color: #1b2730;
  background: #fff;
  outline: none;
  min-width: 160px;
}

/* ── Action Buttons ── */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
  background: #fff;
  color: #5d6b76;
  transition: all 0.15s;
}
.action-btn.ghost { background: #fff; }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-icon { width: 14px; height: 14px; }

/* ── KPI Grid ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 14px;
}
.kpi-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: #fdfcf9;
  transition: box-shadow 0.15s;
}
.kpi-card:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); }
.kpi-card.danger { border-left: 3px solid #dc2626; }
.kpi-card.ok { border-left: 3px solid #16a34a; }
.kpi-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #9eabb4;
}
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #1b2730;
  line-height: 1;
}
.kpi-value.muted { color: #9eabb4; }
.kpi-value.teal { color: #2f8f89; }
.kpi-value.accent { color: #c4692f; }
.kpi-value.warn { color: #f59e0b; }

/* ── Report Card ── */
.report-card {
  padding: 20px 24px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: #fdfcf9;
}
.card-title {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: #1b2730;
}

/* ── Bar Chart ── */
.bar-chart { display: flex; flex-direction: column; gap: 10px; }
.bar-row {
  display: grid;
  grid-template-columns: 80px 1fr 40px;
  align-items: center;
  gap: 10px;
}
.bar-label {
  font-size: 12px;
  color: #5d6b76;
  text-align: right;
}
.bar-track {
  height: 18px;
  background: rgba(28, 40, 52, 0.04);
  border-radius: 2px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
  min-width: 2px;
}
.bar-count {
  font-size: 12px;
  font-weight: 600;
  color: #1b2730;
}

/* ── Coverage Meter ── */
.coverage-meter {
  display: flex;
  align-items: center;
  gap: 12px;
}
.coverage-bar {
  flex: 1;
  height: 22px;
  background: rgba(28, 40, 52, 0.06);
  border-radius: 2px;
  overflow: hidden;
}
.coverage-fill {
  height: 100%;
  background: linear-gradient(90deg, #2f8f89, #56b6af);
  border-radius: 2px;
  transition: width 0.5s ease;
}
.coverage-label {
  font-size: 20px;
  font-weight: 700;
  color: #2f8f89;
  min-width: 50px;
}
.coverage-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9eabb4;
}

/* ── Audit List ── */
.audit-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.audit-row {
  display: grid;
  grid-template-columns: 100px 1fr 100px;
  align-items: start;
  gap: 12px;
  padding: 12px 16px;
  background: #fdfcf9;
  border: 1px solid rgba(28, 40, 52, 0.06);
  transition: box-shadow 0.15s;
}
.audit-row:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); }
.audit-time {
  font-size: 11px;
  color: #9eabb4;
  white-space: nowrap;
}
.audit-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.audit-action {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
}
.audit-detail {
  font-size: 13px;
  color: #1b2730;
}
.audit-actor {
  font-size: 12px;
  color: #5d6b76;
  text-align: right;
}
.tag-create { background: #dcfce7; color: #166534; }
.tag-update { background: #dbeafe; color: #1d4ed8; }
.tag-delete { background: #fee2e2; color: #b91c1c; }
.tag-neutral { background: #f1f5f9; color: #475569; }

/* ── Empty / Loading ── */
.empty-state {
  text-align: center;
  padding: 48px 0;
  color: #9eabb4;
  font-size: 14px;
}
.empty-hint {
  font-size: 12px;
  color: #9eabb4;
  padding: 8px 0;
}
.loading-state {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.loading-icon {
  width: 28px;
  height: 28px;
  color: #9eabb4;
}

@media (max-width: 920px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .bar-row { grid-template-columns: 60px 1fr 30px; }
  .audit-row { grid-template-columns: 1fr; }
}
</style>
