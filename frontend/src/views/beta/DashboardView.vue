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
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth.js";
import HeroSection from "../../components/beta/HeroSection.vue";
import AvailabilityMatrix from "../../components/beta/AvailabilityMatrix.vue";
import Sidebar from "../../components/beta/Sidebar.vue";
import { useBetaNavigation, useBetaSidebarProps } from "@/composables/useBetaNavigation";

const authStore = useAuthStore();
const { activePage, handleNavigate, handleExit } = useBetaNavigation("dashboard");
const { currentUser, roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps();

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
</script>
