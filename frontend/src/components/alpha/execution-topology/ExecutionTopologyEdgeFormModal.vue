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
  nodes: {
    type: Array,
    required: true
  },
  edgeTypeOptions: {
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
    <div class="bg-white rounded-lg shadow-xl w-[560px] max-w-[calc(100%-2rem)] mx-4">
      <div class="px-6 py-4 border-b border-zinc-200">
        <h3 class="text-lg font-semibold text-zinc-900">新建边</h3>
      </div>
      <div class="p-6 space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">源节点 *</label>
            <select
              :value="form.source_node_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.source_node_id ? 'border-red-500' : ''"
              @change="updateField('source_node_id', $event.target.value)"
            >
              <option value="">选择源节点</option>
              <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                {{ node.label }} ({{ node.node_key }})
              </option>
            </select>
            <p v-if="errors.source_node_id" class="mt-1 text-xs text-red-500">{{ errors.source_node_id }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">目标节点 *</label>
            <select
              :value="form.target_node_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.target_node_id ? 'border-red-500' : ''"
              @change="updateField('target_node_id', $event.target.value)"
            >
              <option value="">选择目标节点</option>
              <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">
                {{ node.label }} ({{ node.node_key }})
              </option>
            </select>
            <p v-if="errors.target_node_id" class="mt-1 text-xs text-red-500">{{ errors.target_node_id }}</p>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">边类型</label>
            <select
              :value="form.edge_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              @change="updateField('edge_type', $event.target.value)"
            >
              <option v-for="opt in edgeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">排序</label>
            <input
              :value="form.order_index"
              type="number"
              min="0"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.order_index ? 'border-red-500' : ''"
              @input="updateField('order_index', Number($event.target.value))"
            />
            <p v-if="errors.order_index" class="mt-1 text-xs text-red-500">{{ errors.order_index }}</p>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">标签</label>
          <input
            :value="form.label"
            type="text"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="输入边标签"
            @input="updateField('label', $event.target.value)"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">条件表达式</label>
          <textarea
            :value="form.condition_expr"
            rows="3"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="review_required == true"
            @input="updateField('condition_expr', $event.target.value)"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">配置 JSON</label>
          <textarea
            :value="form.config_json"
            rows="5"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder='{"priority": 1}'
            @input="updateField('config_json', $event.target.value)"
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
