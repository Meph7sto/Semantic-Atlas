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
import HeroSection from "../../components/main/HeroSection.vue";
import AvailabilityMatrix from "../../components/main/AvailabilityMatrix.vue";
import Sidebar from "../../components/main/Sidebar.vue";

const router = useRouter();
const route = useRoute();

// 从 localStorage 获取当前用户信息
const currentUser = ref(null);

// 向后兼容的旧字段
const roleType = ref("");
const roleLabel = ref("");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);

// 页面路由映射
const routeNameToPageKey = {
  "main-dashboard": "dashboard",
  "main-project": "project-management",
  "main-requirements": "requirements",
  "main-requirements-session": "requirements-session",
  "main-requirements-analysis": "requirements-analysis",
  "main-requirements-collection": "requirements-collection",
  "main-products": "products",
};

const pageKeyToRouteName = {
  "dashboard": "main-dashboard",
  "project-management": "main-project",
  "requirements": "main-requirements",
  "requirements-session": "main-requirements-session",
  "requirements-analysis": "main-requirements-analysis",
  "requirements-collection": "main-requirements-collection",
  "products": "main-products",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "dashboard");

onMounted(() => {
  try {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      currentUser.value = JSON.parse(userStr);
    }
  } catch (e) {
    console.error('Failed to parse user data:', e);
  }
});

const handleNavigate = (page) => {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
};

const handleExit = () => {
  try {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('actor');
    localStorage.removeItem('role');
  } catch (e) {
    console.error('Failed to clear auth data:', e);
  }
  router.push({ name: "main-login" });
};
</script>
