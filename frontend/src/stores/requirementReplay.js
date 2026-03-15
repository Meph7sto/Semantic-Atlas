/**
 * Requirement Replay Store
 * 需求回放功能的状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { requirementActorApi } from '@/api/requirementActor'

export const useRequirementReplayStore = defineStore('requirementReplay', () => {
  const MAX_EVENT_LIMIT = 1000

  const getEventVersion = (event, index) => {
    const eventSequence = Number(event?.event_sequence)
    if (Number.isFinite(eventSequence) && eventSequence >= 0) {
      return eventSequence
    }
    return index + 1
  }

  // ========================
  // 状态
  // ========================

  const selectedProjectId = ref('')
  const selectedRequirementId = ref('')

  // 事件和版本
  const events = ref([])
  const versionHistory = ref([])
  const currentVersion = ref(0)
  const maxVersion = ref(0)

  // 需求状态
  const currentState = ref(null)
  const previousState = ref(null)

  // 回放控制
  const isPlaying = ref(false)
  const playbackSpeed = ref(1000) // ms per event
  const autoPlayTimer = ref(null)

  // 加载状态
  const isLoading = ref(false)
  const isLoadingState = ref(false)
  const error = ref(null)

  // SSE连接
  const sseConnection = ref(null)

  // ========================
  // 计算属性
  // ========================

  const canPlayForward = computed(() => currentVersion.value < maxVersion.value)
  const canPlayBackward = computed(() => currentVersion.value > 0)
  const versionProgress = computed(() => {
    if (maxVersion.value === 0) return 0
    return Math.round((currentVersion.value / maxVersion.value) * 100)
  })

  const currentEvent = computed(() => {
    if (currentVersion.value <= 0 || events.value.length === 0) {
      return null
    }

    return events.value.find((event, index) => {
      return getEventVersion(event, index) === currentVersion.value
    }) || null
  })

  // ========================
  // Actions
  // ========================

  /**
   * 加载需求的事件历史
   */
  async function loadEvents(requirementId) {
    isLoading.value = true
    error.value = null

    try {
      const result = await requirementActorApi.getEvents(requirementId, { limit: MAX_EVENT_LIMIT })
      events.value = Array.isArray(result.events) ? result.events : []

      // 加载版本历史
      const versionResult = await requirementActorApi.getVersionHistory(requirementId, MAX_EVENT_LIMIT)
      versionHistory.value = Array.isArray(versionResult.versions) ? versionResult.versions : []

      if (events.value.length === 0) {
        maxVersion.value = 0
        currentVersion.value = 0
        currentState.value = null
        previousState.value = null
        return
      }

      const lastEventIndex = events.value.length - 1
      maxVersion.value = getEventVersion(events.value[lastEventIndex], lastEventIndex)
      currentVersion.value = maxVersion.value

      // 重建当前状态
      await rebuildState(currentVersion.value)
    } catch (err) {
      console.error('Failed to load events:', err)
      error.value = err?.response?.data?.detail || err?.message || '加载事件失败'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 重建指定版本的状态
   */
  async function rebuildState(version = null) {
    isLoadingState.value = true

    try {
      const targetVersion = version !== null ? version : currentVersion.value
      const normalizedVersion = Math.max(
        0,
        Math.min(maxVersion.value, Number(targetVersion) || 0)
      )
      const result = await requirementActorApi.replayToVersion(
        selectedRequirementId.value,
        normalizedVersion
      )

      currentState.value = result.state
      maxVersion.value = Number(result.max_version) || normalizedVersion
      currentVersion.value = normalizedVersion
    } catch (err) {
      console.error('Failed to rebuild state:', err)
      error.value = err?.response?.data?.detail || err?.message || '重建状态失败'
      throw err
    } finally {
      isLoadingState.value = false
    }
  }

  /**
   * 设置当前版本
   */
  async function setCurrentVersion(version) {
    const parsedVersion = Number(version)
    if (!Number.isFinite(parsedVersion)) {
      return
    }

    if (parsedVersion < 0 || parsedVersion > maxVersion.value) {
      return
    }

    // 保存之前的状态
    previousState.value = currentState.value

    currentVersion.value = parsedVersion
    await rebuildState(parsedVersion)
  }

  /**
   * 前进一步
   */
  async function stepForward() {
    if (canPlayForward.value) {
      await setCurrentVersion(currentVersion.value + 1)
    }
  }

  /**
   * 后退一步
   */
  async function stepBackward() {
    if (canPlayBackward.value) {
      await setCurrentVersion(currentVersion.value - 1)
    }
  }

  /**
   * 跳转到第一个版本
   */
  async function jumpToStart() {
    await setCurrentVersion(0)
  }

  /**
   * 跳转到最后一个版本
   */
  async function jumpToEnd() {
    await setCurrentVersion(maxVersion.value)
  }

  /**
   * 开始自动播放
   */
  async function play(speed = null) {
    if (isPlaying.value) return

    isPlaying.value = true

    if (speed !== null) {
      playbackSpeed.value = speed
    }

    while (isPlaying.value && canPlayForward.value) {
      await stepForward()
      await new Promise(resolve => setTimeout(resolve, playbackSpeed.value))
    }

    isPlaying.value = false
  }

  /**
   * 暂停播放
   */
  function pause() {
    isPlaying.value = false
  }

  /**
   * 连接SSE事件流
   */
  function connectSSE(requirementId) {
    disconnectSSE()

    try {
      sseConnection.value = requirementActorApi.connectEventStream(requirementId)

      sseConnection.value.onopen = () => {
        console.log('SSE connection opened')
      }

      sseConnection.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          // 忽略心跳事件
          if (data.event === 'heartbeat') return

          // 处理连接确认
          if (data.event === 'connected') {
            console.log('SSE connected:', data.data)
            return
          }

          // 处理新事件（需要根据实际SSE实现调整）
          // 这里只是示例，实际数据格式可能不同
          console.log('SSE message:', data)
        } catch (err) {
          console.error('Failed to parse SSE message:', err)
        }
      }

      sseConnection.value.onerror = (err) => {
        console.error('SSE connection error:', err)
      }
    } catch (err) {
      console.error('Failed to connect SSE:', err)
    }
  }

  /**
   * 断开SSE连接
   */
  function disconnectSSE() {
    if (sseConnection.value) {
      sseConnection.value.close()
      sseConnection.value = null
      console.log('SSE connection closed')
    }
  }

  /**
   * 提交命令到Actor
   */
  async function submitCommand(command) {
    try {
      const result = await requirementActorApi.submitCommand(
        selectedRequirementId.value,
        command
      )
      return result
    } catch (err) {
      console.error('Failed to submit command:', err)
      error.value = err?.response?.data?.detail || err?.message || '命令提交失败'
      throw err
    }
  }

  /**
   * 更新需求内容
   */
  async function updateContent(updates, metadata = {}) {
    const command = {
      type: 'UpdateRequirementContent',
      updates,
      metadata
    }
    return submitCommand(command)
  }

  /**
   * 更改需求状态
   */
  async function changeStatus(newStatus, metadata = {}) {
    const command = {
      type: 'ChangeStatus',
      new_status: newStatus,
      metadata
    }
    return submitCommand(command)
  }

  /**
   * 添加质量标记
   */
  async function addQualityMarker(markerType, markerValue, metadata = {}) {
    const command = {
      type: 'AddQualityMarker',
      marker_type: markerType,
      marker_value: markerValue,
      metadata
    }
    return submitCommand(command)
  }

  /**
   * 重置状态
   */
  function reset() {
    selectedProjectId.value = ''
    selectedRequirementId.value = ''
    events.value = []
    versionHistory.value = []
    currentVersion.value = 0
    maxVersion.value = 0
    currentState.value = null
    previousState.value = null
    isPlaying.value = false
    isLoading.value = false
    isLoadingState.value = false
    error.value = null
    disconnectSSE()
  }

  return {
    // 状态
    selectedProjectId,
    selectedRequirementId,
    events,
    versionHistory,
    currentVersion,
    maxVersion,
    currentState,
    previousState,
    isPlaying,
    playbackSpeed,
    isLoading,
    isLoadingState,
    error,

    // 计算属性
    canPlayForward,
    canPlayBackward,
    versionProgress,
    currentEvent,

    // Actions
    loadEvents,
    rebuildState,
    setCurrentVersion,
    stepForward,
    stepBackward,
    jumpToStart,
    jumpToEnd,
    play,
    pause,
    connectSSE,
    disconnectSSE,
    submitCommand,
    updateContent,
    changeStatus,
    addQualityMarker,
    reset
  }
})
