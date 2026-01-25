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
import { ref } from "vue";
import { useRouter } from "vue-router";
import HeroSection from "../../components/main/HeroSection.vue";
import AvailabilityMatrix from "../../components/main/AvailabilityMatrix.vue";
import Sidebar from "../../components/main/Sidebar.vue";

const router = useRouter();

const roleType = ref("unified_admin");
const roleLabel = ref("管理员");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);
const activePage = ref("dashboard");

const handleNavigate = (page) => {
  activePage.value = page;
  if (page === "project-management") {
    router.push({ name: "main-project" });
  }
};

const handleExit = () => {
  router.push({ name: "main-login" });
};
</script>
