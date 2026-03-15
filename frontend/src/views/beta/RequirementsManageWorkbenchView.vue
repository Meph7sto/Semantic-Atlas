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

      <main class="canvas workbench-canvas">
        <section class="workbench-header" data-animate style="--delay: 0.05s">
          <div>
            <h1>需求工程管理工作台</h1>
            <p>覆盖需求生命周期、里程碑、分支与合并历史，已迁移到 beta 正式页面。</p>
          </div>
          <button type="button" class="overview-link" @click="router.push({ name: 'beta-requirements-overview' })">
            打开需求总览
          </button>
        </section>

        <section class="workbench-body" data-animate style="--delay: 0.1s">
          <RequirementsManage class="legacy-manage" />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Sidebar from '@/components/beta/Sidebar.vue'
import RequirementsManage from '@/views/alpha/RequirementsManage.vue'

const router = useRouter()
const route = useRoute()

const roleType = ref('unified_admin')
const roleLabel = ref('管理员')
const timestamp = ref(new Date().toLocaleString())
const notificationCount = ref(0)

const routeNameToPageKey = {
  'beta-dashboard': 'dashboard',
  'beta-products': 'products',
  'beta-project': 'project-management',
  'beta-requirements': 'requirements',
  'beta-requirements-session': 'requirements-session',
  'beta-requirements-analysis': 'requirements-analysis',
  'beta-requirements-collection': 'requirements-collection',
  'beta-user-manage': 'user-management',
  'beta-account': 'account',
  'beta-requirements-overview': 'requirements',
}

const pageKeyToRouteName = {
  dashboard: 'beta-dashboard',
  products: 'beta-products',
  'project-management': 'beta-project',
  requirements: 'beta-requirements',
  'requirements-session': 'beta-requirements-session',
  'requirements-analysis': 'beta-requirements-analysis',
  'requirements-collection': 'beta-requirements-collection',
  'user-management': 'beta-user-manage',
  account: 'beta-account',
}

const activePage = computed(() => routeNameToPageKey[route.name] || 'requirements')

function handleNavigate(page) {
  const target = pageKeyToRouteName[page]
  if (target && target !== route.name) {
    router.push({ name: target })
  }
}

function handleExit() {
  router.push({ name: 'beta-login' })
}
</script>

<style scoped>
.workbench-canvas {
  padding: 18px;
  overflow: hidden;
}

.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  padding: 14px 16px;
  border: 1px solid rgba(47, 143, 137, 0.2);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(47, 143, 137, 0.08), rgba(47, 143, 137, 0.03));
}

.workbench-header h1 {
  margin: 0;
  font-size: 20px;
  color: #1f3641;
}

.workbench-header p {
  margin: 6px 0 0;
  color: #506673;
  font-size: 13px;
}

.overview-link {
  border: 1px solid rgba(47, 143, 137, 0.3);
  background: #fff;
  color: #2f8f89;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.overview-link:hover {
  background: rgba(47, 143, 137, 0.08);
}

.workbench-body {
  height: calc(100vh - 170px);
  border-radius: 10px;
  border: 1px solid #e3eaee;
  background: #f7f9fa;
  overflow: auto;
}

.legacy-manage {
  min-height: 100%;
}

@media (max-width: 1024px) {
  .workbench-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .workbench-body {
    height: calc(100vh - 220px);
  }
}
</style>
