<template>
  <div class="state-canvas flex h-full flex-col">
    <div class="mb-4 flex items-center justify-between border-b border-zinc-200 pb-3">
      <h3 class="text-base font-semibold text-zinc-900">状态演进画布</h3>
      <div class="text-sm text-zinc-500">
        v{{ currentVersion }} / v{{ maxVersion }}
      </div>
    </div>

    <div class="mb-4 flex items-center space-x-2 rounded-lg bg-zinc-50 p-2">
      <button
        :disabled="currentVersion <= 0"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="跳转到开始"
        @click="jumpToStart"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
        </svg>
      </button>

      <button
        :disabled="!canPlayBackward"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="后退一步"
        @click="stepBackward"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <button
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200"
        :title="isPlaying ? '暂停' : '播放'"
        @click="isPlaying ? pause() : play()"
      >
        <svg v-if="!isPlaying" class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>

      <button
        :disabled="!canPlayForward"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="前进一步"
        @click="stepForward"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <button
        :disabled="currentVersion >= maxVersion"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="跳转到结束"
        @click="jumpToEnd"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
        </svg>
      </button>
    </div>

    <div class="mb-4">
      <div class="mb-1 flex justify-between text-xs text-zinc-500">
        <span>进度</span>
        <span>{{ versionProgress }}%</span>
      </div>
      <div class="h-2 w-full rounded-full bg-zinc-200">
        <div
          class="h-2 rounded-full bg-emerald-500 transition-all duration-300"
          :style="{ width: `${versionProgress}%` }"
        ></div>
      </div>
    </div>

    <div class="relative min-h-[320px] flex-1 overflow-auto rounded-xl border border-zinc-200 bg-gradient-to-br from-white to-zinc-50">
      <div class="relative" :style="{ width: `${canvasWidth}px`, height: `${canvasHeight}px` }">
        <svg class="pointer-events-none absolute left-0 top-0 h-full w-full">
          <defs>
            <marker
              :id="arrowMarkerId"
              markerWidth="8"
              markerHeight="8"
              refX="7"
              refY="4"
              orient="auto"
            >
              <path d="M0,0 L8,4 L0,8 z" fill="#71717a"></path>
            </marker>
          </defs>
          <line
            v-for="line in lines"
            :key="line.id"
            :x1="line.x1"
            :y1="line.y1"
            :x2="line.x2"
            :y2="line.y2"
            stroke="#a1a1aa"
            stroke-width="2"
            :marker-end="`url(#${arrowMarkerId})`"
          />
        </svg>

        <button
          v-for="node in nodes"
          :key="node.id"
          class="node-card absolute rounded-xl border text-left transition-all duration-200"
          :class="getNodeClass(node)"
          :style="{
            width: `${NODE_WIDTH}px`,
            minHeight: `${NODE_HEIGHT}px`,
            left: `${node.x}px`,
            top: `${node.y}px`
          }"
          @click="selectVersion(node.version)"
        >
          <div class="mb-2 flex items-start justify-between">
            <span class="rounded-md bg-zinc-900/5 px-2 py-0.5 text-xs font-semibold text-zinc-700">
              v{{ node.version }}
            </span>
            <span
              class="text-[11px] font-semibold uppercase tracking-wide"
              :class="getEventColorClass(node.eventType)"
            >
              {{ getEventLabel(node.eventType) }}
            </span>
          </div>

          <div class="text-sm font-semibold text-zinc-900">
            {{ node.title }}
          </div>

          <div v-if="node.subtitle" class="mt-1 max-h-10 overflow-hidden text-xs text-zinc-600">
            {{ node.subtitle }}
          </div>

          <div v-if="node.time" class="mt-3 text-[11px] text-zinc-500">
            {{ node.time }}
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  events: {
    type: Array,
    default: () => []
  },
  currentVersion: {
    type: Number,
    default: 0
  },
  maxVersion: {
    type: Number,
    default: 0
  },
  isPlaying: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'version-select',
  'play',
  'pause',
  'step-forward',
  'step-backward',
  'jump-start',
  'jump-end'
])

const NODE_WIDTH = 220
const NODE_HEIGHT = 112
const NODE_GAP = 76
const CANVAS_PADDING_X = 40
const CANVAS_PADDING_Y = 84
const arrowMarkerId = `state-canvas-arrow-${Math.random().toString(36).slice(2, 8)}`

const canPlayForward = computed(() => props.currentVersion < props.maxVersion)
const canPlayBackward = computed(() => props.currentVersion > 0)
const versionProgress = computed(() => {
  if (props.maxVersion === 0) return 0
  return Math.round((props.currentVersion / props.maxVersion) * 100)
})

const nodes = computed(() => {
  const list = [
    {
      id: 'initial-state',
      version: 0,
      eventType: 'InitialState',
      title: '初始状态',
      subtitle: '尚未执行任何命令',
      time: '',
      x: CANVAS_PADDING_X,
      y: CANVAS_PADDING_Y
    }
  ]

  props.events.forEach((event, index) => {
    const version = getEventVersion(event, index)
    list.push({
      id: event.event_id || `event-${version}-${index}`,
      version,
      eventType: event.event_type,
      title: `${getEventLabel(event.event_type)}`,
      subtitle: getEventSummary(event),
      time: formatTime(event.occurred_at),
      x: CANVAS_PADDING_X + (index + 1) * (NODE_WIDTH + NODE_GAP),
      y: CANVAS_PADDING_Y
    })
  })

  return list
})

const lines = computed(() => {
  return nodes.value.slice(0, -1).map((node, index) => {
    const next = nodes.value[index + 1]
    return {
      id: `${node.id}-${next.id}`,
      x1: node.x + NODE_WIDTH,
      y1: node.y + NODE_HEIGHT / 2,
      x2: next.x,
      y2: next.y + NODE_HEIGHT / 2
    }
  })
})

const canvasWidth = computed(() => {
  const count = Math.max(nodes.value.length, 1)
  const width = CANVAS_PADDING_X * 2 + count * NODE_WIDTH + (count - 1) * NODE_GAP
  return Math.max(width, 900)
})

const canvasHeight = computed(() => {
  return NODE_HEIGHT + CANVAS_PADDING_Y * 2
})

function getEventVersion(event, index) {
  const eventSequence = Number(event?.event_sequence)
  if (Number.isFinite(eventSequence) && eventSequence >= 0) {
    return eventSequence
  }
  return index + 1
}

function getEventLabel(eventType) {
  const labels = {
    InitialState: '开始',
    RequirementCreated: '创建需求',
    RequirementContentUpdated: '更新内容',
    RequirementStatusChanged: '状态变更',
    RequirementQualityMarkerAdded: '添加标记',
    RequirementPriorityChanged: '优先级',
    RequirementEvidenceLinkAdded: '证据关联',
    RequirementDeleted: '删除需求'
  }
  return labels[eventType] || eventType || '事件'
}

function getEventColorClass(eventType) {
  const colors = {
    InitialState: 'text-zinc-500',
    RequirementCreated: 'text-purple-600',
    RequirementContentUpdated: 'text-blue-600',
    RequirementStatusChanged: 'text-amber-600',
    RequirementQualityMarkerAdded: 'text-emerald-600',
    RequirementPriorityChanged: 'text-cyan-600',
    RequirementEvidenceLinkAdded: 'text-pink-600',
    RequirementDeleted: 'text-red-600'
  }
  return colors[eventType] || 'text-zinc-600'
}

function getEventSummary(event) {
  if (!event) return ''
  const data = event.event_data || {}

  if (event.event_type === 'RequirementContentUpdated') {
    const updateKeys = Object.keys(data.updates || {})
    return updateKeys.length > 0 ? `更新字段: ${updateKeys.join(' / ')}` : '内容发生变化'
  }

  if (event.event_type === 'RequirementStatusChanged') {
    return data.new_status ? `新状态: ${data.new_status}` : '状态发生变化'
  }

  if (event.event_type === 'RequirementQualityMarkerAdded') {
    if (data.marker_type && data.marker_value !== undefined) {
      return `${data.marker_type}: ${data.marker_value}`
    }
    return '新增质量标记'
  }

  if (event.event_type === 'RequirementCreated') {
    return data.title || '新建需求'
  }

  return ''
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getNodeClass(node) {
  if (node.version === props.currentVersion) {
    return 'border-emerald-500 bg-emerald-50 shadow-md ring-2 ring-emerald-200'
  }

  if (node.version < props.currentVersion) {
    return 'border-zinc-300 bg-white shadow-sm hover:border-zinc-400'
  }

  return 'border-zinc-200 bg-zinc-100/80 opacity-80 hover:opacity-100'
}

function selectVersion(version) {
  emit('version-select', version)
}

function stepForward() {
  emit('step-forward')
}

function stepBackward() {
  emit('step-backward')
}

function play() {
  emit('play')
}

function pause() {
  emit('pause')
}

function jumpToStart() {
  emit('jump-start')
}

function jumpToEnd() {
  emit('jump-end')
}
</script>

<style scoped>
.state-canvas {
  scrollbar-width: thin;
  scrollbar-color: #d4d4d8 transparent;
}

.node-card {
  padding: 12px;
}
</style>
