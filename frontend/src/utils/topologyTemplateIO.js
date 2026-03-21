/**
 * 拓扑模板导出与导入工具
 *
 * 导出：将 graphDetail（含数据库 ID）转换为可移植的 key 引用格式
 * 导入：读取文件 → 校验 → 按顺序调用 CRUD API 重建拓扑图
 */

import { executionGraphApi } from '@/api/executionGraph'

const FORMAT_ID = 'semantic-atlas-topology-template'
const FORMAT_VERSION = '1.0.0'

// ========================
// Export
// ========================

/**
 * 将 graphDetail 转换为导出 payload（ID→key 引用）
 */
export const buildExportPayload = (graphDetail) => {
  const { graph, containers = [], nodes = [], edges = [] } = graphDetail

  // 构建 ID→key 查找表
  const containerIdToKey = {}
  containers.forEach((c) => {
    containerIdToKey[c.container_id] = c.container_key
  })

  const nodeIdToKey = {}
  nodes.forEach((n) => {
    nodeIdToKey[n.node_id] = n.node_key
  })

  return {
    format: FORMAT_ID,
    version: FORMAT_VERSION,
    exported_at: new Date().toISOString(),
    graph: {
      name: graph.name || '',
      description: graph.description || '',
      status: 'draft',
      layout_json: graph.layout_json || {},
      meta_json: graph.meta_json || {}
    },
    containers: containers.map((c) => ({
      container_key: c.container_key,
      label: c.label,
      role_type: c.role_type || 'agent',
      order_index: c.order_index ?? 0,
      config_json: c.config_json || {}
    })),
    nodes: nodes.map((n) => ({
      node_key: n.node_key,
      label: n.label,
      node_type: n.node_type || 'llm',
      role_type: n.role_type || 'human',
      container_key: containerIdToKey[n.container_id] || null,
      phase_label: n.phase_label || '',
      task_prompt: n.task_prompt || '',
      conditional_edges: n.conditional_edges || [],
      order_index: n.order_index ?? 0,
      config_json: n.config_json || {},
      input_schema_json: n.input_schema_json || []
    })),
    edges: edges.map((e) => ({
      source_node_key: nodeIdToKey[e.source_node_id] || '',
      target_node_key: nodeIdToKey[e.target_node_id] || '',
      edge_type: e.edge_type || 'call',
      label: e.label || '',
      condition_expr: e.condition_expr || '',
      order_index: e.order_index ?? 0,
      config_json: e.config_json || {}
    }))
  }
}

/**
 * 生成 JSON 文件并触发浏览器下载
 */
export const downloadTemplateFile = (payload, filename) => {
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

// ========================
// Import
// ========================

/**
 * 从 File 对象读取并解析模板
 * @param {File} file
 * @returns {Promise<{ok: boolean, value?: object, error?: string}>}
 */
export const readTemplateFile = (file) => {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target.result)
        resolve({ ok: true, value: data })
      } catch {
        resolve({ ok: false, error: '文件不是合法 JSON' })
      }
    }
    reader.onerror = () => {
      resolve({ ok: false, error: '读取文件失败' })
    }
    reader.readAsText(file)
  })
}

/**
 * 校验模板 payload 的格式完整性
 * @returns {{ ok: boolean, errors: string[] }}
 */
export const validateTemplatePayload = (payload) => {
  const errors = []

  if (!payload || typeof payload !== 'object') {
    return { ok: false, errors: ['无效的模板数据'] }
  }

  if (payload.format !== FORMAT_ID) {
    errors.push(`格式标识不匹配: 期望 "${FORMAT_ID}", 实际 "${payload.format}"`)
  }

  if (!payload.graph || !payload.graph.name) {
    errors.push('缺少图名称 (graph.name)')
  }

  if (!Array.isArray(payload.containers)) {
    errors.push('缺少容器列表 (containers)')
  } else {
    const containerKeys = new Set()
    payload.containers.forEach((c, i) => {
      if (!c.container_key) {
        errors.push(`容器 #${i + 1} 缺少 container_key`)
      } else if (containerKeys.has(c.container_key)) {
        errors.push(`容器 container_key 重复: "${c.container_key}"`)
      } else {
        containerKeys.add(c.container_key)
      }
    })
  }

  if (!Array.isArray(payload.nodes)) {
    errors.push('缺少节点列表 (nodes)')
  } else {
    const nodeKeys = new Set()
    payload.nodes.forEach((n, i) => {
      if (!n.node_key) {
        errors.push(`节点 #${i + 1} 缺少 node_key`)
      } else if (nodeKeys.has(n.node_key)) {
        errors.push(`节点 node_key 重复: "${n.node_key}"`)
      } else {
        nodeKeys.add(n.node_key)
      }
    })
  }

  if (!Array.isArray(payload.edges)) {
    errors.push('缺少边列表 (edges)')
  } else {
    payload.edges.forEach((e, i) => {
      if (!e.source_node_key) {
        errors.push(`边 #${i + 1} 缺少 source_node_key`)
      }
      if (!e.target_node_key) {
        errors.push(`边 #${i + 1} 缺少 target_node_key`)
      }
    })
  }

  return { ok: errors.length === 0, errors }
}

/**
 * 导入模板：按顺序创建 graph → containers → nodes → edges
 *
 * @param {string} projectId
 * @param {object} payload - 经过 validateTemplatePayload 校验后的模板数据
 * @param {(message: string) => void} [onProgress] - 进度回调
 * @returns {Promise<{ok: boolean, graphId?: string, error?: string}>}
 */
export const importTemplate = async (projectId, payload, onProgress) => {
  const progress = onProgress || (() => {})

  try {
    // 1. 创建 Graph
    progress('正在创建图...')
    const graph = await executionGraphApi.createGraph(projectId, {
      name: payload.graph.name,
      description: payload.graph.description || ''
    })
    const graphId = graph.graph_id

    // 如果有 layout_json 或 meta_json，更新图
    if (
      (payload.graph.layout_json && Object.keys(payload.graph.layout_json).length > 0) ||
      (payload.graph.meta_json && Object.keys(payload.graph.meta_json).length > 0)
    ) {
      await executionGraphApi.updateGraph(graphId, {
        layout_json: payload.graph.layout_json || undefined,
        meta_json: payload.graph.meta_json || undefined
      })
    }

    // 2. 创建 Containers → 建立 key→id 映射
    const containerKeyToId = {}
    if (payload.containers.length > 0) {
      progress(`正在创建 ${payload.containers.length} 个容器...`)
      for (const c of payload.containers) {
        const container = await executionGraphApi.createContainer(graphId, {
          container_key: c.container_key,
          label: c.label,
          role_type: c.role_type || 'agent',
          order_index: c.order_index ?? 0,
          config_json: c.config_json || {}
        })
        containerKeyToId[c.container_key] = container.container_id
      }
    }

    // 3. 创建 Nodes → 解析 container_key，建立 node_key→id 映射
    const nodeKeyToId = {}
    if (payload.nodes.length > 0) {
      progress(`正在创建 ${payload.nodes.length} 个节点...`)
      for (const n of payload.nodes) {
        const node = await executionGraphApi.createNode(graphId, {
          node_key: n.node_key,
          label: n.label,
          node_type: n.node_type || 'llm',
          role_type: n.role_type || 'human',
          container_id: n.container_key ? (containerKeyToId[n.container_key] || null) : null,
          phase_label: n.phase_label || '',
          task_prompt: n.task_prompt || '',
          conditional_edges: n.conditional_edges || [],
          order_index: n.order_index ?? 0,
          config_json: n.config_json || {},
          input_schema_json: n.input_schema_json || []
        })
        nodeKeyToId[n.node_key] = node.node_id
      }
    }

    // 4. 创建 Edges → 解析 source/target node_key
    if (payload.edges.length > 0) {
      progress(`正在创建 ${payload.edges.length} 条边...`)
      for (const e of payload.edges) {
        const sourceNodeId = nodeKeyToId[e.source_node_key]
        const targetNodeId = nodeKeyToId[e.target_node_key]
        if (!sourceNodeId || !targetNodeId) {
          console.warn(
            `[importTemplate] 跳过边: 无法解析 source="${e.source_node_key}" 或 target="${e.target_node_key}"`
          )
          continue
        }
        await executionGraphApi.createEdge(graphId, {
          source_node_id: sourceNodeId,
          target_node_id: targetNodeId,
          edge_type: e.edge_type || 'call',
          label: e.label || '',
          condition_expr: e.condition_expr || '',
          order_index: e.order_index ?? 0,
          config_json: e.config_json || {}
        })
      }
    }

    progress('导入完成')
    return { ok: true, graphId }
  } catch (err) {
    const message =
      err?.response?.data?.detail ||
      err?.response?.data?.error ||
      err?.message ||
      '导入失败'
    return { ok: false, error: message }
  }
}
