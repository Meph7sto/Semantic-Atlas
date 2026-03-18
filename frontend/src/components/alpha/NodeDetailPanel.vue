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
  Code2,
  Info
} from 'lucide-vue-next'

const props = defineProps({
  selectedNode: { type: Object, default: null },
  selectedEdge: { type: Object, default: null },
  toolResults: { type: Array, default: () => [] }
})

/* ─── collapse state ─── */
const expandedSections = ref({
  basic: true,
  output: true,
  inputSummary: false,
  toolCalls: false,
  rawJson: false
})

const toggleSection = (key) => {
  expandedSections.value[key] = !expandedSections.value[key]
}

/* ─── computed helpers ─── */
const config = computed(() => props.selectedNode?.config_json || {})

const basicInfo = computed(() => {
  const c = config.value
  return {
    nodeKey: props.selectedNode?.node_key || '-',
    nodeType: props.selectedNode?.node_type || '-',
    runStatus: c.run_status || '-',
    startedAt: formatTime(c.started_at),
    finishedAt: formatTime(c.finished_at),
    error: c.error || null
  }
})

const outputSummary = computed(() => config.value.output_summary ?? null)
const inputSummary = computed(() => config.value.input_summary ?? null)
const toolCallResults = computed(() => config.value.tool_call_results || [])

const hasToolCalls = computed(() => toolCallResults.value.length > 0)

/* ─── per-tool-call collapse ─── */
const expandedToolCalls = ref({})

const toggleToolCall = (index) => {
  expandedToolCalls.value = {
    ...expandedToolCalls.value,
    [index]: !expandedToolCalls.value[index]
  }
}

/* ─── status styling ─── */
const statusStyles = {
  pending: { bg: 'bg-stone-100', text: 'text-stone-600', border: 'border-stone-300', label: '等待中' },
  running: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-300', label: '运行中' },
  succeeded: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-300', label: '成功' },
  failed: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-300', label: '失败' }
}

const statusStyle = computed(() => {
  return statusStyles[basicInfo.value.runStatus] || statusStyles.pending
})

/* ─── formatters ─── */
const formatTime = (value) => {
  if (!value) return '-'
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

const formatJson = (value) => {
  if (value === null || value === undefined) return '暂无'
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
}

const formatSummaryText = (value) => {
  if (value === null || value === undefined) return '暂无'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
}

/* ─── tool-specific renderers ─── */
const isCheckConflict = (toolName) => toolName === 'check_conflict'
const isListRequirements = (toolName) => toolName === 'list_requirements'
const isGetRequirement = (toolName) => toolName === 'get_requirement'

const toolCallOneLiner = (entry) => {
  const name = entry.tool_name || '未知工具'
  const args = entry.request?.arguments
  if (isCheckConflict(name)) {
    const conflict = entry.result?.is_conflict
    return conflict ? `❌ 冲突` : `✅ 不冲突`
  }
  if (isListRequirements(name)) {
    const count = entry.result?.count ?? '?'
    const total = entry.result?.total ?? '?'
    return `📋 返回 ${count} 条 / 共 ${total} 条`
  }
  if (isGetRequirement(name)) {
    const title = entry.result?.title
    return title ? `📄 ${title}` : '📄 获取需求详情'
  }
  if (args) {
    const keys = Object.keys(args)
    if (keys.length <= 3) {
      return keys.map(k => `${k}=${JSON.stringify(args[k])}`).join(', ')
    }
    return `${keys.length} 个参数`
  }
  return '查看详情'
}

/* ─── external tool results (passed via prop) ─── */
const externalToolResults = computed(() => props.toolResults || [])
</script>

<template>
  <div class="space-y-4 text-sm text-stone-700">
    <!-- 未选中状态 -->
    <div v-if="!selectedNode && !selectedEdge" class="py-8 text-center text-stone-400">
      <Info class="mx-auto mb-2 h-8 w-8 opacity-40" />
      <p>点击执行图中的节点或边查看详情</p>
    </div>

    <!-- ===== 边详情 ===== -->
    <div v-else-if="selectedEdge" class="space-y-4">
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-stone-500">当前选中</p>
        <p class="mt-2 font-medium text-stone-900">{{ selectedEdge.label || '未命名边' }}</p>
      </div>
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-stone-500">边类型</p>
        <p class="mt-2">{{ selectedEdge.edge_type }}</p>
      </div>
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-stone-500">配置</p>
        <pre class="mt-2 overflow-x-auto bg-stone-900 p-4 text-xs leading-6 text-stone-100">{{ formatJson(selectedEdge.config_json) }}</pre>
      </div>
    </div>

    <!-- ===== 节点详情：分层折叠 ===== -->
    <template v-else-if="selectedNode">
      <div>
        <p class="text-xs uppercase tracking-[0.2em] text-stone-500">当前选中</p>
        <p class="mt-2 font-medium text-stone-900">{{ selectedNode.label || '未命名节点' }}</p>
      </div>

      <!-- 1. 基本信息 -->
      <div class="border border-stone-200 overflow-hidden">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-stone-50"
          @click="toggleSection('basic')"
        >
          <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-stone-600">
            <Info class="h-3.5 w-3.5" />
            基本信息
          </span>
          <component :is="expandedSections.basic ? ChevronDown : ChevronRight" class="h-4 w-4 text-stone-400" />
        </button>
        <div v-show="expandedSections.basic" class="border-t border-stone-100 px-4 py-3 space-y-2">
          <div class="grid grid-cols-2 gap-x-6 gap-y-2">
            <div>
              <span class="text-[11px] text-stone-400">Node Key</span>
              <p class="mt-0.5 text-xs font-mono text-stone-700 break-all">{{ basicInfo.nodeKey }}</p>
            </div>
            <div>
              <span class="text-[11px] text-stone-400">类型</span>
              <p class="mt-0.5 text-xs font-medium text-stone-700">{{ basicInfo.nodeType }}</p>
            </div>
            <div>
              <span class="text-[11px] text-stone-400">状态</span>
              <span
                class="mt-0.5 inline-flex items-center gap-1 border px-2 py-0.5 text-[11px] font-medium"
                :class="[statusStyle.bg, statusStyle.text, statusStyle.border]"
              >
                <CheckCircle2 v-if="basicInfo.runStatus === 'succeeded'" class="h-3 w-3" />
                <XCircle v-else-if="basicInfo.runStatus === 'failed'" class="h-3 w-3" />
                <Clock v-else class="h-3 w-3" />
                {{ statusStyle.label }}
              </span>
            </div>
            <div>
              <span class="text-[11px] text-stone-400">开始时间</span>
              <p class="mt-0.5 text-xs text-stone-700">{{ basicInfo.startedAt }}</p>
            </div>
            <div>
              <span class="text-[11px] text-stone-400">完成时间</span>
              <p class="mt-0.5 text-xs text-stone-700">{{ basicInfo.finishedAt }}</p>
            </div>
          </div>
          <div v-if="basicInfo.error" class="mt-2 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <AlertTriangle class="mr-1 inline h-3.5 w-3.5" />
            {{ basicInfo.error }}
          </div>
        </div>
      </div>

      <!-- 2. LLM 输出 -->
      <div class="border border-stone-200 overflow-hidden">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-stone-50"
          @click="toggleSection('output')"
        >
          <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-stone-600">
            <FileText class="h-3.5 w-3.5" />
            输出内容
          </span>
          <component :is="expandedSections.output ? ChevronDown : ChevronRight" class="h-4 w-4 text-stone-400" />
        </button>
        <div v-show="expandedSections.output" class="border-t border-stone-100 px-4 py-3">
          <div
            v-if="typeof outputSummary === 'string'"
            class="whitespace-pre-wrap text-sm leading-6 text-stone-800"
          >{{ outputSummary || '暂无输出' }}</div>
          <pre
            v-else
            class="overflow-x-auto text-xs leading-6 text-stone-700"
          >{{ formatSummaryText(outputSummary) }}</pre>
        </div>
      </div>

      <!-- 3. 输入摘要 -->
      <div class="border border-stone-200 overflow-hidden">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-stone-50"
          @click="toggleSection('inputSummary')"
        >
          <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-stone-600">
            <Info class="h-3.5 w-3.5" />
            输入摘要
          </span>
          <component :is="expandedSections.inputSummary ? ChevronDown : ChevronRight" class="h-4 w-4 text-stone-400" />
        </button>
        <div v-show="expandedSections.inputSummary" class="border-t border-stone-100 px-4 py-3">
          <div
            v-if="typeof inputSummary === 'string'"
            class="whitespace-pre-wrap text-sm leading-6 text-stone-800"
          >{{ inputSummary || '暂无' }}</div>
          <pre
            v-else
            class="overflow-x-auto text-xs leading-6 text-stone-700"
          >{{ formatSummaryText(inputSummary) }}</pre>
        </div>
      </div>

      <!-- 4. 工具调用 -->
      <div v-if="hasToolCalls" class="border border-stone-200 overflow-hidden">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-stone-50"
          @click="toggleSection('toolCalls')"
        >
          <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-stone-600">
            <Wrench class="h-3.5 w-3.5" />
            工具调用
            <span class="ml-1 inline-flex h-5 min-w-[20px] items-center justify-center bg-stone-200 px-1 text-[10px] font-bold text-stone-600">
              {{ toolCallResults.length }}
            </span>
          </span>
          <component :is="expandedSections.toolCalls ? ChevronDown : ChevronRight" class="h-4 w-4 text-stone-400" />
        </button>
        <div v-show="expandedSections.toolCalls" class="border-t border-stone-100 divide-y divide-stone-100">
          <div
            v-for="(entry, idx) in toolCallResults"
            :key="idx"
            class="px-4 py-2"
          >
            <!-- check_conflict 语义卡片 -->
            <div v-if="isCheckConflict(entry.tool_name)" class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-stone-500 uppercase tracking-[0.15em]">check_conflict</span>
                <span class="text-[11px] text-stone-400">{{ formatTime(entry.recorded_at) }}</span>
              </div>
              <div
                class="flex items-center gap-3 border px-4 py-3"
                :class="entry.result?.is_conflict
                  ? 'border-red-200 bg-red-50'
                  : 'border-emerald-200 bg-emerald-50'"
              >
                <XCircle v-if="entry.result?.is_conflict" class="h-6 w-6 shrink-0 text-red-500" />
                <CheckCircle2 v-else class="h-6 w-6 shrink-0 text-emerald-500" />
                <div>
                  <p class="text-sm font-semibold" :class="entry.result?.is_conflict ? 'text-red-800' : 'text-emerald-800'">
                    {{ entry.result?.is_conflict ? '存在冲突' : '不冲突' }}
                  </p>
                  <p v-if="entry.result?.raw_response" class="mt-1 text-xs text-stone-600">
                    {{ entry.result.raw_response }}
                  </p>
                </div>
              </div>
              <button
                class="text-[11px] text-stone-400 hover:text-stone-600 transition"
                @click="toggleToolCall(idx)"
              >
                {{ expandedToolCalls[idx] ? '隐藏详情' : '查看请求参数' }}
              </button>
              <pre v-show="expandedToolCalls[idx]" class="overflow-x-auto bg-stone-900 p-3 text-xs leading-5 text-stone-100">{{ formatJson(entry.request) }}</pre>
            </div>

            <!-- list_requirements 语义卡片 -->
            <div v-else-if="isListRequirements(entry.tool_name)" class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-stone-500 uppercase tracking-[0.15em]">list_requirements</span>
                <span class="text-[11px] text-stone-400">{{ formatTime(entry.recorded_at) }}</span>
              </div>
              <div class="border border-stone-200 bg-stone-50 overflow-hidden">
                <div class="flex items-center justify-between bg-stone-100 px-3 py-2">
                  <span class="text-xs text-stone-600">
                    返回 <strong>{{ entry.result?.count ?? 0 }}</strong> 条
                    <span v-if="entry.result?.total"> / 共 {{ entry.result.total }} 条</span>
                  </span>
                  <span v-if="entry.result?.has_more" class="text-[10px] text-amber-600 font-medium">还有更多</span>
                </div>
                <div v-if="entry.result?.items?.length" class="divide-y divide-stone-100">
                  <div
                    v-for="(req, rIdx) in entry.result.items"
                    :key="rIdx"
                    class="flex items-start gap-2 px-3 py-2"
                  >
                    <span class="shrink-0 mt-0.5 inline-flex h-4 min-w-[16px] items-center justify-center bg-stone-200 text-[9px] font-bold text-stone-500">
                      {{ rIdx + (entry.result?.start_index || 1) }}
                    </span>
                    <div class="min-w-0 flex-1">
                      <p class="text-xs font-medium text-stone-800 leading-5 line-clamp-2">{{ req.title }}</p>
                      <p class="text-[10px] text-stone-400 mt-0.5">{{ req.status || '未知状态' }}</p>
                    </div>
                  </div>
                </div>
              </div>
              <button
                class="text-[11px] text-stone-400 hover:text-stone-600 transition"
                @click="toggleToolCall(idx)"
              >
                {{ expandedToolCalls[idx] ? '隐藏原始数据' : '查看原始数据' }}
              </button>
              <pre v-show="expandedToolCalls[idx]" class="overflow-x-auto bg-stone-900 p-3 text-xs leading-5 text-stone-100">{{ formatJson(entry) }}</pre>
            </div>

            <!-- 通用工具 -->
            <div v-else class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-xs font-semibold text-stone-500 uppercase tracking-[0.15em]">{{ entry.tool_name || '未知工具' }}</span>
                <span class="text-[11px] text-stone-400">{{ formatTime(entry.recorded_at) }}</span>
              </div>
              <button
                class="flex w-full items-center gap-2 border border-stone-200 bg-stone-50 px-3 py-2 text-left text-xs text-stone-600 transition hover:bg-stone-100"
                @click="toggleToolCall(idx)"
              >
                <component :is="expandedToolCalls[idx] ? ChevronDown : ChevronRight" class="h-3.5 w-3.5 shrink-0 text-stone-400" />
                <span class="truncate">{{ toolCallOneLiner(entry) }}</span>
              </button>
              <pre v-show="expandedToolCalls[idx]" class="overflow-x-auto bg-stone-900 p-3 text-xs leading-5 text-stone-100">{{ formatJson(entry) }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- 5. 原始 JSON -->
      <div class="border border-stone-200 overflow-hidden">
        <button
          class="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-stone-50"
          @click="toggleSection('rawJson')"
        >
          <span class="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.15em] text-stone-600">
            <Code2 class="h-3.5 w-3.5" />
            原始 JSON
          </span>
          <component :is="expandedSections.rawJson ? ChevronDown : ChevronRight" class="h-4 w-4 text-stone-400" />
        </button>
        <div v-show="expandedSections.rawJson" class="border-t border-stone-100">
          <pre class="overflow-x-auto bg-stone-900 p-4 text-xs leading-6 text-stone-100 max-h-[400px] overflow-y-auto">{{ formatJson(selectedNode.config_json) }}</pre>
        </div>
      </div>
    </template>

    <!-- ===== 外部工具结果列表 (从 prop 传入) ===== -->
    <div v-if="externalToolResults.length > 0" class="space-y-3 border-t border-stone-200 pt-4 mt-4">
      <p class="text-xs font-semibold uppercase tracking-[0.15em] text-stone-500">全部工具调用结果</p>
      <div
        v-for="(entry, idx) in externalToolResults"
        :key="'ext-' + idx"
        class="border border-stone-200 overflow-hidden"
      >
        <!-- check_conflict -->
        <div v-if="isCheckConflict(entry.tool_name)" class="px-4 py-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-stone-500 uppercase tracking-[0.15em]">check_conflict</span>
            <span class="text-[11px] text-stone-400">{{ entry.nodeKey || '' }}</span>
          </div>
          <div
            class="flex items-center gap-3 border px-4 py-3"
            :class="entry.result?.is_conflict
              ? 'border-red-200 bg-red-50'
              : 'border-emerald-200 bg-emerald-50'"
          >
            <XCircle v-if="entry.result?.is_conflict" class="h-6 w-6 shrink-0 text-red-500" />
            <CheckCircle2 v-else class="h-6 w-6 shrink-0 text-emerald-500" />
            <div>
              <p class="text-sm font-semibold" :class="entry.result?.is_conflict ? 'text-red-800' : 'text-emerald-800'">
                {{ entry.result?.is_conflict ? '存在冲突' : '不冲突' }}
              </p>
              <p v-if="entry.result?.raw_response" class="mt-1 text-xs text-stone-600">{{ entry.result.raw_response }}</p>
            </div>
          </div>
        </div>

        <!-- list_requirements -->
        <div v-else-if="isListRequirements(entry.tool_name)" class="px-4 py-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold text-stone-500 uppercase tracking-[0.15em]">list_requirements</span>
            <span class="text-[11px] text-stone-400">{{ entry.nodeKey || '' }}</span>
          </div>
          <div class="border border-stone-200 bg-stone-50 overflow-hidden">
            <div class="flex items-center justify-between bg-stone-100 px-3 py-2">
              <span class="text-xs text-stone-600">
                返回 <strong>{{ entry.result?.count ?? 0 }}</strong> 条
                <span v-if="entry.result?.total"> / 共 {{ entry.result.total }} 条</span>
              </span>
            </div>
            <div v-if="entry.result?.items?.length" class="divide-y divide-stone-100 max-h-[200px] overflow-y-auto">
              <div
                v-for="(req, rIdx) in entry.result.items"
                :key="rIdx"
                class="flex items-start gap-2 px-3 py-2"
              >
                <span class="shrink-0 mt-0.5 inline-flex h-4 min-w-[16px] items-center justify-center bg-stone-200 text-[9px] font-bold text-stone-500">
                  {{ rIdx + (entry.result?.start_index || 1) }}
                </span>
                <p class="text-xs font-medium text-stone-800 leading-5 line-clamp-2 min-w-0 flex-1">{{ req.title }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 通用 -->
        <div v-else class="px-4 py-3">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">{{ entry.tool_name }}</span>
            <span class="text-[11px] text-stone-400">{{ entry.nodeKey || '' }}</span>
          </div>
          <pre class="mt-2 overflow-x-auto text-xs leading-6 text-stone-700">{{ formatJson(entry.result) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
