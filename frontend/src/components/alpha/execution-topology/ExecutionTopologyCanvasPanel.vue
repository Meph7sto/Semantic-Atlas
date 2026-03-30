<script setup>
import { AlertTriangle, CheckCircle2, Eye, RefreshCw } from 'lucide-vue-next'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'

defineProps({
  selectedGraphId: {
    type: String,
    required: true
  },
  currentGraph: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    required: true
  },
  graphHints: {
    type: Array,
    required: true
  },
  validationSummary: {
    type: Object,
    default: null
  },
  graphDetail: {
    type: Object,
    required: true
  },
  selectedCanvasId: {
    type: String,
    default: null
  },
  selectedContainerId: {
    type: String,
    default: null
  },
  structureLoading: {
    type: Boolean,
    required: true
  },
  validationLoading: {
    type: Boolean,
    required: true
  }
})

const emit = defineEmits([
  'select-graph-object',
  'validate-topology',
  'view-structure',
  'refresh',
  'select-object',
  'layout-change'
])

const emitObjectSelection = (type, id) => {
  emit('select-object', { type, id })
}
</script>

<template>
  <div class="flex-1 flex flex-col bg-zinc-200 overflow-hidden">
    <div class="px-4 py-3 bg-white border-b border-zinc-200 flex items-center justify-between">
      <div class="flex items-center gap-2 min-w-0">
        <span v-if="currentGraph" class="text-sm font-medium text-zinc-900 truncate">{{ currentGraph.name }}</span>
        <span v-if="currentGraph" class="text-xs text-zinc-500">({{ currentGraph.status }})</span>
      </div>
      <div class="flex gap-1">
        <button
          v-if="selectedGraphId"
          class="px-3 py-1.5 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded transition-colors"
          @click="emit('select-graph-object')"
        >
          图属性
        </button>
        <button
          v-if="selectedGraphId"
          :disabled="validationLoading"
          class="px-3 py-1.5 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          @click="emit('validate-topology')"
        >
          {{ validationLoading ? '校验中...' : '校验拓扑' }}
        </button>
        <button
          v-if="selectedGraphId"
          :disabled="structureLoading"
          class="p-1.5 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          title="查看结构"
          @click="emit('view-structure')"
        >
          <Eye v-if="!structureLoading" class="w-4 h-4" />
          <div v-else class="w-4 h-4 animate-spin border-2 border-zinc-300 border-t-blue-600 rounded-full"></div>
        </button>
        <button
          v-if="selectedGraphId"
          class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded transition-colors"
          title="刷新"
          @click="emit('refresh')"
        >
          <RefreshCw :class="{ 'animate-spin': loading }" class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div v-if="selectedGraphId && graphHints.length" class="border-b border-amber-200 bg-amber-50 px-4 py-2 space-y-1">
      <div v-for="hint in graphHints" :key="hint" class="flex items-start gap-2 text-xs text-amber-700">
        <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" />
        <span>{{ hint }}</span>
      </div>
    </div>

    <div v-if="selectedGraphId && validationSummary" class="border-b border-zinc-200 bg-white px-4 py-2">
      <div class="flex items-center gap-3 text-xs">
        <span
          class="inline-flex items-center gap-1 rounded-full px-2 py-1"
          :class="validationSummary.isValid ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'"
        >
          <CheckCircle2 v-if="validationSummary.isValid" class="w-3.5 h-3.5" />
          <AlertTriangle v-else class="w-3.5 h-3.5" />
          {{ validationSummary.isValid ? '校验通过' : '校验未通过' }}
        </span>
        <span class="text-zinc-500">错误 {{ validationSummary.errorCount }} 条</span>
        <span class="text-zinc-500">警告 {{ validationSummary.warningCount }} 条</span>
      </div>
    </div>

    <div class="flex-1 p-4 overflow-auto">
      <ExecutionGraphCanvas
        v-if="selectedGraphId"
        :containers="graphDetail.containers"
        :nodes="graphDetail.nodes"
        :edges="graphDetail.edges"
        :layout="graphDetail.graph?.layout_json || {}"
        :selected-id="selectedCanvasId"
        :selected-container-id="selectedContainerId"
        @select-node="emitObjectSelection('node', $event)"
        @select-edge="emitObjectSelection('edge', $event)"
        @select-container="emitObjectSelection('container', $event)"
        @layout-change="emit('layout-change', $event)"
      />
      <div v-else class="flex items-center justify-center h-full text-zinc-400">
        <div class="text-center">
          <svg class="w-16 h-16 mx-auto mb-3 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 003 21h15a2.25 2.25 0 002.25-2.25V11.25" />
          </svg>
          <p class="text-sm">请选择一个图开始编辑</p>
          <p class="text-xs mt-1">从左侧列表选择或创建新图</p>
        </div>
      </div>
    </div>
  </div>
</template>
