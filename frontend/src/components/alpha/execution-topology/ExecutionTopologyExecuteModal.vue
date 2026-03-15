<script setup>
const props = defineProps({
  form: {
    type: Object,
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
  },
  executionLoading: {
    type: Boolean,
    required: true
  }
})

const emit = defineEmits(['update:form', 'close', 'submit'])

const updateField = (field, value) => {
  emit('update:form', { ...props.form, [field]: value })
}
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg shadow-xl w-[720px] max-w-[calc(100%-2rem)] max-h-[calc(100%-2rem)] overflow-hidden flex flex-col">
      <div class="px-6 py-4 border-b border-zinc-200 flex items-center justify-between">
        <h3 class="text-lg font-semibold text-zinc-900">执行拓扑模板</h3>
        <span class="text-xs text-zinc-500">创建运行时图并按拓扑推进</span>
      </div>
      <div class="p-6 space-y-4 overflow-y-auto">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">运行时图名称</label>
            <input
              :value="form.runtimeGraphName"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="可选，默认基于模板名称生成"
              @input="updateField('runtimeGraphName', $event.target.value)"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">最大步数</label>
            <input
              :value="form.maxSteps"
              type="number"
              min="1"
              max="1000"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              @input="updateField('maxSteps', Number($event.target.value))"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">运行时图描述</label>
          <input
            :value="form.runtimeGraphDescription"
            type="text"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="可选"
            @input="updateField('runtimeGraphDescription', $event.target.value)"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">输入 Payload(JSON 对象)</label>
          <textarea
            :value="form.inputPayload"
            rows="8"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder='{"message":"run topology"}'
            @input="updateField('inputPayload', $event.target.value)"
          />
        </div>

        <div v-if="executionError" class="px-3 py-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
          {{ executionError }}
        </div>

        <div v-if="executionResult" class="space-y-2">
          <div class="flex items-center gap-3 text-sm">
            <span class="font-medium text-zinc-900">执行结果</span>
            <span class="px-2 py-1 rounded text-xs" :class="executionStatusClass">{{ executionResult.status }}</span>
            <span v-if="executionResult.runtime_graph?.graph_id" class="text-xs text-zinc-500">{{ executionResult.runtime_graph.graph_id }}</span>
          </div>
          <pre class="max-h-80 overflow-auto rounded-lg bg-zinc-950 p-4 text-xs text-zinc-100">{{ JSON.stringify(executionResult, null, 2) }}</pre>
        </div>
      </div>
      <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
        <button
          class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          @click="emit('close')"
        >
          关闭
        </button>
        <button
          :disabled="executionLoading"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          @click="emit('submit')"
        >
          {{ executionLoading ? '执行中...' : '开始执行' }}
        </button>
      </div>
    </div>
  </div>
</template>
