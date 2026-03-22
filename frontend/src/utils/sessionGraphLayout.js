/**
 * 会话执行图合并布局工具函数
 * 供 RequirementAgentChat / ConflictAgentChat 等多 Agent 页面共用
 */

export const createEmptyGraphDetail = () => ({ graph: null, containers: [], subgraphs: [], nodes: [], edges: [] })

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

export const buildMergedSessionGraphDetail = (chainPayload) => {
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

  const allNodes = details.flatMap(d => d.nodes || []).sort((a, b) => {
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

    ;(detail?.containers || []).forEach((container) => {
      mergedContainers.push({
        ...container,
        label: `${graphLabel} · ${container.label || container.container_key || '未命名容器'}`,
        graph_index: graphIndex + 1
      })
      containerOffsets[container.container_id] = detail?.graph?.layout_json?.container_offsets?.[container.container_id] || { dx: 0, dy: 0 }
    })

    ;(detail?.subgraphs || []).forEach((subgraph) => {
      mergedSubgraphs.push({
        ...subgraph,
        graph_index: graphIndex + 1
      })
    })

    const nodes = sortByOrder(detail?.nodes || [])
    nodes.forEach((node) => {
      mergedNodes.push({
        ...node,
        graph_index: graphIndex + 1
      })
    })

    const incomingEdges = new Map()
    ;(detail?.edges || []).forEach((edge) => {
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
