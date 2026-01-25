<script setup>
import { ref } from 'vue'
import { RouterView, RouterLink } from 'vue-router'
import {
  LayoutDashboard,
  GitCompare,
  FileSearch,
  PanelLeftClose,
  PanelLeftOpen,
  FileText,
  MessageSquare,
  Folder,
  ChevronDown,
  ChevronRight,
  Network,
  ClipboardList
} from 'lucide-vue-next'

const isSidebarOpen = ref(true)
const isTopGroupOpen = ref(true)
</script>

<template>
  <div class="flex h-screen w-full bg-white">
    <!-- Sidebar Toggle Button (Floating when closed) -->
    <div v-if="!isSidebarOpen" class="absolute top-4 left-4 z-50">
      <button 
        @click="isSidebarOpen = true"
        class="p-2 text-zinc-500 hover:bg-zinc-100/80 hover:text-zinc-900 rounded-md transition-colors"
        title="Open Sidebar"
      >
        <PanelLeftOpen class="w-5 h-5" />
      </button>
    </div>

    <!-- Sidebar -->
    <aside 
      class="flex flex-col border-r border-zinc-200 bg-zinc-50 transition-[width,opacity,transform] duration-300 ease-in-out overflow-hidden"
      :class="isSidebarOpen ? 'w-64 opacity-100 translate-x-0' : 'w-0 opacity-0 -translate-x-4'"
    >
      <div class="p-4 mb-4 flex items-center justify-between">
        <h1 class="text-zinc-900 text-lg font-semibold tracking-wide whitespace-nowrap">Semantic Atlas</h1>
        <button 
          @click="isSidebarOpen = false"
          class="p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 rounded-md transition-colors"
          title="Close Sidebar"
        >
          <PanelLeftClose class="w-4 h-4" />
        </button>
      </div>
      
      <nav class="flex-1 px-3 space-y-1 overflow-y-auto">
        <!-- Collapsible group (top) -->
        <div class="space-y-1">
          <button
            type="button"
            @click="isTopGroupOpen = !isTopGroupOpen"
            class="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            :aria-expanded="isTopGroupOpen"
          >
            <span class="flex items-center gap-3 min-w-0">
              <Folder class="w-4 h-4 flex-shrink-0" />
              <span class="whitespace-nowrap truncate">需求分析</span>
            </span>
            <ChevronDown v-if="isTopGroupOpen" class="w-4 h-4 flex-shrink-0" />
            <ChevronRight v-else class="w-4 h-4 flex-shrink-0" />
          </button>

          <div v-show="isTopGroupOpen" class="pl-4 ml-3 border-l border-zinc-200 space-y-1">
            <RouterLink
              to="/alpha/transcript-ingestion"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <span class="whitespace-nowrap">Phase 1: 录音解析</span>
            </RouterLink>

            <RouterLink
              to="/alpha/context-builder"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <span class="whitespace-nowrap">Phase 2: 上下文构建</span>
            </RouterLink>

            <RouterLink
              to="/alpha/requirements-extraction"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <span class="whitespace-nowrap">Phase 3: 需求抽取</span>
            </RouterLink>

            <RouterLink
              to="/alpha/l4-testing"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <span class="whitespace-nowrap">Phase 4: 底层需求</span>
            </RouterLink>
          </div>
        </div>

        <RouterLink 
          to="/alpha/conflict" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <GitCompare class="w-4 h-4" />
          <span class="whitespace-nowrap">Requirement Conflict</span>
        </RouterLink>

        <!-- Placeholders for other views if they exist -->
        <RouterLink 
          to="/alpha/classification" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <LayoutDashboard class="w-4 h-4" />
          <span class="whitespace-nowrap">Classification</span>
        </RouterLink>

        <RouterLink 
          to="/alpha/requirements-manage" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <ClipboardList class="w-4 h-4" />
          <span class="whitespace-nowrap">Requirements Monitor</span>
        </RouterLink>

        <RouterLink 
          to="/alpha/traceability" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <FileSearch class="w-4 h-4" />
          <span class="whitespace-nowrap">Traceability</span>
        </RouterLink>
        <RouterLink 
          to="/alpha/acquisition" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <FileText class="w-4 h-4" />
          <span class="whitespace-nowrap">Acquisition</span>
        </RouterLink>

        <RouterLink 
          to="/alpha/acquisition-trace" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Network class="w-4 h-4" />
          <span class="whitespace-nowrap">Acquisition + Trace</span>
        </RouterLink>

        <RouterLink 
          to="/alpha/chat" 
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <MessageSquare class="w-4 h-4" />
          <span class="whitespace-nowrap">General Q&amp;A</span>
        </RouterLink>
      </nav>


    </aside>

    <!-- Main Content -->
    <main class="flex-1 flex flex-col h-full overflow-hidden bg-white relative transition-all duration-300">
      <RouterView />
    </main>
  </div>
</template>

<style>
</style>
