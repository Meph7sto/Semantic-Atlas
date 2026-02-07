<script setup>
import { ref, computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AlphaSidebar from '@/components/alpha/AlphaSidebar.vue'

const route = useRoute()

// Layout mode detection
const isMainRoute = computed(() => route.path.startsWith('/main'))
const isGuideRoute = computed(() => route.path.startsWith('/guide'))
const isAlphaRoute = computed(() => !isMainRoute.value && !isGuideRoute.value)

// Alpha sidebar state
const isSidebarOpen = ref(true)
</script>

<template>
  <!-- Main routes: Self-contained layout -->
  <div v-if="isMainRoute" class="min-h-screen">
    <RouterView />
  </div>

  <!-- Guide route: Full-screen without sidebar -->
  <div v-else-if="isGuideRoute" class="min-h-screen bg-white">
    <RouterView />
  </div>

  <!-- Alpha routes: Sidebar + Content layout -->
  <div v-else-if="isAlphaRoute" class="flex h-screen w-full bg-white">
    <AlphaSidebar v-model:isOpen="isSidebarOpen" />

    <main class="flex-1 flex flex-col h-full overflow-hidden bg-white relative transition-all duration-300">
      <RouterView />
    </main>
  </div>
</template>
