<script setup>
import { ref, computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { Palette } from 'lucide-vue-next'
import AlphaSidebar from '@/components/alpha/AlphaSidebar.vue'
import SessionAssistantPanel from '@/components/beta/SessionAssistantPanel.vue'
import { useStyleVariant } from '@/composables/useStyleVariant.js'
import { useAuthStore } from '@/stores/auth.js'

const authStore = useAuthStore()
const { isNewStyle, setStyleVariant, styleVariant } = useStyleVariant()

const route = useRoute()

// Layout mode detection
const isMainRoute = computed(() => route.path.startsWith('/beta'))
const isGuideRoute = computed(() => route.path.startsWith('/guide'))
const isAlphaRoute = computed(() => !isMainRoute.value && !isGuideRoute.value)
const showStyleSwitcher = computed(() => isMainRoute.value || isGuideRoute.value)

// Alpha sidebar state
const isSidebarOpen = ref(true)
</script>

<template>
  <!-- Main routes: Self-contained layout -->
  <div
    v-if="isMainRoute"
    class="min-h-screen semantic-style-shell"
    :class="{ 'semantic-style-new': isNewStyle }"
  >
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
    <SessionAssistantPanel v-if="authStore.isAuthenticated" />
  </div>

  <!-- Guide route: Full-screen without sidebar -->
  <div
    v-else-if="isGuideRoute"
    class="min-h-screen bg-white semantic-style-shell"
    :class="{ 'semantic-style-new': isNewStyle }"
  >
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

  <div v-if="showStyleSwitcher" class="style-switcher" role="group" aria-label="样式切换">
    <Palette class="style-switcher__icon" />
    <button
      type="button"
      class="style-switcher__option"
      :class="{ active: styleVariant === 'classic' }"
      :aria-pressed="styleVariant === 'classic'"
      @click="setStyleVariant('classic')"
    >
      默认
    </button>
    <button
      type="button"
      class="style-switcher__option"
      :class="{ active: styleVariant === 'new' }"
      :aria-pressed="styleVariant === 'new'"
      @click="setStyleVariant('new')"
    >
      新样式
    </button>
  </div>
</template>

<style scoped>
.style-switcher {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1200;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px;
  border: 1px solid rgba(28, 40, 52, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 30px rgba(28, 40, 52, 0.12);
  backdrop-filter: blur(12px);
}

.style-switcher__icon {
  width: 16px;
  height: 16px;
  margin: 0 6px;
  color: #5d6b76;
}

.style-switcher__option {
  min-width: 56px;
  border: 0;
  border-radius: 999px;
  padding: 7px 12px;
  background: transparent;
  color: #394956;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.style-switcher__option:hover {
  transform: translateY(-1px);
}

.style-switcher__option.active {
  background: #1b2730;
  color: #fff;
}

@media (max-width: 640px) {
  .style-switcher {
    right: 12px;
    bottom: 12px;
  }

  .style-switcher__option {
    min-width: 48px;
    padding: 7px 10px;
  }
}
</style>
