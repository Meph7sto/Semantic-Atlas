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
  containers: {
    type: Array,
    required: true
  },
  nodeTypeOptions: {
    type: Array,
    required: true
  },
  submitDisabled: {
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
    <div class="bg-white rounded-lg shadow-xl w-[680px] max-w-[calc(100%-2rem)] max-h-[calc(100%-2rem)] overflow-hidden mx-4 flex flex-col">
      <div class="px-6 py-4 border-b border-zinc-200">
        <h3 class="text-lg font-semibold text-zinc-900">新建节点</h3>
      </div>
      <div class="p-6 space-y-4 overflow-y-auto">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">所属容器</label>
            <select
              :value="form.container_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              @change="updateField('container_id', $event.target.value)"
            >
              <option value="">未分配</option>
              <option v-for="container in containers" :key="container.container_id" :value="container.container_id">
                {{ container.label }} ({{ container.container_key }})
              </option>
            </select>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">节点 Key *</label>
            <input
              :value="form.node_key"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.node_key ? 'border-red-500' : ''"
              placeholder="例如: step1"
              @input="updateField('node_key', $event.target.value)"
            />
            <p v-if="errors.node_key" class="mt-1 text-xs text-red-500">{{ errors.node_key }}</p>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">标签 *</label>
          <input
            :value="form.label"
            type="text"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            :class="errors.label ? 'border-red-500' : ''"
            placeholder="例如: 第一步"
            @input="updateField('label', $event.target.value)"
          />
          <p v-if="errors.label" class="mt-1 text-xs text-red-500">{{ errors.label }}</p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">节点类型</label>
            <select
              :value="form.node_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              @change="updateField('node_type', $event.target.value)"
            >
              <option v-for="opt in nodeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">阶段标签（phase_label）</label>
            <input
              :value="form.phase_label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: fetch_requirements"
              @input="updateField('phase_label', $event.target.value)"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">任务提示词（task_prompt）</label>
          <textarea
            :value="form.task_prompt"
            rows="3"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="描述该拓扑节点应完成的任务目标（将注入节点执行上下文）"
            @input="updateField('task_prompt', $event.target.value)"
          />
        </div>

        <div v-if="form.node_type === 'llm'">
          <label class="block text-sm font-medium text-zinc-700 mb-1">条件出边（conditional_edges）</label>
          <div class="text-xs text-zinc-500 mb-1">阶段完成后根据 route_key 决定走哪条出边，仅 llm 类型节点需要。</div>
          <textarea
            :value="form.conditional_edges"
            rows="3"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder='[{"condition": "pass", "target_node_id": "..."}]'
            @input="updateField('conditional_edges', $event.target.value)"
          />
        </div>



        <div v-if="errors.form" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
          {{ errors.form }}
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
