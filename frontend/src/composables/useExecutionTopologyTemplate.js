import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { executionGraphApi } from '@/api/executionGraph'
import { manageApi } from '@/api/project'
import {
  isBlank,
  normalizeContainerPayload,
  normalizeEdgePayload,
  normalizeGraphPayload,
  normalizeNodePayload,
  parseJsonInput
} from '@/utils/topologyEditor'
import {
  buildExportPayload,
  downloadTemplateFile,
  readTemplateFile,
  validateTemplatePayload,
  importTemplate
} from '@/utils/topologyTemplateIO'

const createEmptyGraphDetail = () => ({
  graph: null,
  containers: [],
  nodes: [],
  edges: []
})

const createSelectedObject = (type = 'graph', id = null) => ({
  type,
  id
})

const createGraphForm = () => ({
  name: '',
  description: '',
  agentType: ''
})

const createContainerForm = () => ({
  container_key: '',
  label: '',
  role_type: 'agent',
  order_index: 0,
  config_json: '{}'
})


const createNodeForm = () => ({
  container_id: '',
  node_key: '',
  label: '',
  node_type: 'llm',
  phase_label: '',
  task_prompt: '',
  conditional_edges: '[]'
})

const createEdgeForm = () => ({
  source_node_id: '',
  target_node_id: '',
  edge_type: 'call',
  label: '',
  condition_expr: '',
  order_index: 0,
  config_json: '{}'
})

const createExecuteForm = () => ({
  inputPayload: '{}',
  maxSteps: 100,
  runtimeGraphName: '',
  runtimeGraphDescription: ''
})

const nodeTypeOptions = [
  { value: 'llm', label: 'LLM' },
  { value: 'invoke', label: 'Invoke' },
  { value: 'handoff', label: 'Handoff' }
]

const roleTypeOptions = [
  { value: 'human', label: 'Human' },
  { value: 'agent', label: 'Agent' },
  { value: 'system', label: 'System' }
]

const edgeTypeOptions = [
  { value: 'call', label: 'Call' },
  { value: 'return', label: 'Return' },
  { value: 'retry', label: 'Retry' },
  { value: 'seq', label: 'Seq' }
]

const agentTypeOptions = [
  { value: '', label: '不关联（通用模板）' },
  { value: 'requirement_agent', label: '需求 Agent（requirement_agent）' },
  { value: 'conflict_detection_agent', label: '冲突检测 Agent（conflict_detection_agent）' }
]

const getErrorMessage = (err, fallback) => {
  return err?.response?.data?.detail || err?.response?.data?.error || err?.response?.data?.message || err?.message || fallback
}

export function useExecutionTopologyTemplate() {
  const projects = ref([])
  const selectedProjectId = ref('')
  const graphs = ref([])
  const selectedGraphId = ref('')

  const graphDetail = ref(createEmptyGraphDetail())
  const selectedObject = ref(createSelectedObject())

  const loading = ref(false)
  const error = ref('')

  const showNewGraphDialog = ref(false)
  const showNewContainerDialog = ref(false)
  const showNewNodeDialog = ref(false)
  const showNewEdgeDialog = ref(false)
  const showStructureViewer = ref(false)
  const showExecuteDialog = ref(false)

  const graphFormErrors = ref({})
  const containerFormErrors = ref({})
  const nodeFormErrors = ref({})
  const edgeFormErrors = ref({})

  const newGraphForm = ref(createGraphForm())
  const newContainerForm = ref(createContainerForm())
  const newNodeForm = ref(createNodeForm())
  const newEdgeForm = ref(createEdgeForm())

  const structureData = ref(null)
  const structureLoading = ref(false)
  const structureError = ref('')

  const activeRightTab = ref('inspector')
  const validationLoading = ref(false)
  const validationResult = ref(null)
  const executionLoading = ref(false)
  const executionResult = ref(null)
  const executionError = ref('')

  const importLoading = ref(false)
  const importError = ref('')
  const importProgress = ref('')

  const executeForm = ref(createExecuteForm())

  const currentGraph = computed(() => graphDetail.value.graph)

  const selectedCanvasId = computed(() => {
    if (selectedObject.value.type === 'node' || selectedObject.value.type === 'edge') {
      return selectedObject.value.id
    }
    return null
  })

  const selectedContainerId = computed(() => {
    return selectedObject.value.type === 'container' ? selectedObject.value.id : null
  })

  const selectedGraphData = computed(() => {
    return selectedObject.value.type === 'graph' ? graphDetail.value.graph : null
  })

  const selectedContainerData = computed(() => {
    if (selectedObject.value.type !== 'container') return null
    return graphDetail.value.containers.find((item) => item.container_id === selectedObject.value.id) || null
  })

  const selectedNodeData = computed(() => {
    if (selectedObject.value.type !== 'node') return null
    return graphDetail.value.nodes.find((item) => item.node_id === selectedObject.value.id) || null
  })

  const selectedEdgeData = computed(() => {
    if (selectedObject.value.type !== 'edge') return null
    return graphDetail.value.edges.find((item) => item.edge_id === selectedObject.value.id) || null
  })

  const selectedInspectorObject = computed(() => {
    return selectedGraphData.value || selectedContainerData.value || selectedNodeData.value || selectedEdgeData.value
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
      const containerId = node.container_id
      if (containerId && groups[containerId]) {
        groups[containerId].push(node)
        return
      }
      unassigned.push(node)
    })

    return { groups, unassigned }
  })



  const graphHints = computed(() => {
    const hints = []
    if (!selectedGraphId.value) return hints

    if (graphDetail.value.nodes.length === 0) {
      hints.push('空图建议：先建容器 -> 再建节点 -> 再连边 -> 再校验 -> 再执行。')
    }

    const hasBusinessNode = graphDetail.value.nodes.some((item) =>
      ['llm', 'invoke', 'handoff'].includes(item.node_type)
    )
    if (graphDetail.value.nodes.length > 0 && !hasBusinessNode) {
      hints.push('当前没有业务节点（LLM / Invoke / Handoff），执行前请至少配置一个。')
    }

    return hints
  })

  const validationSummary = computed(() => {
    const result = validationResult.value
    if (!result?.success || !result.result) {
      return null
    }

    return {
      isValid: result.result.is_valid,
      errorCount: result.result.errors?.length || 0,
      warningCount: result.result.warnings?.length || 0
    }
  })

  const nodeMap = computed(() => {
    const map = {}
    graphDetail.value.nodes.forEach((node) => {
      map[node.node_id] = node
    })
    return map
  })

  const executionStatusClass = computed(() => {
    const status = executionResult.value?.status
    if (status === 'succeeded') return 'bg-emerald-100 text-emerald-700'
    if (status === 'failed') return 'bg-red-100 text-red-700'
    if (status === 'suspended') return 'bg-amber-100 text-amber-700'
    return 'bg-zinc-100 text-zinc-700'
  })

  const findContainer = (rawValue) => {
    if (!rawValue) return null
    const target = String(rawValue).trim()
    return graphDetail.value.containers.find((container) => (
      container.container_id === target ||
      container.container_key === target ||
      container.label === target
    )) || null
  }

  const findNodeByKey = (rawValue) => {
    if (!rawValue) return null
    const target = String(rawValue).trim()
    return graphDetail.value.nodes.find((node) => (
      node.node_id === target ||
      node.node_key === target ||
      node.label === target
    )) || null
  }

  const findEdgeByContainerRelation = (sourceContainerId, targetContainerId, edgeType) => {
    return graphDetail.value.edges.find((edge) => {
      const sourceNode = nodeMap.value[edge.source_node_id]
      const targetNode = nodeMap.value[edge.target_node_id]
      return sourceNode?.container_id === sourceContainerId &&
        targetNode?.container_id === targetContainerId &&
        edge.edge_type === edgeType
    }) || null
  }

  const resolveValidationTarget = (message) => {
    if (!message) return null

    const edgeIdMatch = message.match(/Edge '([^']+)'/)
    if (edgeIdMatch) {
      const edge = graphDetail.value.edges.find((item) => item.edge_id === edgeIdMatch[1])
      if (edge) {
        return {
          type: 'edge',
          id: edge.edge_id,
          label: edge.label || edge.edge_type
        }
      }
    }

    const duplicateEdgeMatch = message.match(/Duplicate edge: ([^ ]+) -> ([^ ]+) \(([^)]+)\)/)
    if (duplicateEdgeMatch) {
      const edge = findEdgeByContainerRelation(duplicateEdgeMatch[1], duplicateEdgeMatch[2], duplicateEdgeMatch[3])
      if (edge) {
        return {
          type: 'edge',
          id: edge.edge_id,
          label: edge.label || edge.edge_type
        }
      }
      const container = findContainer(duplicateEdgeMatch[1])
      if (container) {
        return {
          type: 'container',
          id: container.container_id,
          label: container.label
        }
      }
    }

    const nodeMatch = message.match(/node '([^']+)'/i)
    if (nodeMatch) {
      const node = findNodeByKey(nodeMatch[1])
      if (node) {
        return {
          type: 'node',
          id: node.node_id,
          label: node.label
        }
      }
    }

    const containerMatch = message.match(/container(?: key)?[: ]+'?([^'()]+)'?/i)
    if (containerMatch) {
      const container = findContainer(containerMatch[1])
      if (container) {
        return {
          type: 'container',
          id: container.container_id,
          label: container.label
        }
      }
    }

    const duplicateContainerMatch = message.match(/Duplicate container key: (.+)$/)
    if (duplicateContainerMatch) {
      const container = findContainer(duplicateContainerMatch[1])
      if (container) {
        return {
          type: 'container',
          id: container.container_id,
          label: container.label
        }
      }
    }

    return null
  }

  const validationItems = computed(() => {
    const result = validationResult.value?.result
    if (!result) return []

    const errors = (result.errors || []).map((message, index) => ({
      id: `error-${index}`,
      level: 'error',
      message,
      target: resolveValidationTarget(message)
    }))

    const warnings = (result.warnings || []).map((message, index) => ({
      id: `warning-${index}`,
      level: 'warning',
      message,
      target: resolveValidationTarget(message)
    }))

    return [...errors, ...warnings]
  })

  const resetSelectionState = () => {
    selectedGraphId.value = ''
    graphDetail.value = createEmptyGraphDetail()
    selectedObject.value = createSelectedObject()
    validationResult.value = null
    executionResult.value = null
    activeRightTab.value = 'inspector'
  }

  const resetGraphForm = () => {
    newGraphForm.value = createGraphForm()
    graphFormErrors.value = {}
  }

  const resetContainerForm = () => {
    newContainerForm.value = createContainerForm()
    containerFormErrors.value = {}
  }



  const resetNodeForm = () => {
    newNodeForm.value = createNodeForm()
    nodeFormErrors.value = {}
  }

  const resetEdgeForm = () => {
    newEdgeForm.value = createEdgeForm()
    edgeFormErrors.value = {}
  }

  const updateGraphForm = (form) => {
    newGraphForm.value = form
  }

  const updateContainerForm = (form) => {
    newContainerForm.value = form
  }



  const updateNodeForm = (form) => {
    newNodeForm.value = form
  }

  const updateEdgeForm = (form) => {
    newEdgeForm.value = form
  }

  const updateExecuteForm = (form) => {
    executeForm.value = form
  }

  const openNewGraphDialog = () => {
    resetGraphForm()
    showNewGraphDialog.value = true
  }

  const closeNewGraphDialog = () => {
    showNewGraphDialog.value = false
    resetGraphForm()
  }

  const openNewContainerDialog = () => {
    resetContainerForm()
    showNewContainerDialog.value = true
  }

  const closeNewContainerDialog = () => {
    showNewContainerDialog.value = false
    resetContainerForm()
  }



  const openNewNodeDialog = () => {
    resetNodeForm()
    showNewNodeDialog.value = true
  }

  const closeNewNodeDialog = () => {
    showNewNodeDialog.value = false
    resetNodeForm()
  }

  const openNewEdgeDialog = () => {
    resetEdgeForm()
    showNewEdgeDialog.value = true
  }

  const closeNewEdgeDialog = () => {
    showNewEdgeDialog.value = false
    resetEdgeForm()
  }

  const closeExecuteDialog = () => {
    showExecuteDialog.value = false
  }

  const setActiveRightTab = (tab) => {
    activeRightTab.value = tab
  }

  const selectObject = (type, id) => {
    selectedObject.value = { type, id }
    activeRightTab.value = 'inspector'
  }

  const handleProjectChange = async (projectId) => {
    selectedProjectId.value = projectId
    resetSelectionState()
    await loadGraphs()
  }

  const loadProjects = async () => {
    try {
      loading.value = true
      const data = await manageApi.listProjects()
      const projectList = data?.projects || []
      projects.value = projectList

      if (projectList.length > 0 && !selectedProjectId.value) {
        selectedProjectId.value = projectList[0].project_id
      }

      if (projectList.length === 0) {
        resetSelectionState()
      }
    } catch (err) {
      error.value = getErrorMessage(err, '加载项目列表失败')
    } finally {
      loading.value = false
    }
  }

  const loadGraphs = async () => {
    if (!selectedProjectId.value) {
      graphs.value = []
      resetSelectionState()
      return
    }

    try {
      loading.value = true
      error.value = ''
      const items = await executionGraphApi.listGraphs(selectedProjectId.value)
      graphs.value = items

      if (!items.some((item) => item.graph_id === selectedGraphId.value)) {
        resetSelectionState()
      }
    } catch (err) {
      error.value = getErrorMessage(err, '加载图列表失败')
    } finally {
      loading.value = false
    }
  }

  const loadGraphDetail = async (graphId) => {
    if (!graphId) return

    try {
      loading.value = true
      error.value = ''
      graphDetail.value = await executionGraphApi.getGraphDetail(graphId)

      const current = selectedObject.value
      if (current.type === 'container' && !graphDetail.value.containers.some((item) => item.container_id === current.id)) {
        selectedObject.value = createSelectedObject('graph', graphId)
      }

      if (current.type === 'node' && !graphDetail.value.nodes.some((item) => item.node_id === current.id)) {
        selectedObject.value = createSelectedObject('graph', graphId)
      }
      if (current.type === 'edge' && !graphDetail.value.edges.some((item) => item.edge_id === current.id)) {
        selectedObject.value = createSelectedObject('graph', graphId)
      }
    } catch (err) {
      error.value = getErrorMessage(err, '加载图详情失败')
      graphDetail.value = createEmptyGraphDetail()
    } finally {
      loading.value = false
    }
  }

  const handleSelectGraph = async (graph) => {
    selectedGraphId.value = graph.graph_id
    selectedObject.value = createSelectedObject('graph', graph.graph_id)
    validationResult.value = null
    await loadGraphDetail(graph.graph_id)
  }

  const validateGraphForm = () => {
    const errors = {}
    if (isBlank(newGraphForm.value.name)) {
      errors.name = '图名称不能为空'
    }
    graphFormErrors.value = errors
    if (Object.keys(errors).length > 0) return null
    return normalizeGraphPayload(newGraphForm.value)
  }

  const validateContainerForm = () => {
    const errors = {}
    if (isBlank(newContainerForm.value.container_key)) {
      errors.container_key = '容器 key 不能为空'
    }
    if (isBlank(newContainerForm.value.label)) {
      errors.label = '容器名称不能为空'
    }

    const duplicated = graphDetail.value.containers.some((item) => (
      item.container_key?.trim().toLowerCase() === newContainerForm.value.container_key?.trim().toLowerCase()
    ))
    if (duplicated) {
      errors.container_key = '容器 key 已存在'
    }

    if (Number(newContainerForm.value.order_index) < 0) {
      errors.order_index = '排序不能小于 0'
    }

    const normalized = normalizeContainerPayload(newContainerForm.value)
    if (!normalized.ok) {
      errors.form = normalized.error
    }

    containerFormErrors.value = errors
    if (Object.keys(errors).length > 0 || !normalized.ok) return null
    return normalized.value
  }



  const validateNodeForm = () => {
    const errors = {}
    if (isBlank(newNodeForm.value.node_key)) {
      errors.node_key = '节点 key 不能为空'
    }
    if (isBlank(newNodeForm.value.label)) {
      errors.label = '节点标签不能为空'
    }

    const duplicated = graphDetail.value.nodes.some((item) => (
      item.node_key?.trim().toLowerCase() === newNodeForm.value.node_key?.trim().toLowerCase()
    ))
    if (duplicated) {
      errors.node_key = '节点 key 已存在'
    }

    if (Number(newNodeForm.value.order_index) < 0) {
      errors.order_index = '排序不能小于 0'
    }

    const normalized = normalizeNodePayload(newNodeForm.value)
    if (!normalized.ok) {
      errors.form = normalized.error
    }

    nodeFormErrors.value = errors
    if (Object.keys(errors).length > 0 || !normalized.ok) return null
    return normalized.value
  }

  const validateEdgeForm = () => {
    const errors = {}
    if (!newEdgeForm.value.source_node_id) {
      errors.source_node_id = '请选择源节点'
    }
    if (!newEdgeForm.value.target_node_id) {
      errors.target_node_id = '请选择目标节点'
    }
    if (newEdgeForm.value.source_node_id && newEdgeForm.value.source_node_id === newEdgeForm.value.target_node_id) {
      errors.target_node_id = '不允许创建自环边'
    }

    const duplicated = graphDetail.value.edges.some((item) => (
      item.source_node_id === newEdgeForm.value.source_node_id &&
      item.target_node_id === newEdgeForm.value.target_node_id &&
      item.edge_type === newEdgeForm.value.edge_type
    ))
    if (duplicated) {
      errors.form = '同源节点、目标节点和边类型的边已存在'
    }

    if (Number(newEdgeForm.value.order_index) < 0) {
      errors.order_index = '排序不能小于 0'
    }

    const normalized = normalizeEdgePayload(newEdgeForm.value)
    if (!normalized.ok) {
      errors.form = normalized.error
    }

    edgeFormErrors.value = errors
    if (Object.keys(errors).length > 0 || !normalized.ok) return null
    return normalized.value
  }

  const handleCreateGraph = async () => {
    if (!selectedProjectId.value) {
      error.value = '请先选择项目'
      return
    }

    const payload = validateGraphForm()
    if (!payload) return

    // 若选择了 agentType，写入 meta_json
    if (newGraphForm.value.agentType) {
      payload.meta_json = { agent_type: newGraphForm.value.agentType }
    }

    try {
      loading.value = true
      error.value = ''
      const graph = await executionGraphApi.createGraph(selectedProjectId.value, payload)
      graphs.value.unshift(graph)
      closeNewGraphDialog()
      await handleSelectGraph(graph)
    } catch (err) {
      error.value = getErrorMessage(err, '创建图失败')
    } finally {
      loading.value = false
    }
  }

  const handleCreateContainer = async () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    const payload = validateContainerForm()
    if (!payload) return

    try {
      loading.value = true
      error.value = ''
      const container = await executionGraphApi.createContainer(selectedGraphId.value, payload)
      graphDetail.value.containers.push(container)
      closeNewContainerDialog()
      selectObject('container', container.container_id)
    } catch (err) {
      error.value = getErrorMessage(err, '创建容器失败')
    } finally {
      loading.value = false
    }
  }


  const handleCreateNode = async () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    const payload = validateNodeForm()
    if (!payload) return

    try {
      loading.value = true
      error.value = ''
      const node = await executionGraphApi.createNode(selectedGraphId.value, payload)
      graphDetail.value.nodes.push(node)
      closeNewNodeDialog()
      selectObject('node', node.node_id)
    } catch (err) {
      error.value = getErrorMessage(err, '创建节点失败')
    } finally {
      loading.value = false
    }
  }

  const handleCreateEdge = async () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    const payload = validateEdgeForm()
    if (!payload) return

    try {
      loading.value = true
      error.value = ''
      const edge = await executionGraphApi.createEdge(selectedGraphId.value, payload)
      graphDetail.value.edges.push(edge)
      closeNewEdgeDialog()
      selectObject('edge', edge.edge_id)
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
      const index = graphDetail.value.nodes.findIndex((item) => item.node_id === nodeId)
      if (index !== -1) {
        graphDetail.value.nodes[index] = updated
      }
    } catch (err) {
      error.value = getErrorMessage(err, '调整节点归属失败')
    } finally {
      loading.value = false
    }
  }

  const handleDeleteContainer = async (containerId) => {
    if (!window.confirm('确定要删除此容器吗？删除后节点会变为未分配。')) return

    try {
      loading.value = true
      error.value = ''
      await executionGraphApi.deleteContainer(containerId)
      graphDetail.value.containers = graphDetail.value.containers.filter((item) => item.container_id !== containerId)

      graphDetail.value.nodes = graphDetail.value.nodes.map((node) => (
        node.container_id === containerId ? { ...node, container_id: null } : node
      ))
      if (selectedObject.value.type === 'container' && selectedObject.value.id === containerId) {
        selectedObject.value = createSelectedObject('graph', selectedGraphId.value)
      }

    } catch (err) {
      error.value = getErrorMessage(err, '删除容器失败')
    } finally {
      loading.value = false
    }
  }

  const handleDeleteNode = async (nodeId) => {
    if (!window.confirm('确定要删除此节点吗？')) return

    try {
      loading.value = true
      error.value = ''
      await executionGraphApi.deleteNode(nodeId)
      graphDetail.value.nodes = graphDetail.value.nodes.filter((item) => item.node_id !== nodeId)
      graphDetail.value.edges = graphDetail.value.edges.filter((edge) => (
        edge.source_node_id !== nodeId && edge.target_node_id !== nodeId
      ))
      if (selectedObject.value.type === 'node' && selectedObject.value.id === nodeId) {
        selectedObject.value = createSelectedObject('graph', selectedGraphId.value)
      }
    } catch (err) {
      error.value = getErrorMessage(err, '删除节点失败')
    } finally {
      loading.value = false
    }
  }

  const handleDeleteEdge = async (edgeId) => {
    if (!window.confirm('确定要删除此边吗？')) return

    try {
      loading.value = true
      error.value = ''
      await executionGraphApi.deleteEdge(edgeId)
      graphDetail.value.edges = graphDetail.value.edges.filter((item) => item.edge_id !== edgeId)
      if (selectedObject.value.type === 'edge' && selectedObject.value.id === edgeId) {
        selectedObject.value = createSelectedObject('graph', selectedGraphId.value)
      }
    } catch (err) {
      error.value = getErrorMessage(err, '删除边失败')
    } finally {
      loading.value = false
    }
  }

  const handleDeleteGraph = async (graphId) => {
    if (!window.confirm('确定要删除此图吗？')) return

    try {
      loading.value = true
      error.value = ''
      await executionGraphApi.deleteGraph(graphId)
      graphs.value = graphs.value.filter((item) => item.graph_id !== graphId)

      if (selectedGraphId.value === graphId) {
        resetSelectionState()
      }
    } catch (err) {
      error.value = getErrorMessage(err, '删除图失败')
    } finally {
      loading.value = false
    }
  }

  const handleUpdateObject = async (data) => {
    try {
      loading.value = true
      error.value = ''

      if (selectedObject.value.type === 'graph') {
        const updated = await executionGraphApi.updateGraph(selectedObject.value.id, data)
        graphDetail.value.graph = updated
        const graphIndex = graphs.value.findIndex((item) => item.graph_id === updated.graph_id)
        if (graphIndex !== -1) {
          graphs.value[graphIndex] = { ...graphs.value[graphIndex], ...updated }
        }
      } else if (selectedObject.value.type === 'container') {
        const updated = await executionGraphApi.updateContainer(selectedObject.value.id, data)
        const index = graphDetail.value.containers.findIndex((item) => item.container_id === selectedObject.value.id)
        if (index !== -1) {
          graphDetail.value.containers[index] = updated
        }
      } else if (selectedObject.value.type === 'node') {
        const updated = await executionGraphApi.updateNode(selectedObject.value.id, data)
        const index = graphDetail.value.nodes.findIndex((item) => item.node_id === selectedObject.value.id)
        if (index !== -1) {
          graphDetail.value.nodes[index] = updated
        }
      } else if (selectedObject.value.type === 'edge') {
        const updated = await executionGraphApi.updateEdge(selectedObject.value.id, data)
        const index = graphDetail.value.edges.findIndex((item) => item.edge_id === selectedObject.value.id)
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

  const handleUpdateNodeContent = async ({ task_prompt, input_node_ids }) => {
    if (selectedObject.value.type !== 'node' || !selectedObject.value.id) return
    try {
      loading.value = true
      error.value = ''
      const updated = await executionGraphApi.updateNode(selectedObject.value.id, {
        task_prompt,
        input_schema_json: input_node_ids
      })
      const index = graphDetail.value.nodes.findIndex((item) => item.node_id === selectedObject.value.id)
      if (index !== -1) {
        graphDetail.value.nodes[index] = updated
      }
    } catch (err) {
      error.value = getErrorMessage(err, '保存节点内容失败')
    } finally {
      loading.value = false
    }
  }

  const handleSelectGraphObject = () => {
    if (selectedGraphId.value) {
      selectObject('graph', selectedGraphId.value)
    }
  }

  const handleRefresh = async () => {
    if (selectedGraphId.value) {
      await loadGraphDetail(selectedGraphId.value)
    } else {
      await loadGraphs()
    }
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

    if (layoutSaveTimer) clearTimeout(layoutSaveTimer)
    const graphId = selectedGraphId.value
    layoutSaveTimer = setTimeout(async () => {
      try {
        const updated = await executionGraphApi.updateGraph(graphId, {
          layout_json: nextLayout
        })
        if (selectedGraphId.value === graphId) {
          graphDetail.value.graph = updated
        }
      } catch (err) {
        error.value = getErrorMessage(err, '保存画布布局失败')
      }
    }, 450)
  }

  const handleViewStructure = async () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    try {
      structureLoading.value = true
      structureError.value = ''
      error.value = ''
      const data = await executionGraphApi.getTopologyStructure(selectedGraphId.value)
      if (data.success) {
        structureData.value = data.structure
        showStructureViewer.value = true
      } else {
        structureError.value = data.error || '获取拓扑结构失败'
        error.value = structureError.value
      }
    } catch (err) {
      const message = getErrorMessage(err, '获取拓扑结构失败')
      structureError.value = message
      error.value = message
    } finally {
      structureLoading.value = false
    }
  }

  const handleCloseStructureViewer = () => {
    showStructureViewer.value = false
    structureData.value = null
    structureError.value = ''
  }

  const handleValidateTopology = async () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    try {
      validationLoading.value = true
      error.value = ''
      const data = await executionGraphApi.validateTopologyStructure(selectedGraphId.value)
      validationResult.value = data
      activeRightTab.value = 'validation'
      if (!data.success) {
        error.value = data.error || '校验拓扑失败'
      }
    } catch (err) {
      const message = getErrorMessage(err, '校验拓扑失败')
      error.value = message
      validationResult.value = {
        success: false,
        error: message
      }
      activeRightTab.value = 'validation'
    } finally {
      validationLoading.value = false
    }
  }

  const handleSelectValidationItem = (item) => {
    if (!item?.target) return
    selectedObject.value = { type: item.target.type, id: item.target.id }
  }

  const handleOpenExecuteDialog = () => {
    if (!selectedGraphId.value) {
      error.value = '请先选择一个图'
      return
    }

    showExecuteDialog.value = true
    executionError.value = ''
  }

  const handleExecuteGraph = async () => {
    if (!selectedGraphId.value) {
      executionError.value = '请先选择一个图'
      return
    }

    const payload = parseJsonInput(executeForm.value.inputPayload, {
      fallback: {},
      label: '输入 payload'
    })
    if (!payload.ok || payload.value === null || Array.isArray(payload.value) || typeof payload.value !== 'object') {
      executionError.value = payload.error || '输入 payload 必须是 JSON 对象'
      return
    }

    try {
      executionLoading.value = true
      executionError.value = ''
      error.value = ''
      const data = await executionGraphApi.executeTopology(selectedGraphId.value, {
        input_payload: payload.value,
        max_steps: Number(executeForm.value.maxSteps) || 100,
        runtime_graph_name: executeForm.value.runtimeGraphName || undefined,
        runtime_graph_description: executeForm.value.runtimeGraphDescription || undefined
      })
      executionResult.value = data
      activeRightTab.value = 'execution'
    } catch (err) {
      const message = getErrorMessage(err, '执行拓扑失败')
      executionError.value = message
      error.value = message
    } finally {
      executionLoading.value = false
    }
  }

  const handleExportTemplate = () => {
    if (!selectedGraphId.value || !graphDetail.value.graph) {
      error.value = '请先选择一个图'
      return
    }

    try {
      const payload = buildExportPayload(graphDetail.value)
      const graphName = graphDetail.value.graph.name || 'topology'
      const safeName = graphName.replace(/[^a-zA-Z0-9\u4e00-\u9fff_-]/g, '_')
      downloadTemplateFile(payload, `${safeName}_template.satpl.json`)
    } catch (err) {
      error.value = '导出失败: ' + (err.message || '未知错误')
    }
  }

  const handleImportTemplate = async (file) => {
    if (!selectedProjectId.value) {
      error.value = '请先选择项目'
      return
    }

    if (!file) return

    importLoading.value = true
    importError.value = ''
    importProgress.value = '正在读取文件...'
    error.value = ''

    try {
      // 1. 读取文件
      const readResult = await readTemplateFile(file)
      if (!readResult.ok) {
        importError.value = readResult.error
        return
      }

      // 2. 校验格式
      const validation = validateTemplatePayload(readResult.value)
      if (!validation.ok) {
        importError.value = '模板校验失败:\n' + validation.errors.join('\n')
        return
      }

      // 3. 执行导入
      const result = await importTemplate(
        selectedProjectId.value,
        readResult.value,
        (msg) => { importProgress.value = msg }
      )

      if (!result.ok) {
        importError.value = result.error
        return
      }

      // 4. 刷新列表并选中新图
      await loadGraphs()
      if (result.graphId) {
        const newGraph = graphs.value.find((g) => g.graph_id === result.graphId)
        if (newGraph) {
          await handleSelectGraph(newGraph)
        }
      }

      importProgress.value = '导入完成'
    } catch (err) {
      importError.value = '导入失败: ' + (err.message || '未知错误')
    } finally {
      importLoading.value = false
    }
  }

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

  return {
    projects,
    selectedProjectId,
    graphs,
    selectedGraphId,
    graphDetail,
    selectedObject,
    loading,
    error,
    showNewGraphDialog,
    showNewContainerDialog,

    showNewNodeDialog,
    showNewEdgeDialog,
    showStructureViewer,
    showExecuteDialog,
    graphFormErrors,
    containerFormErrors,

    nodeFormErrors,
    edgeFormErrors,
    newGraphForm,
    newContainerForm,

    newNodeForm,
    newEdgeForm,
    structureData,
    structureLoading,
    activeRightTab,
    validationLoading,
    validationResult,
    executionLoading,
    executionResult,
    executionError,
    executeForm,
    nodeTypeOptions,
    roleTypeOptions,
    edgeTypeOptions,
    agentTypeOptions,
    currentGraph,
    selectedCanvasId,
    selectedContainerId,
    selectedGraphData,
    selectedContainerData,

    selectedNodeData,
    selectedEdgeData,
    selectedInspectorObject,
    nodesByContainer,

    graphHints,
    validationSummary,
    validationItems,
    executionStatusClass,
    updateGraphForm,
    updateContainerForm,

    updateNodeForm,
    updateEdgeForm,
    updateExecuteForm,
    openNewGraphDialog,
    closeNewGraphDialog,
    openNewContainerDialog,
    closeNewContainerDialog,

    openNewNodeDialog,
    closeNewNodeDialog,
    openNewEdgeDialog,
    closeNewEdgeDialog,
    closeExecuteDialog,
    setActiveRightTab,
    selectObject,
    handleProjectChange,
    handleSelectGraph,
    handleCreateGraph,
    handleCreateContainer,

    handleCreateNode,
    handleCreateEdge,
    handleAssignNodeContainer,
    handleDeleteContainer,
    handleDeleteNode,
    handleDeleteEdge,
    handleDeleteGraph,
    handleUpdateObject,
    handleSelectGraphObject,
    handleRefresh,
    handleCanvasLayoutChange,
    handleViewStructure,
    handleCloseStructureViewer,
    handleValidateTopology,
    handleSelectValidationItem,
    handleOpenExecuteDialog,
    handleExecuteGraph,
    handleUpdateNodeContent,
    handleExportTemplate,
    handleImportTemplate,
    importLoading,
    importError,
    importProgress
  }
}
