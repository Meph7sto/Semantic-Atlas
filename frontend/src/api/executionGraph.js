import { api } from './request'

export const executionGraphApi = {
  /**
   * 健康检查
   */
  async health() {
    const resp = await api.get('/health')
    return resp.data
  },

  // ========================
  // Graph Methods
  // ========================

  /**
   * 创建执行拓扑图
   * @param {string} projectId - 项目 ID
   * @param {object} data - 图数据 {name, description}
   */
  async createGraph(projectId, data) {
    const resp = await api.post(`/execution-topology/projects/${encodeURIComponent(projectId)}`, data)
    return resp.data
  },

  /**
   * 列出项目的执行拓扑图
   * @param {string} projectId - 项目 ID
   */
  async listGraphs(projectId) {
    const resp = await api.get(`/execution-topology/projects/${encodeURIComponent(projectId)}`)
    return resp.data?.graphs || []
  },

  /**
   * 获取指定的执行拓扑图
   * @param {string} graphId - 图 ID
   */
  async getGraph(graphId) {
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}`)
    return resp.data
  },

  /**
   * 更新执行拓扑图
   * @param {string} graphId - 图 ID
   * @param {object} data - 更新数据 {name, description, status, layout_json, meta_json}
   */
  async updateGraph(graphId, data) {
    const resp = await api.patch(`/execution-topology/${encodeURIComponent(graphId)}`, data)
    return resp.data
  },

  /**
   * 删除执行拓扑图（软删除）
   * @param {string} graphId - 图 ID
   */
  async deleteGraph(graphId) {
    const resp = await api.delete(`/execution-topology/${encodeURIComponent(graphId)}`)
    return resp.data
  },

  // ========================
  // Container Methods
  // ========================

  /**
   * 在图中创建容器
   * @param {string} graphId - 图 ID
   * @param {object} data - 容器数据 {container_key, label, role_type, config_json, order_index}
   */
  async createContainer(graphId, data) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/containers`, data)
    return resp.data
  },

  /**
   * 更新容器
   * @param {string} containerId - 容器 ID
   * @param {object} data - 更新数据 {label, role_type, config_json, order_index}
   */
  async updateContainer(containerId, data) {
    const resp = await api.patch(`/execution-topology/containers/${encodeURIComponent(containerId)}`, data)
    return resp.data
  },

  /**
   * 删除容器
   * @param {string} containerId - 容器 ID
   */
  async deleteContainer(containerId) {
    const resp = await api.delete(`/execution-topology/containers/${encodeURIComponent(containerId)}`)
    return resp.data
  },

  // ========================
  // Subgraph Methods
  // ========================

  /**
   * 在图中创建子图
   * @param {string} graphId - 图 ID
   * @param {object} data - 子图数据 {container_id, subgraph_key, label, task_description, order_index, config_json}
   */
  async createSubgraph(graphId, data) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/subgraphs`, data)
    return resp.data
  },

  /**
   * 列出图中的子图
   * @param {string} graphId - 图 ID
   */
  async listSubgraphs(graphId) {
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}/subgraphs`)
    return resp.data?.subgraphs || []
  },

  /**
   * 更新子图
   * @param {string} subgraphId - 子图 ID
   * @param {object} data - 更新数据 {label, task_description, order_index, config_json}
   */
  async updateSubgraph(subgraphId, data) {
    const resp = await api.patch(`/execution-topology/subgraphs/${encodeURIComponent(subgraphId)}`, data)
    return resp.data
  },

  /**
   * 删除子图
   * @param {string} subgraphId - 子图 ID
   */
  async deleteSubgraph(subgraphId) {
    const resp = await api.delete(`/execution-topology/subgraphs/${encodeURIComponent(subgraphId)}`)
    return resp.data
  },

  // ========================
  // Node Methods
  // ========================

  /**
   * 在图中创建节点
   * @param {string} graphId - 图 ID
   * @param {object} data - 节点数据 {node_key, label, node_type, role_type, config_json, input_schema_json, order_index}
   */
  async createNode(graphId, data) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/nodes`, data)
    return resp.data
  },

  /**
   * 更新节点
   * @param {string} nodeId - 节点 ID
   * @param {object} data - 更新数据 {label, node_type, role_type, config_json, input_schema_json, order_index}
   */
  async updateNode(nodeId, data) {
    const resp = await api.patch(`/execution-topology/nodes/${encodeURIComponent(nodeId)}`, data)
    return resp.data
  },

  /**
   * 删除节点
   * @param {string} nodeId - 节点 ID
   */
  async deleteNode(nodeId) {
    const resp = await api.delete(`/execution-topology/nodes/${encodeURIComponent(nodeId)}`)
    return resp.data
  },

  // ========================
  // Edge Methods
  // ========================

  /**
   * 在图中创建边
   * @param {string} graphId - 图 ID
   * @param {object} data - 边数据 {source_node_id, target_node_id, edge_type, label, condition_expr, config_json, order_index}
   */
  async createEdge(graphId, data) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/edges`, data)
    return resp.data
  },

  /**
   * 更新边
   * @param {string} edgeId - 边 ID
   * @param {object} data - 更新数据 {label, edge_type, condition_expr, config_json, order_index}
   */
  async updateEdge(edgeId, data) {
    const resp = await api.patch(`/execution-topology/edges/${encodeURIComponent(edgeId)}`, data)
    return resp.data
  },

  /**
   * 删除边
   * @param {string} edgeId - 边 ID
   */
  async deleteEdge(edgeId) {
    const resp = await api.delete(`/execution-topology/edges/${encodeURIComponent(edgeId)}`)
    return resp.data
  },

  // ========================
  // Aggregated Methods
  // ========================

  /**
   * 获取图的完整信息（包括节点和边）
   * @param {string} graphId - 图 ID
   */
  async getGraphDetail(graphId) {
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}/detail`)
    return resp.data
  },

  // ========================
  // Topology Structure Methods
  // ========================

  /**
   * 获取编译的拓扑结构
   * @param {string} graphId - 图 ID
   */
  async getTopologyStructure(graphId) {
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}/structure`)
    return resp.data
  },

  /**
   * 验证拓扑结构
   * @param {string} graphId - 图 ID
   */
  async validateTopologyStructure(graphId) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/validate`)
    return resp.data
  },

  /**
   * 获取所有容器定义
   * @param {string} graphId - 图 ID
   * @param {string} nodeType - 节点类型过滤（可选）
   * @param {string} roleType - 角色类型过滤（可选）
   */
  async getContainers(graphId, nodeType = null, roleType = null) {
    const params = new URLSearchParams()
    if (nodeType) params.append('node_type', nodeType)
    if (roleType) params.append('role_type', roleType)
    const queryString = params.toString()
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}/containers${queryString ? '?' + queryString : ''}`)
    return resp.data
  },

  /**
   * 导出拓扑供代理使用
   * @param {string} graphId - 图 ID
   * @param {string} format - 导出格式（默认 'json'）
   */
  async exportTopology(graphId, format = 'json') {
    const params = new URLSearchParams()
    if (format) params.append('format', format)
    const queryString = params.toString()
    const resp = await api.get(`/execution-topology/${encodeURIComponent(graphId)}/export${queryString ? '?' + queryString : ''}`)
    return resp.data
  },

  /**
   * 执行拓扑模板并创建运行时图
   * @param {string} graphId - 图 ID
   * @param {object} data - 执行参数 {input_payload, max_steps, runtime_graph_name, runtime_graph_description}
   */
  async executeTopology(graphId, data = {}) {
    const resp = await api.post(`/execution-topology/${encodeURIComponent(graphId)}/execute`, data)
    return resp.data
  },
}
