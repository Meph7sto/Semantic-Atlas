<script setup>
import { computed, ref, watch } from 'vue'
import {
  isBlank,
  normalizeInspectorPayload,
  stringifyJsonForEditor
} from '@/utils/topologyEditor'

const props = defineProps({
  selectedObject: {
    type: Object,
    default: null
  },
  objectType: {
    type: String,
    default: 'graph'
  }
})

const emit = defineEmits(['update'])

const formData = ref({})
const errors = ref({})

const graphStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'active', label: '激活' },
  { value: 'running', label: '运行中' },
  { value: 'succeeded', label: '已成功' },
  { value: 'failed', label: '已失败' },
  { value: 'suspended', label: '已挂起' }
]

const nodeTypeOptions = [
  { value: 'start', label: 'Start (开始)' },
  { value: 'llm', label: 'LLM (模型)' },
  { value: 'invoke', label: 'Invoke (工具调用)' },
  { value: 'handoff', label: 'Handoff (交接)' },
  { value: 'end', label: 'End (结束)' }
]

const roleTypeOptions = [
  { value: 'human', label: 'Human (人工)' },
  { value: 'agent', label: 'Agent (智能体)' },
  { value: 'system', label: 'System (系统)' }
]

const edgeTypeOptions = [
  { value: 'call', label: 'Call (调用)' },
  { value: 'return', label: 'Return (返回)' },
  { value: 'retry', label: 'Retry (重试)' },
  { value: 'seq', label: 'Seq (顺序)' }
]

const asObject = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value
}

const hydrateFormData = (selectedObject, objectType) => {
  if (!selectedObject) {
    return {}
  }

  const cloned = JSON.parse(JSON.stringify(selectedObject))

  if (objectType === 'container') {
    cloned.config_json = stringifyJsonForEditor(cloned.config_json, '{}')
  }

  if (objectType === 'node') {
    const nodeConfig = asObject(cloned.config_json)
    cloned.stage_prompt = typeof nodeConfig.stage_prompt === 'string' ? nodeConfig.stage_prompt : ''
    cloned.config_json = stringifyJsonForEditor(cloned.config_json, '{}')
    cloned.input_schema_json = stringifyJsonForEditor(cloned.input_schema_json, '[]')
  }

  if (objectType === 'edge') {
    cloned.config_json = stringifyJsonForEditor(cloned.config_json, '{}')
  }

  return cloned
}

watch(
  [() => props.selectedObject, () => props.objectType],
  ([selectedObject, objectType]) => {
    formData.value = hydrateFormData(selectedObject, objectType)
    errors.value = {}
  },
  { immediate: true }
)

const metadataFields = computed(() => {
  if (!props.selectedObject) return []

  if (props.objectType === 'graph') {
    return [
      { label: 'Graph ID', value: props.selectedObject.graph_id || '-' },
      { label: '类型', value: props.selectedObject.graph_type || '-' },
      { label: '版本', value: props.selectedObject.version ?? '-' },
      { label: '创建时间', value: props.selectedObject.created_at || '-' }
    ]
  }

  if (props.objectType === 'container') {
    return [
      { label: 'Container ID', value: props.selectedObject.container_id || '-' },
      { label: 'Container Key', value: props.selectedObject.container_key || '-' },
      { label: '创建时间', value: props.selectedObject.created_at || '-' }
    ]
  }

  if (props.objectType === 'node') {
    return [
      { label: 'Node ID', value: props.selectedObject.node_id || '-' },
      { label: 'Node Key', value: props.selectedObject.node_key || '-' },
      { label: '容器 ID', value: props.selectedObject.container_id || '未分配' },
      { label: '创建时间', value: props.selectedObject.created_at || '-' }
    ]
  }

  if (props.objectType === 'edge') {
    return [
      { label: 'Edge ID', value: props.selectedObject.edge_id || '-' },
      { label: '源节点', value: props.selectedObject.source_node_id || '-' },
      { label: '目标节点', value: props.selectedObject.target_node_id || '-' },
      { label: '创建时间', value: props.selectedObject.created_at || '-' }
    ]
  }

  return []
})

const handleSave = () => {
  errors.value = {}

  if (props.objectType === 'graph' && isBlank(formData.value.name)) {
    errors.value.name = '名称不能为空'
  }

  if (props.objectType === 'container' && isBlank(formData.value.label)) {
    errors.value.label = '容器名称不能为空'
  }

  if (props.objectType === 'node' && isBlank(formData.value.label)) {
    errors.value.label = '节点标签不能为空'
  }

  const normalized = normalizeInspectorPayload(props.objectType, formData.value)
  if (!normalized.ok) {
    errors.value.form = normalized.error
    return
  }

  if (props.objectType === 'container' && isBlank(normalized.value.label)) {
    errors.value.label = '容器名称不能为空'
  }

  if (props.objectType === 'node' && isBlank(normalized.value.label)) {
    errors.value.label = '节点标签不能为空'
  }

  if (Object.keys(errors.value).length > 0) {
    return
  }

  emit('update', normalized.value)
}

const objectTypeTitle = computed(() => {
  const titles = {
    graph: '图属性',
    container: '容器属性',
    node: '节点属性',
    edge: '边属性'
  }
  return titles[props.objectType] || '属性'
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 border-l border-zinc-200">
    <div class="px-4 py-3 border-b border-zinc-200 bg-white">
      <h2 class="text-sm font-semibold text-zinc-900">{{ objectTypeTitle }}</h2>
    </div>

    <div v-if="!selectedObject" class="flex-1 flex items-center justify-center text-zinc-400">
      <div class="text-center">
        <svg class="w-12 h-12 mx-auto mb-2 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.042 21.672L13.684 16.6m0 0l-2.51 5.072a2.25 2.25 0 01-2.247-1.674L5.385 7.168a2.25 2.25 0 011.33-1.95l5.517-3.498a2.25 2.25 0 011.451 1.276l3.842 4.03a2.25 2.25 0 002.927-.656L17.788 13.33a2.25 2.25 0 011.254 2.342z" />
        </svg>
        <p class="text-sm">请选择一个对象进行编辑</p>
      </div>
    </div>

    <div v-else class="flex-1 overflow-y-auto p-4">
      <form @submit.prevent="handleSave" class="space-y-4">
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
        </div>

        <div v-if="objectType === 'container'" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">容器名称 *</label>
            <input
              v-model="formData.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.label ? 'border-red-500' : ''"
              placeholder="输入容器名称"
            />
            <p v-if="errors.label" class="mt-1 text-xs text-red-500">{{ errors.label }}</p>
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

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">排序</label>
            <input
              v-model.number="formData.order_index"
              type="number"
              min="0"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">配置 JSON</label>
            <textarea
              v-model="formData.config_json"
              rows="5"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder='{"parallelism": 1}'
            />
          </div>
        </div>

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

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">排序</label>
            <input
              v-model.number="formData.order_index"
              type="number"
              min="0"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>


          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">配置 JSON</label>
            <textarea
              v-model="formData.config_json"
              rows="4"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder='{"timeout": 60}'
            />
          </div>

        </div>

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
            <label class="block text-xs font-medium text-zinc-700 mb-1">排序</label>
            <input
              v-model.number="formData.order_index"
              type="number"
              min="0"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-700 mb-1">配置 JSON</label>
            <textarea
              v-model="formData.config_json"
              rows="4"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder='{"priority": 1}'
            />
          </div>
        </div>

        <div v-if="errors.form" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
          {{ errors.form }}
        </div>

        <div class="space-y-2 rounded-lg border border-zinc-200 bg-white p-3">
          <div class="text-xs font-semibold text-zinc-700">只读信息</div>
          <div
            v-for="field in metadataFields"
            :key="field.label"
            class="rounded border border-zinc-100 bg-zinc-50 px-3 py-2"
          >
            <div class="text-[11px] text-zinc-500">{{ field.label }}</div>
            <div class="break-all text-xs text-zinc-800">{{ field.value }}</div>
          </div>
        </div>

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
