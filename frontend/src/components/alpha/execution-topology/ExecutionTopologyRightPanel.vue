<script setup>
import { ref, watch, computed } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import ExecutionGraphInspector from '@/components/alpha/ExecutionGraphInspector.vue'

const props = defineProps({
  activeTab: {
    type: String,
    required: true
  },
  inspectorObject: {
    type: Object,
    default: null
  },
  objectType: {
    type: String,
    required: true
  },
  allNodes: {
    type: Array,
    default: () => []
  },
  validationLoading: {
    type: Boolean,
    required: true
  },
  validationResult: {
    type: Object,
    default: null
  },
  validationItems: {
    type: Array,
    required: true
  },
  executionError: {
    type: String,
    required: true
  },
  executionResult: {
    type: Object,
    default: null
  },
  executionStatusClass: {
    type: String,
    required: true
  }
})

const emit = defineEmits([
  'update:active-tab',
  'update-object',
  'validate-topology',
  'select-validation-item',
  'open-execute-dialog',
  'update-node-content'
])

// 判断当前是否选中节点
const isNodeSelected = computed(() => props.objectType === 'node')

// 中间 Tab 的值
const middleTabValue = computed(() => isNodeSelected.value ? 'node-content' : 'validation')
const middleTabLabel = computed(() => isNodeSelected.value ? '节点内容' : '校验')

// 节点内容 Tab 的本地状态
const nodeContentForm = ref({ task_prompt: '', input_node_ids: [] })
const nodeContentSaving = ref(false)

// 当选中的节点变化时，同步表单数据
watch(
  () => [props.inspectorObject, props.objectType],
  ([obj, type]) => {
    if (type !== 'node' || !obj) {
      nodeContentForm.value = { task_prompt: '', input_node_ids: [] }
      return
    }
    nodeContentForm.value = {
      task_prompt: obj.task_prompt || '',
      input_node_ids: Array.isArray(obj.input_schema_json) ? [...obj.input_schema_json] : []
    }
  },
  { immediate: true, deep: true }
)

// 输入节点列表（排除当前节点自身）
const availableInputNodes = computed(() => {
  if (!props.inspectorObject?.node_id) return props.allNodes
  return props.allNodes.filter(n => n.node_id !== props.inspectorObject.node_id)
})

const toggleInputNode = (nodeId) => {
  const ids = nodeContentForm.value.input_node_ids
  const idx = ids.indexOf(nodeId)
  if (idx === -1) {
    nodeContentForm.value.input_node_ids = [...ids, nodeId]
  } else {
    nodeContentForm.value.input_node_ids = ids.filter(id => id !== nodeId)
  }
}

const handleSaveNodeContent = () => {
  nodeContentSaving.value = true
  emit('update-node-content', {
    task_prompt: nodeContentForm.value.task_prompt,
    input_node_ids: nodeContentForm.value.input_node_ids
  })
  nodeContentSaving.value = false
}
</script>

<template>
  <div class="w-[360px] bg-white border-l border-zinc-200 overflow-hidden flex flex-col">
    <div class="border-b border-zinc-200 bg-white">
      <div class="flex">
        <button
          class="flex-1 px-3 py-2 text-sm transition-colors"
          :class="activeTab === 'inspector' ? 'bg-zinc-100 text-zinc-900 font-medium' : 'text-zinc-500 hover:bg-zinc-50'"
          @click="emit('update:active-tab', 'inspector')"
        >
          属性
        </button>
        <button
          class="flex-1 px-3 py-2 text-sm transition-colors"
          :class="activeTab === middleTabValue ? 'bg-zinc-100 text-zinc-900 font-medium' : 'text-zinc-500 hover:bg-zinc-50'"
          @click="emit('update:active-tab', middleTabValue)"
        >
          {{ middleTabLabel }}
        </button>
        <button
          class="flex-1 px-3 py-2 text-sm transition-colors"
          :class="activeTab === 'execution' ? 'bg-zinc-100 text-zinc-900 font-medium' : 'text-zinc-500 hover:bg-zinc-50'"
          @click="emit('update:active-tab', 'execution')"
        >
          执行
        </button>
      </div>
    </div>

    <ExecutionGraphInspector
      v-if="activeTab === 'inspector'"
      :selected-object="inspectorObject"
      :object-type="objectType"
      @update="emit('update-object', $event)"
    />

    <!-- 节点内容 Tab（仅节点选中时） -->
    <div v-else-if="activeTab === 'node-content' && isNodeSelected" class="flex-1 overflow-y-auto bg-zinc-50">
      <div class="p-4 space-y-4">

        <!-- 任务提示词 -->
        <div class="rounded-lg border border-zinc-200 bg-white p-4 space-y-2">
          <div class="text-sm font-semibold text-zinc-900">任务提示词（task_prompt）</div>
          <div class="text-xs text-zinc-500">描述本节点应完成的任务目标，将注入节点执行上下文。</div>
          <textarea
            v-model="nodeContentForm.task_prompt"
            rows="5"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="描述该拓扑节点应完成的任务目标（注入节点执行上下文）"
          />
        </div>

        <!-- 输入节点选择 -->
        <div class="rounded-lg border border-zinc-200 bg-white p-4 space-y-2">
          <div class="text-sm font-semibold text-zinc-900">输入节点</div>
          <div class="text-xs text-zinc-500">勾选后，这些节点的输出将作为本节点的增量输入上下文。</div>
          <div v-if="availableInputNodes.length === 0" class="text-xs text-zinc-400 py-2">
            当前图中暂无其他节点
          </div>
          <div v-else class="space-y-1 max-h-[240px] overflow-y-auto">
            <label
              v-for="node in availableInputNodes"
              :key="node.node_id"
              class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-zinc-50 transition-colors"
            >
              <input
                type="checkbox"
                :checked="nodeContentForm.input_node_ids.includes(node.node_id)"
                class="rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                @change="toggleInputNode(node.node_id)"
              />
              <span class="text-sm text-zinc-800">{{ node.label }}</span>
              <span class="text-xs text-zinc-400 ml-auto">{{ node.node_type }}</span>
            </label>
          </div>
        </div>

        <!-- 保存按钮 -->
        <button
          class="w-full px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors disabled:bg-zinc-400"
          :disabled="nodeContentSaving"
          @click="handleSaveNodeContent"
        >
          保存节点内容
        </button>
      </div>
    </div>

    <!-- 校验 Tab -->
    <div v-else-if="activeTab === 'validation'" class="flex-1 overflow-y-auto bg-zinc-50">
      <div class="p-4 space-y-4">
        <div class="rounded-lg border border-zinc-200 bg-white p-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-semibold text-zinc-900">拓扑校验</div>
              <div class="text-xs text-zinc-500">先校验，再执行，错误项可点击定位。</div>
            </div>
            <button
              :disabled="validationLoading"
              class="px-3 py-1.5 text-xs text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors disabled:bg-zinc-400"
              @click="emit('validate-topology')"
            >
              {{ validationLoading ? '校验中...' : '重新校验' }}
            </button>
          </div>
        </div>

        <div v-if="!validationResult" class="rounded-lg border border-dashed border-zinc-300 bg-white px-4 py-6 text-center text-sm text-zinc-500">
          还没有校验结果，点击"重新校验"或顶部"校验拓扑"开始。
        </div>

        <div v-else-if="!validationResult.success" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {{ validationResult.error || '校验失败' }}
        </div>

        <template v-else>
          <div class="grid grid-cols-3 gap-3">
            <div class="rounded-lg border border-zinc-200 bg-white p-3">
              <div class="text-[11px] text-zinc-500">状态</div>
              <div class="mt-1 text-sm font-semibold" :class="validationResult.result.is_valid ? 'text-emerald-700' : 'text-red-700'">
                {{ validationResult.result.is_valid ? '通过' : '未通过' }}
              </div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-white p-3">
              <div class="text-[11px] text-zinc-500">错误</div>
              <div class="mt-1 text-sm font-semibold text-red-700">{{ validationResult.result.errors?.length || 0 }}</div>
            </div>
            <div class="rounded-lg border border-zinc-200 bg-white p-3">
              <div class="text-[11px] text-zinc-500">警告</div>
              <div class="mt-1 text-sm font-semibold text-amber-700">{{ validationResult.result.warnings?.length || 0 }}</div>
            </div>
          </div>

          <div v-if="validationItems.length === 0" class="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            当前拓扑没有发现错误或警告，可以继续执行。
          </div>

          <button
            v-for="item in validationItems"
            :key="item.id"
            type="button"
            class="w-full rounded-lg border px-4 py-3 text-left transition-colors"
            :class="item.level === 'error' ? 'border-red-200 bg-red-50 hover:bg-red-100' : 'border-amber-200 bg-amber-50 hover:bg-amber-100'"
            @click="emit('select-validation-item', item)"
          >
            <div class="flex items-start gap-3">
              <AlertTriangle class="w-4 h-4 mt-0.5 shrink-0" :class="item.level === 'error' ? 'text-red-600' : 'text-amber-600'" />
              <div class="min-w-0">
                <div class="text-xs font-semibold" :class="item.level === 'error' ? 'text-red-700' : 'text-amber-700'">
                  {{ item.level === 'error' ? '错误' : '警告' }}
                </div>
                <div class="mt-1 text-sm text-zinc-800 break-words">{{ item.message }}</div>
                <div v-if="item.target" class="mt-2 text-xs text-zinc-500">
                  点击已定位到：{{ item.target.type }} / {{ item.target.label }}
                </div>
              </div>
            </div>
          </button>
        </template>
      </div>
    </div>

    <!-- 执行 Tab -->
    <div v-else class="flex-1 overflow-y-auto bg-zinc-50">
      <div class="p-4 space-y-4">
        <div class="rounded-lg border border-zinc-200 bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-zinc-900">执行结果</div>
              <div class="text-xs text-zinc-500">执行前建议先通过校验。</div>
            </div>
            <button
              class="px-3 py-1.5 text-xs text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors"
              @click="emit('open-execute-dialog')"
            >
              执行拓扑
            </button>
          </div>
        </div>

        <div v-if="executionError" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {{ executionError }}
        </div>

        <div v-if="!executionResult" class="rounded-lg border border-dashed border-zinc-300 bg-white px-4 py-6 text-center text-sm text-zinc-500">
          还没有执行结果。
        </div>

        <div v-else class="space-y-3">
          <div class="rounded-lg border border-zinc-200 bg-white p-4">
            <div class="flex items-center justify-between">
              <span class="text-sm font-semibold text-zinc-900">状态</span>
              <span class="px-2 py-1 rounded text-xs" :class="executionStatusClass">{{ executionResult.status }}</span>
            </div>
            <div v-if="executionResult.runtime_graph?.graph_id" class="mt-3 text-xs text-zinc-500 break-all">
              Runtime Graph ID: {{ executionResult.runtime_graph.graph_id }}
            </div>
          </div>
          <pre class="max-h-[420px] overflow-auto rounded-lg bg-zinc-950 p-4 text-xs text-zinc-100">{{ JSON.stringify(executionResult, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
