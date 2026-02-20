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
        <HeroSection />
        <section class="grid" data-animate style="--delay: 0.12s">
          <AvailabilityMatrix class="wide" />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";
import HeroSection from "../../components/beta/HeroSection.vue";
import AvailabilityMatrix from "../../components/beta/AvailabilityMatrix.vue";
import Sidebar from "../../components/beta/Sidebar.vue";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

// 从 authStore 获取当前用户信息
const currentUser = computed(() => authStore.user);

// 向后兼容的旧字段
const roleType = computed(() => {
  const role = authStore.systemIdentity || authStore.systemRole
  const roleMap = {
    'SYS_ADMIN': 'unified_admin',
    'SYS_USER': 'unified_member',
    'SYS_CLIENT': 'unified_client',
    'SYS_CONTRACTOR': 'unified_contractor',
    'admin': 'unified_admin',
    'member': 'unified_member',
    'viewer': 'unified_viewer'
  }
  return roleMap[role] || 'unified_member'
})

const roleLabel = computed(() => currentUser.value?.display_name || currentUser.value?.username || roleType.value)
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);

// 加载项目权限上下文的标志
const loadingContexts = ref(new Set())

// 加载项目权限上下文
async function loadProjectContext(projectId) {
  if (!projectId || loadingContexts.value.has(projectId)) {
    return
  }

  loadingContexts.value.add(projectId)
  try {
    await authStore.loadProjectContext(projectId)
  } catch (error) {
    console.error('Failed to load project context:', error)
  } finally {
    loadingContexts.value.delete(projectId)
  }
}

// 页面路由映射
const routeNameToPageKey = {
  "beta-dashboard": "dashboard",
  "beta-project": "project-management",
  "beta-requirements": "requirements",
  "beta-requirements-session": "requirements-session",
  "beta-requirements-analysis": "requirements-analysis",
  "beta-requirements-collection": "requirements-collection",
  "beta-products": "products",
};

const pageKeyToRouteName = {
  "dashboard": "beta-dashboard",
  "project-management": "beta-project",
  "requirements": "beta-requirements",
  "requirements-session": "beta-requirements-session",
  "requirements-analysis": "beta-requirements-analysis",
  "requirements-collection": "beta-requirements-collection",
  "products": "beta-products",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "dashboard");

onMounted(() => {
  // authStore.init() 已在路由守卫中调用
  // 这里可以预加载常用项目的权限上下文
});

const handleExit = async () => {
  try {
    await authStore.logout()
  } catch (e) {
    console.error('Failed to logout:', e);
  }
  router.push({ name: "beta-login" });
};

const handleNavigate = (page) => {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
};
</script>
