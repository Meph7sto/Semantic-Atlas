/**
 * 会话执行图合并布局工具函数
 * 供 RequirementAgentChat / ConflictAgentChat 等多 Agent 页面共用
 */

export const createEmptyGraphDetail = () => ({ graph: null, containers: [], subgraphs: [], nodes: [], edges: [] })

const SESSION_CONTROLLER_MODE_TO_CONTAINER_KEYS = {
  delegate_requirement: ['requirement_agent'],
  delegate_conflict: ['conflict_detection'],
  delegate_classification: ['requirement_classification_agent']
}

const normalizeContainerKeys = (value) => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean)
}

const isSubgraphBoundaryNode = (node) => {
  if (!node?.subgraph_id) return false
  return node.node_type === 'start' || node.node_type === 'end'
}

const shouldHideNode = (node, options = {}) => {
  if (options.hideSubgraphBoundaryNodes && isSubgraphBoundaryNode(node)) {
    return true
  }
  return false
}

const edgeTypePriority = (edgeType) => {
  switch (String(edgeType || '').trim()) {
    case 'return':
      return 4
    case 'call':
      return 3
    case 'retry':
      return 2
    case 'seq':
      return 1
    default:
      return 0
  }
}

const buildCollapsedEdge = ({ sourceNodeId, targetNodeId, pathEdges = [], hiddenNodeIds = [], fallbackOrder = 0 }) => {
  const chosen = [...pathEdges].sort((a, b) => (
    edgeTypePriority(b?.edge_type) - edgeTypePriority(a?.edge_type)
  ))[0] || {}

  return {
    edge_id: `collapsed:${pathEdges.map((edge) => edge.edge_id).filter(Boolean).join('>') || `${sourceNodeId}>${targetNodeId}`}`,
    graph_id: chosen.graph_id || null,
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
    edge_type: chosen.edge_type || 'seq',
    label: chosen.label || chosen.edge_type || 'seq',
    condition_expr: chosen.condition_expr || null,
    config_json: {
      ...(chosen.config_json || {}),
      collapsed_from_hidden_nodes: hiddenNodeIds,
      collapsed_from_edge_ids: pathEdges.map((edge) => edge.edge_id).filter(Boolean),
      collapsed_for_display: true
    },
    order_index: Number(chosen.order_index ?? fallbackOrder ?? 0),
    created_at: chosen.created_at || ''
  }
}

const collapseHiddenNodes = ({ nodes = [], edges = [], hiddenNodeIds = new Set() }) => {
  if (!hiddenNodeIds.size) {
    return {
      nodes,
      edges
    }
  }

  const visibleNodes = nodes.filter((node) => !hiddenNodeIds.has(node.node_id))
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.node_id))
  const outgoingBySource = new Map()

  edges.forEach((edge) => {
    if (!outgoingBySource.has(edge.source_node_id)) {
      outgoingBySource.set(edge.source_node_id, [])
    }
    outgoingBySource.get(edge.source_node_id).push(edge)
  })

  const collapsedEdges = []
  const dedupe = new Set()

  const pushCollapsedEdge = (edge, pathEdges, hiddenIds) => {
    if (edge.source_node_id === edge.target_node_id) return
    const key = [
      edge.source_node_id,
      edge.target_node_id,
      edge.edge_type,
      edge.condition_expr || ''
    ].join('|')
    if (dedupe.has(key)) return
    dedupe.add(key)
    collapsedEdges.push(edge)
  }

  const shouldTraverseHiddenEdge = (pathEdges, outgoingEdges, nextEdge) => {
    const hasCallBranch = outgoingEdges.some((edge) => edge?.edge_type === 'call')
    const hasNonCallBranch = outgoingEdges.some((edge) => edge?.edge_type !== 'call')

    if (!hasCallBranch || !hasNonCallBranch) {
      return true
    }

    // Hidden invoke boundary nodes act like a fork: caller follows `call`, callee follows `return -> seq`.
    const pathIncludesReturn = pathEdges.some((edge) => edge?.edge_type === 'return')
    if (pathIncludesReturn) {
      return nextEdge?.edge_type !== 'call'
    }

    return nextEdge?.edge_type === 'call'
  }

  const walkHiddenPath = (sourceVisibleId, currentNodeId, pathEdges, visitedHidden) => {
    if (visitedHidden.has(currentNodeId)) return
    visitedHidden.add(currentNodeId)

    const outgoing = outgoingBySource.get(currentNodeId) || []
    outgoing.forEach((nextEdge) => {
      if (!shouldTraverseHiddenEdge(pathEdges, outgoing, nextEdge)) {
        return
      }

      const nextTargetId = nextEdge.target_node_id
      const nextPath = [...pathEdges, nextEdge]
      const hiddenIds = [...visitedHidden]

      if (visibleNodeIds.has(nextTargetId)) {
        pushCollapsedEdge(
          buildCollapsedEdge({
            sourceNodeId: sourceVisibleId,
            targetNodeId: nextTargetId,
            pathEdges: nextPath,
            hiddenNodeIds: hiddenIds,
            fallbackOrder: nextEdge.order_index
          }),
          nextPath,
          hiddenIds
        )
        return
      }

      if (hiddenNodeIds.has(nextTargetId)) {
        walkHiddenPath(sourceVisibleId, nextTargetId, nextPath, new Set(visitedHidden))
      }
    })
  }

  visibleNodes.forEach((node) => {
    const outgoing = outgoingBySource.get(node.node_id) || []
    outgoing.forEach((edge) => {
      const targetId = edge.target_node_id
      if (visibleNodeIds.has(targetId)) {
        pushCollapsedEdge(edge, [edge], [])
        return
      }
      if (hiddenNodeIds.has(targetId)) {
        walkHiddenPath(node.node_id, targetId, [edge], new Set())
      }
    })
  })

  return {
    nodes: visibleNodes,
    edges: collapsedEdges
  }
}

const buildVisibleDetailGraph = (detail, options = {}) => {
  const visibleContainerKeys = resolveVisibleContainerKeys(detail, options)
  const containers = (detail?.containers || []).filter((container) => {
    if (!visibleContainerKeys) return true
    return visibleContainerKeys.has(String(container.container_key || '').trim())
  })
  const visibleContainerIds = new Set(containers.map((container) => container.container_id))
  const nodesInContainers = (detail?.nodes || []).filter((node) => {
    if (!visibleContainerKeys) return true
    return visibleContainerIds.has(node.container_id)
  })
  const hiddenNodeIds = new Set(
    nodesInContainers
      .filter((node) => shouldHideNode(node, options))
      .map((node) => node.node_id)
  )
  const edgesInContainers = (detail?.edges || []).filter((edge) => {
    const sourceNode = nodesInContainers.find((node) => node.node_id === edge.source_node_id)
    const targetNode = nodesInContainers.find((node) => node.node_id === edge.target_node_id)
    return Boolean(sourceNode && targetNode)
  })
  const collapsed = collapseHiddenNodes({
    nodes: nodesInContainers,
    edges: edgesInContainers,
    hiddenNodeIds
  })
  const visibleNodeIds = new Set(collapsed.nodes.map((node) => node.node_id))

  return {
    containers,
    subgraphs: (detail?.subgraphs || []).filter((subgraph) => {
      if (!visibleContainerKeys) return true
      return visibleContainerIds.has(subgraph.container_id)
    }),
    nodes: sortByOrder(collapsed.nodes),
    edges: collapsed.edges.filter((edge) => (
      visibleNodeIds.has(edge.source_node_id) && visibleNodeIds.has(edge.target_node_id)
    ))
  }
}

const resolveVisibleContainerKeys = (detail, options = {}) => {
  if (!options.filterDelegatedContainers) return null

  const meta = detail?.graph?.meta_json || {}
  const selectedKeys = normalizeContainerKeys(meta.selected_container_keys)
  const dispatchedKeys = normalizeContainerKeys(meta.dispatched_agents)
  const delegatedAgent = String(meta.delegated_agent || '').trim()
  const mode = String(meta.session_controller_mode || '').trim()

  const derivedKeys = selectedKeys.length
    ? selectedKeys
    : dispatchedKeys.length
      ? dispatchedKeys
      : delegatedAgent
        ? [delegatedAgent]
        : (SESSION_CONTROLLER_MODE_TO_CONTAINER_KEYS[mode] || [])

  if (!derivedKeys.length) return null
  return new Set(['conductor', ...derivedKeys])
}

export const sortByOrder = (items = []) => {
  return [...items].sort((a, b) => {
    const getOrder = (n) => {
      if (n?.node_type === 'start') return -999999
      if (n?.node_type === 'end') return 999999
      return Number(n?.order_index || 0)
    }
    const orderDiff = getOrder(a) - getOrder(b)
    if (orderDiff !== 0) return orderDiff
    return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
  })
}

export const resolveBoundaryNode = (detail, type) => {
  const nodes = sortByOrder(detail?.nodes || [])
  if (!nodes.length) return null
  if (type === 'start') {
    return nodes.find((node) => node.node_type === 'start') || nodes[0]
  }
  return [...nodes].reverse().find((node) => node.node_type === 'end') || nodes[nodes.length - 1]
}

export const buildMergedSessionGraphDetail = (chainPayload, options = {}) => {
  const details = chainPayload?.graphs || []
  if (!details.length) return createEmptyGraphDetail()

  const mergedContainers = []
  const mergedSubgraphs = []
  const mergedNodes = []
  const mergedEdges = []
  const nodePositions = {}
  const edgeOffsets = {}
  const containerOffsets = {}

  const startX = 94
  const baseY = 98
  const laneHeight = 220
  const colWidth = 240
  const graphRowGap = 140
  const stackGraphsByRow = options.stackGraphsByRow === true
  const alignLaneStarts = options.alignLaneStarts === true

  const visibleGraphs = details.map((detail) => buildVisibleDetailGraph(detail, options))

  let globalNextX = startX
  let nextGraphBaseY = baseY

  let laneByKey = null
  let unassignedLaneIdx = 0

  if (!stackGraphsByRow) {
    const laneSeen = new Set()
    const laneOrderList = []

    const allNodes = visibleGraphs.flatMap((detail) => detail.nodes).sort((a, b) => {
      const getOrder = (n) => {
        if (n?.node_type === 'start') return -999999
        if (n?.node_type === 'end') return 999999
        return Number(n?.order_index || 0)
      }
      const orderDiff = getOrder(a) - getOrder(b)
      if (orderDiff !== 0) return orderDiff
      return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
    })

    allNodes.forEach((node) => {
      const lk = node.subgraph_id || node.container_id || 'unassigned'
      if (!laneSeen.has(lk)) {
        laneSeen.add(lk)
        laneOrderList.push(lk)
      }
    })

    laneByKey = new Map()
    laneOrderList.forEach((lk, idx) => laneByKey.set(lk, idx))
    unassignedLaneIdx = laneOrderList.length
  }

  visibleGraphs.forEach((visibleDetail, graphIndex) => {
    const detail = details[graphIndex]
    const graphLabel = `第${graphIndex + 1}轮`
    const containers = visibleDetail.containers
    const subgraphs = visibleDetail.subgraphs
    const nodes = visibleDetail.nodes
    const visibleNodeIds = new Set(nodes.map((node) => node.node_id))

    containers.forEach((container) => {
      mergedContainers.push({
        ...container,
        label: `${graphLabel} · ${container.label || container.container_key || '未命名容器'}`,
        graph_index: graphIndex + 1
      })
      containerOffsets[container.container_id] = detail?.graph?.layout_json?.container_offsets?.[container.container_id] || { dx: 0, dy: 0 }
    })

    subgraphs.forEach((subgraph) => {
      mergedSubgraphs.push({
        ...subgraph,
        graph_index: graphIndex + 1
      })
    })

    nodes.forEach((node) => {
      mergedNodes.push({
        ...node,
        graph_index: graphIndex + 1
      })
    })

    const incomingEdges = new Map()
    ;(visibleDetail.edges || []).forEach((edge) => {
      if (!visibleNodeIds.has(edge.source_node_id) || !visibleNodeIds.has(edge.target_node_id)) {
        return
      }
      mergedEdges.push({
        ...edge,
        graph_index: graphIndex + 1
      })
      edgeOffsets[edge.edge_id] = detail?.graph?.layout_json?.edge_offsets?.[edge.edge_id] || { dx: 0, dy: 0 }
      
      if (!incomingEdges.has(edge.target_node_id)) incomingEdges.set(edge.target_node_id, [])
      incomingEdges.get(edge.target_node_id).push(edge.source_node_id)
    })

    const graphBaseX = stackGraphsByRow ? startX : globalNextX
    const graphBaseY = stackGraphsByRow ? nextGraphBaseY : baseY
    const graphLaneByKey = stackGraphsByRow ? new Map() : laneByKey
    const graphUnassignedLaneIdx = stackGraphsByRow ? (() => {
      nodes.forEach((node) => {
        const lk = node.subgraph_id || node.container_id || 'unassigned'
        if (!graphLaneByKey.has(lk)) {
          graphLaneByKey.set(lk, graphLaneByKey.size)
        }
      })
      return graphLaneByKey.size
    })() : unassignedLaneIdx
    const graphNodeById = new Map(nodes.map((node) => [node.node_id, node]))

    const nodeCol = new Map()
    const colOccupied = new Map()
    let maxGraphCol = 0
    let maxGraphLane = 0

    nodes.forEach((node) => {
      const lk = node.subgraph_id || node.container_id || 'unassigned'
      const laneIdx = graphLaneByKey.has(lk) ? graphLaneByKey.get(lk) : graphUnassignedLaneIdx

      if (!colOccupied.has(laneIdx)) colOccupied.set(laneIdx, new Set())

      let minCol = 0
      const sources = incomingEdges.get(node.node_id) || []
      sources.forEach((srcId) => {
        if (alignLaneStarts) {
          const sourceNode = graphNodeById.get(srcId)
          const sourceLaneKey = sourceNode?.subgraph_id || sourceNode?.container_id || 'unassigned'
          if (sourceLaneKey !== lk) {
            return
          }
        }
        if (nodeCol.has(srcId)) {
          minCol = Math.max(minCol, nodeCol.get(srcId) + 1)
        }
      })

      while (colOccupied.get(laneIdx).has(minCol)) {
        minCol++
      }

      nodeCol.set(node.node_id, minCol)
      colOccupied.get(laneIdx).add(minCol)
      maxGraphCol = Math.max(maxGraphCol, minCol)
      maxGraphLane = Math.max(maxGraphLane, laneIdx)

      nodePositions[node.node_id] = {
        x: graphBaseX + minCol * colWidth + (stackGraphsByRow ? 0 : (minCol % 2 === 0 ? 0 : 8)),
        y: graphBaseY + laneIdx * laneHeight
      }
    })

    if (nodes.length > 0) {
      if (stackGraphsByRow) {
        nextGraphBaseY += (maxGraphLane + 1) * laneHeight + graphRowGap
      } else {
        globalNextX += (maxGraphCol + 1) * colWidth + 120
      }
    } else if (stackGraphsByRow) {
      nextGraphBaseY += laneHeight + graphRowGap
    }
  })

  for (let index = 1; index < details.length; index += 1) {
    const previousVisible = visibleGraphs[index - 1]
    const currentVisible = visibleGraphs[index]
    const previousDetail = details[index - 1]
    const currentDetail = details[index]
    const sourceNode = resolveBoundaryNode(previousVisible, 'end')
    const targetNode = resolveBoundaryNode(currentVisible, 'start')
    if (!sourceNode || !targetNode) continue

    mergedEdges.push({
      edge_id: `session-link-${previousDetail?.graph?.graph_id || index - 1}-${currentDetail?.graph?.graph_id || index}`,
      graph_id: currentDetail?.graph?.graph_id,
      source_node_id: sourceNode.node_id,
      target_node_id: targetNode.node_id,
      edge_type: 'call',
      label: `会话链 ${index} -> ${index + 1}`,
      condition_expr: null,
      config_json: {
        session_chain: true,
        prev_graph_id: currentDetail?.graph?.meta_json?.prev_graph_id || null
      },
      order_index: 10_000 + index,
      created_at: currentDetail?.graph?.created_at || ''
    })
  }

  const tailGraph = details[details.length - 1]?.graph || null
  return {
    graph: {
      graph_id: chainPayload?.active_graph_id || tailGraph?.graph_id || '',
      status: tailGraph?.status || 'idle',
      project_id: tailGraph?.project_id || null,
      layout_json: {
        node_positions: nodePositions,
        edge_offsets: edgeOffsets,
        container_offsets: containerOffsets
      },
      meta_json: {
        session_id: chainPayload?.session_id || '',
        active_graph_id: chainPayload?.active_graph_id || '',
        graph_count: details.length
      }
    },
    containers: mergedContainers,
    subgraphs: mergedSubgraphs,
    nodes: mergedNodes,
    edges: mergedEdges
  }
}
