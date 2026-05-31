<template>
  <div class="tab-content">
    <div v-if="!traceResult" class="empty-result">
      <Network class="empty-icon" />
      <p>点击「一键分析」生成追溯网络</p>
    </div>

    <div v-else class="network-shell">
      <div class="network-header">
        <div class="network-heading">
          <h3>需求追溯关系图</h3>
          <p>左侧聚合顶层需求，右侧展开底层执行项。拖拽卡片可调整视图，连线会实时跟随。</p>
        </div>
        <div class="network-summary">
          <span v-for="chip in summaryChips" :key="chip.label" class="summary-chip">
            <strong>{{ chip.value }}</strong>
            {{ chip.label }}
          </span>
        </div>
      </div>

      <div
        ref="boardRef"
        class="network-board"
        :style="{ minHeight: `${boardHeight}px` }"
      >
        <div class="board-guides">
          <div
            class="board-guide board-guide--interactive"
            :class="{ dragging: dragState?.type === 'guide' && dragState?.guide === 'left' }"
            :style="{ left: `${guidePositions.left}px` }"
            @pointerdown="onGuidePointerDown('left', $event)"
          >
            <span class="board-guide__handle">拖拽调整</span>
          </div>
          <div
            class="board-guide board-guide--interactive"
            :class="{ dragging: dragState?.type === 'guide' && dragState?.guide === 'right' }"
            :style="{ left: `${guidePositions.right}px` }"
            @pointerdown="onGuidePointerDown('right', $event)"
          >
            <span class="board-guide__handle">拖拽调整</span>
          </div>
        </div>

        <div class="board-top">
          <div class="lane-title lane-title-left">
            <strong>顶层需求</strong>
            <span>{{ leftNodes.length }} 个</span>
          </div>
          <div class="board-center-summary">
            <span class="summary-pill">{{ summaryStats.total }} 条已建立关系</span>
            <span class="summary-pill">{{ summaryStats.implementation }} 条主实现链路</span>
            <span class="summary-pill">{{ summaryStats.risk }} 条潜在冲突旁路</span>
          </div>
          <div class="lane-title lane-title-right">
            <strong>底层需求</strong>
            <span>{{ rightNodes.length }} 个</span>
          </div>
        </div>

        <svg class="board-links" :viewBox="`0 0 ${boardMetrics.width || 1} ${boardMetrics.height || 1}`" preserveAspectRatio="none">
          <defs>
            <marker
              v-for="type in markerTypes"
              :key="type.key"
              :id="type.markerId"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" :fill="type.color" />
            </marker>
          </defs>

          <path
            v-for="link in renderedLinks"
            :key="link.key"
            class="trace-link"
            :class="{
              active: isLinkFocused(link),
              dim: focusedNodeId && !isLinkFocused(link),
            }"
            :d="link.path"
            :stroke="link.color"
            :stroke-width="link.width"
            :marker-end="`url(#${link.markerId})`"
          />
        </svg>

        <article
          v-for="node in positionedNodes"
          :key="node.id"
          :ref="(el) => setNodeRef(node.id, el)"
          class="trace-card"
          :class="[
            node.side === 'left' ? `trace-card--${node.level.toLowerCase()}` : 'trace-card--low',
            {
              active: focusedNodeId === node.id,
              dim: focusedNodeId && !isNodeFocused(node.id),
              dragging: dragState?.type === 'card' && dragState?.id === node.id,
            },
          ]"
          :style="getNodeStyle(node)"
          @pointerdown="onCardPointerDown(node, $event)"
          @mouseenter="hoveredNodeId = node.id"
          @mouseleave="clearHover(node.id)"
        >
          <div class="trace-card__top">
            <span class="trace-card__code">{{ node.code }}</span>
            <span class="trace-card__level">{{ node.levelLabel }}</span>
          </div>

          <p class="trace-card__title">{{ node.title }}</p>

          <div class="trace-card__meta">
            <span
              v-for="tag in node.tags"
              :key="`${node.id}-${tag}`"
              class="trace-card__tag"
            >
              {{ tag }}
            </span>
          </div>

          <div class="trace-card__footer">
            <span>关联 {{ linkCountByNode[node.id] || 0 }} 条</span>
            <span>拖拽调整</span>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Network } from 'lucide-vue-next'

const CARD_WIDTH = 260
const DEFAULT_CARD_HEIGHT = 124
const BOARD_SIDE_PADDING = 18
const GUIDE_CARD_GAP = 18
const GUIDE_MIN_CENTER_GAP = 280
const KEYWORD_TAGS = [
  '统一规划',
  '执行监控',
  '时间窗口',
  '审批',
  '签名校验',
  '发送回执',
  '姿态准备',
  '载荷预热',
  '观测窗口',
  '安全保护',
  '自动终止',
  '紧急例外',
  '流程旁路',
  '状态检查',
  '安全审计',
  '实时阻断',
  '全链路留痕',
  '双人审批',
  '状态同步',
  '进度反馈',
  '时间冲突',
  '重排',
  '界面呈现',
  '圈次',
]

const props = defineProps({
  traceResult: { type: Object, default: null },
  allHighLevelRequirements: { type: Array, default: () => [] },
  lowLevelRequirements: { type: Array, default: () => [] },
  isActive: { type: Boolean, default: false },
})

const boardRef = ref(null)
const boardMetrics = ref({ width: 0, height: 0 })
const hoveredNodeId = ref('')
const nodeLayouts = ref({})
const nodeSizes = ref({})
const renderedLinks = ref([])
const dragState = ref(null)
const guideState = ref({ left: 0, right: 0 })

const nodeElements = new Map()
let resizeObserver = null
let sceneRefreshRaf = 0
let linkRefreshRaf = 0

function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase()
  if (!text) return 'L1'
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1'
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2'
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3'
  return 'L1'
}

function getRelationTypeColor(type) {
  const colors = {
    implementation: '#54b97f',
    support: '#78a8ff',
    dependency: '#e29a72',
    decomposition: '#efb85d',
    general: '#97a0ab',
  }
  return colors[type] || '#97a0ab'
}

function getRelationStrokeWidth(type) {
  if (type === 'implementation') return 2.4
  if (type === 'dependency') return 2
  return 1.7
}

function getLevelLabel(level) {
  const labels = {
    L1: 'L1 业务',
    L2: 'L2 相关方',
    L3: 'L3 系统',
    L4: '底层需求',
  }
  return labels[level] || '需求'
}

function getStatement(req, fallback = '') {
  return String(req?.statement || req?.text || req?.title || req?.shall_statement || fallback || '').trim()
}

function formatCode(rawId, prefix, index) {
  const fallback = `${prefix}-${String(index + 1).padStart(2, '0')}`
  return String(rawId || fallback).trim().toUpperCase()
}

function getFallbackTags(text) {
  const parts = String(text || '')
    .split(/[，。,；;、\s]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => item.replace(/^(进行|完成|实现|支持|允许|记录|显示|检测到|任务|系统|卫星|所有|当前)/, '').trim())
    .filter((item) => item.length >= 2)
    .map((item) => item.slice(0, 6))

  return [...new Set(parts)].slice(0, 3)
}

function buildTags(req, level, side) {
  const statement = getStatement(req)
  const tags = []

  KEYWORD_TAGS.forEach((tag) => {
    if (statement.includes(tag) && !tags.includes(tag)) tags.push(tag)
  })

  ;[req?.priority, req?.status, req?.module, req?.component]
    .filter(Boolean)
    .forEach((tag) => {
      const text = String(tag).trim()
      if (text && !tags.includes(text)) tags.push(text.slice(0, 8))
    })

  if (!tags.length) {
    tags.push(...getFallbackTags(statement))
  }

  if (!tags.length) {
    tags.push(side === 'left' ? getLevelLabel(level) : '底层需求')
  }

  return tags.slice(0, 3)
}

function buildNode(req, index, side) {
  const level = side === 'left' ? normalizeLevel(req.level || req.category) : 'L4'
  const id = req.req_id || req.id || `${side}_${index}`
  const title = getStatement(req, `未命名${side === 'left' ? '顶层' : '底层'}需求`)
  return {
    id,
    side,
    level,
    code: formatCode(req.req_id || req.id, side === 'left' ? 'REQ' : 'LOW', index),
    title,
    tags: buildTags(req, level, side),
    levelLabel: getLevelLabel(level),
  }
}

const leftNodes = computed(() => props.allHighLevelRequirements.map((req, index) => buildNode(req, index, 'left')))
const rightNodes = computed(() => props.lowLevelRequirements.map((req, index) => buildNode(req, index, 'right')))
const allNodes = computed(() => [...leftNodes.value, ...rightNodes.value])

const relations = computed(() => {
  const availableIds = new Set(allNodes.value.map((node) => node.id))
  const relationList = Array.isArray(props.traceResult?.relations) ? props.traceResult.relations : []

  return relationList
    .filter((rel) => rel?.has_relation !== false)
    .map((rel, index) => {
      const source = rel.high_req_id
      const target = rel.low_req_id
      return {
        key: `${source || 'high'}-${target || 'low'}-${index}`,
        source,
        target,
        type: rel.relation_type || 'general',
        color: getRelationTypeColor(rel.relation_type),
        width: getRelationStrokeWidth(rel.relation_type),
      }
    })
    .filter((rel) => availableIds.has(rel.source) && availableIds.has(rel.target))
})

const linkCountByNode = computed(() => {
  const counts = {}
  relations.value.forEach((rel) => {
    counts[rel.source] = (counts[rel.source] || 0) + 1
    counts[rel.target] = (counts[rel.target] || 0) + 1
  })
  return counts
})

const summaryStats = computed(() => {
  const stats = {
    total: relations.value.length,
    implementation: 0,
    support: 0,
    dependency: 0,
    risk: 0,
  }

  relations.value.forEach((rel) => {
    if (rel.type === 'implementation') stats.implementation += 1
    if (rel.type === 'support') stats.support += 1
    if (rel.type === 'dependency' || rel.type === 'decomposition') {
      stats.dependency += 1
      stats.risk += 1
    }
  })

  return stats
})

const summaryChips = computed(() => ([
  { label: '顶层需求', value: leftNodes.value.length },
  { label: '底层需求', value: rightNodes.value.length },
  { label: '追溯关系', value: summaryStats.value.total },
  { label: '可拖拽卡片', value: allNodes.value.length },
]))

const markerTypes = computed(() => {
  const seen = new Set()
  return relations.value.reduce((items, rel) => {
    if (seen.has(rel.type)) return items
    seen.add(rel.type)
    items.push({
      key: rel.type,
      markerId: `trace-marker-${rel.type}`,
      color: rel.color,
    })
    return items
  }, [])
})

const boardHeight = computed(() => {
  const maxCount = Math.max(leftNodes.value.length, rightNodes.value.length, 1)
  return Math.max(720, 150 + maxCount * 108)
})

const focusedNodeId = computed(() => hoveredNodeId.value || dragState.value?.id || '')

const positionedNodes = computed(() => allNodes.value.map((node) => ({
  ...node,
  position: nodeLayouts.value[node.id] || getFallbackPosition(node.side),
})))

const guidePositions = computed(() => guideState.value)

function getLaneWidth(width) {
  return Math.min(340, Math.max(290, width * 0.23))
}

function getGuideLimits(width) {
  const minLeft = BOARD_SIDE_PADDING + CARD_WIDTH + GUIDE_CARD_GAP
  const maxRight = Math.max(minLeft + GUIDE_MIN_CENTER_GAP, width - BOARD_SIDE_PADDING - CARD_WIDTH - GUIDE_CARD_GAP)
  return { minLeft, maxRight }
}

function clampGuidePositions(positions, width) {
  const safeWidth = width || boardMetrics.value.width || 1280
  const laneWidth = getLaneWidth(safeWidth)
  const defaultLeft = laneWidth + 24
  const defaultRight = Math.max(defaultLeft + GUIDE_MIN_CENTER_GAP, safeWidth - laneWidth - 24)
  const { minLeft, maxRight } = getGuideLimits(safeWidth)
  let left = Number.isFinite(positions?.left) ? positions.left : defaultLeft
  let right = Number.isFinite(positions?.right) ? positions.right : defaultRight

  left = clamp(left, minLeft, maxRight - GUIDE_MIN_CENTER_GAP)
  right = clamp(right, left + GUIDE_MIN_CENTER_GAP, maxRight)
  left = clamp(left, minLeft, right - GUIDE_MIN_CENTER_GAP)

  return { left, right }
}

function syncGuidePositions() {
  const width = boardMetrics.value.width || boardRef.value?.clientWidth || 0
  if (!width) return
  guideState.value = clampGuidePositions(guideState.value, width)
}

function getFallbackPosition(side) {
  const width = boardMetrics.value.width || 1280
  const guides = clampGuidePositions(guideState.value, width)
  return {
    x: side === 'left'
      ? BOARD_SIDE_PADDING
      : Math.max(BOARD_SIDE_PADDING, guides.right + GUIDE_CARD_GAP),
    y: 92,
  }
}

function getNodeHeight(nodeId) {
  return nodeSizes.value[nodeId]?.height || DEFAULT_CARD_HEIGHT
}

function getLaneBounds(side, nodeHeight = DEFAULT_CARD_HEIGHT) {
  const width = boardMetrics.value.width || 1280
  const height = boardMetrics.value.height || boardHeight.value
  const guides = clampGuidePositions(guideState.value, width)
  const minY = 86
  const maxY = Math.max(minY, height - nodeHeight - 20)

  if (side === 'left') {
    const minX = BOARD_SIDE_PADDING
    const maxX = Math.max(minX, guides.left - CARD_WIDTH - GUIDE_CARD_GAP)
    return { minX, maxX, minY, maxY, defaultX: minX }
  }

  const minX = Math.max(BOARD_SIDE_PADDING, guides.right + GUIDE_CARD_GAP)
  const maxX = Math.max(minX, width - CARD_WIDTH - BOARD_SIDE_PADDING)
  return { minX, maxX, minY, maxY, defaultX: maxX }
}

function distributeY(index, total, bounds) {
  if (total <= 1) return bounds.minY + Math.max(0, (bounds.maxY - bounds.minY) / 2)
  return bounds.minY + ((bounds.maxY - bounds.minY) * index) / (total - 1)
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function setNodeRef(id, el) {
  if (el) {
    nodeElements.set(id, el)
  } else {
    nodeElements.delete(id)
  }
}

function measureScene() {
  if (!boardRef.value) return

  boardMetrics.value = {
    width: boardRef.value.clientWidth,
    height: boardRef.value.clientHeight,
  }

  const nextSizes = {}
  nodeElements.forEach((el, id) => {
    nextSizes[id] = {
      width: el.offsetWidth || CARD_WIDTH,
      height: el.offsetHeight || DEFAULT_CARD_HEIGHT,
    }
  })
  nodeSizes.value = nextSizes
}

function syncNodeLayouts({ reset = false } = {}) {
  if (!boardRef.value) return

  const nextLayouts = {}
  const currentLayouts = nodeLayouts.value || {}

  ;[
    { side: 'left', nodes: leftNodes.value },
    { side: 'right', nodes: rightNodes.value },
  ].forEach(({ side, nodes }) => {
    nodes.forEach((node, index) => {
      const nodeHeight = getNodeHeight(node.id)
      const bounds = getLaneBounds(side, nodeHeight)
      const existing = currentLayouts[node.id]

      nextLayouts[node.id] = {
        x: reset || !existing
          ? bounds.defaultX
          : clamp(existing.x, bounds.minX, bounds.maxX),
        y: reset || !existing
          ? distributeY(index, nodes.length, bounds)
          : clamp(existing.y, bounds.minY, bounds.maxY),
      }
    })
  })

  nodeLayouts.value = nextLayouts
}

function buildRenderedLinks() {
  if (!boardMetrics.value.width || !boardMetrics.value.height) {
    renderedLinks.value = []
    return
  }

  renderedLinks.value = relations.value
    .map((rel) => {
      const sourceLayout = nodeLayouts.value[rel.source]
      const targetLayout = nodeLayouts.value[rel.target]
      if (!sourceLayout || !targetLayout) return null

      const sourceHeight = getNodeHeight(rel.source)
      const targetHeight = getNodeHeight(rel.target)

      const startX = sourceLayout.x + CARD_WIDTH
      const startY = sourceLayout.y + sourceHeight / 2
      const endX = targetLayout.x
      const endY = targetLayout.y + targetHeight / 2
      const curve = Math.max(140, Math.abs(endX - startX) * 0.34)

      return {
        ...rel,
        path: `M ${startX} ${startY} C ${startX + curve} ${startY}, ${endX - curve} ${endY}, ${endX} ${endY}`,
        markerId: `trace-marker-${rel.type}`,
      }
    })
    .filter(Boolean)
}

async function refreshScene({ reset = false } = {}) {
  if (!props.isActive || !props.traceResult) return

  await nextTick()
  measureScene()
  syncGuidePositions()
  syncNodeLayouts({ reset })

  await nextTick()
  measureScene()
  syncGuidePositions()
  syncNodeLayouts({ reset: false })
  buildRenderedLinks()
}

function scheduleSceneRefresh(options = {}) {
  if (sceneRefreshRaf) cancelAnimationFrame(sceneRefreshRaf)
  sceneRefreshRaf = requestAnimationFrame(() => {
    sceneRefreshRaf = 0
    refreshScene(options)
  })
}

function scheduleLinkRefresh() {
  if (linkRefreshRaf) cancelAnimationFrame(linkRefreshRaf)
  linkRefreshRaf = requestAnimationFrame(() => {
    linkRefreshRaf = 0
    buildRenderedLinks()
  })
}

function getNodeStyle(node) {
  const position = node.position || getFallbackPosition(node.side)
  return {
    width: `${CARD_WIDTH}px`,
    transform: `translate(${position.x}px, ${position.y}px)`,
  }
}

function isNodeFocused(nodeId) {
  if (!focusedNodeId.value) return true
  if (focusedNodeId.value === nodeId) return true
  return relations.value.some((rel) => (
    (rel.source === focusedNodeId.value && rel.target === nodeId) ||
    (rel.target === focusedNodeId.value && rel.source === nodeId)
  ))
}

function isLinkFocused(link) {
  if (!focusedNodeId.value) return true
  return link.source === focusedNodeId.value || link.target === focusedNodeId.value
}

function clearHover(nodeId) {
  if (dragState.value?.type === 'card' && dragState.value?.id === nodeId) return
  if (hoveredNodeId.value === nodeId) hoveredNodeId.value = ''
}

function onGuidePointerDown(guide, event) {
  if (event.button !== 0) return

  dragState.value = {
    type: 'guide',
    guide,
    startX: event.clientX,
    origin: guideState.value[guide],
  }

  hoveredNodeId.value = ''
  event.preventDefault()
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onCardPointerDown(node, event) {
  if (event.button !== 0) return

  const origin = nodeLayouts.value[node.id]
  if (!origin) return

  dragState.value = {
    type: 'card',
    id: node.id,
    side: node.side,
    startX: event.clientX,
    startY: event.clientY,
    originX: origin.x,
    originY: origin.y,
  }

  hoveredNodeId.value = node.id
  event.preventDefault()
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

function onPointerMove(event) {
  if (!dragState.value) return

  if (dragState.value.type === 'guide') {
    const width = boardMetrics.value.width || boardRef.value?.clientWidth || 0
    if (!width) return

    const { guide, startX, origin } = dragState.value
    guideState.value = clampGuidePositions(
      {
        ...guideState.value,
        [guide]: origin + (event.clientX - startX),
      },
      width,
    )
    syncNodeLayouts({ reset: false })
    scheduleLinkRefresh()
    return
  }

  const { id, side, startX, startY, originX, originY } = dragState.value
  const bounds = getLaneBounds(side, getNodeHeight(id))

  nodeLayouts.value = {
    ...nodeLayouts.value,
    [id]: {
      x: clamp(originX + (event.clientX - startX), bounds.minX, bounds.maxX),
      y: clamp(originY + (event.clientY - startY), bounds.minY, bounds.maxY),
    },
  }

  scheduleLinkRefresh()
}

function stopDragging() {
  dragState.value = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}

function onPointerUp() {
  stopDragging()
}

const nodeSignature = computed(() => allNodes.value.map((node) => `${node.id}:${node.title}`).join('|'))
const relationSignature = computed(() => relations.value.map((rel) => `${rel.source}-${rel.target}-${rel.type}`).join('|'))

watch(
  () => props.isActive,
  (isActive) => {
    if (isActive) scheduleSceneRefresh({ reset: false })
  },
)

watch(
  [nodeSignature, relationSignature],
  () => {
    if (props.isActive && props.traceResult) scheduleSceneRefresh({ reset: true })
  },
)

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (props.isActive && props.traceResult) scheduleSceneRefresh({ reset: false })
    })
    if (boardRef.value) resizeObserver.observe(boardRef.value)
  }

  if (props.isActive && props.traceResult) {
    scheduleSceneRefresh({ reset: true })
  }
})

watch(boardRef, (element, previous) => {
  if (resizeObserver && previous) resizeObserver.unobserve(previous)
  if (resizeObserver && element) resizeObserver.observe(element)
})

onBeforeUnmount(() => {
  if (sceneRefreshRaf) cancelAnimationFrame(sceneRefreshRaf)
  if (linkRefreshRaf) cancelAnimationFrame(linkRefreshRaf)
  if (resizeObserver) resizeObserver.disconnect()
  stopDragging()
})
</script>

<style scoped>
.tab-content {
  height: 100%;
  overflow-y: auto;
  background:
    radial-gradient(circle at 52% 44%, rgba(47, 143, 137, 0.06), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 247, 241, 0.94));
}

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: rgba(28, 40, 52, 0.4);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.3;
}

.network-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
  padding: 6px;
}

.network-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 10px 4px 0;
}

.network-heading h3 {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink-950);
}

.network-heading p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(28, 40, 52, 0.58);
}

.network-summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: rgba(255, 255, 255, 0.78);
  font-size: 11px;
  color: rgba(28, 40, 52, 0.62);
  white-space: nowrap;
}

.summary-chip strong {
  color: var(--ink-950);
  font-size: 12px;
}

.network-board {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background:
    radial-gradient(circle at 50% 50%, rgba(47, 143, 137, 0.08), transparent 40%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(249, 244, 235, 0.82));
}

.board-guides {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.board-guide {
  position: absolute;
  top: 56px;
  bottom: 18px;
  width: 1px;
  background: linear-gradient(180deg, rgba(28, 40, 52, 0), rgba(28, 40, 52, 0.1), rgba(28, 40, 52, 0));
  border-left: 1px dashed rgba(28, 40, 52, 0.08);
}

.board-guide--interactive {
  pointer-events: auto;
  cursor: col-resize;
}

.board-guide--interactive::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -10px;
  width: 20px;
}

.board-guide--interactive.dragging,
.board-guide--interactive:hover {
  border-left-color: rgba(196, 105, 47, 0.42);
}

.board-guide__handle {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 8px;
  border: 1px solid rgba(28, 40, 52, 0.07);
  background: rgba(255, 255, 255, 0.88);
  color: rgba(28, 40, 52, 0.54);
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.board-guide--interactive.dragging .board-guide__handle,
.board-guide--interactive:hover .board-guide__handle {
  opacity: 1;
  color: var(--accent-strong);
  border-color: rgba(196, 105, 47, 0.18);
}

.board-top {
  position: absolute;
  inset: 14px 18px auto;
  display: grid;
  grid-template-columns: 260px 1fr 260px;
  align-items: center;
  gap: 14px;
  z-index: 3;
}

.lane-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: rgba(28, 40, 52, 0.58);
}

.lane-title strong {
  color: var(--ink-950);
  font-size: 13px;
}

.board-center-summary {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.summary-pill {
  padding: 7px 10px;
  border: 1px solid rgba(28, 40, 52, 0.07);
  background: rgba(255, 255, 255, 0.78);
  font-size: 11px;
  color: rgba(28, 40, 52, 0.64);
  white-space: nowrap;
}

.board-links {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.trace-link {
  fill: none;
  opacity: 0.5;
  transition: opacity 0.18s ease, stroke-width 0.18s ease;
}

.trace-link.active {
  opacity: 0.98;
}

.trace-link.dim {
  opacity: 0.1;
}

.trace-card {
  position: absolute;
  z-index: 2;
  padding: 12px 12px 10px;
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 10px 28px rgba(28, 40, 52, 0.08);
  cursor: grab;
  user-select: none;
  transition: box-shadow 0.18s ease, transform 0.18s ease, opacity 0.18s ease;
}

.trace-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  border-radius: 18px 0 0 18px;
  background: currentColor;
  opacity: 0.9;
}

.trace-card:hover,
.trace-card.active {
  box-shadow: 0 14px 32px rgba(28, 40, 52, 0.12);
}

.trace-card.dragging {
  cursor: grabbing;
  z-index: 4;
}

.trace-card.dim {
  opacity: 0.28;
}

.trace-card--l1 {
  color: #5b8df7;
  background: linear-gradient(135deg, rgba(91, 141, 247, 0.1), rgba(255, 255, 255, 0.96) 55%);
}

.trace-card--l2 {
  color: #8561ef;
  background: linear-gradient(135deg, rgba(133, 97, 239, 0.1), rgba(255, 255, 255, 0.96) 55%);
}

.trace-card--l3 {
  color: #f2a93f;
  background: linear-gradient(135deg, rgba(242, 169, 63, 0.11), rgba(255, 255, 255, 0.96) 55%);
}

.trace-card--low {
  color: #65b783;
  background: linear-gradient(135deg, rgba(101, 183, 131, 0.1), rgba(255, 255, 255, 0.96) 55%);
}

.trace-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.trace-card__code {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: rgba(28, 40, 52, 0.5);
}

.trace-card__level {
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(28, 40, 52, 0.06);
  background: rgba(255, 255, 255, 0.82);
  font-size: 10px;
  font-weight: 700;
  color: currentColor;
  white-space: nowrap;
}

.trace-card__title {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-950);
  word-break: break-word;
}

.trace-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.trace-card__tag {
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(28, 40, 52, 0.05);
  font-size: 10px;
  color: rgba(28, 40, 52, 0.62);
  white-space: nowrap;
}

.trace-card__footer {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 10px;
  color: rgba(28, 40, 52, 0.45);
}

@media (max-width: 1200px) {
  .network-header {
    flex-direction: column;
  }

  .network-summary {
    justify-content: flex-start;
  }
}
</style>
