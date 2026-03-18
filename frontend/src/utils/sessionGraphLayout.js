/**
 * 会话执行图合并布局工具函数
 * 供 RequirementAgentChat / ConflictAgentChat 等多 Agent 页面共用
 */

export const createEmptyGraphDetail = () => ({ graph: null, containers: [], nodes: [], edges: [] })

export const sortByOrder = (items = []) => {
  return [...items].sort((a, b) => {
    const orderDiff = Number(a?.order_index || 0) - Number(b?.order_index || 0)
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
  const mergedNodes = []
  const mergedEdges = []
  const nodePositions = {}
  const edgeOffsets = {}
  const containerOffsets = {}

  const startX = 94
  const baseY = 98
  const columnGap = 320
  const rowGap = 112
  const rowHeight = 400

  details.forEach((detail, graphIndex) => {
    let baseX = startX
    const currentBaseY = baseY + graphIndex * rowHeight
    const graphLabel = `第${graphIndex + 1}轮`
    const containers = sortByOrder(detail?.containers || [])
    const nodes = sortByOrder(detail?.nodes || [])

    // 将含 end 节点的容器排到最后（最右列）
    const endNodeContainerIds = new Set(
      nodes.filter((n) => n.node_type === 'end').map((n) => n.container_id).filter(Boolean)
    )
    const nonEndContainers = containers.filter((c) => !endNodeContainerIds.has(c.container_id))
    const endContainers = containers.filter((c) => endNodeContainerIds.has(c.container_id))
    const reorderedContainers = [...nonEndContainers, ...endContainers]

    const containerOrder = reorderedContainers.map((container) => container.container_id)
    const nodesByContainer = new Map(containerOrder.map((containerId) => [containerId, []]))
    const unassignedNodes = []

    nodes.forEach((node) => {
      if (node.container_id && nodesByContainer.has(node.container_id)) {
        nodesByContainer.get(node.container_id).push(node)
        return
      }
      unassignedNodes.push(node)
    })

    reorderedContainers.forEach((container) => {
      mergedContainers.push({
        ...container,
        label: `${graphLabel} · ${container.label || container.container_key || '未命名容器'}`,
        graph_index: graphIndex + 1
      })
    })

    nodes.forEach((node) => {
      mergedNodes.push({
        ...node,
        graph_index: graphIndex + 1
      })
    })

    ;(detail?.edges || []).forEach((edge) => {
      mergedEdges.push({
        ...edge,
        graph_index: graphIndex + 1
      })
      edgeOffsets[edge.edge_id] = detail?.graph?.layout_json?.edge_offsets?.[edge.edge_id] || { dx: 0, dy: 0 }
    })

    const columns = [
      ...containerOrder.map((containerId) => sortByOrder(nodesByContainer.get(containerId) || [])),
      ...(unassignedNodes.length ? [sortByOrder(unassignedNodes)] : [])
    ]

    columns.forEach((columnNodes, columnIndex) => {
      columnNodes.forEach((node, rowIndex) => {
        nodePositions[node.node_id] = {
          x: baseX + columnIndex * columnGap + (rowIndex % 2 === 0 ? 0 : 8),
          y: currentBaseY + rowIndex * rowGap
        }
      })
    })

    reorderedContainers.forEach((container) => {
      containerOffsets[container.container_id] = detail?.graph?.layout_json?.container_offsets?.[container.container_id] || { dx: 0, dy: 0 }
    })
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
    nodes: mergedNodes,
    edges: mergedEdges
  }
}
