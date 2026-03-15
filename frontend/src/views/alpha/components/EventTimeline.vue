<template>
  <div class="event-timeline h-full flex flex-col">
    <!-- 标题和控制 -->
    <div class="mb-4 flex items-center justify-between border-b border-zinc-200 pb-3">
      <h3 class="text-base font-semibold text-zinc-900">事件时间线</h3>
      <div class="text-sm text-zinc-500">
        {{ currentVersion }} / {{ maxVersion }}
      </div>
    </div>

    <!-- 播放控制 -->
    <div class="mb-4 flex items-center space-x-2 rounded-lg bg-zinc-50 p-2">
      <button
        @click="jumpToStart"
        :disabled="currentVersion <= 0"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="跳转到开始"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
        </svg>
      </button>

      <button
        @click="stepBackward"
        :disabled="!canPlayBackward"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="后退一步"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <button
        @click="isPlaying ? pause() : play()"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200"
        :title="isPlaying ? '暂停' : '播放'"
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
        @click="stepForward"
        :disabled="!canPlayForward"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="前进一步"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <button
        @click="jumpToEnd"
        :disabled="currentVersion >= maxVersion"
        class="rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-200 disabled:opacity-30 disabled:hover:bg-transparent"
        title="跳转到结束"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
        </svg>
      </button>
    </div>

    <!-- 进度条 -->
    <div class="mb-4">
      <div class="mb-1 flex justify-between text-xs text-zinc-500">
        <span>进度</span>
        <span>{{ versionProgress }}%</span>
      </div>
      <div class="h-2 w-full rounded-full bg-zinc-200">
        <div
          class="h-2 rounded-full bg-blue-500 transition-all duration-300"
          :style="{ width: `${versionProgress}%` }"
        ></div>
      </div>
    </div>

    <!-- 时间线列表 -->
    <div class="flex-1 overflow-y-auto space-y-3 pr-2">
      <div v-if="events.length === 0" class="flex h-full items-center justify-center text-zinc-500">
        <p>暂无事件历史</p>
      </div>

      <div
        v-for="(event, index) in events"
        :key="event.event_id"
        class="timeline-item group relative pl-8"
        :class="{
          'opacity-50': index > currentVersion
        }"
        @click="selectVersion(index)"
      >
        <!-- 节点圆圈 -->
        <div
          class="absolute left-0 top-1.5 h-5 w-5 rounded-full border-2 transition-all duration-200"
          :class="getNodeClass(event.event_type, index)"
        >
          <span class="flex h-full items-center justify-center text-xs font-medium">{{ index }}</span>
        </div>

        <!-- 连接线 -->
        <div
          v-if="index < events.length - 1"
          class="absolute left-[9px] top-6 h-8 w-0.5 bg-zinc-300"
        ></div>

        <!-- 事件卡片 -->
        <div
          class="cursor-pointer rounded-lg border p-3 transition-all duration-200 hover:shadow-md"
          :class="{
            'border-zinc-300 bg-white': index !== currentVersion,
            'border-blue-500 bg-blue-50': index === currentVersion,
            'border-transparent bg-transparent hover:border-zinc-300 hover:bg-white': index > currentVersion
          }"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center space-x-2">
                <span class="text-xs font-semibold uppercase tracking-wide" :class="getEventColorClass(event.event_type)">
                  {{ getEventLabel(event.event_type) }}
                </span>
                <span v-if="event.source" class="text-xs text-zinc-500">
                  来源: {{ event.source }}
                </span>
              </div>
              <div v-if="event.occurred_at" class="mt-1 text-xs text-zinc-500">
                {{ formatTime(event.occurred_at) }}
              </div>
            </div>
            <!-- 当前版本指示器 -->
            <div v-if="index === currentVersion" class="ml-2">
              <svg class="h-4 w-4 text-blue-500" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
              </svg>
            </div>
          </div>
        </div>
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

const emit = defineEmits(['version-select', 'play', 'pause', 'step-forward', 'step-backward', 'jump-start', 'jump-end'])

const canPlayForward = computed(() => props.currentVersion < props.maxVersion)
const canPlayBackward = computed(() => props.currentVersion > 0)
const versionProgress = computed(() => {
  if (props.maxVersion === 0) return 0
  return Math.round((props.currentVersion / props.maxVersion) * 100)
})

function getEventLabel(eventType) {
  const labels = {
    'RequirementCreated': '创建需求',
    'RequirementContentUpdated': '更新内容',
    'RequirementStatusChanged': '状态变更',
    'RequirementQualityMarkerAdded': '添加标记',
    'RequirementPriorityChanged': '优先级变更',
    'RequirementEvidenceLinkAdded': '添加证据',
    'RequirementDeleted': '删除需求'
  }
  return labels[eventType] || eventType
}

function getEventColorClass(eventType) {
  const colors = {
    'RequirementCreated': 'text-purple-600',
    'RequirementContentUpdated': 'text-blue-600',
    'RequirementStatusChanged': 'text-orange-600',
    'RequirementQualityMarkerAdded': 'text-green-600',
    'RequirementPriorityChanged': 'text-cyan-600',
    'RequirementEvidenceLinkAdded': 'text-pink-600',
    'RequirementDeleted': 'text-red-600'
  }
  return colors[eventType] || 'text-zinc-600'
}

function getNodeClass(eventType, index) {
  if (index < props.currentVersion) {
    return 'bg-green-500 border-green-600 text-white'
  } else if (index === props.currentVersion) {
    return 'bg-blue-500 border-blue-600 text-white scale-110 shadow-md'
  } else {
    return 'bg-zinc-200 border-zinc-300 text-zinc-600'
  }
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
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
.event-timeline {
  scrollbar-width: thin;
  scrollbar-color: #d4d4d8 transparent;
}

.event-timeline::-webkit-scrollbar {
  width: 6px;
}

.event-timeline::-webkit-scrollbar-thumb {
  background-color: #d4d4d8;
  border-radius: 3px;
}
</style>
