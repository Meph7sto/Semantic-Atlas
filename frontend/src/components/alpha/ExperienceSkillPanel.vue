<script setup>
import { computed } from 'vue'
import {
  CheckCircle2,
  Clock,
  Info,
  Layers,
  Sparkles,
  Workflow,
  XCircle
} from 'lucide-vue-next'

const props = defineProps({
  graph: {
    type: Object,
    default: null
  }
})

const normalizeStringArray = (value) => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean)
}

const normalizeGraphStatus = (value) => {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return 'idle'
  return normalized
}

const snapshot = computed(() => {
  const graph = props.graph || null
  const meta = graph?.meta_json && typeof graph.meta_json === 'object'
    ? graph.meta_json
    : {}

  const skillIds = normalizeStringArray(meta.injected_skill_ids)
  const primarySkillId = String(meta.injected_skill_id || skillIds[0] || '').trim()
  const sharedSkillIds = normalizeStringArray(meta.injected_shared_skill_ids)
  const targetId = String(meta.injected_skill_target_id || '').trim()
  const currentNodeKey = String(meta.current_node_key || '').trim()
  const selectedContainerKeys = normalizeStringArray(meta.selected_container_keys)
  const dispatchedAgents = normalizeStringArray(meta.dispatched_agents)

  const rawRelevance = Number(meta.injected_skill_relevance)
  const relevance = Number.isFinite(rawRelevance)
    ? Math.max(0, Math.min(1, rawRelevance))
    : null

  const hasInjectedSkill = Boolean(primarySkillId || skillIds.length || sharedSkillIds.length)
  const graphStatus = normalizeGraphStatus(graph?.status)

  const displayMeta = {
    injected_skill_id: primarySkillId || null,
    injected_skill_ids: skillIds,
    injected_skill_target_id: targetId || null,
    injected_shared_skill_ids: sharedSkillIds,
    injected_skill_relevance: relevance,
    current_node_key: currentNodeKey || null,
    selected_container_keys: selectedContainerKeys,
    dispatched_agents: dispatchedAgents
  }

  return {
    hasGraph: Boolean(graph?.graph_id),
    graphId: String(graph?.graph_id || '').trim(),
    graphStatus,
    hasInjectedSkill,
    primarySkillId,
    skillIds,
    targetId,
    sharedSkillIds,
    relevance,
    currentNodeKey,
    selectedContainerKeys,
    dispatchedAgents,
    displayMeta
  }
})

const graphStatusLabel = computed(() => {
  switch (snapshot.value.graphStatus) {
    case 'running':
      return '运行中'
    case 'succeeded':
      return '已完成'
    case 'failed':
      return '失败'
    case 'suspended':
      return '已挂起'
    case 'draft':
      return '草稿'
    default:
      return '未开始'
  }
})

const graphStatusTone = computed(() => {
  switch (snapshot.value.graphStatus) {
    case 'running':
      return 'border-blue-200 bg-blue-50 text-blue-700'
    case 'succeeded':
      return 'border-emerald-200 bg-emerald-50 text-emerald-700'
    case 'failed':
      return 'border-red-200 bg-red-50 text-red-700'
    case 'suspended':
      return 'border-amber-200 bg-amber-50 text-amber-700'
    default:
      return 'border-stone-200 bg-stone-100 text-stone-600'
  }
})

const injectionTone = computed(() => {
  if (snapshot.value.hasInjectedSkill) {
    return {
      chip: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      panel: 'border-emerald-200 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.14),_transparent_52%),linear-gradient(135deg,#f8fffc_0%,#ffffff_62%,#effaf4_100%)]',
      title: '已注入经验技能',
      subtitle: '当前 active graph 已命中可复用经验，后续节点会带着技能上下文继续执行。'
    }
  }

  return {
    chip: 'border-stone-200 bg-stone-100 text-stone-600',
    panel: 'border-stone-200 bg-[radial-gradient(circle_at_top_left,_rgba(120,113,108,0.08),_transparent_48%),linear-gradient(135deg,#fafaf9_0%,#ffffff_58%,#f5f5f4_100%)]',
    title: '当前未命中技能',
    subtitle: '这轮执行暂未注入经验技能，系统仍按默认 prompt 与运行时上下文继续处理。'
  }
})

const relevancePercent = computed(() => {
  if (snapshot.value.relevance == null) return null
  return Math.round(snapshot.value.relevance * 100)
})

const relevanceBarStyle = computed(() => {
  const percent = relevancePercent.value
  if (percent == null) {
    return { width: '12%' }
  }
  return { width: `${Math.max(12, Math.min(100, percent))}%` }
})

const formatJson = (value) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch (_err) {
    return String(value)
  }
}
</script>

<template>
  <div class="overflow-hidden border border-stone-200 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
    <div class="border-b border-stone-200 px-5 py-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="flex items-center gap-2 text-lg font-semibold text-stone-900">
            <Sparkles class="h-5 w-5 text-amber-600" />
            经验技能命中
          </h2>
          <p class="mt-1 text-xs text-stone-500">
            从当前 active graph 的 <span class="font-mono text-stone-700">meta_json</span> 读取技能注入状态。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <span
            class="inline-flex items-center gap-1 border px-2.5 py-1 text-[11px] font-medium"
            :class="injectionTone.chip"
          >
            <CheckCircle2 v-if="snapshot.hasInjectedSkill" class="h-3.5 w-3.5" />
            <XCircle v-else class="h-3.5 w-3.5" />
            {{ snapshot.hasInjectedSkill ? 'Skill Hit' : 'No Hit' }}
          </span>
          <span
            class="inline-flex items-center gap-1 border px-2.5 py-1 text-[11px] font-medium"
            :class="graphStatusTone"
          >
            <Clock class="h-3.5 w-3.5" :class="snapshot.graphStatus === 'running' ? 'animate-spin' : ''" />
            {{ graphStatusLabel }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="!snapshot.hasGraph" class="px-5 py-10 text-center text-sm text-stone-400">
      <Workflow class="mx-auto mb-3 h-10 w-10 opacity-30" />
      当前还没有 active graph，等会话总控开始执行后，这里会出现技能命中状态。
    </div>

    <div v-else class="px-5 py-5">
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.18fr)_minmax(0,1fr)]">
        <section
          class="relative overflow-hidden border p-5"
          :class="injectionTone.panel"
        >
          <div class="absolute right-0 top-0 h-24 w-24 bg-[radial-gradient(circle,_rgba(245,158,11,0.18),_transparent_68%)]" />
          <div class="relative">
            <p class="text-[11px] font-semibold uppercase tracking-[0.24em] text-stone-500">Injection State</p>
            <h3 class="mt-3 text-2xl font-semibold tracking-tight text-stone-900">
              {{ injectionTone.title }}
            </h3>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-stone-600">
              {{ injectionTone.subtitle }}
            </p>

            <div class="mt-5 flex flex-wrap gap-2">
              <span class="inline-flex items-center gap-1 border border-stone-200 bg-white/80 px-2.5 py-1 text-[11px] text-stone-600">
                <Info class="h-3.5 w-3.5 text-stone-400" />
                Active Graph: <span class="font-mono text-stone-800">{{ snapshot.graphId }}</span>
              </span>
              <span
                v-if="snapshot.currentNodeKey"
                class="inline-flex items-center gap-1 border border-stone-200 bg-white/80 px-2.5 py-1 text-[11px] text-stone-600"
              >
                <Workflow class="h-3.5 w-3.5 text-stone-400" />
                Current Node: <span class="font-mono text-stone-800">{{ snapshot.currentNodeKey }}</span>
              </span>
            </div>

            <div class="mt-5 grid gap-3 md:grid-cols-2">
              <div class="border border-stone-200 bg-white/75 px-4 py-3">
                <div class="text-[11px] uppercase tracking-[0.18em] text-stone-400">主 Skill</div>
                <div class="mt-2 break-all font-mono text-xs leading-5 text-stone-800">
                  {{ snapshot.primarySkillId || '未命中' }}
                </div>
                <div v-if="snapshot.skillIds.length > 1" class="mt-2 text-[11px] text-stone-500">
                  共 {{ snapshot.skillIds.length }} 个 target-specific skill 被记录
                </div>
              </div>

              <div class="border border-stone-200 bg-white/75 px-4 py-3">
                <div class="text-[11px] uppercase tracking-[0.18em] text-stone-400">Target</div>
                <div class="mt-2 break-all font-mono text-xs leading-5 text-stone-800">
                  {{ snapshot.targetId || '未记录' }}
                </div>
                <div class="mt-2 text-[11px] text-stone-500">
                  当前显示的是这次注入对应的 experience target
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
          <div class="border border-stone-200 bg-[linear-gradient(180deg,#fffdf8_0%,#ffffff_100%)] p-4">
            <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
              <Layers class="h-3.5 w-3.5 text-amber-600" />
              Shared Patterns
            </div>
            <div class="mt-3 flex min-h-[64px] flex-wrap gap-2">
              <template v-if="snapshot.sharedSkillIds.length">
                <span
                  v-for="skillId in snapshot.sharedSkillIds"
                  :key="skillId"
                  class="inline-flex items-center border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-mono text-amber-700"
                >
                  {{ skillId }}
                </span>
              </template>
              <p v-else class="text-sm leading-6 text-stone-500">
                当前没有命中共享模式，说明这轮主要依赖 target-specific skill 或默认上下文。
              </p>
            </div>
          </div>

          <div class="border border-stone-200 bg-[linear-gradient(180deg,#f8fafc_0%,#ffffff_100%)] p-4">
            <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
              <Sparkles class="h-3.5 w-3.5 text-blue-600" />
              Relevance
            </div>
            <div class="mt-3 flex items-end justify-between gap-3">
              <div>
                <div class="text-3xl font-semibold tracking-tight text-stone-900">
                  {{ relevancePercent != null ? `${relevancePercent}%` : 'N/A' }}
                </div>
                <div class="mt-1 text-xs text-stone-500">
                  {{ relevancePercent != null ? '注入相关度得分' : '当前没有 relevance 分数' }}
                </div>
              </div>
              <div class="text-right text-[11px] text-stone-500">
                <div>Skill IDs: {{ snapshot.skillIds.length }}</div>
                <div>Shared: {{ snapshot.sharedSkillIds.length }}</div>
              </div>
            </div>
            <div class="mt-4 h-2 overflow-hidden rounded-full bg-stone-200">
              <div
                class="h-full bg-[linear-gradient(90deg,#0f766e_0%,#0891b2_42%,#f59e0b_100%)] transition-all duration-300"
                :style="relevanceBarStyle"
              />
            </div>
          </div>

          <div class="border border-stone-200 bg-[linear-gradient(180deg,#fbfbfa_0%,#ffffff_100%)] p-4 md:col-span-2 xl:col-span-1">
            <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
              <Workflow class="h-3.5 w-3.5 text-stone-700" />
              调度上下文
            </div>
            <div class="mt-3 space-y-3">
              <div>
                <div class="text-[11px] text-stone-400">Selected Containers</div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <span
                    v-for="containerKey in snapshot.selectedContainerKeys"
                    :key="containerKey"
                    class="inline-flex items-center border border-stone-200 bg-stone-100 px-2.5 py-1 text-[11px] font-medium text-stone-700"
                  >
                    {{ containerKey }}
                  </span>
                  <span
                    v-if="!snapshot.selectedContainerKeys.length"
                    class="text-sm text-stone-500"
                  >
                    暂无容器选择记录
                  </span>
                </div>
              </div>

              <div>
                <div class="text-[11px] text-stone-400">Dispatched Agents</div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <span
                    v-for="agent in snapshot.dispatchedAgents"
                    :key="agent"
                    class="inline-flex items-center border border-stone-900 bg-stone-900 px-2.5 py-1 text-[11px] font-medium text-white"
                  >
                    {{ agent }}
                  </span>
                  <span
                    v-if="!snapshot.dispatchedAgents.length"
                    class="text-sm text-stone-500"
                  >
                    当前未记录额外调度信息
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="mt-4 overflow-hidden border border-stone-200">
        <div class="border-b border-stone-200 bg-stone-50 px-4 py-3">
          <p class="text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
            Runtime Meta Snapshot
          </p>
        </div>
        <pre class="max-h-[260px] overflow-auto bg-stone-900 p-4 text-xs leading-6 text-stone-100">{{ formatJson(snapshot.displayMeta) }}</pre>
      </div>
    </div>
  </div>
</template>
