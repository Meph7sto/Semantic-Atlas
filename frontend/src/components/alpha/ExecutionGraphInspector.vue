<script setup>
import { ref, watch, computed } from 'vue'

const props = defineProps({
  selectedObject: {
    type: Object,
    default: null
  },
  objectType: {
    type: String,
    default: 'graph' // 'graph' | 'node' | 'edge'
  }
})

const emit = defineEmits(['update'])

// 表单数据
const formData = ref({})
const errors = ref({})

// 监听选中对象变化
watch(() => props.selectedObject, (newObj) => {
  if (newObj) {
    // 深拷贝数据以避免直接修改
    formData.value = JSON.parse(JSON.stringify(newObj))
  } else {
    formData.value = {}
  }
  errors.value = {}
}, { immediate: true })

// 图状态选项
const graphStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '激活' },
  { value: 'running', label: '运行中' },
  { value: 'succeeded', label: '已成功' },
  { value: 'failed', label: '已失败' },
  { value: 'suspended', label: '已挂起' }
]

// 节点类型选项
const nodeTypeOptions = [
  { value: 'start', label: 'Start (开始)' },
  { value: 'node', label: 'Node (节点)' },
  { value: 'decision', label: 'Decision (决策)' },
  { value: 'handoff', label: 'Handoff (交接)' },
  { value: 'end', label: 'End (结束)' },
  { value: 'llm', label: 'LLM (模型)' },
  { value: 'invoke', label: 'Invoke (工具调用)' }
]

// 角色类型选项
const roleTypeOptions = [
  { value: 'human', label: 'Human (人工)' },
  { value: 'agent', label: 'Agent (智能体)' },
  { value: 'system', label: 'System (系统)' }
]

// 边类型选项
const edgeTypeOptions = [
  { value: 'call', label: 'Call (调用)' },
  { value: 'return', label: 'Return (返回)' },
  { value: 'retry', label: 'Retry (重试)' }
]

// 验证 JSON 字段
const validateJson = (value) => {
  if (!value || value.trim() === '') return true
  try {
    JSON.parse(value)
    return true
  } catch {
    return false
  }
}

// 保存更改
const handleSave = () => {
  errors.value = {}

  // 验证必填字段
  if (!formData.value.label && props.objectType !== 'edge') {
    errors.value.label = '标签不能为空'
  }

  // 验证 JSON 字段
  if (props.objectType === 'node') {
    if (formData.value.config_json && !validateJson(formData.value.config_json)) {
      errors.value.config_json = '无效的 JSON 格式'
    }
    if (formData.value.input_schema_json && !validateJson(formData.value.input_schema_json)) {
      errors.value.input_schema_json = '无效的 JSON 格式'
    }
    if (formData.value.output_schema_json && !validateJson(formData.value.output_schema_json)) {
      errors.value.output_schema_json = '无效的 JSON 格式'
    }
  } else if (props.objectType === 'edge') {
    if (formData.value.config_json && !validateJson(formData.value.config_json)) {
      errors.value.config_json = '无效的 JSON 格式'
    }
  }

  // 如果有错误，不保存
  if (Object.keys(errors.value).length > 0) {
    return
  }

  // 转换 JSON 字符串为对象
  const updateData = { ...formData.value }
  if (updateData.config_json && typeof updateData.config_json === 'string') {
    try {
      updateData.config_json = JSON.parse(updateData.config_json)
    } catch {
      // 保持原样
    }
  }
  if (updateData.input_schema_json && typeof updateData.input_schema_json === 'string') {
    try {
      updateData.input_schema_json = JSON.parse(updateData.input_schema_json)
    } catch {
      // 保持原样
    }
  }
  if (updateData.output_schema_json && typeof updateData.output_schema_json === 'string') {
    try {
      updateData.output_schema_json = JSON.parse(updateData.output_schema_json)
    } catch {
      // 保持原样
    }
  }

  emit('update', updateData)
}

// 当前对象类型标题
const objectTypeTitle = computed(() => {
  const titles = {
    graph: '图属性',
    node: '节点属性',
    edge: '边属性'
  }
  return titles[props.objectType] || '属性'
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 border-l border-zinc-200">
    <!-- 标题 -->
    <div class="px-4 py-3 border-b border-zinc-200 bg-white">
      <h2 class="text-sm font-semibold text-zinc-900">{{ objectTypeTitle }}</h2>
    </div>

    <!-- 未选中状态 -->
    <div v-if="!selectedObject" class="flex-1 flex items-center justify-center text-zinc-400">
      <div class="text-center">
        <svg class="w-12 h-12 mx-auto mb-2 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.042 21.672L13.684 16.6m0 0l-2.51 5.072a2.25 2.25 0 01-2.247-1.674L5.385 7.168a2.25 2.25 0 011.33-1.95l5.517-3.498a2.25 2.25 0 011.451 1.276l3.842 4.03a2.25 2.25 0 002.927-.656L17.788 13.33a2.25 2.25 0 011.254 2.342z" />
        </svg>
        <p class="text-sm">请选择一个对象进行编辑</p>
      </div>
    </div>

    <!-- 表单区域 -->
    <div v-else class="flex-1 overflow-y-auto p-4">
      <form @submit.prevent="handleSave" class="space-y-4">
        <!-- 图属性 -->
        <div v-if="objectType === 'graph'" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">名称 *</label>
            <input
              v-model="formData.name"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.name ? 'border-red-500' : ''"
              placeholder="输入图名称"
            />
            <p v-if="errors.name" class="mt-1 text-xs text-red-500">{{ errors.name }}</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">描述</label>
            <textarea
              v-model="formData.description"
              rows="3"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder="输入图描述"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">状态</label>
            <select
              v-model="formData.status"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in graphStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">版本</label>
            <input
              v-model="formData.version"
              type="number"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm bg-zinc-100"
              disabled
            />
          </div>
        </div>

        <!-- 节点属性 -->
        <div v-if="objectType === 'node'" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">标签 *</label>
            <input
              v-model="formData.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.label ? 'border-red-500' : ''"
              placeholder="输入节点标签"
            />
            <p v-if="errors.label" class="mt-1 text-xs text-red-500">{{ errors.label }}</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">节点 Key</label>
            <input
              v-model="formData.node_key"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm bg-zinc-100"
              disabled
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">节点类型</label>
            <select
              v-model="formData.node_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in nodeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">角色类型</label>
            <select
              v-model="formData.role_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in roleTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-zinc-700 mb-1">X 坐标</label>
              <input
                v-model.number="formData.x"
                type="number"
                class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-zinc-700 mb-1">Y 坐标</label>
              <input
                v-model.number="formData.y"
                type="number"
                class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">配置 JSON</label>
            <textarea
              v-model="formData.config_json"
              rows="4"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              :class="errors.config_json ? 'border-red-500' : ''"
              placeholder='{"timeout": 60, "retryable": true}'
            />
            <p v-if="errors.config_json" class="mt-1 text-xs text-red-500">{{ errors.config_json }}</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">输入模式 JSON</label>
            <textarea
              v-model="formData.input_schema_json"
              rows="3"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              :class="errors.input_schema_json ? 'border-red-500' : ''"
              placeholder='["requirement_id", "change_request_text"]'
            />
            <p v-if="errors.input_schema_json" class="mt-1 text-xs text-red-500">{{ errors.input_schema_json }}</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">输出模式 JSON</label>
            <textarea
              v-model="formData.output_schema_json"
              rows="3"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              :class="errors.output_schema_json ? 'border-red-500' : ''"
              placeholder='["review_result", "next_action"]'
            />
            <p v-if="errors.output_schema_json" class="mt-1 text-xs text-red-500">{{ errors.output_schema_json }}</p>
          </div>
        </div>

        <!-- 边属性 -->
        <div v-if="objectType === 'edge'" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">标签</label>
            <input
              v-model="formData.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入边标签"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">边类型</label>
            <select
              v-model="formData.edge_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in edgeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">条件表达式</label>
            <textarea
              v-model="formData.condition_expr"
              rows="3"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder="review_required == true"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">配置 JSON</label>
            <textarea
              v-model="formData.config_json"
              rows="4"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              :class="errors.config_json ? 'border-red-500' : ''"
              placeholder='{"priority": 1}'
            />
            <p v-if="errors.config_json" class="mt-1 text-xs text-red-500">{{ errors.config_json }}</p>
          </div>
        </div>

        <!-- 保存按钮 -->
        <div class="pt-4 border-t border-zinc-200">
          <button
            type="submit"
            class="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
          >
            保存更改
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
