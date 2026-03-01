<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
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
  layout: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['select-node', 'select-edge', 'layout-change'])

const NODE_WIDTH = 136
const NODE_HEIGHT = 64
const MIN_X = 24
const MIN_Y = 24

const canvasRef = ref(null)
const movedByDrag = ref(false)
const nodePositions = ref({})
const edgeOffsets = ref({})

const nodeDragState = ref(null)
const edgeDragState = ref(null)

const nodeColors = {
  start: 'bg-emerald-100 border-emerald-500 text-emerald-900',
  task: 'bg-blue-100 border-blue-500 text-blue-900',
  decision: 'bg-amber-100 border-amber-500 text-amber-900',
  handoff: 'bg-sky-100 border-sky-500 text-sky-900',
  end: 'bg-rose-100 border-rose-500 text-rose-900'
}

const nodeLabels = {
  start: 'START',
  task: 'TASK',
  decision: 'DECISION',
  handoff: 'HANDOFF',
  end: 'END'
}

const toNumber = (value, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const clamp = (value, minValue = 0) => Math.max(value, minValue)

const round2 = (value) => Math.round(value * 100) / 100

const buildAutoLayout = (nodes) => {
  const positions = {}
  const gridCols = 4
  const gridSpacingX = 220
  const gridSpacingY = 140

  const startNodes = nodes.filter((n) => n.node_type === 'start')
  const endNodes = nodes.filter((n) => n.node_type === 'end')
  const normalNodes = nodes.filter((n) => n.node_type !== 'start' && n.node_type !== 'end')

  startNodes.forEach((node, index) => {
    positions[node.node_id] = { x: 80, y: 90 + index * gridSpacingY }
  })

  normalNodes.forEach((node, index) => {
    const col = index % gridCols
    const row = Math.floor(index / gridCols)
    positions[node.node_id] = {
      x: 260 + col * gridSpacingX,
      y: 90 + row * gridSpacingY
    }
  })

  endNodes.forEach((node, index) => {
    positions[node.node_id] = {
      x: 260 + gridCols * gridSpacingX,
      y: 90 + index * gridSpacingY
    }
  })

  return positions
}

const syncLayoutState = () => {
  const incomingNodePositions = props.layout?.node_positions || {}
  const incomingEdgeOffsets = props.layout?.edge_offsets || {}
  const autoLayout = buildAutoLayout(props.nodes)
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
}

watch([() => props.nodes, () => props.edges, () => props.layout], syncLayoutState, {
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

  emit('layout-change', {
    node_positions: normalizedPositions,
    edge_offsets: normalizedEdgeOffsets
  })
}

const toCanvasPoint = (event) => {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
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

  movedByDrag.value = false
  emit('select-edge', edgePath.id)
  edgeDragState.value = {
    pointerId: event.pointerId,
    edgeId: edgePath.id,
    startX: pointer.x,
    startY: pointer.y,
    originDx: toNumber(current.dx, 0),
    originDy: toNumber(current.dy, 0)
  }

  event.preventDefault()
}

const handleGlobalPointerMove = (event) => {
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

  if (edgeDragState.value && edgeDragState.value.pointerId === event.pointerId) {
    const pointer = toCanvasPoint(event)
    const deltaX = pointer.x - edgeDragState.value.startX
    const deltaY = pointer.y - edgeDragState.value.startY

    edgeOffsets.value = {
      ...edgeOffsets.value,
      [edgeDragState.value.edgeId]: {
        dx: edgeDragState.value.originDx + deltaX,
        dy: edgeDragState.value.originDy + deltaY
      }
    }

    movedByDrag.value = true
  }
}

const finishDragging = (event) => {
  if (nodeDragState.value && nodeDragState.value.pointerId === event.pointerId) {
    nodeDragState.value = null
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

const edgePaths = computed(() => {
  return props.edges
    .map((edge) => {
      const sourcePos = nodePositions.value[edge.source_node_id]
      const targetPos = nodePositions.value[edge.target_node_id]
      if (!sourcePos || !targetPos) return null

      const startX = sourcePos.x + NODE_WIDTH
      const startY = sourcePos.y + NODE_HEIGHT / 2
      const endX = targetPos.x
      const endY = targetPos.y + NODE_HEIGHT / 2

      const baseCenterX = (startX + endX) / 2
      const baseCenterY = (startY + endY) / 2
      const offset = edgeOffsets.value[edge.edge_id] || { dx: 0, dy: 0 }
      const controlX = baseCenterX + toNumber(offset.dx, 0)
      const controlY = baseCenterY + toNumber(offset.dy, 0)

      const t = 0.5
      const labelX =
        (1 - t) * (1 - t) * startX +
        2 * (1 - t) * t * controlX +
        t * t * endX
      const labelY =
        (1 - t) * (1 - t) * startY +
        2 * (1 - t) * t * controlY +
        t * t * endY

      return {
        id: edge.edge_id,
        edgeType: edge.edge_type,
        label: edge.label,
        path: `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`,
        controlX,
        controlY,
        labelX,
        labelY
      }
    })
    .filter(Boolean)
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
    ref="canvasRef"
    class="relative bg-white border border-zinc-300 rounded-xl overflow-hidden"
    style="min-height: 560px; background-image: linear-gradient(0deg, rgba(15,23,42,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.04) 1px, transparent 1px); background-size: 24px 24px;"
  >
    <svg class="absolute inset-0 w-full h-full" style="z-index: 1;">
      <defs>
        <marker id="execution-graph-arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
        </marker>
      </defs>

      <g v-for="edgePath in edgePaths" :key="edgePath.id">
        <path
          :d="edgePath.path"
          fill="none"
          stroke="transparent"
          stroke-width="16"
          class="cursor-grab"
          @pointerdown.stop="handleEdgePointerDown(edgePath, $event)"
          @click.stop="handleEdgeClick(edgePath)"
        />

        <path
          :d="edgePath.path"
          fill="none"
          marker-end="url(#execution-graph-arrow)"
          :stroke="selectedId === edgePath.id ? '#2563eb' : '#64748b'"
          :stroke-width="selectedId === edgePath.id ? 2.8 : 2"
          class="pointer-events-none transition-all"
        />

        <circle
          :cx="edgePath.controlX"
          :cy="edgePath.controlY"
          :r="selectedId === edgePath.id ? 6 : 5"
          :fill="selectedId === edgePath.id ? '#2563eb' : '#94a3b8'"
          class="cursor-grab"
          @pointerdown.stop="handleEdgePointerDown(edgePath, $event)"
          @click.stop="handleEdgeClick(edgePath)"
        />

        <text
          v-if="edgePath.label"
          :x="edgePath.labelX"
          :y="edgePath.labelY - 10"
          font-size="12"
          :fill="selectedId === edgePath.id ? '#1d4ed8' : '#475569'"
          text-anchor="middle"
          class="pointer-events-none select-none"
        >
          {{ edgePath.label }}
        </text>
      </g>
    </svg>

    <div
      v-for="node in nodes"
      :key="node.node_id"
      class="absolute select-none touch-none cursor-move transition-shadow"
      :class="[
        nodeColors[node.node_type] || nodeColors.task,
        selectedId === node.node_id
          ? 'ring-2 ring-blue-500 shadow-lg border-2'
          : 'border-2 shadow-sm hover:shadow-md'
      ]"
      :style="{
        left: `${nodePositions[node.node_id]?.x ?? MIN_X}px`,
        top: `${nodePositions[node.node_id]?.y ?? MIN_Y}px`,
        width: `${NODE_WIDTH}px`,
        height: `${NODE_HEIGHT}px`,
        zIndex: selectedId === node.node_id ? 12 : 8
      }"
      @pointerdown="handleNodePointerDown(node, $event)"
      @click.stop="handleNodeClick(node)"
    >
      <div class="flex flex-col items-center justify-center h-full px-2">
        <span class="text-[10px] tracking-wide font-bold mb-1">{{ nodeLabels[node.node_type] || 'TASK' }}</span>
        <span class="text-xs font-medium truncate w-full text-center">{{ node.label }}</span>
      </div>
      <div class="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
      <div class="absolute -right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-white border border-zinc-400 rounded-full" />
    </div>

    <div class="absolute right-4 top-3 px-2 py-1 text-[11px] text-zinc-500 bg-white/90 rounded border border-zinc-200">
      拖动节点可移动，拖动边中点可调整连线路径
    </div>

    <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center text-zinc-400">
      <div class="text-center">
        <p class="text-sm">暂无节点</p>
        <p class="text-xs mt-1">请从左侧面板添加节点</p>
      </div>
    </div>
  </div>
</template>
