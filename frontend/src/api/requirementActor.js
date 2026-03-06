/**
 * Requirement Actor API 封装
 * 提供 Actor 命令、事件查询、回放等接口
 */

import { api } from './request'

export const requirementActorApi = {
  /**
   * 获取需求的事件历史
   */
  async getEvents(requirementId, { limit = 100, offset = 0 } = {}) {
    const normalizedLimit = Math.max(1, Math.min(1000, Number(limit) || 100))
    const normalizedOffset = Math.max(0, Number(offset) || 0)

    const resp = await api.get(`/requirement-actor/events/${requirementId}`, {
      params: { limit: normalizedLimit, offset: normalizedOffset }
    })
    return resp.data
  },

  /**
   * 获取需求的版本历史列表
   */
  async getVersionHistory(requirementId, limit = 50) {
    const normalizedLimit = Math.max(1, Math.min(1000, Number(limit) || 50))

    const resp = await api.get(`/requirement-actor/versions/${requirementId}`, {
      params: { limit: normalizedLimit }
    })
    return resp.data
  },

  /**
   * 重放事件到指定版本
   */
  async replayToVersion(requirementId, version, useSnapshot = true) {
    const resp = await api.get(
      `/requirement-actor/replay/${requirementId}/${version}`,
      { params: { use_snapshot: useSnapshot } }
    )
    return resp.data
  },

  /**
   * 获取需求的最新快照
   */
  async getSnapshot(requirementId) {
    const resp = await api.get(`/requirement-actor/snapshot/${requirementId}`)
    return resp.data
  },

  /**
   * 提交通用命令
   */
  async submitCommand(requirementId, command) {
    const resp = await api.post(`/requirement-actor/command`, command, {
      params: { requirement_id: requirementId }
    })
    return resp.data
  },

  /**
   * 创建需求命令
   */
  async createRequirement(requirementId, content, status = 'Draft', priority = 'medium', metadata = {}) {
    const resp = await api.post(`/requirement-actor/command/create`, content, {
      params: { requirement_id: requirementId, status, priority }
    })
    return resp.data
  },

  /**
   * 更新需求内容
   */
  async updateContent(requirementId, updates, metadata = {}) {
    const resp = await api.post(`/requirement-actor/command/update-content`, {
      updates,
      metadata
    }, {
      params: { requirement_id: requirementId }
    })
    return resp.data
  },

  /**
   * 更改需求状态
   */
  async changeStatus(requirementId, newStatus, metadata = {}) {
    const resp = await api.post(`/requirement-actor/command/change-status`, null, {
      params: { requirement_id: requirementId, new_status: newStatus }
    })
    return resp.data
  },

  /**
   * 添加质量标记
   */
  async addQualityMarker(requirementId, markerType, markerValue, metadata = {}) {
    const resp = await api.post(`/requirement-actor/command/add-quality-marker`, null, {
      params: {
        requirement_id: requirementId,
        marker_type: markerType,
        marker_value: markerValue
      }
    })
    return resp.data
  },

  /**
   * 查询需求状态（读模型）
   */
  async queryRequirement(requirementId, minVersion = null, timeout = 5) {
    const params = { timeout }
    if (minVersion !== null) {
      params.min_version = minVersion
    }
    const resp = await api.get(`/requirement-actor/query`, {
      params: { requirement_id: requirementId, ...params }
    })
    return resp.data
  },

  /**
   * 创建事件流连接（SSE）
   */
  connectEventStream(requirementId) {
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http'
    const host = window.location.host
    return new EventSource(`${protocol}://${host}/api/v2/requirement-actor/events/stream/${requirementId}`)
  },

  /**
   * 获取Actor健康状态
   */
  async getActorHealth(requirementId) {
    const resp = await api.get(`/requirement-actor/health/${requirementId}`)
    return resp.data
  },

  /**
   * 获取全局Actor统计
   */
  async getActorStats() {
    const resp = await api.get('/requirement-actor/stats')
    return resp.data
  },

  /**
   * 获取所有允许的状态转换
   */
  async getTransitions() {
    const resp = await api.get('/requirement-actor/transitions')
    return resp.data
  }
}
