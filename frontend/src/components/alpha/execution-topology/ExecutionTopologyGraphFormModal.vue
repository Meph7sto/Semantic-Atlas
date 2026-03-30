<script setup>
const props = defineProps({
  form: {
    type: Object,
    required: true
  },
  errors: {
    type: Object,
    required: true
  },
  submitDisabled: {
    type: Boolean,
    required: true
  },
  agentTypeOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:form', 'close', 'submit'])

const updateField = (field, value) => {
  emit('update:form', { ...props.form, [field]: value })
}
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg shadow-xl w-96 max-w-full mx-4">
      <div class="px-6 py-4 border-b border-zinc-200">
        <h3 class="text-lg font-semibold text-zinc-900">新建执行拓扑图</h3>
      </div>
      <div class="p-6 space-y-4">
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">名称 *</label>
          <input
            :value="form.name"
            type="text"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            :class="errors.name ? 'border-red-500' : ''"
            placeholder="输入图名称"
            @input="updateField('name', $event.target.value)"
          />
          <p v-if="errors.name" class="mt-1 text-xs text-red-500">{{ errors.name }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">描述</label>
          <textarea
            :value="form.description"
            rows="3"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="输入图描述"
            @input="updateField('description', $event.target.value)"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">关联 Agent（可选）</label>
          <select
            :value="form.agentType"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="updateField('agentType', $event.target.value)"
          >
            <option v-for="opt in agentTypeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
          <p class="mt-1 text-xs text-zinc-400">关联后该图将作为指定 Agent 的执行模板</p>
        </div>
      </div>
      <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
        <button
          class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          @click="emit('close')"
        >
          取消
        </button>
        <button
          :disabled="submitDisabled"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          @click="emit('submit')"
        >
          创建
        </button>
      </div>
    </div>
  </div>
</template>
