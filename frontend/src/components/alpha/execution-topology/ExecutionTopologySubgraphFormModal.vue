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
    <div class="bg-white rounded-lg shadow-xl w-[600px] max-w-[calc(100%-2rem)] max-h-[calc(100%-2rem)] overflow-hidden mx-4 flex flex-col">
      <div class="px-6 py-4 border-b border-zinc-200">
        <h3 class="text-lg font-semibold text-zinc-900">新建子图</h3>
      </div>
      <div class="p-6 space-y-4 overflow-y-auto">
        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">所属容器 *</label>
          <select
            :value="form.container_id"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            :class="errors.container_id ? 'border-red-500' : ''"
            @change="updateField('container_id', $event.target.value)"
          >
            <option value="">请选择容器</option>
            <option v-for="container in containers" :key="container.container_id" :value="container.container_id">
              {{ container.label }} ({{ container.container_key }})
            </option>
          </select>
          <p v-if="errors.container_id" class="mt-1 text-xs text-red-500">{{ errors.container_id }}</p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">子图 Key *</label>
            <input
              :value="form.subgraph_key"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.subgraph_key ? 'border-red-500' : ''"
              placeholder="例如: review_subgraph"
              @input="updateField('subgraph_key', $event.target.value)"
            />
            <p v-if="errors.subgraph_key" class="mt-1 text-xs text-red-500">{{ errors.subgraph_key }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">子图名称 *</label>
            <input
              :value="form.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="errors.label ? 'border-red-500' : ''"
              placeholder="例如: 需求评审"
              @input="updateField('label', $event.target.value)"
            />
            <p v-if="errors.label" class="mt-1 text-xs text-red-500">{{ errors.label }}</p>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-zinc-700 mb-1">任务描述 *</label>
          <textarea
            :value="form.task_description"
            rows="4"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            :class="errors.task_description ? 'border-red-500' : ''"
            placeholder="描述该子图的任务目标，将注入 start 节点执行上下文..."
            @input="updateField('task_description', $event.target.value)"
          />
          <p v-if="errors.task_description" class="mt-1 text-xs text-red-500">{{ errors.task_description }}</p>
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
