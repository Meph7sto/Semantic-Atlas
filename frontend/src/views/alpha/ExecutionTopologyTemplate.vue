<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { executionGraphApi } from '@/api/executionGraph'
import { manageApi } from '@/api/project'
import { Plus, RefreshCw, Trash2, Eye } from 'lucide-vue-next'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'
import ExecutionGraphInspector from '@/components/alpha/ExecutionGraphInspector.vue'
import TopologyStructureViewer from '@/components/alpha/TopologyStructureViewer.vue'

// 状态
const projects = ref([])
const selectedProjectId = ref('')
const graphs = ref([])
const selectedGraphId = ref('')

const graphDetail = ref({
  graph: null,
  containers: [],
  nodes: [],
  edges: []
})

const selectedObject = ref({
  type: 'graph', // 'graph' | 'node' | 'edge'
  id: null
})

// 加载状态
const loading = ref(false)
const error = ref('')

// 新建对话框状态
const showNewGraphDialog = ref(false)
const newGraphForm = ref({
  name: '',
  description: ''
})

// 新建节点对话框状态
const showNewNodeDialog = ref(false)
const showNewContainerDialog = ref(false)
const newContainerForm = ref({
  container_key: '',
  label: '',
  role_type: 'agent'
})

const newNodeForm = ref({
  container_id: '',
  node_key: '',
  label: '',
  node_type: 'node',
  role_type: 'human'
})

// 新建边对话框状态
const showNewEdgeDialog = ref(false)
const newEdgeForm = ref({
  source_node_id: '',
  target_node_id: '',
  edge_type: 'call',
  label: '',
  condition_expr: ''
})

// 拓扑结构查看器状态
const showStructureViewer = ref(false)
const structureData = ref(null)
const structureLoading = ref(false)
const structureError = ref('')

// 节点类型选项
const nodeTypeOptions = [
  { value: 'start', label: 'Start' },
  { value: 'node', label: 'Node' },
  { value: 'decision', label: 'Decision' },
  { value: 'handoff', label: 'Handoff' },
  { value: 'end', label: 'End' }
]

// 角色类型选项
const roleTypeOptions = [
  { value: 'human', label: 'Human' },
  { value: 'agent', label: 'Agent' },
  { value: 'system', label: 'System' }
]

// 边类型选项
const edgeTypeOptions = [
  { value: 'call', label: 'Call' },
  { value: 'return', label: 'Return' },
  { value: 'retry', label: 'Retry' }
]

const getErrorMessage = (err, fallback) => {
  return err?.response?.data?.detail || err?.response?.data?.error || err?.response?.data?.message || err?.message || fallback
}

// 获取当前选中的图
const currentGraph = ref(null)

// 计算属性
const selectedCanvasId = computed(() => {
  if (selectedObject.value.type === 'node' || selectedObject.value.type === 'edge') {
    return selectedObject.value.id
  }
  return null
})

const selectedGraphData = computed(() => {
  if (selectedObject.value.type === 'graph') {
    return graphDetail.value.graph
  }
  return null
})

const selectedNodeData = computed(() => {
  if (selectedObject.value.type === 'node') {
    return graphDetail.value.nodes.find(n => n.node_id === selectedObject.value.id)
  }
  return null
})

const selectedEdgeData = computed(() => {
  if (selectedObject.value.type === 'edge') {
    return graphDetail.value.edges.find(e => e.edge_id === selectedObject.value.id)
  }
  return null
})

const nodesByContainer = computed(() => {
  const groups = {}
  const unassigned = []
  const containers = graphDetail.value.containers || []
  const nodes = graphDetail.value.nodes || []

  containers.forEach((container) => {
    groups[container.container_id] = []
  })
  nodes.forEach((node) => {
    const cid = node.container_id
    if (cid && groups[cid]) {
      groups[cid].push(node)
    } else {
      unassigned.push(node)
    }
  })
  return { groups, unassigned }
})

// 加载项目列表
const loadProjects = async () => {
  try {
    loading.value = true
    const data = await manageApi.listProjects()
    const projectList = data?.projects || []
    projects.value = projectList

    if (projectList.length > 0 && !selectedProjectId.value) {
      selectedProjectId.value = projectList[0].project_id
    }
  } catch (err) {
    error.value = getErrorMessage(err, '加载项目列表失败')
  } finally {
    loading.value = false
  }
}

// 加载图列表
const loadGraphs = async () => {
  if (!selectedProjectId.value) return

  try {
    loading.value = true
    graphs.value = await executionGraphApi.listGraphs(selectedProjectId.value)
  } catch (err) {
    error.value = getErrorMessage(err, '加载图列表失败')
  } finally {
    loading.value = false
  }
}

// 加载图详情
const loadGraphDetail = async (graphId) => {
  if (!graphId) return

  try {
    loading.value = true
    error.value = ''
    graphDetail.value = await executionGraphApi.getGraphDetail(graphId)
    currentGraph.value = graphDetail.value.graph
  } catch (err) {
    error.value = getErrorMessage(err, '加载图详情失败')
    graphDetail.value = { graph: null, containers: [], nodes: [], edges: [] }
  } finally {
    loading.value = false
  }
}

// 选择图
const handleSelectGraph = (graph) => {
  selectedGraphId.value = graph.graph_id
  loadGraphDetail(graph.graph_id)
  // 重置选中对象
  selectedObject.value = { type: 'graph', id: graph.graph_id }
}

// 创建新图
const handleCreateGraph = async () => {
  if (!selectedProjectId.value) {
    error.value = '请先选择项目'
    return
  }

  try {
    loading.value = true
    error.value = ''

    const graph = await executionGraphApi.createGraph(selectedProjectId.value, {
      name: newGraphForm.value.name,
      description: newGraphForm.value.description
    })

    graphs.value.unshift(graph)
    showNewGraphDialog.value = false
    newGraphForm.value = { name: '', description: '' }

    // 选择新创建的图
    handleSelectGraph(graph)
  } catch (err) {
    error.value = getErrorMessage(err, '创建图失败')
  } finally {
    loading.value = false
  }
}

// 创建新容器
const handleCreateContainer = async () => {
  if (!selectedGraphId.value) {
    error.value = '请先选择一个图'
    return
  }

  try {
    loading.value = true
    error.value = ''
    const container = await executionGraphApi.createContainer(selectedGraphId.value, newContainerForm.value)
    graphDetail.value.containers.push(container)
    showNewContainerDialog.value = false
    newContainerForm.value = {
      container_key: '',
      label: '',
      role_type: 'agent'
    }
  } catch (err) {
    error.value = getErrorMessage(err, '创建容器失败')
  } finally {
    loading.value = false
  }
}

// 创建新节点
const handleCreateNode = async () => {
  if (!selectedGraphId.value) {
    error.value = '请先选择一个图'
    return
  }

  try {
    loading.value = true
    error.value = ''

    const payload = {
      ...newNodeForm.value,
      container_id: newNodeForm.value.container_id || null
    }
    const node = await executionGraphApi.createNode(selectedGraphId.value, payload)

    graphDetail.value.nodes.push(node)
    showNewNodeDialog.value = false
    newNodeForm.value = {
      container_id: '',
      node_key: '',
      label: '',
      node_type: 'node',
      role_type: 'human'
    }
  } catch (err) {
    error.value = getErrorMessage(err, '创建节点失败')
  } finally {
    loading.value = false
  }
}

// 创建新边
const handleCreateEdge = async () => {
  if (!selectedGraphId.value) {
    error.value = '请先选择一个图'
    return
  }

  try {
    loading.value = true
    error.value = ''

    const edge = await executionGraphApi.createEdge(selectedGraphId.value, newEdgeForm.value)

    graphDetail.value.edges.push(edge)
    showNewEdgeDialog.value = false
    newEdgeForm.value = {
      source_node_id: '',
      target_node_id: '',
      edge_type: 'call',
      label: '',
      condition_expr: ''
    }
  } catch (err) {
    error.value = getErrorMessage(err, '创建边失败')
  } finally {
    loading.value = false
  }
}

const handleAssignNodeContainer = async (nodeId, containerId) => {
  try {
    loading.value = true
    error.value = ''
    const updated = await executionGraphApi.updateNode(nodeId, {
      container_id: containerId || ''
    })
    const idx = graphDetail.value.nodes.findIndex(n => n.node_id === nodeId)
    if (idx !== -1) {
      graphDetail.value.nodes[idx] = updated
    }
  } catch (err) {
    error.value = getErrorMessage(err, '调整节点归属失败')
  } finally {
    loading.value = false
  }
}

const handleDeleteContainer = async (containerId) => {
  if (!confirm('确定要删除此容器吗？删除后节点会变为未分配。')) return
  try {
    loading.value = true
    error.value = ''
    await executionGraphApi.deleteContainer(containerId)
    graphDetail.value.containers = graphDetail.value.containers.filter(c => c.container_id !== containerId)
    graphDetail.value.nodes = graphDetail.value.nodes.map((node) => (
      node.container_id === containerId ? { ...node, container_id: null } : node
    ))
  } catch (err) {
    error.value = getErrorMessage(err, '删除容器失败')
  } finally {
    loading.value = false
  }
}

// 删除节点
const handleDeleteNode = async (nodeId) => {
  if (!confirm('确定要删除此节点吗？')) return

  try {
    loading.value = true
    error.value = ''

    await executionGraphApi.deleteNode(nodeId)

    // 从列表中移除节点及其相关边
    graphDetail.value.nodes = graphDetail.value.nodes.filter(n => n.node_id !== nodeId)
    graphDetail.value.edges = graphDetail.value.edges.filter(e =>
      e.source_node_id !== nodeId && e.target_node_id !== nodeId
    )

    // 重置选中状态
    if (selectedObject.value.type === 'node' && selectedObject.value.id === nodeId) {
      selectedObject.value = { type: 'graph', id: selectedGraphId.value }
    }
  } catch (err) {
    error.value = getErrorMessage(err, '删除节点失败')
  } finally {
    loading.value = false
  }
}

// 删除边
const handleDeleteEdge = async (edgeId) => {
  if (!confirm('确定要删除此边吗？')) return

  try {
    loading.value = true
    error.value = ''

    await executionGraphApi.deleteEdge(edgeId)

    // 从列表中移除边
    graphDetail.value.edges = graphDetail.value.edges.filter(e => e.edge_id !== edgeId)

    // 重置选中状态
    if (selectedObject.value.type === 'edge' && selectedObject.value.id === edgeId) {
      selectedObject.value = { type: 'graph', id: selectedGraphId.value }
    }
  } catch (err) {
    error.value = getErrorMessage(err, '删除边失败')
  } finally {
    loading.value = false
  }
}

// 删除图
const handleDeleteGraph = async (graphId) => {
  if (!confirm('确定要删除此图吗？')) return

  try {
    loading.value = true
    error.value = ''

    await executionGraphApi.deleteGraph(graphId)

    // 从列表中移除
    graphs.value = graphs.value.filter(g => g.graph_id !== graphId)

    // 如果删除的是当前图，清空详情
    if (selectedGraphId.value === graphId) {
      selectedGraphId.value = ''
      graphDetail.value = { graph: null, containers: [], nodes: [], edges: [] }
      selectedObject.value = { type: 'graph', id: null }
      currentGraph.value = null
    }
  } catch (err) {
    error.value = getErrorMessage(err, '删除图失败')
  } finally {
    loading.value = false
  }
}

// 更新对象
const handleUpdateObject = async (data) => {
  try {
    loading.value = true
    error.value = ''

    if (selectedObject.value.type === 'graph') {
      const updated = await executionGraphApi.updateGraph(selectedObject.value.id, data)
      currentGraph.value = updated
      graphDetail.value.graph = updated
    } else if (selectedObject.value.type === 'node') {
      const updated = await executionGraphApi.updateNode(selectedObject.value.id, data)
      // 更新节点列表中的节点
      const index = graphDetail.value.nodes.findIndex(n => n.node_id === selectedObject.value.id)
      if (index !== -1) {
        graphDetail.value.nodes[index] = updated
      }
    } else if (selectedObject.value.type === 'edge') {
      const updated = await executionGraphApi.updateEdge(selectedObject.value.id, data)
      // 更新边列表中的边
      const index = graphDetail.value.edges.findIndex(e => e.edge_id === selectedObject.value.id)
      if (index !== -1) {
        graphDetail.value.edges[index] = updated
      }
    }
  } catch (err) {
    error.value = getErrorMessage(err, '更新失败')
  } finally {
    loading.value = false
  }
}

// 选择节点
const handleSelectNode = (nodeId) => {
  selectedObject.value = { type: 'node', id: nodeId }
}

const handleSelectEdge = (edgeId) => {
  selectedObject.value = { type: 'edge', id: edgeId }
}

let layoutSaveTimer = null

const handleCanvasLayoutChange = (layoutPatch) => {
  if (!selectedGraphId.value || !graphDetail.value.graph) return

  const nextLayout = {
    ...(graphDetail.value.graph.layout_json || {}),
    ...(layoutPatch || {})
  }

  graphDetail.value.graph = {
    ...graphDetail.value.graph,
    layout_json: nextLayout
  }
  currentGraph.value = {
    ...(currentGraph.value || {}),
    layout_json: nextLayout
  }

  if (layoutSaveTimer) clearTimeout(layoutSaveTimer)
  const graphId = selectedGraphId.value
  layoutSaveTimer = setTimeout(async () => {
    try {
      const updated = await executionGraphApi.updateGraph(graphId, {
        layout_json: nextLayout
      })
      if (selectedGraphId.value === graphId) {
        graphDetail.value.graph = updated
        currentGraph.value = updated
      }
    } catch (err) {
      error.value = getErrorMessage(err, '保存画布布局失败')
    }
  }, 450)
}

// 选择图
const handleSelectGraphObject = () => {
  if (selectedGraphId.value) {
    selectedObject.value = { type: 'graph', id: selectedGraphId.value }
  }
}

// 刷新
const handleRefresh = () => {
  if (selectedGraphId.value) {
    loadGraphDetail(selectedGraphId.value)
  } else {
    loadGraphs()
  }
}

// 查看拓扑结构
const handleViewStructure = async () => {
  if (!selectedGraphId.value) {
    error.value = '请先选择一个图'
    return
  }

  try {
    structureLoading.value = true
    structureError.value = ''
    error.value = ''

    // 调用后端 API 获取拓扑结构
    const data = await executionGraphApi.getTopologyStructure(selectedGraphId.value)

    if (data.success) {
      structureData.value = data.structure
      showStructureViewer.value = true
    } else {
      structureError.value = data.error || '获取拓扑结构失败'
      error.value = data.error || '获取拓扑结构失败'
    }
  } catch (err) {
    const message = getErrorMessage(err, '获取拓扑结构失败')
    structureError.value = message
    error.value = message
  } finally {
    structureLoading.value = false
  }
}

// 关闭结构查看器
const handleCloseStructureViewer = () => {
  showStructureViewer.value = false
  structureData.value = null
  structureError.value = ''
}

// 页面加载时初始化
onMounted(async () => {
  await loadProjects()
  await loadGraphs()
})

onBeforeUnmount(() => {
  if (layoutSaveTimer) {
    clearTimeout(layoutSaveTimer)
    layoutSaveTimer = null
  }
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-100">
    <!-- 错误提示 -->
    <div v-if="error" class="px-4 py-2 bg-red-50 border-b border-red-200">
      <p class="text-sm text-red-600">{{ error }}</p>
    </div>

    <!-- 主内容区：三栏布局 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧：图列表、节点列表、边列表 -->
      <div class="w-72 flex flex-col border-r border-zinc-200 bg-white overflow-hidden">
        <!-- 项目选择 -->
        <div class="px-4 py-3 border-b border-zinc-200">
          <label class="block text-xs font-medium text-zinc-700 mb-1">选择项目</label>
          <select
            v-model="selectedProjectId"
            class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadGraphs"
          >
            <option v-for="project in projects" :key="project.project_id" :value="project.project_id">
              {{ project.name }}
            </option>
          </select>
        </div>

        <!-- 图列表 -->
        <div class="flex-1 flex flex-col overflow-hidden">
          <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900">执行拓扑图</h3>
            <button
              @click="showNewGraphDialog = true"
              :disabled="!selectedProjectId"
              class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-zinc-500"
              title="新建图"
            >
              <Plus class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto px-2 py-2">
            <div
              v-for="graph in graphs"
              :key="graph.graph_id"
              class="mb-2 p-3 border rounded-lg cursor-pointer transition-all"
              :class="[
                selectedGraphId === graph.graph_id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50'
              ]"
              @click="handleSelectGraph(graph)"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-medium text-zinc-900">{{ graph.name }}</span>
                <button
                  @click.stop="handleDeleteGraph(graph.graph_id)"
                  class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                  title="删除"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
              <span class="text-xs text-zinc-500 truncate">{{ graph.description || '无描述' }}</span>
            </div>

            <div v-if="graphs.length === 0" class="text-center py-8 text-zinc-400">
              <p class="text-sm">暂无执行拓扑图</p>
              <p class="text-xs mt-1">点击上方 + 按钮创建新图</p>
            </div>
          </div>
        </div>

        <!-- 容器列表 -->
        <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
          <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900">容器</h3>
            <div class="flex gap-1">
              <button
                @click="showNewContainerDialog = true"
                class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
                title="新建容器"
              >
                <Plus class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto px-2 py-2 max-h-40">
            <div
              v-for="container in graphDetail.containers"
              :key="container.container_id"
              class="mb-1 p-2 border rounded flex items-center justify-between border-zinc-200"
            >
              <div class="flex-1 min-w-0">
                <div class="text-xs font-medium text-zinc-900">{{ container.label }}</div>
                <div class="text-[11px] text-zinc-500">{{ container.container_key }} · {{ container.role_type }}</div>
              </div>
              <button
                @click.stop="handleDeleteContainer(container.container_id)"
                class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                title="删除容器"
              >
                <Trash2 class="w-3 h-3" />
              </button>
            </div>

            <div v-if="graphDetail.containers.length === 0" class="text-center py-4 text-zinc-400">
              <p class="text-xs">暂无容器</p>
            </div>
          </div>
        </div>

        <!-- 节点列表 -->
        <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
          <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900">节点</h3>
            <div class="flex gap-1">
              <button
                @click="showNewNodeDialog = true"
                class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
                title="新建节点"
              >
                <Plus class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div class="flex-1 overflow-y-auto px-2 py-2 max-h-56">
            <div
              v-for="container in graphDetail.containers"
              :key="`group-${container.container_id}`"
              class="mb-2"
            >
              <div class="px-1 py-1 text-[11px] font-semibold text-zinc-500">
                {{ container.label }}
              </div>
              <div
                v-for="node in nodesByContainer.groups[container.container_id] || []"
                :key="node.node_id"
                class="mb-1 p-2 border rounded cursor-pointer"
                :class="[
                  selectedObject.type === 'node' && selectedObject.id === node.node_id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-zinc-200 hover:border-zinc-300'
                ]"
                @click="handleSelectNode(node.node_id)"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="min-w-0">
                    <div class="text-xs font-medium text-zinc-900 truncate">{{ node.label }}</div>
                    <div class="text-xs text-zinc-500">{{ node.node_type }}</div>
                  </div>
                  <button
                    @click.stop="handleDeleteNode(node.node_id)"
                    class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                    title="删除"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
                <select
                  :value="node.container_id || ''"
                  @change="handleAssignNodeContainer(node.node_id, $event.target.value)"
                  class="mt-1 w-full px-2 py-1 border border-zinc-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                :class="[
                  selectedObject.type === 'node' && selectedObject.id === node.node_id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-zinc-200 hover:border-zinc-300'
                ]"
                @click="handleSelectNode(node.node_id)"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="min-w-0">
                    <div class="text-xs font-medium text-zinc-900 truncate">{{ node.label }}</div>
                    <div class="text-xs text-zinc-500">{{ node.node_type }}</div>
                  </div>
                  <button
                    @click.stop="handleDeleteNode(node.node_id)"
                    class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                    title="删除"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
                <select
                  :value="node.container_id || ''"
                  @change="handleAssignNodeContainer(node.node_id, $event.target.value)"
                  class="mt-1 w-full px-2 py-1 border border-zinc-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="">未分配</option>
                  <option v-for="opt in graphDetail.containers" :key="opt.container_id" :value="opt.container_id">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>

            <div
              v-if="graphDetail.nodes.length === 0"
              class="text-center py-4 text-zinc-400"
            >
              <p class="text-xs">暂无节点</p>
            </div>
          </div>
        </div>

        <!-- 边列表 -->
        <div v-if="selectedGraphId" class="border-t border-zinc-200 flex-1 flex flex-col overflow-hidden">
          <div class="px-4 py-3 border-b border-zinc-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-zinc-900">边</h3>
            <button
              @click="showNewEdgeDialog = true"
              class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded-md transition-colors"
              title="新建边"
            >
              <Plus class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto px-2 py-2">
            <div
              v-for="edge in graphDetail.edges"
              :key="edge.edge_id"
              class="mb-1 p-2 border rounded cursor-pointer flex items-center justify-between"
              :class="[
                selectedObject.type === 'edge' && selectedObject.id === edge.edge_id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-zinc-200 hover:border-zinc-300'
              ]"
              @click="handleSelectEdge(edge.edge_id)"
            >
              <div class="flex-1 min-w-0">
                <div class="text-xs font-medium text-zinc-900">{{ edge.label || edge.edge_type }}</div>
                <div class="text-xs text-zinc-500">{{ edge.edge_type }}</div>
              </div>
              <button
                @click.stop="handleDeleteEdge(edge.edge_id)"
                class="p-1 text-zinc-400 hover:text-red-500 transition-colors"
                title="删除"
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

      <!-- 中间：画布 -->
      <div class="flex-1 flex flex-col bg-zinc-200 overflow-hidden">
        <div class="px-4 py-3 bg-white border-b border-zinc-200 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span v-if="currentGraph" class="text-sm font-medium text-zinc-900">{{ currentGraph.name }}</span>
            <span v-if="currentGraph" class="text-xs text-zinc-500">({{ currentGraph.status }})</span>
          </div>
          <div class="flex gap-1">
            <button
              v-if="selectedGraphId"
              @click="handleSelectGraphObject"
              class="px-3 py-1.5 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded transition-colors"
            >
              图属性
            </button>
            <button
              v-if="selectedGraphId"
              @click="handleViewStructure"
              :disabled="structureLoading"
              class="p-1.5 text-xs text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-zinc-500"
              title="查看结构"
            >
              <Eye v-if="!structureLoading" class="w-4 h-4" />
              <div v-else class="w-4 h-4 animate-spin border-2 border-zinc-300 border-t-blue-600 rounded-full"></div>
            </button>
            <button
              v-if="selectedGraphId"
              @click="handleRefresh"
              class="p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 rounded transition-colors"
              title="刷新"
            >
              <RefreshCw :class="{ 'animate-spin': loading }" class="w-4 h-4" />
            </button>
          </div>
        </div>

        <div class="flex-1 p-4 overflow-auto">
          <ExecutionGraphCanvas
            v-if="selectedGraphId"
            :containers="graphDetail.containers"
            :nodes="graphDetail.nodes"
            :edges="graphDetail.edges"
            :layout="graphDetail.graph?.layout_json || {}"
            :selected-id="selectedCanvasId"
            @select-node="handleSelectNode"
            @select-edge="handleSelectEdge"
            @layout-change="handleCanvasLayoutChange"
          />
          <div v-else class="flex items-center justify-center h-full text-zinc-400">
            <div class="text-center">
              <svg class="w-16 h-16 mx-auto mb-3 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 011.254 2.342z" />
              </svg>
              <p class="text-sm">请选择一个图开始编辑</p>
              <p class="text-xs mt-1">从左侧列表选择或创建新图</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：属性编辑器 -->
      <div v-if="selectedGraphId" class="w-80 bg-white border-l border-zinc-200 overflow-hidden">
        <ExecutionGraphInspector
          :selected-object="selectedGraphData || selectedNodeData || selectedEdgeData"
          :object-type="selectedObject.type"
          @update="handleUpdateObject"
        />
      </div>
    </div>

    <!-- 新建图对话框 -->
    <div v-if="showNewGraphDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-96 max-w-full mx-4">
        <div class="px-6 py-4 border-b border-zinc-200">
          <h3 class="text-lg font-semibold text-zinc-900">新建执行拓扑图</h3>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">名称 *</label>
            <input
              v-model="newGraphForm.name"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入图名称"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">描述</label>
            <textarea
              v-model="newGraphForm.description"
              rows="3"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder="输入图描述（可选）"
            />
          </div>
        </div>
        <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
          <button
            @click="showNewGraphDialog = false"
            class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          >
            取消
          </button>
          <button
            @click="handleCreateGraph"
            :disabled="loading || !newGraphForm.name || !selectedProjectId"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          >
            创建
          </button>
        </div>
      </div>
    </div>

    <!-- 新建容器对话框 -->
    <div v-if="showNewContainerDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-96 max-w-full mx-4">
        <div class="px-6 py-4 border-b border-zinc-200">
          <h3 class="text-lg font-semibold text-zinc-900">新建容器</h3>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">容器 Key *</label>
            <input
              v-model="newContainerForm.container_key"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: planner_agent"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">容器名称 *</label>
            <input
              v-model="newContainerForm.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: 规划 Agent"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">角色类型</label>
            <select
              v-model="newContainerForm.role_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in roleTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
          <button
            @click="showNewContainerDialog = false"
            class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          >
            取消
          </button>
          <button
            @click="handleCreateContainer"
            :disabled="loading || !newContainerForm.container_key || !newContainerForm.label"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          >
            创建
          </button>
        </div>
      </div>
    </div>

    <!-- 新建节点对话框 -->
    <div v-if="showNewNodeDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-96 max-w-full mx-4">
        <div class="px-6 py-4 border-b border-zinc-200">
          <h3 class="text-lg font-semibold text-zinc-900">新建节点</h3>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">所属容器</label>
            <select
              v-model="newNodeForm.container_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">未分配</option>
              <option v-for="container in graphDetail.containers" :key="container.container_id" :value="container.container_id">
                {{ container.label }} ({{ container.container_key }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">节点 Key *</label>
            <input
              v-model="newNodeForm.node_key"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: step1"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">标签 *</label>
            <input
              v-model="newNodeForm.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: 第一步"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">节点类型</label>
            <select
              v-model="newNodeForm.node_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in nodeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">角色类型</label>
            <select
              v-model="newNodeForm.role_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in roleTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
          <button
            @click="showNewNodeDialog = false"
            class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          >
            取消
          </button>
          <button
            @click="handleCreateNode"
            :disabled="loading || !newNodeForm.node_key || !newNodeForm.label"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          >
            创建
          </button>
        </div>
      </div>
    </div>

    <!-- 新建边对话框 -->
    <div v-if="showNewEdgeDialog" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg shadow-xl w-96 max-w-full mx-4">
        <div class="px-6 py-4 border-b border-zinc-200">
          <h3 class="text-lg font-semibold text-zinc-900">新建边</h3>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">源节点</label>
            <select
              v-model="newEdgeForm.source_node_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">选择源节点</option>
              <option v-for="node in graphDetail.nodes" :key="node.node_id" :value="node.node_id">
                {{ node.label }} ({{ node.node_key }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">目标节点</label>
            <select
              v-model="newEdgeForm.target_node_id"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">选择目标节点</option>
              <option v-for="node in graphDetail.nodes" :key="node.node_id" :value="node.node_id">
                {{ node.label }} ({{ node.node_key }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">边类型</label>
            <select
              v-model="newEdgeForm.edge_type"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option v-for="opt in edgeTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">标签</label>
            <input
              v-model="newEdgeForm.label"
              type="text"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入边标签（可选）"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-zinc-700 mb-1">条件表达式</label>
            <textarea
              v-model="newEdgeForm.condition_expr"
              rows="2"
              class="w-full px-3 py-2 border border-zinc-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder="例如: review_required == true"
            />
          </div>
        </div>
        <div class="px-6 py-4 border-t border-zinc-200 flex justify-end gap-2">
          <button
            @click="showNewEdgeDialog = false"
            class="px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
          >
            取消
          </button>
          <button
            @click="handleCreateEdge"
            :disabled="loading || !newEdgeForm.source_node_id || !newEdgeForm.target_node_id"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-400 rounded transition-colors"
          >
            创建
          </button>
        </div>
      </div>
    </div>

    <!-- 拓扑结构查看器 -->
    <TopologyStructureViewer
      v-if="showStructureViewer"
      :structure="structureData"
      :loading="structureLoading"
      @close="handleCloseStructureViewer"
    />
  </div>
</template>

