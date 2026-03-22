<script setup>
import { ref } from 'vue'
import { Download, Plus, Trash2, Upload } from 'lucide-vue-next'

defineProps({
  projects: {
    type: Array,
    required: true
  },
  selectedProjectId: {
    type: String,
    required: true
  },
  graphs: {
    type: Array,
    required: true
  },
  selectedGraphId: {
    type: String,
    required: true
  },
  graphDetail: {
    type: Object,
    required: true
  },
  selectedObject: {
    type: Object,
    required: true
  },
  nodesByContainer: {
    type: Object,
    required: true
  }
})

const emit = defineEmits([
  'project-change',
  'create-graph',
  'select-graph',
  'delete-graph',
  'create-container',
  'select-object',
  'delete-container',
  'create-node',
  'assign-node-container',
  'delete-node',
  'create-edge',
  'delete-edge',
  'export-template',
  'import-template'
])

const importFileInput = ref(null)

const triggerImport = () => {
  importFileInput.value?.click()
}

const onFileSelected = (event) => {
  const file = event.target.files?.[0]
  if (file) {
    emit('import-template', file)
  }
  // 重置以允许再次选择相同文件
  event.target.value = ''
}

const emitObjectSelection = (type, id) => {
  emit('select-object', { type, id })
}
</script>

<template>
  <div class="w-72 flex flex-col border-r border-zinc-200 bg-white overflow-hidden">
    <div class="px-4 py-3 border-b border-zinc-200">
      <label class="block text-xs font-medium text-zinc-700 mb-1">选择项目</label>
      <select
        :value="selectedProjectId"
        class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        @change="emit('project-change', $event.target.value)"
      >
        <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
          {{ project.name }}
        </option>
      </select>
    </div>

    <div class="flex-1 flex flex-col overflow-hidden">
      <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-zinc-900">执行拓扑图</h3>
        <div class="flex items-center gap-1">
          <button
            :disabled="!selectedProjectId"
            class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title="导入模板"
            @click="triggerImport"
          >
            <Upload class="w-4 h-4" />
          </button>
          <input
            ref="importFileInput"
            type="file"
            accept=".json,.satpl.json"
            class="hidden"
            @change="onFileSelected"
          />
          <button
            :disabled="!selectedProjectId"
            class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title="新建图"
            @click="emit('create-graph')"
          >
            <Plus class="w-4 h-4" />
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2">
        <div
          v-for="graph in graphs"
          :key="graph.graph_id"
          class="mb-2 p-3 border rounded-lg cursor-pointer transition-all"
          :class="selectedGraphId === graph.graph_id ? 'border-blue-500 bg-blue-50' : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'"
          @click="emit('select-graph', graph)"
        >
          <div class="flex items-center justify-between mb-1 gap-2">
            <span class="text-sm font-medium text-zinc-900 truncate">{{ graph.name }}</span>
            <div class="flex items-center gap-0.5">
              <button
                v-if="selectedGraphId === graph.graph_id"
                class="p-1 text-zinc-400 hover:text-blue-500 transition-colors"
                title="导出模板"
                @click.stop="emit('export-template')"
              >
                <Download class="w-4 h-4" />
              </button>
              <button
                class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                title="删除"
                @click.stop="emit('delete-graph', graph.graph_id)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-zinc-500 truncate">{{ graph.description || '无描述' }}</span>
            <div class="flex items-center gap-1">
              <span
                v-if="graph.meta_json?.agent_type"
                class="shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium"
                :class="graph.meta_json.agent_type === 'requirement_agent'
                  ? 'bg-blue-100 text-blue-700'
                  : graph.meta_json.agent_type === 'conflict_detection_agent'
                    ? 'bg-orange-100 text-orange-700'
                    : 'bg-zinc-100 text-zinc-600'"
                :title="graph.meta_json.agent_type"
              >
                {{
                  graph.meta_json.agent_type === 'requirement_agent' ? '需求'
                  : graph.meta_json.agent_type === 'conflict_detection_agent' ? '冲突'
                  : graph.meta_json.agent_type
                }}
              </span>
              <span class="text-[11px] px-2 py-0.5 rounded bg-zinc-100 text-zinc-600">{{ graph.status }}</span>
            </div>
          </div>
        </div>

        <div v-if="graphs.length === 0" class="text-center py-8 text-zinc-400">
          <p class="text-sm">暂无执行拓扑图</p>
          <p class="text-xs mt-1">点击上方 + 按钮创建新图</p>
        </div>
      </div>
    </div>

    <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
      <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-zinc-900">容器</h3>
        <button
          class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
          title="新建容器"
          @click="emit('create-container')"
        >
          <Plus class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2 max-h-44">
        <div
          v-for="container in graphDetail.containers"
          :key="container.container_id"
          class="mb-1 p-2 border rounded flex items-center justify-between gap-2 cursor-pointer"
          :class="selectedObject.type === 'container' && selectedObject.id === container.container_id ? 'border-blue-500 bg-blue-50' : 'border-zinc-200'"
          @click="emitObjectSelection('container', container.container_id)"
        >
          <div class="flex-1 min-w-0">
            <div class="text-xs font-medium text-zinc-900">{{ container.label }}</div>
            <div class="text-[11px] text-zinc-500">{{ container.container_key }} · {{ container.role_type }}</div>
          </div>
          <button
            class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
            title="删除容器"
            @click.stop="emit('delete-container', container.container_id)"
          >
            <Trash2 class="w-3 h-3" />
          </button>
        </div>

        <div v-if="graphDetail.containers.length === 0" class="text-center py-4 text-zinc-400">
          <p class="text-xs">暂无容器</p>
        </div>
      </div>
    </div>

    <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
      <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-zinc-900">节点</h3>
        <button
          class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
          title="新建节点"
          @click="emit('create-node')"
        >
          <Plus class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2 max-h-56">
        <div v-for="container in graphDetail.containers" :key="`group-${container.container_id}`" class="mb-2">
          <div class="px-1 py-1 text-[11px] font-semibold text-zinc-500">{{ container.label }}</div>
          <div
            v-for="node in nodesByContainer.groups[container.container_id] || []"
            :key="node.node_id"
            class="mb-1 p-2 border rounded cursor-pointer"
            :class="selectedObject.type === 'node' && selectedObject.id === node.node_id ? 'border-blue-500 bg-blue-50' : 'border-zinc-200 hover:border-zinc-300'"
            @click="emitObjectSelection('node', node.node_id)"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="text-xs font-medium text-zinc-900 truncate">{{ node.label }}</div>
                <div class="text-xs text-zinc-500">{{ node.node_type }}</div>
              </div>
              <button
                class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                title="删除"
                @click.stop="emit('delete-node', node.node_id)"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
            <select
              :value="node.container_id || ''"
              class="mt-1 w-full px-2 py-1 border border-zinc-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
              @change="emit('assign-node-container', node.node_id, $event.target.value)"
            >
              <option value="">未分配</option>
              <option v-for="opt in graphDetail.containers" :key="opt.container_id" :value="opt.container_id">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div v-if="nodesByContainer.unassigned.length" class="mb-2">
          <div class="px-1 py-1 text-[11px] font-semibold text-zinc-500">未分配</div>
          <div
            v-for="node in nodesByContainer.unassigned"
            :key="`unassigned-${node.node_id}`"
            class="mb-1 p-2 border rounded cursor-pointer"
            :class="selectedObject.type === 'node' && selectedObject.id === node.node_id ? 'border-blue-500 bg-blue-50' : 'border-zinc-200 hover:border-zinc-300'"
            @click="emitObjectSelection('node', node.node_id)"
          >
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="text-xs font-medium text-zinc-900 truncate">{{ node.label }}</div>
                <div class="text-xs text-zinc-500">{{ node.node_type }}</div>
              </div>
              <button
                class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                title="删除"
                @click.stop="emit('delete-node', node.node_id)"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
            <select
              :value="node.container_id || ''"
              class="mt-1 w-full px-2 py-1 border border-zinc-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
              @change="emit('assign-node-container', node.node_id, $event.target.value)"
            >
              <option value="">未分配</option>
              <option v-for="opt in graphDetail.containers" :key="opt.container_id" :value="opt.container_id">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div v-if="graphDetail.nodes.length === 0" class="text-center py-4 text-zinc-400">
          <p class="text-xs">暂无节点</p>
        </div>
      </div>
    </div>

    <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
      <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-zinc-900">边</h3>
        <button
          class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
          title="新建边"
          @click="emit('create-edge')"
        >
          <Plus class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2">
        <div
          v-for="edge in graphDetail.edges"
          :key="edge.edge_id"
          class="mb-1 p-2 border rounded cursor-pointer flex items-center justify-between gap-2"
          :class="selectedObject.type === 'edge' && selectedObject.id === edge.edge_id ? 'border-blue-500 bg-blue-50' : 'border-zinc-200 hover:border-zinc-300'"
          @click="emitObjectSelection('edge', edge.edge_id)"
        >
          <div class="flex-1 min-w-0">
            <div class="text-xs font-medium text-zinc-900">{{ edge.label || edge.edge_type }}</div>
            <div class="text-xs text-zinc-500">{{ edge.edge_type }}</div>
          </div>
          <button
            class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
            title="删除"
            @click.stop="emit('delete-edge', edge.edge_id)"
          >
            <Trash2 class="w-3 h-3" />
          </button>
        </div>

        <div v-if="graphDetail.edges.length === 0" class="text-center py-4 text-zinc-400">
          <p class="text-xs">暂无边</p>
        </div>
      </div>
    </div>
  </div>
</template>
