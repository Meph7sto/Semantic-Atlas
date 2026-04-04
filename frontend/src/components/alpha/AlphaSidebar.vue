<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  LayoutDashboard,
  GitCompare,
  FileSearch,
  PanelLeftClose,
  PanelLeftOpen,
  FileText,
  Mic,
  MessageSquare,
  BrainCircuit,
  Folder,
  ChevronDown,
  ChevronRight,
  Network,
  ClipboardList,
  Bell,
  Smartphone,
  ArrowLeft,
  FolderUp,
  Image,
  Workflow,
  Radio,
  ShieldAlert,
  Bot,
  AlertTriangle
} from 'lucide-vue-next'

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:isOpen'])

const isTopGroupOpen = ref(true)
const isPostProcessingOpen = ref(false)   // 需求后处理（默认折叠）
const isMobileManagementOpen = ref(false) // 移动端管理（默认折叠）

const toggleSidebar = (open) => {
  emit('update:isOpen', open)
}
</script>

<template>
  <div class="relative h-full">
    <!-- Sidebar Toggle Button (Floating when closed) -->
    <div v-if="!isOpen" class="absolute top-4 left-4 z-50">
      <button
        @click="toggleSidebar(true)"
        class="p-2 text-zinc-500 hover:bg-zinc-100/80 hover:text-zinc-900 rounded-md transition-colors"
        title="Open Sidebar"
      >
        <PanelLeftOpen class="w-5 h-5" />
      </button>
    </div>

    <!-- Sidebar -->
    <aside
      class="flex flex-col h-full border-r border-zinc-200 bg-zinc-50 transition-[width,opacity,transform] duration-300 ease-in-out overflow-hidden"
      :class="isOpen ? 'w-64 opacity-100 translate-x-0' : 'w-0 opacity-0 -translate-x-4'"
    >
      <!-- Header -->
      <div class="p-4 mb-4 flex items-center justify-between">
        <h1 class="text-zinc-900 text-lg font-semibold tracking-wide whitespace-nowrap">Semantic Atlas</h1>
        <button
          @click="toggleSidebar(false)"
          class="p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 rounded-md transition-colors"
          title="Close Sidebar"
        >
          <PanelLeftClose class="w-4 h-4" />
        </button>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 px-3 space-y-1 overflow-y-auto">
        <!-- Collapsible group: 需求分析 Phase 1-4 -->
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

        <!-- Collapsible group: 需求后处理 -->
        <div class="space-y-1">
          <button
            type="button"
            @click="isPostProcessingOpen = !isPostProcessingOpen"
            class="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            :aria-expanded="isPostProcessingOpen"
          >
            <span class="flex items-center gap-3 min-w-0">
              <Folder class="w-4 h-4 flex-shrink-0" />
              <span class="whitespace-nowrap truncate">需求后处理</span>
            </span>
            <ChevronDown v-if="isPostProcessingOpen" class="w-4 h-4 flex-shrink-0" />
            <ChevronRight v-else class="w-4 h-4 flex-shrink-0" />
          </button>

          <div v-show="isPostProcessingOpen" class="pl-4 ml-3 border-l border-zinc-200 space-y-1">
            <RouterLink
              to="/alpha/conflict"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <GitCompare class="w-4 h-4" />
              <span class="whitespace-nowrap">Requirement Conflict</span>
            </RouterLink>

            <RouterLink
              to="/alpha/conflict-agent"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <ShieldAlert class="w-4 h-4" />
              <span class="whitespace-nowrap">Conflict Agent</span>
            </RouterLink>

            <RouterLink
              to="/alpha/classification"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <LayoutDashboard class="w-4 h-4" />
              <span class="whitespace-nowrap">Classification</span>
            </RouterLink>

            <RouterLink
              to="/alpha/requirement-classification-agent"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <BrainCircuit class="w-4 h-4" />
              <span class="whitespace-nowrap">Classification Agent</span>
            </RouterLink>

            <RouterLink
              to="/alpha/traceability"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <FileSearch class="w-4 h-4" />
              <span class="whitespace-nowrap">Traceability</span>
            </RouterLink>
          </div>
        </div>

        <!-- Standalone nav items -->
        <RouterLink
          to="/alpha/requirements-manage"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <ClipboardList class="w-4 h-4" />
          <span class="whitespace-nowrap">Requirements Monitor</span>
        </RouterLink>

        <RouterLink
          to="/alpha/requirements-manage-table"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <ClipboardList class="w-4 h-4" />
          <span class="whitespace-nowrap">Requirements Table</span>
        </RouterLink>

        <RouterLink
          to="/alpha/defects"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <AlertTriangle class="w-4 h-4" />
          <span class="whitespace-nowrap">缺陷与问题</span>
        </RouterLink>

      <RouterLink
        to="/alpha/requirement-agent"
        active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
      >
        <BrainCircuit class="w-4 h-4" />
        <span class="whitespace-nowrap">Requirement Agent</span>
      </RouterLink>

      <RouterLink
        to="/alpha/session-controller"
        active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
      >
        <Bot class="w-4 h-4" />
        <span class="whitespace-nowrap">Session Controller</span>
      </RouterLink>

      <RouterLink
        to="/alpha/chat"
        active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
      >
        <MessageSquare class="w-4 h-4" />
        <span class="whitespace-nowrap">General Q&amp;A</span>
      </RouterLink>
        <RouterLink
          to="/alpha/acquisition-trace"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Network class="w-4 h-4" />
          <span class="whitespace-nowrap">Acquisition + Trace</span>
        </RouterLink>

        <!-- Collapsible group: 移动端管理 -->
        <div class="space-y-1">
          <button
            type="button"
            @click="isMobileManagementOpen = !isMobileManagementOpen"
            class="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            :aria-expanded="isMobileManagementOpen"
          >
            <span class="flex items-center gap-3 min-w-0">
              <Smartphone class="w-4 h-4 flex-shrink-0" />
              <span class="whitespace-nowrap truncate">移动端管理</span>
            </span>
            <ChevronDown v-if="isMobileManagementOpen" class="w-4 h-4 flex-shrink-0" />
            <ChevronRight v-else class="w-4 h-4 flex-shrink-0" />
          </button>

          <div v-show="isMobileManagementOpen" class="pl-4 ml-3 border-l border-zinc-200 space-y-1">
            <RouterLink
              to="/alpha/message-push"
              active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
              class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
            >
              <Bell class="w-4 h-4" />
              <span class="whitespace-nowrap">Message Push</span>
            </RouterLink>

          <RouterLink
            to="/alpha/mobile-bridge"
            active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
          >
            <Smartphone class="w-4 h-4" />
            <span class="whitespace-nowrap">Mobile Bridge</span>
          </RouterLink>

          <RouterLink
            to="/alpha/file-receive"
            active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
          >
            <FolderUp class="w-4 h-4" />
            <span class="whitespace-nowrap">File Receive</span>
          </RouterLink>
        </div>
      </div>

        <RouterLink
          to="/alpha/execution-topology"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Workflow class="w-4 h-4" />
          <span class="whitespace-nowrap">执行拓扑模板</span>
        </RouterLink>

        <RouterLink
          to="/alpha/actor-visual-tester"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Radio class="w-4 h-4" />
          <span class="whitespace-nowrap">Actor Visual Tester</span>
        </RouterLink>

        <RouterLink
          to="/alpha/requirement-replay"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="whitespace-nowrap">需求回放</span>
        </RouterLink>

        <RouterLink
          to="/alpha/image-caption"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Image class="w-4 h-4" />
          <span class="whitespace-nowrap">图生文</span>
        </RouterLink>

        <RouterLink
          to="/alpha/asr"
          active-class="bg-white shadow-sm ring-1 ring-zinc-200 text-zinc-900"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900"
        >
          <Mic class="w-4 h-4" />
          <span class="whitespace-nowrap">语音转写（ASR）</span>
        </RouterLink>
      </nav>

      <!-- Footer: Return to Guide -->
      <div class="p-3 border-t border-zinc-200">
        <RouterLink
          to="/guide"
          class="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 transition-all hover:bg-zinc-200/50 hover:text-zinc-900 border border-zinc-300"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="whitespace-nowrap">返回 Guide</span>
        </RouterLink>
      </div>
    </aside>
  </div>
</template>
