<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { Bot, X } from 'lucide-vue-next'
import AiChatPanel from './AiChatPanel.vue'
import { aiChatApi, agentTaskApi } from '../../utils/api'

const props = defineProps({
    projectId: {
        type: String,
        default: null,
    },
})

const resolvedProjectId = ref(null)

const syncProjectId = () => {
    resolvedProjectId.value = props.projectId || localStorage.getItem('lastProjectId') || null
}

// Panel state
const isPanelOpen = ref(false)
const isMinimized = ref(false)

// Notification counts
const unreadCount = ref(0)
const pendingTaskCount = ref(0)

// Dragging state
const ballRef = ref(null)
const isDragging = ref(false)
const hasDragged = ref(false)
const position = ref({ x: 0, y: 0 })
const dragStart = ref({ x: 0, y: 0 })
const initialPos = ref({ x: 0, y: 0 })

// Computed
const hasNotification = computed(() => unreadCount.value > 0 || pendingTaskCount.value > 0)
const notificationCount = computed(() => unreadCount.value + pendingTaskCount.value)

const panelSide = ref('right')

const updatePanelSide = () => {
    const ball = ballRef.value
    if (!ball) return
    const rect = ball.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    panelSide.value = centerX < window.innerWidth / 2 ? 'left' : 'right'
}

// Ball position style
const ballStyle = computed(() => {
    if (position.value.x === 0 && position.value.y === 0) {
        // Default position: bottom-right
        return {
            right: '24px',
            bottom: '24px',
        }
    }
    return {
        left: `${position.value.x}px`,
        top: `${position.value.y}px`,
    }
})

// Fetch notification counts
const fetchCounts = async () => {
    try {
        syncProjectId()
        const [unread, pending] = await Promise.all([
            aiChatApi.getUnreadCount({ projectId: resolvedProjectId.value }),
            agentTaskApi.getPendingCount({ projectId: resolvedProjectId.value }),
        ])
        unreadCount.value = unread
        pendingTaskCount.value = pending
    } catch (e) {
        console.error('Failed to fetch notification counts:', e)
    }
}

// Panel actions
const togglePanel = () => {
    if (hasDragged.value) {
        hasDragged.value = false
        return
    }

    syncProjectId()

    if (isMinimized.value) {
        isMinimized.value = false
        isPanelOpen.value = true
    } else {
        isPanelOpen.value = !isPanelOpen.value
    }
}

const closePanel = () => {
    isPanelOpen.value = false
    isMinimized.value = false
}

const minimizePanel = () => {
    isMinimized.value = true
    isPanelOpen.value = false
}

// Drag handlers
const onMouseDown = (e) => {
    if (e.button !== 0) return // Only left click
    isDragging.value = true
    hasDragged.value = false
    dragStart.value = { x: e.clientX, y: e.clientY }
    
    const ball = ballRef.value
    if (ball) {
        const rect = ball.getBoundingClientRect()
        initialPos.value = { x: rect.left, y: rect.top }
    }
    
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    e.preventDefault()
}

const onMouseMove = (e) => {
    if (!isDragging.value) return
    
    const dx = e.clientX - dragStart.value.x
    const dy = e.clientY - dragStart.value.y
    
    // Consider it a drag if moved more than 5px
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
        hasDragged.value = true
    }
    
    let newX = initialPos.value.x + dx
    let newY = initialPos.value.y + dy
    
    // Keep within viewport
    const ballSize = 56 // w-14 = 56px
    newX = Math.max(0, Math.min(window.innerWidth - ballSize, newX))
    newY = Math.max(0, Math.min(window.innerHeight - ballSize, newY))
    
    position.value = { x: newX, y: newY }
}

const onMouseUp = () => {
    if (!isDragging.value) return
    isDragging.value = false
    
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    
    // Edge snapping
    if (hasDragged.value) {
        snapToEdge()
        updatePanelSide()
    }
}

const snapToEdge = () => {
    const ballSize = 56
    const padding = 24
    const centerX = position.value.x + ballSize / 2
    const viewportWidth = window.innerWidth
    
    // Snap to left or right edge
    if (centerX < viewportWidth / 2) {
        position.value.x = padding
    } else {
        position.value.x = viewportWidth - ballSize - padding
    }
}

// Touch handlers for mobile
const onTouchStart = (e) => {
    const touch = e.touches[0]
    isDragging.value = true
    hasDragged.value = false
    dragStart.value = { x: touch.clientX, y: touch.clientY }
    
    const ball = ballRef.value
    if (ball) {
        const rect = ball.getBoundingClientRect()
        initialPos.value = { x: rect.left, y: rect.top }
    }
}

const onTouchMove = (e) => {
    if (!isDragging.value) return
    const touch = e.touches[0]
    
    const dx = touch.clientX - dragStart.value.x
    const dy = touch.clientY - dragStart.value.y
    
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
        hasDragged.value = true
    }
    
    let newX = initialPos.value.x + dx
    let newY = initialPos.value.y + dy
    
    const ballSize = 56
    newX = Math.max(0, Math.min(window.innerWidth - ballSize, newX))
    newY = Math.max(0, Math.min(window.innerHeight - ballSize, newY))
    
    position.value = { x: newX, y: newY }
    e.preventDefault()
}

const onTouchEnd = () => {
    if (!isDragging.value) return
    isDragging.value = false
    
    if (hasDragged.value) {
        snapToEdge()
        updatePanelSide()
    }
}

// Event handlers for panel updates
const onMessagesRead = () => {
    fetchCounts()
}

const onTaskResolved = () => {
    fetchCounts()
}

// Polling for notification updates
let pollInterval = null

onMounted(() => {
    syncProjectId()
    fetchCounts()
    pollInterval = setInterval(fetchCounts, 30000) // Poll every 30 seconds

    updatePanelSide()
    window.addEventListener('resize', updatePanelSide)
})

onBeforeUnmount(() => {
    if (pollInterval) {
        clearInterval(pollInterval)
    }
    window.removeEventListener('resize', updatePanelSide)
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
})

// Watch for project changes
watch(() => props.projectId, () => {
    syncProjectId()
    fetchCounts()
})
</script>

<template>
    <div class="fixed z-[9999]" :style="ballStyle" ref="ballRef">
        <!-- Floating Ball -->
        <button
            @mousedown="onMouseDown"
            @touchstart.passive="onTouchStart"
            @touchmove="onTouchMove"
            @touchend="onTouchEnd"
            @click="togglePanel"
            class="ai-fab-btn relative w-14 h-14 rounded-full shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center cursor-pointer select-none"
            :class="{ 'scale-95': isDragging, 'ai-fab-open': isPanelOpen }"
        >
            <Bot class="w-6 h-6" />
            
            <!-- Notification Badge -->
            <span
                v-if="hasNotification"
                class="ai-fab-badge absolute -top-1 -right-1 min-w-5 h-5 px-1.5 text-white text-xs font-bold rounded-full flex items-center justify-center shadow-sm animate-pulse"
            >
                {{ notificationCount > 99 ? '99+' : notificationCount }}
            </span>
            
            <!-- Minimized indicator -->
            <span
                v-if="isMinimized && !hasNotification"
                class="ai-fab-dot absolute -top-1 -right-1 w-3 h-3 rounded-full shadow-sm"
            />
        </button>

        <!-- Chat Panel -->
        <Transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 scale-95 translate-y-2"
            enter-to-class="opacity-100 scale-100 translate-y-0"
            leave-active-class="transition-all duration-150 ease-in"
            leave-from-class="opacity-100 scale-100 translate-y-0"
            leave-to-class="opacity-0 scale-95 translate-y-2"
        >
            <AiChatPanel
                v-if="isPanelOpen"
                :project-id="resolvedProjectId"
                :anchor-side="panelSide"
                :unread-count="unreadCount"
                :pending-task-count="pendingTaskCount"
                @close="closePanel"
                @minimize="minimizePanel"
                @messages-read="onMessagesRead"
                @task-resolved="onTaskResolved"
            />
        </Transition>
    </div>
</template>

<style scoped>
.ai-fab-btn {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
  color: #fff;
  box-shadow: 0 14px 30px rgba(27, 39, 48, 0.18);
}

.ai-fab-btn:hover {
  filter: saturate(1.05);
}

.ai-fab-open {
  outline: 2px solid rgba(196, 105, 47, 0.35);
  outline-offset: 2px;
}

.ai-fab-badge {
  background: var(--signal);
}

.ai-fab-dot {
  background: var(--teal);
}
</style>
