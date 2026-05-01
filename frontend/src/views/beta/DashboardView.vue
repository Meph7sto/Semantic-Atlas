<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="currentUser?.role || roleType"
        :roleLabel="currentUser?.display_name || currentUser?.username || roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <!-- 项目选择器 + 刷新按钮 -->
        <section class="page-header nav-style" data-animate style="--delay: 0.02s">
          <div class="nav-left">
            <span class="nav-title">仪表盘 · Dashboard</span>
          </div>
          <div class="nav-center">
            <div class="project-selector">
              <svg class="selector-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              <select v-model="selectedProjectId" class="project-select sa-input">
                <option value="">请选择项目</option>
                <option
                  v-for="p in projects"
                  :key="p.project_id"
                  :value="p.project_id"
                >{{ p.name }}</option>
              </select>
            </div>
          </div>
          <div class="page-actions">
            <span v-if="lastRefreshedAt" class="refresh-hint">
              更新于 {{ lastRefreshedAt }}
            </span>
            <button
              type="button"
              class="action-btn refresh-btn sa-button sa-button--primary"
              @click="handleRefresh"
              :disabled="isLoadingData"
            >
              <svg
                class="refresh-icon"
                :class="{ spinning: isLoadingData }"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
              </svg>
              {{ isLoadingData ? '加载中' : '刷新' }}
            </button>
          </div>
        </section>

        <!-- 错误提示 -->
        <div v-if="loadError" class="error-banner" data-animate style="--delay: 0.05s">
          <span>⚠️ {{ loadError }}</span>
          <button type="button" @click="handleRefresh">重试</button>
        </div>

        <!-- 未选择项目提示 -->
        <section v-if="!selectedProjectId" class="empty-project-hint" data-animate style="--delay: 0.08s">
          <div class="empty-content">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            <h2>选择一个项目开始</h2>
            <p>请从顶部下拉菜单选择项目，仪表盘将展示该项目的实时统计数据。</p>
            <button type="button" class="primary-btn sa-button sa-button--primary" @click="handleNavigate('project-management')">
              前往项目管理
            </button>
          </div>
        </section>

        <!-- 仪表盘内容 -->
        <template v-else>
          <HeroSection
            :reqStats="reqStats"
            :reviewStats="reviewStats"
            :defectStats="defectStats"
            :baselineInfo="baselineInfo"
            :gateMetrics="gateMetrics"
            :latestActivityLabel="latestActivityLabel"
            :loading="isLoadingData"
            @navigate="handleNavigate"
          />
          <section class="grid" data-animate style="--delay: 0.12s">
            <AvailabilityMatrix
              class="wide"
              :todos="myTodos"
              :reviews="myReviews"
              :loading="isLoadingData"
              :currentUserId="authStore.userId"
              @navigate="handleNavigate"
            />
          </section>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from "vue";
import { useAuthStore } from "@/stores/auth.js";
import HeroSection from "../../components/beta/HeroSection.vue";
import AvailabilityMatrix from "../../components/beta/AvailabilityMatrix.vue";
import Sidebar from "../../components/beta/Sidebar.vue";
import { useBetaNavigation, useBetaSidebarProps } from "@/composables/useBetaNavigation";
import { useDashboardData } from "@/composables/useDashboardData";

const authStore = useAuthStore();
const { activePage, handleNavigate, handleExit } = useBetaNavigation("dashboard");
const { currentUser, roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps();

const {
  projects,
  selectedProjectId,
  isLoadingData,
  loadError,
  lastRefreshedAt,
  reqStats,
  reviewStats,
  defectStats,
  baselineInfo,
  gateMetrics,
  latestActivityLabel,
  myTodos,
  myReviews,
  loadProjects,
  loadDashboardData,
  refresh,
} = useDashboardData();

async function handleRefresh() {
  await refresh();
}

onMounted(async () => {
  await loadProjects();
  if (selectedProjectId.value) {
    await loadDashboardData();
  }
});
</script>

<style scoped>
/* 项目选择器 */
.project-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(47, 143, 137, 0.06);
  padding: 6px 16px;
  border: 1px solid rgba(47, 143, 137, 0.15);
}

.selector-icon {
  width: 16px;
  height: 16px;
  color: #5d6b76;
  flex-shrink: 0;
}

.project-select {
  border: none;
  background: transparent;
  font-size: 13px;
  color: #1b2730;
  outline: none;
  cursor: pointer;
  min-width: 180px;
  padding: 2px 4px;
}

/* 刷新按钮 */
.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.refresh-hint {
  font-size: 11px;
  color: #9eabb4;
}

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
.action-btn:hover {
  border-color: #5d6b76;
  color: #1b2730;
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 错误提示 */
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #fff5f5;
  border: 1px solid #f0c9ca;
  color: #9c5e5e;
  font-size: 13px;
  margin-bottom: 20px;
}
.error-banner button {
  background: none;
  border: 1px solid #c4767a;
  color: #c4767a;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}

/* 空项目提示 */
.empty-project-hint {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.empty-content {
  text-align: center;
  max-width: 400px;
}

.empty-icon {
  width: 64px;
  height: 64px;
  color: #c8d0d8;
  margin-bottom: 20px;
}

.empty-content h2 {
  font-size: 24px;
  font-family: serif;
  color: #1b2730;
  margin: 0 0 12px;
}

.empty-content p {
  font-size: 14px;
  color: #9eabb4;
  line-height: 1.6;
  margin: 0 0 24px;
}

.primary-btn {
  background: var(--accent, #c4692f);
  color: white;
  border: none;
  padding: 10px 24px;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.primary-btn:hover {
  opacity: 0.9;
}
</style>
