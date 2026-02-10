<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AlphaSidebar from '@/components/alpha/AlphaSidebar.vue'
import AiFloatingBall from '@/components/ai-chat/AiFloatingBall.vue'

const route = useRoute()

// Layout mode detection
const isMainRoute = computed(() => route.path.startsWith('/main'))
const isGuideRoute = computed(() => route.path.startsWith('/guide'))
const isAlphaRoute = computed(() => !isMainRoute.value && !isGuideRoute.value)

// Alpha sidebar state
const isSidebarOpen = ref(true)

// Main routes: use lastProjectId if available
const lastProjectId = ref(localStorage.getItem('lastProjectId') || null)

const syncLastProjectId = () => {
  lastProjectId.value = localStorage.getItem('lastProjectId') || null
}

watch(
  () => route.fullPath,
  () => {
    syncLastProjectId()
  }
)

const onProjectChanged = (e) => {
  const pid = e?.detail?.projectId
  if (pid !== undefined) {
    lastProjectId.value = pid || null
    return
  }
  syncLastProjectId()
}

const onStorage = (e) => {
  if (e?.key === 'lastProjectId') syncLastProjectId()
}

onMounted(() => {
  // Ensure we pick up latest value even if set during child mounts.
  syncLastProjectId()
  window.addEventListener('project-changed', onProjectChanged)
  window.addEventListener('storage', onStorage)
})

onBeforeUnmount(() => {
  window.removeEventListener('project-changed', onProjectChanged)
  window.removeEventListener('storage', onStorage)
})
</script>

<template>
  <!-- Main routes: Self-contained layout -->
  <div v-if="isMainRoute" class="min-h-screen">
    <RouterView v-slot="{ Component, route: viewRoute }">
      <KeepAlive>
        <component
          :is="Component"
          v-if="viewRoute.meta?.keepAlive"
          :key="viewRoute.name || viewRoute.path"
        />
      </KeepAlive>
      <component
        :is="Component"
        v-if="!viewRoute.meta?.keepAlive"
        :key="viewRoute.fullPath"
      />
    </RouterView>
    <!-- AI Floating Ball -->
    <AiFloatingBall :project-id="lastProjectId" />
  </div>

  <!-- Guide route: Full-screen without sidebar -->
  <div v-else-if="isGuideRoute" class="min-h-screen bg-white">
    <RouterView />
  </div>

  <!-- Alpha routes: Sidebar + Content layout -->
  <div v-else-if="isAlphaRoute" class="flex h-screen w-full bg-white">
    <AlphaSidebar v-model:isOpen="isSidebarOpen" />

    <main class="flex-1 flex flex-col h-full overflow-hidden bg-white relative transition-all duration-300">
      <RouterView v-slot="{ Component, route: viewRoute }">
        <KeepAlive>
          <component
            :is="Component"
            v-if="viewRoute.meta?.keepAlive"
            :key="viewRoute.name || viewRoute.path"
          />
        </KeepAlive>
        <component
          :is="Component"
          v-if="!viewRoute.meta?.keepAlive"
          :key="viewRoute.fullPath"
        />
      </RouterView>
    </main>
  </div>
</template>
