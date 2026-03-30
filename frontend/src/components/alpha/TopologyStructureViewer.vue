<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  structure: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const showJson = ref(false)
const activeTab = ref('tree') // 'tree' or 'json'

const nodeTypeColors = {
  llm: 'bg-blue-100 text-blue-900',
  invoke: 'bg-cyan-100 text-cyan-900',
  handoff: 'bg-sky-100 text-sky-900'
}

const edgeTypeColors = {
  call: 'bg-purple-100 text-purple-900',
  return: 'bg-green-100 text-green-900',
  retry: 'bg-orange-100 text-orange-900'
}

const formatJson = (data) => {
  return JSON.stringify(data, null, 2)
}

const copyToClipboard = (text) => {
  navigator.clipboard.writeText(text)
}

const normalizedTopology = computed(() => {
  if (!props.structure) return null
  return props.structure.topology || props.structure
})

const downloadJson = () => {
  const data = JSON.stringify(normalizedTopology.value || props.structure, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `topology-${normalizedTopology.value?.graph_id || 'structure'}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const buildTreeData = (structure) => {
  const containerMap = new Map()
  structure.containers?.forEach(container => {
    containerMap.set(container.container_id, container)
  })

  const edgeMap = new Map()
  structure.edges?.forEach(edge => {
    if (!edgeMap.has(edge.source_container_id)) {
      edgeMap.set(edge.source_container_id, [])
    }
    edgeMap.get(edge.source_container_id).push(edge)
  })

  const buildNode = (containerId, level = 0) => {
    const container = containerMap.get(containerId)
    if (!container) return null

    return {
      id: container.container_id,
      key: container.container_key || container.node_key,
      label: container.label,
      role: container.role_type,
      nodeCount: container.node_count || container.nodes?.length || 0,
      nodeTypes: container.node_types || [],
      nodes: container.nodes || [],
      level: level,
      children: (edgeMap.get(containerId) || [])
        .filter(edge => edge.edge_type === 'call')
        .map(edge => buildNode(edge.target_container_id, level + 1))
        .filter(child => child !== null)
    }
  }

  const roots = (structure.start_containers || [])
    .map(id => buildNode(id, 0))
    .filter(node => node !== null)

  return roots
}

const treeData = computed(() => {
  if (!normalizedTopology.value) return []
  return buildTreeData(normalizedTopology.value)
})
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col m-4">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b">
        <h2 class="text-lg font-semibold">拓扑结构预览</h2>
        <button
          @click="emit('close')"
          class="text-gray-500 hover:text-gray-700 transition-colors"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Tab Toggle -->
      <div class="flex border-b">
        <button
          @click="activeTab = 'tree'"
          :class="[
            'flex-1 py-3 px-4 text-sm font-medium transition-colors',
            activeTab === 'tree' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
          ]"
        >
          树状视图
        </button>
        <button
          @click="activeTab = 'json'"
          :class="[
            'flex-1 py-3 px-4 text-sm font-medium transition-colors',
            activeTab === 'json' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-700'
          ]"
        >
          JSON 视图
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-auto p-4">
        <div v-if="loading" class="flex items-center justify-center h-full">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
        </div>

        <div v-else-if="!normalizedTopology" class="text-gray-500 text-center py-8">
          暂无结构数据
        </div>

        <!-- Tree View -->
        <div v-else-if="activeTab === 'tree'" class="space-y-4">
          <div
            v-for="node in treeData"
            :key="node.id"
            class="ml-4"
          >
            <TreeNode :node="node" :depth="0" />
          </div>
        </div>

        <!-- JSON View -->
        <div v-else-if="activeTab === 'json'" class="space-y-4">
          <div class="bg-gray-50 rounded-lg p-4">
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-sm font-medium text-gray-700">导出 JSON</h3>
              <div class="flex gap-2">
                <button
                  @click="copyToClipboard(formatJson(normalizedTopology))"
                  class="inline-flex items-center px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                  <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l-3-3m3 3l3-3m-9-9v14" />
                  </svg>
                  复制
                </button>
                <button
                  @click="downloadJson()"
                  class="inline-flex items-center px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 transition-colors"
                >
                  <svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 013-3h1m-7 0a3 3 0 013 3v1a3 3 0 01-3h-1m7 3a3 3 0 01-3h1v-3a3 3 0 013 3h-1M14 7v7a3 3 0 013-3h-1m7 0a3 3 0 013 3v-7a3 3 0 01-3h-1m-7 3a3 3 0 01-3h-1z" />
                  </svg>
                  下载
                </button>
              </div>
            </div>

            <!-- Summary Section -->
            <div class="bg-white border rounded-lg p-4 mb-4">
              <h3 class="text-sm font-medium text-gray-700 mb-3">结构概览</h3>
              <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span class="text-gray-500">图 ID:</span>
                  <span class="font-mono ml-2">{{ normalizedTopology?.graph_id }}</span>
                </div>
                <div>
                  <span class="text-gray-500">图名称:</span>
                  <span class="ml-2">{{ normalizedTopology?.graph_name }}</span>
                </div>
                <div>
                  <span class="text-gray-500">容器数量:</span>
                  <span class="ml-2">{{ normalizedTopology?.containers?.length || 0 }}</span>
                </div>
                <div>
                  <span class="text-gray-500">边数量:</span>
                  <span class="ml-2">{{ normalizedTopology?.edges?.length || 0 }}</span>
                </div>
                <div>
                  <span class="text-gray-500">入口容器:</span>
                  <span class="ml-2">{{ normalizedTopology?.start_containers?.length || 0 }}</span>
                </div>
                <div>
                  <span class="text-gray-500">出口容器:</span>
                  <span class="ml-2">{{ normalizedTopology?.end_containers?.length || 0 }}</span>
                </div>
              </div>
            </div>

            <!-- Validation Status -->
            <div
              :class="[
                'border rounded-lg p-4',
                normalizedTopology?.validation_status === 'valid' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
              ]"
            >
              <h3 class="text-sm font-medium mb-2">
                验证状态:
                <span :class="[
                  'ml-2',
                  normalizedTopology?.validation_status === 'valid' ? 'text-green-700' : 'text-red-700'
                ]">
                  {{ normalizedTopology?.validation_status === 'valid' ? '有效' : '无效' }}
                </span>
              </h3>
              <ul v-if="normalizedTopology?.validation_errors?.length" class="list-disc list-inside text-sm text-red-600 space-y-1">
                <li v-for="error in normalizedTopology.validation_errors" :key="error">
                  {{ error }}
                </li>
              </ul>
              <p v-else class="text-sm text-green-600">拓扑结构验证通过</p>
            </div>

            <!-- JSON Content -->
            <div class="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
              <pre class="text-sm">{{ formatJson(normalizedTopology) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// TreeNode subcomponent
const TreeNode = {
  props: ['node', 'depth'],
  template: `
    <div class="flex items-start">
      <div
        class="px-3 py-2 rounded text-sm border bg-slate-50 text-slate-900"
        :style="{ marginLeft: depth * 16 + 'px' }"
      >
        <span class="font-semibold">[容器] {{ node.label }}</span>
        <span class="text-xs ml-2 opacity-75">({{ node.key }})</span>
        <span class="text-xs ml-2 text-slate-600">role={{ node.role }}</span>
        <span class="text-xs ml-2 text-slate-600">nodes={{ node.nodeCount }}</span>
        <div v-if="node.nodes?.length" class="text-xs text-slate-600 mt-1">
          {{ node.nodes.map(n => n.label || n.node_key).join(' | ') }}
        </div>
      </div>
      <div v-if="node.children?.length > 0" class="ml-4 border-l border-gray-300">
        <TreeNode
          v-for="child in node.children"
          :key="child.id"
          :node="child"
          :depth="depth + 1"
        />
      </div>
    </div>
  `
}
</script>
