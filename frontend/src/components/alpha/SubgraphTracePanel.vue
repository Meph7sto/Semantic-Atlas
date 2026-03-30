<script setup>
import { computed, ref } from 'vue'
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Wrench,
  FileText,
  ArrowRight,
  Layers,
  RefreshCw
} from 'lucide-vue-next'

const props = defineProps({
  containers: { type: Array, default: () => [] },
  subgraphs: { type: Array, default: () => [] },
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] }
})

/* ─── expand / collapse per subgraph ─── */
const expandedSubgraphs = ref({})

const toggleSubgraph = (subgraphId) => {
  expandedSubgraphs.value = {
    ...expandedSubgraphs.value,
    [subgraphId]: !expandedSubgraphs.value[subgraphId]
  }
}

const isExpanded = (subgraphId) => expandedSubgraphs.value[subgraphId] === true

/* ─── expand / collapse per tool call inside a subgraph ─── */
const expandedToolCalls = ref({})

const toggleToolCall = (toolKey) => {
  expandedToolCalls.value = {
    ...expandedToolCalls.value,
    [toolKey]: !expandedToolCalls.value[toolKey]
  }
}

/* ─── status styling ─── */
const statusConfig = {
  pending: { bg: 'bg-stone-100', text: 'text-stone-600', border: 'border-stone-300', label: '等待中', icon: Clock },
  running: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-300', label: '运行中', icon: RefreshCw, pulse: true },
  completed: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-300', label: '已完成', icon: CheckCircle2 },
  failed: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-300', label: '失败', icon: XCircle }
}

const getStatusConfig = (status) => statusConfig[status] || statusConfig.pending

/* ─── subgraph accent bar color ─── */
const subgraphAccentColors = {
  pending: 'border-l-stone-400',
  running: 'border-l-blue-500',
  completed: 'border-l-emerald-500',
  failed: 'border-l-red-500'
}

const getAccentColor = (status) => subgraphAccentColors[status] || subgraphAccentColors.pending

/* ─── group subgraphs by container ─── */
const sortByOrder = (items) => {
  return [...items].sort((a, b) => {
    const orderDiff = Number(a?.order_index || 0) - Number(b?.order_index || 0)
    if (orderDiff !== 0) return orderDiff
    return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
  })
}

const containerMap = computed(() => {
  const map = {}
  props.containers.forEach((container) => {
    map[container.container_id] = container
  })
  return map
})

const nodesBySubgraph = computed(() => {
  const map = {}
  props.nodes.forEach((node) => {
    const subgraphId = node.subgraph_id
    if (!subgraphId) return
    if (!map[subgraphId]) {
      map[subgraphId] = []
    }
    map[subgraphId].push(node)
  })
  return map
})

const groupedByContainer = computed(() => {
  const groups = []
  const sorted = sortByOrder(props.containers)

  sorted.forEach((container) => {
    const containerSubgraphs = sortByOrder(
      props.subgraphs.filter((sg) => sg.container_id === container.container_id)
    )
    if (containerSubgraphs.length === 0) return

    groups.push({
      container,
      subgraphs: containerSubgraphs
    })
  })

  /* unassigned subgraphs (no container_id) */
  const unassigned = sortByOrder(
    props.subgraphs.filter((sg) => !sg.container_id || !containerMap.value[sg.container_id])
  )
  if (unassigned.length > 0) {
    groups.push({
      container: { container_id: '__unassigned__', label: '未分配容器', role_type: 'unassigned' },
      subgraphs: unassigned
    })
  }

  return groups
})

/* ─── cross-container invoke edges ─── */
const crossContainerEdges = computed(() => {
  const nodeMap = {}
  props.nodes.forEach((node) => {
    nodeMap[node.node_id] = node
  })

  return props.edges
    .filter((edge) => {
      if (edge.edge_type !== 'call' && edge.edge_type !== 'return') return false
      const source = nodeMap[edge.source_node_id]
      const target = nodeMap[edge.target_node_id]
      if (!source || !target) return false
      return source.container_id !== target.container_id
    })
    .map((edge) => {
      const source = nodeMap[edge.source_node_id]
      const target = nodeMap[edge.target_node_id]
      return {
        edgeId: edge.edge_id,
        edgeType: edge.edge_type,
        label: edge.label || edge.edge_type,
        sourceContainer: containerMap.value[source.container_id]?.label || source.container_id || '?',
        targetContainer: containerMap.value[target.container_id]?.label || target.container_id || '?'
      }
    })
})

/* ─── extract tool call results from nodes in a subgraph ─── */
const getSubgraphToolCalls = (subgraphId) => {
  const nodes = nodesBySubgraph.value[subgraphId] || []
  return nodes.flatMap((node) => {
    const results = node.config_json?.tool_call_results || []
    return results.map((entry) => ({
      nodeKey: node.node_key,
      ...entry
    }))
  })
}

/* ─── extract scratchpad entries from subgraph nodes ─── */
const getSubgraphScratchpad = (subgraphId) => {
  const nodes = nodesBySubgraph.value[subgraphId] || []
  return nodes.flatMap((node) => {
    return node.config_json?.scratchpad_entries || []
  })
}

/* ─── container role colors ─── */
const containerRoleColors = {
  human: 'border-teal-400 bg-teal-50/60',
  agent: 'border-blue-400 bg-blue-50/60',
  system: 'border-violet-400 bg-violet-50/60',
  unassigned: 'border-stone-300 bg-stone-50/60'
}

const getContainerStyle = (roleType) => containerRoleColors[roleType] || containerRoleColors.agent

/* ─── formatters ─── */
const formatJson = (value) => {
  if (value === null || value === undefined) return '暂无'
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
}

const formatTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const toolOneLiner = (entry) => {
  const name = entry.tool_name || '未知工具'
  if (name === 'check_conflict') {
    return entry.result?.is_conflict ? '❌ 冲突' : '✅ 不冲突'
  }
  if (name === 'list_requirements') {
    return `📋 返回 ${entry.result?.count ?? '?'} 条`
  }
  const args = entry.request?.arguments
  if (args) {
    const keys = Object.keys(args)
    if (keys.length <= 3) {
      return keys.map((k) => `${k}=${JSON.stringify(args[k])}`).join(', ')
    }
    return `${keys.length} 个参数`
  }
  return '查看详情'
}
</script>

<template>
  <div class="space-y-5 text-sm text-stone-700">
    <!-- empty state -->
    <div
      v-if="subgraphs.length === 0"
      class="py-10 text-center text-stone-400"
    >
      <Layers class="mx-auto mb-3 h-10 w-10 opacity-30" />
      <p class="text-sm">暂无 Subgraph 数据</p>
      <p class="mt-1 text-xs text-stone-400">使用「执行图模式」运行后，将在此展示 subgraph 分组轨迹</p>
    </div>

    <!-- grouped containers -->
    <div
      v-for="group in groupedByContainer"
      :key="group.container.container_id"
      class="border-l-4 rounded-r overflow-hidden"
      :class="getContainerStyle(group.container.role_type)"
    >
      <!-- container header -->
      <div class="px-4 py-3 border-b border-stone-200/60">
        <div class="flex items-center justify-between">
          <h3 class="text-xs font-bold uppercase tracking-[0.15em] text-stone-600">
            {{ group.container.label || group.container.container_key || '容器' }}
          </h3>
          <span class="text-[10px] text-stone-400">
            {{ group.subgraphs.length }} subgraph{{ group.subgraphs.length !== 1 ? 's' : '' }}
          </span>
        </div>
      </div>

      <!-- subgraph cards -->
      <div class="divide-y divide-stone-200/50">
        <div
          v-for="subgraph in group.subgraphs"
          :key="subgraph.subgraph_id"
          class="bg-white/80"
        >
          <!-- subgraph header row -->
          <button
            class="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-stone-50/80"
            @click="toggleSubgraph(subgraph.subgraph_id)"
          >
            <component
              :is="isExpanded(subgraph.subgraph_id) ? ChevronDown : ChevronRight"
              class="h-4 w-4 shrink-0 text-stone-400"
            />

            <!-- accent bar + label -->
            <div
              class="flex-1 flex items-center gap-2 border-l-[3px] pl-2"
              :class="getAccentColor(subgraph.status)"
            >
              <span class="text-xs font-semibold text-stone-800 truncate">
                {{ subgraph.label || subgraph.subgraph_key || 'Subgraph' }}
              </span>
            </div>

            <!-- status badge -->
            <span
              class="inline-flex shrink-0 items-center gap-1 border px-2 py-0.5 text-[10px] font-medium"
              :class="[
                getStatusConfig(subgraph.status).bg,
                getStatusConfig(subgraph.status).text,
                getStatusConfig(subgraph.status).border
              ]"
            >
              <component
                :is="getStatusConfig(subgraph.status).icon"
                class="h-3 w-3"
                :class="getStatusConfig(subgraph.status).pulse ? 'animate-spin' : ''"
              />
              {{ getStatusConfig(subgraph.status).label }}
            </span>
          </button>

          <!-- subgraph expanded content -->
          <div v-show="isExpanded(subgraph.subgraph_id)" class="border-t border-stone-100 px-4 py-3 space-y-3">

            <!-- task_description -->
            <div v-if="subgraph.task_description" class="rounded border border-stone-200 bg-stone-50 px-3 py-2">
              <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-stone-400 mb-1">
                <FileText class="inline h-3 w-3 mr-0.5" />
                Task Prompt
              </p>
              <p class="whitespace-pre-wrap text-xs leading-5 text-stone-700">{{ subgraph.task_description }}</p>
            </div>

            <!-- scratchpad entries -->
            <div v-if="getSubgraphScratchpad(subgraph.subgraph_id).length > 0">
              <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-stone-400 mb-1.5">
                Scratchpad
              </p>
              <div class="space-y-1">
                <div
                  v-for="(entry, idx) in getSubgraphScratchpad(subgraph.subgraph_id)"
                  :key="idx"
                  class="flex gap-2 text-[11px] leading-4"
                >
                  <span class="shrink-0 inline-flex h-4 items-center bg-stone-200 px-1.5 text-[9px] font-bold text-stone-500">
                    {{ entry.type || 'note' }}
                  </span>
                  <span class="text-stone-600 break-all">{{ entry.content || formatJson(entry) }}</span>
                </div>
              </div>
            </div>

            <!-- tool calls -->
            <div v-if="getSubgraphToolCalls(subgraph.subgraph_id).length > 0">
              <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-stone-400 mb-1.5">
                <Wrench class="inline h-3 w-3 mr-0.5" />
                工具调用
                <span class="ml-1 inline-flex h-4 min-w-[16px] items-center justify-center bg-stone-200 px-1 text-[9px] font-bold text-stone-500">
                  {{ getSubgraphToolCalls(subgraph.subgraph_id).length }}
                </span>
              </p>
              <div class="divide-y divide-stone-100 border border-stone-200 rounded overflow-hidden">
                <div
                  v-for="(entry, idx) in getSubgraphToolCalls(subgraph.subgraph_id)"
                  :key="idx"
                  class="px-3 py-2"
                >
                  <button
                    class="flex w-full items-center gap-2 text-left text-xs text-stone-600 transition hover:text-stone-900"
                    @click="toggleToolCall(`${subgraph.subgraph_id}-${idx}`)"
                  >
                    <component
                      :is="expandedToolCalls[`${subgraph.subgraph_id}-${idx}`] ? ChevronDown : ChevronRight"
                      class="h-3.5 w-3.5 shrink-0 text-stone-400"
                    />
                    <span class="font-semibold text-stone-500 uppercase text-[10px] tracking-wider">{{ entry.tool_name || '?' }}</span>
                    <span class="flex-1 truncate text-[11px] text-stone-500">{{ toolOneLiner(entry) }}</span>
                    <span v-if="entry.recorded_at" class="shrink-0 text-[10px] text-stone-400">{{ formatTime(entry.recorded_at) }}</span>
                  </button>
                  <pre
                    v-show="expandedToolCalls[`${subgraph.subgraph_id}-${idx}`]"
                    class="mt-2 overflow-x-auto bg-stone-900 p-3 text-xs leading-5 text-stone-100 rounded max-h-[300px] overflow-y-auto"
                  >{{ formatJson(entry) }}</pre>
                </div>
              </div>
            </div>

            <!-- no content fallback -->
            <div
              v-if="!subgraph.task_description && getSubgraphScratchpad(subgraph.subgraph_id).length === 0 && getSubgraphToolCalls(subgraph.subgraph_id).length === 0"
              class="text-xs text-stone-400 italic"
            >
              暂无详细内容
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- cross-container invoke links -->
    <div v-if="crossContainerEdges.length > 0" class="space-y-2">
      <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-stone-400">
        跨容器调用
      </p>
      <div
        v-for="edge in crossContainerEdges"
        :key="edge.edgeId"
        class="flex items-center gap-2 border border-amber-200 bg-amber-50/60 px-3 py-2 rounded text-xs text-amber-800"
      >
        <span class="font-medium">{{ edge.sourceContainer }}</span>
        <ArrowRight class="h-3.5 w-3.5 text-amber-500" />
        <span class="font-medium">{{ edge.targetContainer }}</span>
        <span class="ml-auto text-[10px] uppercase tracking-wider text-amber-600 font-semibold">{{ edge.edgeType }}</span>
      </div>
    </div>
  </div>
</template>
