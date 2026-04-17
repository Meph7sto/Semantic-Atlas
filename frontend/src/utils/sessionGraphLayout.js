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

  const laneSeen = new Set()
  const laneOrderList = []

  const allNodes = details.flatMap((detail) => {
    const visibleContainerKeys = resolveVisibleContainerKeys(detail, options)
    const nodes = detail?.nodes || []
    if (!visibleContainerKeys) return nodes
    const containersById = new Map((detail?.containers || []).map((container) => [container.container_id, container]))
    return nodes.filter((node) => {
      const container = containersById.get(node.container_id)
      return container && visibleContainerKeys.has(String(container.container_key || '').trim())
    })
  }).sort((a, b) => {
    const getOrder = (n) => {
      if (n?.node_type === 'start') return -999999
      if (n?.node_type === 'end') return 999999
      return Number(n?.order_index || 0)
    }
    const orderDiff = getOrder(a) - getOrder(b)
    if (orderDiff !== 0) return orderDiff
    return String(a?.created_at || '').localeCompare(String(b?.created_at || ''))
  })

  allNodes.forEach(node => {
    const lk = node.subgraph_id || node.container_id || 'unassigned'
    if (!laneSeen.has(lk)) {
      laneSeen.add(lk)
      laneOrderList.push(lk)
    }
  })

  const laneByKey = new Map()
  laneOrderList.forEach((lk, idx) => laneByKey.set(lk, idx))
  const unassignedLaneIdx = laneOrderList.length

  let globalNextX = startX

  details.forEach((detail, graphIndex) => {
    const graphLabel = `第${graphIndex + 1}轮`
    const visibleContainerKeys = resolveVisibleContainerKeys(detail, options)
    const containers = (detail?.containers || []).filter((container) => {
      if (!visibleContainerKeys) return true
      return visibleContainerKeys.has(String(container.container_key || '').trim())
    })
    const visibleContainerIds = new Set(containers.map((container) => container.container_id))
    const subgraphs = (detail?.subgraphs || []).filter((subgraph) => {
      if (!visibleContainerKeys) return true
      return visibleContainerIds.has(subgraph.container_id)
    })
    const nodes = sortByOrder((detail?.nodes || []).filter((node) => {
      if (!visibleContainerKeys) return true
      return visibleContainerIds.has(node.container_id)
    }))
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
    ;(detail?.edges || []).forEach((edge) => {
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

    const nodeCol = new Map()
    const colOccupied = new Map()
    let maxGraphCol = 0

    nodes.forEach((node) => {
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
      maxGraphCol = Math.max(maxGraphCol, minCol)

      nodePositions[node.node_id] = {
        x: globalNextX + minCol * colWidth + (minCol % 2 === 0 ? 0 : 8),
        y: baseY + laneIdx * laneHeight
      }
    })

    if (nodes.length > 0) {
      globalNextX += (maxGraphCol + 1) * colWidth + 120
    }
  })

  for (let index = 1; index < details.length; index += 1) {
    const previous = details[index - 1]
    const current = details[index]
    const sourceNode = resolveBoundaryNode(previous, 'end')
    const targetNode = resolveBoundaryNode(current, 'start')
    if (!sourceNode || !targetNode) continue

    mergedEdges.push({
      edge_id: `session-link-${previous.graph?.graph_id}-${current.graph?.graph_id}`,
      graph_id: current.graph?.graph_id,
      source_node_id: sourceNode.node_id,
      target_node_id: targetNode.node_id,
      edge_type: 'call',
      label: `会话链 ${index} -> ${index + 1}`,
      condition_expr: null,
      config_json: {
        session_chain: true,
        prev_graph_id: current.graph?.meta_json?.prev_graph_id || null
      },
      order_index: 10_000 + index,
      created_at: current.graph?.created_at || ''
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
