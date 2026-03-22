<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  containers: {
    type: Array,
    default: () => []
  },
  nodes: {
    type: Array,
    default: () => []
  },
  edges: {
    type: Array,
    default: () => []
  },
  selectedId: {
    type: String,
    default: null
  },
  selectedContainerId: {
    type: String,
    default: null
  },
  layout: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['select-node', 'select-edge', 'select-container', 'layout-change'])

const NODE_WIDTH = 136
const NODE_HEIGHT = 64
const MIN_X = 24
const MIN_Y = 24
const CONTAINER_HEADER_HEIGHT = 34
const CONTAINER_PADDING_X = 26
const CONTAINER_PADDING_Y = 22
const CONTAINER_MIN_WIDTH = 244
const CONTAINER_MIN_HEIGHT = 150

const AUTO_LAYOUT_BASE_X = 94
const AUTO_LAYOUT_BASE_Y = 98
const AUTO_LAYOUT_COLUMN_GAP = 240
const AUTO_LAYOUT_ROW_GAP = 220

const CURVE_FACTOR = 0.4
const CURVE_MIN = 50

const wrapperRef = ref(null)
const canvasRef = ref(null)
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const canvasDragState = ref(null)
const movedByDrag = ref(false)
const nodePositions = ref({})
const edgeOffsets = ref({})
const containerOffsets = ref({})

const nodeDragState = ref(null)
const edgeDragState = ref(null)
const containerDragState = ref(null)

const nodeTypeRank = {
  start: 0,
  llm: 1,
  invoke: 2,
  handoff: 3,
  end: 4
}

const nodeColors = {
  start: 'bg-emerald-100 border-emerald-500 text-emerald-900',
  llm: 'bg-indigo-100 border-indigo-500 text-indigo-900',
  invoke: 'bg-fuchsia-100 border-fuchsia-500 text-fuchsia-900',
  handoff: 'bg-sky-100 border-sky-500 text-sky-900',
  end: 'bg-rose-100 border-rose-500 text-rose-900'
}

const nodeLabels = {
  start: 'START',
  llm: 'LLM',
  invoke: 'INVOKE',
  handoff: 'HANDOFF',
  end: 'END'
}

const edgeTypeLabels = {
  call: '调用',
  return: '返回',
  retry: '重试',
  seq: '顺序'
}

const edgeRelationLabels = {
  intra: '容器内',
  cross: '跨容器',
  partial: '跨未分配'
}

const edgeStyleMap = {
  intra: {
    color: '#475569',
    activeColor: '#1d4ed8',
    dash: '',
    markerId: 'execution-graph-arrow-intra'
  },
  cross: {
    color: '#b45309',
    activeColor: '#1d4ed8',
    dash: '7 5',
    markerId: 'execution-graph-arrow-cross'
  },
  partial: {
    color: '#7c3aed',
    activeColor: '#1d4ed8',
    dash: '4 4',
    markerId: 'execution-graph-arrow-partial'
  }
}

const containerPalettes = {
  human: {
    stroke: '#0f766e',
    fill: 'rgba(20, 184, 166, 0.10)',
    header: 'rgba(20, 184, 166, 0.16)',
    text: '#134e4a'
  },
  agent: {
    stroke: '#2563eb',
    fill: 'rgba(59, 130, 246, 0.10)',
    header: 'rgba(59, 130, 246, 0.18)',
    text: '#1e3a8a'
  },
  system: {
    stroke: '#7c3aed',
    fill: 'rgba(124, 58, 237, 0.10)',
    header: 'rgba(124, 58, 237, 0.18)',
    text: '#4c1d95'
  },
  unassigned: {
    stroke: '#64748b',
    fill: 'rgba(148, 163, 184, 0.10)',
    header: 'rgba(148, 163, 184, 0.18)',
    text: '#334155'
  }
}

const toNumber = (value, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const clamp = (value, minValue = 0) => Math.max(value, minValue)

const round2 = (value) => Math.round(value * 100) / 100

const normalizeLabel = (value, fallback = '') => {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

const sortByOrderAndLabel = (a, b) => {
  const orderDiff = toNumber(a?.order_index, 0) - toNumber(b?.order_index, 0)
  if (orderDiff !== 0) return orderDiff
  const aLabel = normalizeLabel(a?.label, normalizeLabel(a?.container_key, ''))
  const bLabel = normalizeLabel(b?.label, normalizeLabel(b?.container_key, ''))
  return aLabel.localeCompare(bLabel, 'zh-CN')
}

const sortNodes = (nodes) => {
  return [...nodes].sort((a, b) => {
    const getOrder = (n) => {
      if (n?.node_type === 'start') return -999999
      if (n?.node_type === 'end') return 999999
      return toNumber(n?.order_index, 0)
    }
    const orderDiff = getOrder(a) - getOrder(b)
    if (orderDiff !== 0) return orderDiff
    const rankDiff = toNumber(nodeTypeRank[a?.node_type], 99) - toNumber(nodeTypeRank[b?.node_type], 99)
    if (rankDiff !== 0) return rankDiff
    return normalizeLabel(a?.label, '').localeCompare(normalizeLabel(b?.label, ''), 'zh-CN')
  })
}

const resolveContainerPalette = (roleType, isUnassigned = false) => {
  if (isUnassigned) return containerPalettes.unassigned
  return containerPalettes[roleType] || containerPalettes.agent
}

const buildNodeColumns = (nodes, containers) => {
  const sortedContainers = [...containers].sort(sortByOrderAndLabel)
  const grouped = {}
  sortedContainers.forEach((container) => {
    grouped[container.container_id] = []
  })

  const unassignedNodes = []
  nodes.forEach((node) => {
    if (node.container_id && grouped[node.container_id]) {
      grouped[node.container_id].push(node)
      return
    }
    unassignedNodes.push(node)
  })

  const columns = sortedContainers.map((container) => ({
    id: container.container_id,
    label: normalizeLabel(container.label, container.container_key || '未命名容器'),
    roleType: container.role_type || 'agent',
    isUnassigned: false,
    nodes: sortNodes(grouped[container.container_id] || [])
  }))

  if (unassignedNodes.length > 0) {
    columns.push({
      id: '__unassigned__',
      label: '未分配容器',
      roleType: 'unassigned',
      isUnassigned: true,
      nodes: sortNodes(unassignedNodes)
    })
  }

  return columns
}

const buildAutoLayout = (nodes, edges, containers) => {
  const positions = {}

  const sortedNodes = sortNodes(nodes)

  const laneSeen = new Set()
  const laneOrderList = []

  sortedNodes.forEach((node) => {
    const lk = node.subgraph_id || node.container_id || 'unassigned'
    if (!laneSeen.has(lk)) {
      laneSeen.add(lk)
      laneOrderList.push(lk)
    }
  })

  const laneByKey = new Map()
  laneOrderList.forEach((lk, idx) => laneByKey.set(lk, idx))
  const unassignedLaneIdx = laneOrderList.length

  const incomingEdges = new Map()
  edges.forEach((edge) => {
    if (!incomingEdges.has(edge.target_node_id)) incomingEdges.set(edge.target_node_id, [])
    incomingEdges.get(edge.target_node_id).push(edge.source_node_id)
  })

  const nodeCol = new Map()
  const colOccupied = new Map()

  sortedNodes.forEach((node) => {
    const lk = node.subgraph_id || node.container_id || 'unassigned'
    const laneIdx = laneByKey.has(lk) ? laneByKey.get(lk) : unassignedLaneIdx
    if (!colOccupied.has(laneIdx)) colOccupied.set(laneIdx, new Set())

    let minCol = 0
    const sources = incomingEdges.get(node.node_id) || []
    sources.forEach((srcId) => {
      if (nodeCol.has(srcId)) {
        minCol = Math.max(minCol, nodeCol.get(srcId) + 1)
      }
    })

    while (colOccupied.get(laneIdx).has(minCol)) {
      minCol++
    }

    nodeCol.set(node.node_id, minCol)
    colOccupied.get(laneIdx).add(minCol)

    positions[node.node_id] = {
      x: AUTO_LAYOUT_BASE_X + minCol * AUTO_LAYOUT_COLUMN_GAP + (minCol % 2 === 0 ? 0 : 8),
      y: AUTO_LAYOUT_BASE_Y + laneIdx * AUTO_LAYOUT_ROW_GAP
    }
  })

  return positions
}

const syncLayoutState = () => {
  const incomingNodePositions = props.layout?.node_positions || {}
  const incomingEdgeOffsets = props.layout?.edge_offsets || {}
  const incomingContainerOffsets = props.layout?.container_offsets || {}
  const autoLayout = buildAutoLayout(props.nodes, props.edges, props.containers)
  const mergedPositions = {}

  props.nodes.forEach((node) => {
    const nodeId = node.node_id
    const incoming = incomingNodePositions[nodeId]
    const existing = nodePositions.value[nodeId]
    const fallback = autoLayout[nodeId] || { x: MIN_X, y: MIN_Y }
    const source = incoming || existing || fallback

    mergedPositions[nodeId] = {
      x: clamp(toNumber(source?.x, fallback.x), MIN_X),
      y: clamp(toNumber(source?.y, fallback.y), MIN_Y)
    }
  })

  nodePositions.value = mergedPositions

  const mergedOffsets = {}
  props.edges.forEach((edge) => {
    const edgeId = edge.edge_id
    const incoming = incomingEdgeOffsets[edgeId]
    const existing = edgeOffsets.value[edgeId]
    const source = incoming || existing || { dx: 0, dy: 0 }

    mergedOffsets[edgeId] = {
      dx: toNumber(source?.dx, 0),
      dy: toNumber(source?.dy, 0)
    }
  })

  edgeOffsets.value = mergedOffsets

  const mergedContainerOffsets = {}
  props.containers.forEach((container) => {
    const containerId = container.container_id
    const incoming = incomingContainerOffsets[containerId]
    const existing = containerOffsets.value[containerId]
    const source = incoming || existing || { dx: 0, dy: 0 }
    mergedContainerOffsets[containerId] = {
      dx: toNumber(source?.dx, 0),
      dy: toNumber(source?.dy, 0)
    }
  })

  const unassignedOffset = incomingContainerOffsets.__unassigned__ || containerOffsets.value.__unassigned__
  if (unassignedOffset) {
    mergedContainerOffsets.__unassigned__ = {
      dx: toNumber(unassignedOffset?.dx, 0),
      dy: toNumber(unassignedOffset?.dy, 0)
    }
  }

  containerOffsets.value = mergedContainerOffsets
}

watch([() => props.nodes, () => props.edges, () => props.containers, () => props.layout], syncLayoutState, {
  immediate: true,
  deep: true
})

const emitLayoutChange = () => {
  const normalizedPositions = {}
  Object.entries(nodePositions.value).forEach(([nodeId, pos]) => {
    normalizedPositions[nodeId] = {
      x: round2(toNumber(pos.x)),
      y: round2(toNumber(pos.y))
    }
  })

  const normalizedEdgeOffsets = {}
  Object.entries(edgeOffsets.value).forEach(([edgeId, offset]) => {
    normalizedEdgeOffsets[edgeId] = {
      dx: round2(toNumber(offset.dx)),
      dy: round2(toNumber(offset.dy))
    }
  })

  const normalizedContainerOffsets = {}
  Object.entries(containerOffsets.value).forEach(([containerId, offset]) => {
    normalizedContainerOffsets[containerId] = {
      dx: round2(toNumber(offset.dx)),
      dy: round2(toNumber(offset.dy))
    }
  })

  emit('layout-change', {
    node_positions: normalizedPositions,
    edge_offsets: normalizedEdgeOffsets,
    container_offsets: normalizedContainerOffsets
  })
}

const zoomIn = () => {
  const newZoom = Math.min(zoom.value + 0.2, 3)
  applyZoomCenter(newZoom)
}
const zoomOut = () => {
  const newZoom = Math.max(zoom.value - 0.2, 0.2)
  applyZoomCenter(newZoom)
}
const resetZoom = () => {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

const applyZoomCenter = (newZoom) => {
  if (!wrapperRef.value) return
  const wrapperRect = wrapperRef.value.getBoundingClientRect()
  const centerX = wrapperRect.width / 2
  const centerY = wrapperRect.height / 2

  const localX = (centerX - panX.value) / zoom.value
  const localY = (centerY - panY.value) / zoom.value

  zoom.value = newZoom
  panX.value = centerX - localX * newZoom
  panY.value = centerY - localY * newZoom
}
const findScrollableParent = (el) => {
  let current = el?.parentElement
  while (current) {
    const style = window.getComputedStyle(current)
    const overflowY = style.overflowY
    if ((overflowY === 'auto' || overflowY === 'scroll') && current.scrollHeight > current.clientHeight) {
      return current
    }
    current = current.parentElement
  }
  return null
}

const handleWheel = (event) => {
  event.preventDefault()
  event.stopPropagation()
  const scrollable = findScrollableParent(wrapperRef.value)
  if (scrollable) {
    scrollable.scrollTop += event.deltaY
    scrollable.scrollLeft += event.deltaX
  }
}



const handleCanvasPointerDown = (event) => {
  if (event.button !== undefined && event.button !== 0 && event.button !== 1) return
  movedByDrag.value = false
  canvasDragState.value = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originPanX: panX.value,
    originPanY: panY.value
  }
  if (wrapperRef.value) {
    wrapperRef.value.setPointerCapture(event.pointerId)
  }
}

const toCanvasPoint = (event) => {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: (event.clientX - rect.left) / zoom.value,
    y: (event.clientY - rect.top) / zoom.value
  }
}

const handleNodePointerDown = (node, event) => {
  if (event.button !== undefined && event.button !== 0) return
  const nodeId = node.node_id
  const position = nodePositions.value[nodeId] || { x: MIN_X, y: MIN_Y }
  const pointer = toCanvasPoint(event)

  movedByDrag.value = false
  nodeDragState.value = {
    pointerId: event.pointerId,
    nodeId,
    startX: pointer.x,
    startY: pointer.y,
    originX: position.x,
    originY: position.y
  }

  event.preventDefault()
}

const handleEdgePointerDown = (edgePath, event) => {
  if (event.button !== undefined && event.button !== 0) return
  const pointer = toCanvasPoint(event)
  const current = edgeOffsets.value[edgePath.id] || { dx: 0, dy: 0 }

  const edge = props.edges.find(e => e.edge_id === edgePath.id)
  const isSelfLoop = edge && edge.source_node_id === edge.target_node_id

  movedByDrag.value = false
  emit('select-edge', edgePath.id)
  edgeDragState.value = {
    pointerId: event.pointerId,
    edgeId: edgePath.id,
    isSelfLoop,
    startX: pointer.x,
    startY: pointer.y,
    originDx: toNumber(current.dx, 0),
    originDy: toNumber(current.dy, 0)
  }

  event.preventDefault()
}

const resolveNodeContainerId = (node) => {
  if (!node?.container_id) return '__unassigned__'
  const exists = props.containers.some((container) => container.container_id === node.container_id)
  return exists ? node.container_id : '__unassigned__'
}

const handleContainerPointerDown = (box, event) => {
  if (event.button !== undefined && event.button !== 0) return
  const pointer = toCanvasPoint(event)
  const targetContainerId = box.id
  const nodeIds = props.nodes
    .filter((node) => resolveNodeContainerId(node) === targetContainerId)
    .map((node) => node.node_id)

  const originNodePositions = {}
  nodeIds.forEach((nodeId) => {
    const pos = nodePositions.value[nodeId] || { x: MIN_X, y: MIN_Y }
    originNodePositions[nodeId] = { x: pos.x, y: pos.y }
  })

  const currentOffset = containerOffsets.value[targetContainerId] || { dx: 0, dy: 0 }

  movedByDrag.value = false
  emit('select-container', targetContainerId)
  containerDragState.value = {
    pointerId: event.pointerId,
    containerId: targetContainerId,
    nodeIds,
    originNodePositions,
    originOffsetDx: toNumber(currentOffset.dx, 0),
    originOffsetDy: toNumber(currentOffset.dy, 0),
    startX: pointer.x,
    startY: pointer.y
  }

  event.preventDefault()
}

const handleContainerClick = (containerId) => {
  if (movedByDrag.value) {
    movedByDrag.value = false
    return
  }
  emit('select-container', containerId)
}

const handleGlobalPointerMove = (event) => {
  if (canvasDragState.value && canvasDragState.value.pointerId === event.pointerId) {
    const deltaX = event.clientX - canvasDragState.value.startX
    const deltaY = event.clientY - canvasDragState.value.startY
    panX.value = canvasDragState.value.originPanX + deltaX
    panY.value = canvasDragState.value.originPanY + deltaY
    movedByDrag.value = true
    return
  }

  if (nodeDragState.value && nodeDragState.value.pointerId === event.pointerId) {
    const pointer = toCanvasPoint(event)
    const deltaX = pointer.x - nodeDragState.value.startX
    const deltaY = pointer.y - nodeDragState.value.startY

    nodePositions.value = {
      ...nodePositions.value,
      [nodeDragState.value.nodeId]: {
        x: clamp(nodeDragState.value.originX + deltaX, MIN_X),
        y: clamp(nodeDragState.value.originY + deltaY, MIN_Y)
      }
    }

    movedByDrag.value = true
    return
  }

  if (containerDragState.value && containerDragState.value.pointerId === event.pointerId) {
    const pointer = toCanvasPoint(event)
    const deltaX = pointer.x - containerDragState.value.startX
    const deltaY = pointer.y - containerDragState.value.startY

    if (containerDragState.value.nodeIds.length > 0) {
      const nextPositions = { ...nodePositions.value }
      containerDragState.value.nodeIds.forEach((nodeId) => {
        const origin = containerDragState.value.originNodePositions[nodeId] || { x: MIN_X, y: MIN_Y }
        nextPositions[nodeId] = {
          x: clamp(origin.x + deltaX, MIN_X),
          y: clamp(origin.y + deltaY, MIN_Y)
        }
      })
      nodePositions.value = nextPositions
    } else {
      containerOffsets.value = {
        ...containerOffsets.value,
        [containerDragState.value.containerId]: {
          dx: containerDragState.value.originOffsetDx + deltaX,
          dy: containerDragState.value.originOffsetDy + deltaY
        }
      }
    }

    movedByDrag.value = true
    return
  }

    if (edgeDragState.value && edgeDragState.value.pointerId === event.pointerId) {
    const pointer = toCanvasPoint(event)
    const deltaX = pointer.x - edgeDragState.value.startX
    const deltaY = pointer.y - edgeDragState.value.startY

    // normal cubic bezier midpoint moves by 0.75, self-loops move by 1.0.
    const DRAG_SCALE = edgeDragState.value.isSelfLoop ? 1.0 : 0.75

    edgeOffsets.value = {
      ...edgeOffsets.value,
      [edgeDragState.value.edgeId]: {
        dx: edgeDragState.value.originDx + deltaX / DRAG_SCALE,
        dy: edgeDragState.value.originDy + deltaY / DRAG_SCALE
      }
    }

    movedByDrag.value = true
  }
}

const finishDragging = (event) => {
  if (canvasDragState.value && canvasDragState.value.pointerId === event.pointerId) {
    canvasDragState.value = null
    return
  }

  if (nodeDragState.value && nodeDragState.value.pointerId === event.pointerId) {
    nodeDragState.value = null
    emitLayoutChange()
    return
  }

  if (containerDragState.value && containerDragState.value.pointerId === event.pointerId) {
    containerDragState.value = null
    emitLayoutChange()
    return
  }

  if (edgeDragState.value && edgeDragState.value.pointerId === event.pointerId) {
    edgeDragState.value = null
    emitLayoutChange()
  }
}

const handleNodeClick = (node) => {
  if (movedByDrag.value) {
    movedByDrag.value = false
    return
  }
  emit('select-node', node.node_id)
}

const handleEdgeClick = (edgePath) => {
  if (movedByDrag.value) {
    movedByDrag.value = false
    return
  }
  emit('select-edge', edgePath.id)
}

const nodeById = computed(() => {
  const map = {}
  props.nodes.forEach((node) => {
    map[node.node_id] = node
  })
  return map
})

const containerBoxes = computed(() => {
  const columns = buildNodeColumns(props.nodes, props.containers)
  const boxes = []

  let minPopulatedY = AUTO_LAYOUT_BASE_Y
  let hasPositionedNodes = false
  let totalEmptyContainers = 0

  columns.forEach((column) => {
    const positionedNodes = column.nodes
      .map((node) => ({ position: nodePositions.value[node.node_id] }))
      .filter((item) => item.position)

    if (positionedNodes.length > 0) {
      const minY = Math.min(...positionedNodes.map((item) => item.position.y))
      if (!hasPositionedNodes) {
        minPopulatedY = minY
        hasPositionedNodes = true
      } else {
        minPopulatedY = Math.min(minPopulatedY, minY)
      }
    } else {
      totalEmptyContainers++
    }
  })

  let currentEmptyIndex = 0

  columns.forEach((column) => {
    const positionedNodes = column.nodes
      .map((node) => ({ position: nodePositions.value[node.node_id] }))
      .filter((item) => item.position)

    let left
    let top
    let width
    let height

    if (positionedNodes.length > 0) {
      const minX = Math.min(...positionedNodes.map((item) => item.position.x))
      const minY = Math.min(...positionedNodes.map((item) => item.position.y))
      const maxX = Math.max(...positionedNodes.map((item) => item.position.x))
      const maxY = Math.max(...positionedNodes.map((item) => item.position.y))

      left = clamp(minX - CONTAINER_PADDING_X, 10)
      top = minY - CONTAINER_HEADER_HEIGHT - 14
      width = Math.max(CONTAINER_MIN_WIDTH, maxX - minX + NODE_WIDTH + CONTAINER_PADDING_X * 2)
      height = Math.max(
        CONTAINER_MIN_HEIGHT,
        maxY - minY + NODE_HEIGHT + CONTAINER_HEADER_HEIGHT + CONTAINER_PADDING_Y
      )
    } else {
      left = clamp(AUTO_LAYOUT_BASE_X - CONTAINER_PADDING_X, 10)
      
      const emptyBaseY = hasPositionedNodes 
        ? minPopulatedY - totalEmptyContainers * AUTO_LAYOUT_ROW_GAP 
        : AUTO_LAYOUT_BASE_Y
        
      top = emptyBaseY + currentEmptyIndex * AUTO_LAYOUT_ROW_GAP - CONTAINER_HEADER_HEIGHT - 14
      width = CONTAINER_MIN_WIDTH
      height = CONTAINER_MIN_HEIGHT
      currentEmptyIndex++
    }

    boxes.push({
      id: column.id,
      label: column.label,
      roleType: column.roleType,
      nodeCount: column.nodes.length,
      left: clamp(left + toNumber(containerOffsets.value[column.id]?.dx, 0), 10),
      top: top + toNumber(containerOffsets.value[column.id]?.dy, 0),
      width,
      height,
      isUnassigned: column.isUnassigned,
      palette: resolveContainerPalette(column.roleType, column.isUnassigned)
    })
  })

  return boxes
})

const resolveEdgeRelation = (sourceContainerId, targetContainerId) => {
  const sourceId = sourceContainerId || '__unassigned__'
  const targetId = targetContainerId || '__unassigned__'
  if (sourceId === targetId) return 'intra'
  if (sourceId === '__unassigned__' || targetId === '__unassigned__') return 'partial'
  return 'cross'
}

// Returns the unit vector pointing outward from a port side
const getSideVector = (side) => {
  if (side === 'right')  return [1, 0]
  if (side === 'left')   return [-1, 0]
  if (side === 'bottom') return [0, 1]
  if (side === 'top')    return [0, -1]
  return [0, 0]
}

// Returns the absolute canvas coordinate of a port on a node
const getPortXY = (pos, side) => {
  switch (side) {
    case 'right':  return { x: pos.x + NODE_WIDTH,      y: pos.y + NODE_HEIGHT / 2 }
    case 'left':   return { x: pos.x,                   y: pos.y + NODE_HEIGHT / 2 }
    case 'bottom': return { x: pos.x + NODE_WIDTH / 2,  y: pos.y + NODE_HEIGHT }
    case 'top':    return { x: pos.x + NODE_WIDTH / 2,  y: pos.y }
  }
}

// Picks source/target port sides based on the relative position of the two nodes
const computeEdgeSides = (sourcePos, targetPos, edge) => {
  if (edge?.config_json?.session_chain) {
    return ['right', 'left']
  }
  const dx = (targetPos.x + NODE_WIDTH / 2) - (sourcePos.x + NODE_WIDTH / 2)
  const dy = (targetPos.y + NODE_HEIGHT / 2) - (sourcePos.y + NODE_HEIGHT / 2)
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? ['right', 'left'] : ['left', 'right']
  }
  return dy >= 0 ? ['bottom', 'top'] : ['top', 'bottom']
}

const edgePaths = computed(() => {
  const mappings = props.edges.map((edge) => {
    const sourcePos = nodePositions.value[edge.source_node_id]
    const targetPos = nodePositions.value[edge.target_node_id]
    if (!sourcePos || !targetPos) return null

    const sourceNode = nodeById.value[edge.source_node_id]
    const targetNode = nodeById.value[edge.target_node_id]
    const relation = resolveEdgeRelation(sourceNode?.container_id, targetNode?.container_id)
    const style = edgeStyleMap[relation] || edgeStyleMap.intra
    const offset = edgeOffsets.value[edge.edge_id] || { dx: 0, dy: 0 }
    const odx = toNumber(offset.dx, 0)
    const ody = toNumber(offset.dy, 0)

    const displayLabel = edge.label
      ? `${edge.label} · ${edgeRelationLabels[relation] || '连线'}`
      : `${edgeTypeLabels[edge.edge_type] || edge.edge_type || '边'} · ${edgeRelationLabels[relation] || '连线'}`

    const isSelfLoop = edge.source_node_id === edge.target_node_id
    if (isSelfLoop) {
      return { edge, isSelfLoop, sourcePos, targetPos, relation, style, odx, ody, displayLabel }
    }

    const [sourceSide, targetSide] = computeEdgeSides(sourcePos, targetPos, edge)
    return { edge, isSelfLoop, sourcePos, targetPos, relation, style, odx, ody, displayLabel, sourceSide, targetSide }
  }).filter(Boolean)

  const ports = {}
  mappings.forEach(m => {
    if (m.isSelfLoop) return
    const sKey = `${m.edge.source_node_id}:::${m.sourceSide}`
    const tKey = `${m.edge.target_node_id}:::${m.targetSide}`

    if (!ports[sKey]) ports[sKey] = []
    if (!ports[tKey]) ports[tKey] = []

    ports[sKey].push({ edgeId: m.edge.edge_id, type: 'source', otherX: m.targetPos.x, otherY: m.targetPos.y })
    ports[tKey].push({ edgeId: m.edge.edge_id, type: 'target', otherX: m.sourcePos.x, otherY: m.sourcePos.y })
  })

  const portOffsets = {}
  Object.entries(ports).forEach(([key, connections]) => {
    const side = key.split(':::')[1]
    connections.sort((a, b) => {
      if (side === 'top' || side === 'bottom') {
        const diff = a.otherX - b.otherX
        return diff !== 0 ? diff : a.edgeId.localeCompare(b.edgeId)
      } else {
        const diff = a.otherY - b.otherY
        return diff !== 0 ? diff : a.edgeId.localeCompare(b.edgeId)
      }
    })

    const count = connections.length
    connections.forEach((conn, index) => {
      let dx = 0
      let dy = 0
      if (side === 'top' || side === 'bottom') {
        const span = Math.min((count - 1) * 24, NODE_WIDTH - 32)
        const step = count > 1 ? span / (count - 1) : 0
        dx = count > 1 ? (index * step - span / 2) : 0
      } else {
        const span = Math.min((count - 1) * 16, NODE_HEIGHT - 24)
        const step = count > 1 ? span / (count - 1) : 0
        dy = count > 1 ? (index * step - span / 2) : 0
      }
      portOffsets[`${conn.edgeId}_${conn.type}`] = { dx, dy }
    })
  })

  return mappings.map((m) => {
    const edge = m.edge
    if (m.isSelfLoop) {
      const sx = m.sourcePos.x + NODE_WIDTH
      const sy = m.sourcePos.y + NODE_HEIGHT * 0.25
      const ex = m.sourcePos.x + NODE_WIDTH
      const ey = m.sourcePos.y + NODE_HEIGHT * 0.75
      const loopR = 50 + m.odx
      const c1x = sx + loopR
      const c1y = sy - 20
      const c2x = ex + loopR
      const c2y = ey + 20
      const controlX = sx + loopR
      const controlY = m.sourcePos.y + NODE_HEIGHT / 2
      return {
        id: edge.edge_id, edgeType: edge.edge_type, label: edge.label, relation: m.relation,
        relationLabel: edgeRelationLabels[m.relation] || '连线', style: m.style, displayLabel: m.displayLabel,
        path: `M ${sx} ${sy} C ${c1x} ${c1y} ${c2x} ${c2y} ${ex} ${ey}`,
        controlX, controlY, labelX: controlX + 12, labelY: controlY - 10
      }
    }

    const startBase = getPortXY(m.sourcePos, m.sourceSide)
    const endBase = getPortXY(m.targetPos, m.targetSide)
    const sOffset = portOffsets[`${edge.edge_id}_source`] || { dx: 0, dy: 0 }
    const tOffset = portOffsets[`${edge.edge_id}_target`] || { dx: 0, dy: 0 }

    const start = { x: startBase.x + sOffset.dx, y: startBase.y + sOffset.dy }
    const end = { x: endBase.x + tOffset.dx, y: endBase.y + tOffset.dy }

    const [svx, svy] = getSideVector(m.sourceSide)
    const [evx, evy] = getSideVector(m.targetSide)
    const dist = Math.hypot(end.x - start.x, end.y - start.y)
    const curve = Math.max(CURVE_MIN, dist * CURVE_FACTOR)

    const c1x = start.x + svx * curve + m.odx
    const c1y = start.y + svy * curve + m.ody
    const c2x = end.x + evx * curve + m.odx
    const c2y = end.y + evy * curve + m.ody

    const controlX = (c1x + c2x) / 2
    const controlY = (c1y + c2y) / 2

    const t = 0.5
    const labelX = (1-t)**3*start.x + 3*(1-t)**2*t*c1x + 3*(1-t)*t**2*c2x + t**3*end.x
    const labelY = (1-t)**3*start.y + 3*(1-t)**2*t*c1y + 3*(1-t)*t**2*c2y + t**3*end.y

    return {
      id: edge.edge_id, edgeType: edge.edge_type, label: edge.label, relation: m.relation,
      relationLabel: edgeRelationLabels[m.relation] || '连线', style: m.style, displayLabel: m.displayLabel,
      path: `M ${start.x} ${start.y} C ${c1x} ${c1y} ${c2x} ${c2y} ${end.x} ${end.y}`,
      controlX: labelX, controlY: labelY, labelX, labelY
    }
  })
})

onMounted(() => {
  window.addEventListener('pointermove', handleGlobalPointerMove)
  window.addEventListener('pointerup', finishDragging)
  window.addEventListener('pointercancel', finishDragging)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', handleGlobalPointerMove)
  window.removeEventListener('pointerup', finishDragging)
  window.removeEventListener('pointercancel', finishDragging)
})
</script>

<template>
  <div
    ref="wrapperRef"
    class="relative bg-white rounded-xl overflow-hidden select-none touch-none w-full h-full cursor-grab active:cursor-grabbing border border-zinc-300"
    style="min-height: 560px;"
    @pointerdown="handleCanvasPointerDown"
    @wheel.prevent="handleWheel"
  >
    <!-- Background grid -->
    <div
      class="absolute inset-0 pointer-events-none"
      :style="{
        backgroundImage: 'linear-gradient(0deg, rgba(15,23,42,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.04) 1px, transparent 1px)',
        backgroundSize: `${24 * zoom}px ${24 * zoom}px`,
        backgroundPosition: `${panX}px ${panY}px`
      }"
    ></div>

    <div
      ref="canvasRef"
      class="absolute origin-top-left"
      :style="{
        transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
        width: '1px',
        height: '1px'
      }"
    >
      <div class="absolute" style="z-index: 1;">
      <div
        v-for="box in containerBoxes"
        :key="box.id"
        class="absolute rounded-2xl border shadow-sm transition-all"
        :class="props.selectedContainerId === box.id ? 'ring-2 ring-blue-500 shadow-lg' : ''"
        :style="{
          left: `${box.left}px`,
          top: `${box.top}px`,
          width: `${box.width}px`,
          height: `${box.height}px`,
          borderColor: box.palette.stroke,
          background: box.palette.fill
        }"
        @click.stop="handleContainerClick(box.id)"
      >
        <div
          class="h-8 px-3 flex items-center justify-between text-[11px] font-semibold border-b rounded-t-2xl cursor-move select-none touch-none"
          :style="{
            borderColor: box.palette.stroke,
            background: box.palette.header,
            color: box.palette.text
          }"
          @pointerdown.stop="handleContainerPointerDown(box, $event)"
          @click.stop="handleContainerClick(box.id)"
        >
          <span class="truncate">{{ box.label }}</span>
          <span>{{ box.nodeCount }} 节点</span>
        </div>
      </div>
    </div>

    <svg class="absolute pointer-events-none" style="z-index: 2; width: 1px; height: 1px; overflow: visible;">
      <defs>
        <marker id="execution-graph-arrow-intra" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#475569" />
        </marker>
        <marker id="execution-graph-arrow-cross" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#b45309" />
        </marker>
        <marker id="execution-graph-arrow-partial" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#7c3aed" />
        </marker>
      </defs>

      <g v-for="edgePath in edgePaths" :key="edgePath.id">
        <path
          :d="edgePath.path"
          fill="none"
          stroke="transparent"
          stroke-width="16"
          class="cursor-grab pointer-events-auto"
          @pointerdown.stop="handleEdgePointerDown(edgePath, $event)"
          @click.stop="handleEdgeClick(edgePath)"
        />

        <path
          :d="edgePath.path"
          fill="none"
          :marker-end="`url(#${edgePath.style.markerId})`"
          :stroke="selectedId === edgePath.id ? edgePath.style.activeColor : edgePath.style.color"
          :stroke-width="selectedId === edgePath.id ? 2.8 : 2"
          :stroke-dasharray="edgePath.style.dash"
          class="pointer-events-none transition-all"
        />

        <circle
          :cx="edgePath.controlX"
          :cy="edgePath.controlY"
          :r="selectedId === edgePath.id ? 6 : 5"
          :fill="selectedId === edgePath.id ? edgePath.style.activeColor : edgePath.style.color"
          class="cursor-grab transition-all pointer-events-auto"
          @pointerdown.stop="handleEdgePointerDown(edgePath, $event)"
          @click.stop="handleEdgeClick(edgePath)"
        />

        <text
          v-if="edgePath.displayLabel"
          :x="edgePath.labelX"
          :y="edgePath.labelY - 10"
          font-size="12"
          :fill="selectedId === edgePath.id ? edgePath.style.activeColor : '#334155'"
          text-anchor="middle"
          class="pointer-events-none select-none"
        >
          {{ edgePath.displayLabel }}
        </text>
      </g>
    </svg>

    <div
      v-for="node in nodes"
      :key="node.node_id"
      class="absolute select-none touch-none cursor-move transition-shadow"
      :class="[
        nodeColors[node.node_type] || nodeColors.node,
        selectedId === node.node_id
          ? 'ring-2 ring-blue-500 shadow-lg border-2'
          : 'border-2 shadow-sm hover:shadow-md'
      ]"
      :style="{
        left: `${nodePositions[node.node_id]?.x ?? MIN_X}px`,
        top: `${nodePositions[node.node_id]?.y ?? MIN_Y}px`,
        width: `${NODE_WIDTH}px`,
        height: `${NODE_HEIGHT}px`,
        zIndex: selectedId === node.node_id ? 16 : 10
      }"
      @pointerdown.stop="handleNodePointerDown(node, $event)"
      @click.stop="handleNodeClick(node)"
    >
      <div class="flex flex-col items-center justify-center h-full px-2">
        <span class="text-[10px] tracking-wide font-bold mb-1">{{ nodeLabels[node.node_type] || 'NODE' }}</span>
        <span class="text-xs font-medium truncate w-full text-center">{{ node.label }}</span>
      </div>
      <div class="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
      <div class="absolute -right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
      <div class="absolute left-1/2 -top-1.5 -translate-x-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
      <div class="absolute left-1/2 -bottom-1.5 -translate-x-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
    </div>

    </div> <!-- close canvasRef -->

    <div class="absolute bottom-4 right-4 flex shadow-[0_2px_10px_rgba(0,0,0,0.08)] border border-zinc-200 rounded-lg overflow-hidden z-20 bg-white/95 backdrop-blur pointer-events-auto">
      <button class="px-2.5 py-1.5 hover:bg-zinc-100 text-zinc-600 transition-colors cursor-pointer" @pointerdown.stop @click.stop="zoomIn" title="放大">
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
      </button>
      <button class="px-3 py-1.5 border-l border-r border-zinc-200 hover:bg-zinc-100 text-zinc-700 transition-colors cursor-pointer" @pointerdown.stop @click.stop="resetZoom" title="重置视角">
        <span class="text-xs font-medium w-[42px] inline-block text-center">{{ Math.round(zoom * 100) }}%</span>
      </button>
      <button class="px-2.5 py-1.5 hover:bg-zinc-100 text-zinc-600 transition-colors cursor-pointer" @pointerdown.stop @click.stop="zoomOut" title="缩小">
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line></svg>
      </button>
    </div>

    <div class="absolute right-4 top-3 px-2 py-1 text-[11px] text-zinc-500 bg-white/90 rounded border border-zinc-200 pointer-events-none" style="z-index: 18;">
      拖动容器标题可整体移动；拖动节点可微调；拖动边中点可调整连线路径
    </div>

    <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center text-zinc-400 pointer-events-none" style="z-index: 10;">
      <div class="text-center bg-white/60 px-4 py-2 rounded-xl backdrop-blur-sm">
        <p class="text-sm font-medium">暂无节点</p>
        <p class="text-xs mt-1">等待模型生成或配置连接</p>
      </div>
    </div>
  </div>
</template>
