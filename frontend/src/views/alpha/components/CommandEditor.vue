<template>
  <div class="command-editor h-full flex flex-col">
    <!-- 标题 -->
    <div class="mb-4 border-b border-zinc-200 pb-3">
      <h3 class="text-base font-semibold text-zinc-900">命令编辑器</h3>
    </div>

    <!-- 禁用状态 -->
    <div v-if="!requirementId" class="flex h-full items-center justify-center">
      <div class="text-zinc-500">请选择一个需求</div>
    </div>

    <!-- 命令编辑表单 -->
    <div v-else class="flex-1 overflow-y-auto">
      <form @submit.prevent="onSubmit" class="space-y-4">
        <!-- 命令类型选择 -->
        <div class="flex flex-col space-y-2">
          <label class="text-sm font-medium text-zinc-700">命令类型</label>
          <select
            v-model="selectedCommandType"
            class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            @change="onCommandTypeChange"
          >
            <option value="">-- 请选择命令 --</option>
            <option
              v-for="cmd in commandTypes"
              :key="cmd.type"
              :value="cmd.type"
            >
              {{ cmd.label }}
            </option>
          </select>
        </div>

        <!-- 动态表单字段 -->
        <div v-if="selectedCommand && selectedCommandType" class="space-y-4">
          <!-- 更新内容命令字段 -->
          <template v-if="selectedCommandType === 'UpdateRequirementContent'">
            <div class="flex flex-col space-y-2">
              <label class="text-sm font-medium text-zinc-700">标题</label>
              <input
                v-model="formData.title"
                type="text"
                class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="输入标题（可选）"
              />
            </div>

            <div class="flex flex-col space-y-2">
              <label class="text-sm font-medium text-zinc-700">描述</label>
              <textarea
                v-model="formData.description"
                rows="4"
                class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                placeholder="输入描述（可选）"
              ></textarea>
            </div>
          </template>

          <!-- 更改状态命令字段 -->
          <template v-if="selectedCommandType === 'ChangeStatus'">
            <div class="flex flex-col space-y-2">
              <label class="text-sm font-medium text-zinc-700">新状态</label>
              <select
                v-model="formData.new_status"
                class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                required
              >
                <option v-for="status in statusOptions" :key="status.value" :value="status.value">
                  {{ status.label }}
                </option>
              </select>
            </div>
          </template>

          <!-- 添加质量标记命令字段 -->
          <template v-if="selectedCommandType === 'AddQualityMarker'">
            <div class="flex flex-col space-y-2">
              <label class="text-sm font-medium text-zinc-700">标记类型</label>
              <input
                v-model="formData.marker_type"
                type="text"
                class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="例如：priority, complexity, risk"
                required
              />
            </div>

            <div class="flex flex-col space-y-2">
              <label class="text-sm font-medium text-zinc-700">标记值</label>
              <input
                v-model="formData.marker_value"
                type="text"
                class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="例如：high, medium, low"
                required
              />
            </div>
          </template>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="isLoading"
            class="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:bg-blue-300"
          >
            {{ isLoading ? '提交中...' : '提交命令' }}
          </button>
        </div>

        <!-- 当前状态信息 -->
        <div v-if="currentState" class="mt-4 rounded-lg bg-zinc-50 p-3">
          <div class="text-xs font-medium uppercase tracking-wide text-zinc-500 mb-2">当前状态</div>
          <div class="space-y-1 text-xs text-zinc-600">
            <div>状态: {{ currentState.status }}</div>
            <div>优先级: {{ currentState.priority }}</div>
          </div>
        </div>
      </form>

      <!-- 命令历史 -->
      <div v-if="commandHistory.length > 0" class="mt-6 border-t border-zinc-200 pt-4">
        <h4 class="mb-3 text-sm font-semibold text-zinc-900">命令历史</h4>
        <div class="space-y-2">
          <div
            v-for="(cmd, index) in commandHistory"
            :key="index"
            class="rounded-md border border-zinc-200 bg-white p-2 text-xs"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ getCommandLabel(cmd.type) }}</span>
              <span class="text-zinc-500">{{ formatTime(cmd.timestamp) }}</span>
            </div>
            <div v-if="cmd.status" class="mt-1">
              <span
                :class="{
                  'text-green-600': cmd.status === 'success',
                  'text-red-600': cmd.status === 'error'
                }"
              >
                {{ cmd.status === 'success' ? '✓ 成功' : '✗ 失败' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { requirementActorApi } from '@/api/requirementActor'

const props = defineProps({
  requirementId: {
    type: String,
    default: ''
  },
  currentState: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['command-submitted'])

const selectedCommandType = ref('')
const formData = ref({})
const isLoading = ref(false)
const commandHistory = ref([])

const commandTypes = [
  {
    type: 'UpdateRequirementContent',
    label: '更新内容',
    fields: ['title', 'description']
  },
  {
    type: 'ChangeStatus',
    label: '更改状态',
    fields: ['new_status']
  },
  {
    type: 'AddQualityMarker',
    label: '添加质量标记',
    fields: ['marker_type', 'marker_value']
  }
]

const statusOptions = [
  { value: 'Draft', label: '草稿' },
  { value: 'PendingReview', label: '待评审' },
  { value: 'UnderReview', label: '评审中' },
  { value: 'Approved', label: '已通过' },
  { value: 'Rejected', label: '已驳回' },
  { value: 'Baselined', label: '已基线' },
  { value: 'ChangeRequested', label: '变更请求' }
]

const selectedCommand = computed(() => {
  return commandTypes.find(cmd => cmd.type === selectedCommandType.value)
})

function onCommandTypeChange() {
  formData.value = {}
  // 重置表单数据
  if (selectedCommandType.value === 'UpdateRequirementContent') {
    formData.value = {
      title: props.currentState?.title || '',
      description: props.currentState?.description || ''
    }
  } else if (selectedCommandType.value === 'ChangeStatus') {
    formData.value = {
      new_status: props.currentState?.status || 'Draft'
    }
  }
}

async function onSubmit() {
  if (!selectedCommandType.value) {
    alert('请选择命令类型')
    return
  }

  isLoading.value = true

  try {
    const command = {
      type: selectedCommandType.value,
      ...formData.value,
      metadata: {}
    }

    await requirementActorApi.submitCommand(props.requirementId, command)

    // 添加到历史
    commandHistory.value.unshift({
      ...command,
      timestamp: new Date().toISOString(),
      status: 'success'
    })

    // 通知父组件
    emit('command-submitted', command)

    // 重置表单
    selectedCommandType.value = ''
    formData.value = {}

    alert('命令提交成功')
  } catch (err) {
    console.error('Failed to submit command:', err)

    // 添加到历史（失败）
    commandHistory.value.unshift({
      type: selectedCommandType.value,
      timestamp: new Date().toISOString(),
      status: 'error'
    })

    alert(`命令提交失败: ${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally {
    isLoading.value = false
  }
}

function getCommandLabel(type) {
  const cmd = commandTypes.find(c => c.type === type)
  return cmd ? cmd.label : type
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

onMounted(() => {
  if (props.currentState) {
    formData.value = {
      title: props.currentState.title || '',
      description: props.currentState.description || ''
    }
  }
})
</script>

<style scoped>
.command-editor {
  scrollbar-width: thin;
  scrollbar-color: #d4d4d8 transparent;
}

.command-editor::-webkit-scrollbar {
  width: 6px;
}

.command-editor::-webkit-scrollbar-thumb {
  background-color: #d4d4d8;
  border-radius: 3px;
}
</style>
