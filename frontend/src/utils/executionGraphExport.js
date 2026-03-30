/**
 * 执行图导出工具
 *
 * 将运行时执行图（graph + containers + subgraphs + nodes + edges）
 * 序列化为 JSON 快照并触发浏览器下载。
 */

const FORMAT_ID = 'semantic-atlas-execution-graph'
const FORMAT_VERSION = '1.0.0'

/**
 * 安全提取对象字段，避免 undefined 污染 JSON
 */
const safeString = (value, fallback = '') =>
  typeof value === 'string' && value.trim() ? value.trim() : fallback

const safeObject = (value) =>
  value && typeof value === 'object' && !Array.isArray(value) ? value : {}

const safeArray = (value) => (Array.isArray(value) ? value : [])

const safeNumber = (value, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

/**
 * 将运行时 graphDetail 构建为导出 payload
 *
 * @param {{ graph: object, containers: object[], subgraphs: object[], nodes: object[], edges: object[] }} graphDetail
 * @returns {object} 可序列化的导出 payload
 */
export const buildExecutionGraphExportPayload = (graphDetail) => {
  const { graph, containers = [], subgraphs = [], nodes = [], edges = [] } = graphDetail

  return {
    format: FORMAT_ID,
    version: FORMAT_VERSION,
    exported_at: new Date().toISOString(),
    graph: {
      graph_id: safeString(graph?.graph_id),
      status: safeString(graph?.status, 'idle'),
      project_id: safeString(graph?.project_id),
      layout_json: safeObject(graph?.layout_json),
      meta_json: safeObject(graph?.meta_json)
    },
    containers: containers.map((c) => ({
      container_id: safeString(c.container_id),
      container_key: safeString(c.container_key),
      label: safeString(c.label),
      role_type: safeString(c.role_type, 'agent'),
      status: safeString(c.status),
      order_index: safeNumber(c.order_index),
      config_json: safeObject(c.config_json),
      graph_index: safeNumber(c.graph_index)
    })),
    subgraphs: subgraphs.map((s) => ({
      subgraph_id: safeString(s.subgraph_id),
      subgraph_key: safeString(s.subgraph_key),
      container_id: safeString(s.container_id),
      label: safeString(s.label),
      status: safeString(s.status),
      task_description: safeString(s.task_description),
      order_index: safeNumber(s.order_index),
      config_json: safeObject(s.config_json),
      graph_index: safeNumber(s.graph_index)
    })),
    nodes: nodes.map((n) => ({
      node_id: safeString(n.node_id),
      node_key: safeString(n.node_key),
      label: safeString(n.label),
      node_type: safeString(n.node_type, 'llm'),
      role_type: safeString(n.role_type),
      container_id: safeString(n.container_id),
      subgraph_id: safeString(n.subgraph_id),
      phase_label: safeString(n.phase_label),
      task_prompt: safeString(n.task_prompt),
      conditional_edges: safeArray(n.conditional_edges),
      order_index: safeNumber(n.order_index),
      config_json: safeObject(n.config_json),
      input_schema_json: safeArray(n.input_schema_json),
      graph_index: safeNumber(n.graph_index)
    })),
    edges: edges.map((e) => ({
      edge_id: safeString(e.edge_id),
      source_node_id: safeString(e.source_node_id),
      target_node_id: safeString(e.target_node_id),
      edge_type: safeString(e.edge_type, 'call'),
      label: safeString(e.label),
      condition_expr: safeString(e.condition_expr),
      order_index: safeNumber(e.order_index),
      config_json: safeObject(e.config_json),
      graph_index: safeNumber(e.graph_index)
    }))
  }
}

/**
 * 将 payload 序列化为 JSON 并触发浏览器下载
 *
 * @param {object} payload - buildExecutionGraphExportPayload 的返回值
 * @param {string} filename - 下载文件名
 */
export const downloadExecutionGraphFile = (payload, filename) => {
  const json = JSON.stringify(payload, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)

  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
