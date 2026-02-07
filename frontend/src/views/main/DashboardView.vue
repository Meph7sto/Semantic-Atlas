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
        <HeroSection />
        <section class="grid" data-animate style="--delay: 0.12s">
          <AvailabilityMatrix class="wide" />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useRouter, useRoute } from "vue-router";
import HeroSection from "../../components/main/HeroSection.vue";
import AvailabilityMatrix from "../../components/main/AvailabilityMatrix.vue";
import Sidebar from "../../components/main/Sidebar.vue";

const router = useRouter();
const route = useRoute();

const roleType = ref("unified_admin");
const roleLabel = ref("管理员");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);
const routeNameToPageKey = {
  "main-dashboard": "dashboard",
  "main-project": "project-management",
  "main-requirements": "requirements",
  "main-requirements-analysis": "requirements-analysis",
  "main-requirements-collection": "requirements-collection",
  "main-products": "products",
};

const pageKeyToRouteName = {
  "dashboard": "main-dashboard",
  "project-management": "main-project",
  "requirements": "main-requirements",
  "requirements-analysis": "main-requirements-analysis",
  "requirements-collection": "main-requirements-collection",
  "products": "main-products",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "dashboard");

const handleNavigate = (page) => {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
};

const handleExit = () => {
  router.push({ name: "main-login" });
};
</script>
