<template>
  <div class="requirement-state h-full flex flex-col">
    <!-- 标题 -->
    <div class="mb-4 border-b border-zinc-200 pb-3">
      <h3 class="text-base font-semibold text-zinc-900">需求状态</h3>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="flex h-full items-center justify-center">
      <div class="text-zinc-500">加载中...</div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!state" class="flex h-full items-center justify-center">
      <div class="text-zinc-500">请选择一个需求查看状态</div>
    </div>

    <!-- 状态内容 -->
    <div v-else class="flex-1 overflow-y-auto">
      <!-- 版本信息 -->
      <div class="mb-4 rounded-lg bg-zinc-50 p-3">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-zinc-700">当前版本</span>
          <span class="text-sm font-semibold text-blue-600">v{{ version }}</span>
        </div>
        <div v-if="maxVersion !== undefined && maxVersion > 0" class="mt-1 text-xs text-zinc-500">
          共 {{ maxVersion + 1 }} 个版本
        </div>
      </div>

      <!-- 状态卡片 -->
      <div class="space-y-4">
        <!-- 标题 -->
        <div class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">标题</div>
          <div class="mt-2 text-base font-medium text-zinc-900">
            {{ state.title || '(无标题)' }}
          </div>
        </div>

        <!-- 描述 -->
        <div class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">描述</div>
          <div class="mt-2 text-sm text-zinc-700 whitespace-pre-wrap">
            {{ state.description || '(无描述)' }}
          </div>
        </div>

        <!-- 状态和优先级 -->
        <div class="grid grid-cols-2 gap-4">
          <div class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
            <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">状态</div>
            <div class="mt-2">
              <span
                class="inline-block rounded-full px-2.5 py-1 text-xs font-medium"
                :class="getStatusClass(state.status)"
              >
                {{ getStatusLabel(state.status) }}
              </span>
            </div>
          </div>

          <div class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
            <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">优先级</div>
            <div class="mt-2">
              <span
                class="inline-block rounded-full px-2.5 py-1 text-xs font-medium"
                :class="getPriorityClass(state.priority)"
              >
                {{ getPriorityLabel(state.priority) }}
              </span>
            </div>
          </div>
        </div>

        <!-- 质量标记 -->
        <div
          v-if="state.quality_markers && Object.keys(state.quality_markers).length > 0"
          class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm"
        >
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">质量标记</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="(value, type) in state.quality_markers"
              :key="type"
              class="inline-flex items-center rounded-md bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700"
            >
              <span class="font-semibold">{{ type }}:</span>
              <span class="ml-1">{{ value }}</span>
            </span>
          </div>
        </div>

        <!-- 时间信息 -->
        <div class="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500 mb-2">时间信息</div>
          <div class="space-y-1 text-xs text-zinc-600">
            <div v-if="state.created_at">
              <span class="font-medium">创建时间:</span>
              {{ formatTime(state.created_at) }}
            </div>
            <div v-if="state.updated_at">
              <span class="font-medium">更新时间:</span>
              {{ formatTime(state.updated_at) }}
            </div>
          </div>
        </div>

        <!-- 需求ID -->
        <div class="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500">需求ID</div>
          <div class="mt-1 text-xs font-mono text-zinc-700">
            {{ state.requirement_id }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: {
    type: Object,
    default: null
  },
  version: {
    type: Number,
    default: 0
  },
  maxVersion: {
    type: Number,
    default: undefined
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

function getStatusLabel(status) {
  const labels = {
    'Draft': '草稿',
    'PendingReview': '待评审',
    'UnderReview': '评审中',
    'Approved': '已通过',
    'Rejected': '已驳回',
    'Baselined': '已基线',
    'ChangeRequested': '变更请求',
    // 兼容历史状态值
    'Under Review': '审核中',
    'Confirmed': '已确认',
    'In Progress': '进行中',
    'Completed': '已完成',
    'Archived': '已归档'
  }
  return labels[status] || status
}

function getStatusClass(status) {
  const classes = {
    'Draft': 'bg-zinc-100 text-zinc-700',
    'PendingReview': 'bg-amber-100 text-amber-700',
    'UnderReview': 'bg-yellow-100 text-yellow-700',
    'Approved': 'bg-emerald-100 text-emerald-700',
    'Rejected': 'bg-rose-100 text-rose-700',
    'Baselined': 'bg-sky-100 text-sky-700',
    'ChangeRequested': 'bg-orange-100 text-orange-700',
    // 兼容历史状态值
    'Under Review': 'bg-yellow-100 text-yellow-700',
    'Confirmed': 'bg-green-100 text-green-700',
    'In Progress': 'bg-blue-100 text-blue-700',
    'Completed': 'bg-emerald-100 text-emerald-700',
    'Archived': 'bg-gray-100 text-gray-600'
  }
  return classes[status] || 'bg-zinc-100 text-zinc-700'
}

function getPriorityLabel(priority) {
  const labels = {
    'low': '低',
    'medium': '中',
    'high': '高',
    'critical': '紧急'
  }
  return labels[priority] || priority
}

function getPriorityClass(priority) {
  const classes = {
    'low': 'bg-green-100 text-green-700',
    'medium': 'bg-yellow-100 text-yellow-700',
    'high': 'bg-orange-100 text-orange-700',
    'critical': 'bg-red-100 text-red-700'
  }
  return classes[priority] || 'bg-zinc-100 text-zinc-700'
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style scoped>
.requirement-state {
  scrollbar-width: thin;
  scrollbar-color: #d4d4d8 transparent;
}

.requirement-state::-webkit-scrollbar {
  width: 6px;
}

.requirement-state::-webkit-scrollbar-thumb {
  background-color: #d4d4d8;
  border-radius: 3px;
}
</style>
