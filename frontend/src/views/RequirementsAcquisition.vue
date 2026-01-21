
<script setup>
import { ref, computed, watch } from 'vue'
import { FileText, Loader2, ArrowRight, Briefcase, Users, Layout, Quote, Settings2 } from 'lucide-vue-next'

const inputText = ref('')
const isLoading = ref(false)
const error = ref(null)
const result = ref(null)
const progress = ref({
  stage: '',
  clean: { current: 0, total: 0 },
  extract: { current: 0, total: 0 }
})
const boardColumns = ref([])
const dragState = ref({
  cardId: null,
  fromColumnId: null,
  overColumnId: null,
  overIndex: null
})

const extractModel = ref('deepseek-reasoner')
const cleanModel = ref('deepseek-chat')

// 通过业务后端代理推理后端（保留 SSE 进度流，并在后端自动入库）
const INFERENCE_BASE = '/api/requirements'

const cleanPercent = computed(() => {
  const total = progress.value.clean.total
  if (!total) return 0
  return Math.round((progress.value.clean.current / total) * 100)
})

const extractPercent = computed(() => {
  const total = progress.value.extract.total
  if (!total) return 0
  return Math.round((progress.value.extract.current / total) * 100)
})

const baseColumns = [
  {
    id: 'business',
    title: 'L1 业务需求 (Mission)',
    icon: Briefcase,
    headerClass: 'bg-sky-50/70 border-sky-200',
    iconClass: 'text-sky-700',
    ringClass: 'ring-sky-200/80',
    badgeClass: 'bg-sky-100 text-sky-700 border-sky-200'
  },
  {
    id: 'stakeholder',
    title: 'L2 利益相关者需求',
    icon: Users,
    headerClass: 'bg-zinc-100/80 border-zinc-200',
    iconClass: 'text-zinc-700',
    ringClass: 'ring-zinc-300/70',
    badgeClass: 'bg-zinc-100 text-zinc-700 border-zinc-200'
  },
  {
    id: 'system',
    title: 'L3 系统需求',
    icon: Layout,
    headerClass: 'bg-amber-50/70 border-amber-200',
    iconClass: 'text-amber-700',
    ringClass: 'ring-amber-200/80',
    badgeClass: 'bg-amber-100 text-amber-700 border-amber-200'
  }
]

function buildBoard(payload) {
  if (!payload) {
    boardColumns.value = baseColumns.map((column) => ({ ...column, items: [] }))
    return
  }

  let counter = 0
  const toItems = (items, source) =>
    (items || []).map((item) => ({
      id: `${source}-${++counter}`,
      source,
      ...item
    }))

  boardColumns.value = baseColumns.map((column) => {
    if (column.id === 'business') {
      return { ...column, items: toItems(payload.business_requirements, column.id) }
    }
    if (column.id === 'stakeholder') {
      return { ...column, items: toItems(payload.stakeholder_requirements, column.id) }
    }
    return { ...column, items: toItems(payload.system_requirements, column.id) }
  })
}

function resetDragState() {
  dragState.value = {
    cardId: null,
    fromColumnId: null,
    overColumnId: null,
    overIndex: null
  }
}

function onDragStart(event, columnId, cardId) {
  dragState.value = {
    cardId,
    fromColumnId: columnId,
    overColumnId: columnId,
    overIndex: null
  }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', cardId)
}

function onColumnDragOver(event, columnId, itemCount) {
  if (!dragState.value.cardId) return
  // 只在以下情况更新到末尾位置：
  // 1. 刚进入新列（列ID变化）
  // 2. 之前没有设置过精确位置（overIndex 为 null）
  // 如果已经在同一列且有精确位置，保持不变（避免覆盖卡片间隙时的位置）
  if (dragState.value.overColumnId !== columnId || dragState.value.overIndex === null) {
    dragState.value.overColumnId = columnId
    dragState.value.overIndex = itemCount
  }
  event.dataTransfer.dropEffect = 'move'
}

function onCardDragOver(event, columnId, cardIndex) {
  if (!dragState.value.cardId) return
  event.stopPropagation()
  const rect = event.currentTarget.getBoundingClientRect()
  const offsetY = event.clientY - rect.top
  const ratio = offsetY / rect.height

  // 使用迟滞带防止在边界处抖动
  // 只有当鼠标明显进入上半部分 (<35%) 或下半部分 (>65%) 时才更新位置
  let insertIndex = dragState.value.overIndex
  if (dragState.value.overColumnId !== columnId) {
    // 刚进入新列，使用 50% 作为初始判断
    insertIndex = ratio > 0.5 ? cardIndex + 1 : cardIndex
  } else if (ratio < 0.35) {
    insertIndex = cardIndex
  } else if (ratio > 0.65) {
    insertIndex = cardIndex + 1
  }
  // 在 35%-65% 区间内保持上次的位置，避免抖动

  dragState.value.overColumnId = columnId
  dragState.value.overIndex = insertIndex
  event.dataTransfer.dropEffect = 'move'
}

function onDrop(columnId) {
  const { cardId, fromColumnId, overIndex } = dragState.value
  if (!cardId || !fromColumnId) {
    resetDragState()
    return
  }

  const fromColumn = boardColumns.value.find((column) => column.id === fromColumnId)
  const toColumn = boardColumns.value.find((column) => column.id === columnId)
  if (!fromColumn || !toColumn) {
    resetDragState()
    return
  }

  const cardIndex = fromColumn.items.findIndex((item) => item.id === cardId)
  if (cardIndex === -1) {
    resetDragState()
    return
  }

  const [card] = fromColumn.items.splice(cardIndex, 1)
  let targetIndex = Number.isInteger(overIndex) ? overIndex : toColumn.items.length

  if (fromColumnId === columnId && targetIndex > cardIndex) {
    targetIndex -= 1
  }

  const clampedIndex = Math.max(0, Math.min(targetIndex, toColumn.items.length))
  toColumn.items.splice(clampedIndex, 0, card)

  resetDragState()
}

function showDropIndicator(columnId, index) {
  return (
    dragState.value.cardId &&
    dragState.value.overColumnId === columnId &&
    dragState.value.overIndex === index
  )
}

watch(result, (payload) => {
  buildBoard(payload)
}, { immediate: true })

async function readResponsePayload(response) {
  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()
  if (!text) {
    return { data: null, text: '' }
  }
  if (contentType.includes('application/json')) {
    try {
      return { data: JSON.parse(text), text }
    } catch (err) {
      return { data: null, text }
    }
  }
  try {
    return { data: JSON.parse(text), text }
  } catch (err) {
    return { data: null, text }
  }
}

async function analyzeRequirements() {
  if (!inputText.value.trim()) return
  
  isLoading.value = true
  error.value = null
  result.value = null
  progress.value = {
    stage: '',
    clean: { current: 0, total: 0 },
    extract: { current: 0, total: 0 }
  }
  
  try {
    const response = await fetch(`${INFERENCE_BASE}/extract/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        text: inputText.value,
        chunk_size: 3600,
        overlap: 500,
        clean_model: cleanModel.value,
        extract_model: extractModel.value
      })
    })

    if (!response.ok) {
      const { data, text } = await readResponsePayload(response)
      const message = data?.error || data?.detail || `HTTP ${response.status}`
      const snippet = text ? text.replace(/\s+/g, ' ').slice(0, 200) : ''
      throw new Error(snippet ? `${message}: ${snippet}` : message)
    }

    if (!response.body) {
      throw new Error('Empty response body')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let streamError = null
    let gotResult = false

    const handleEvent = (event, payload) => {
      if (event === 'progress') {
        if (payload.stage === 'clean_polish') {
          progress.value.stage = 'clean_polish'
          progress.value.clean.current = payload.current || 0
          progress.value.clean.total = payload.total || 0
        } else if (payload.stage === 'extract') {
          progress.value.stage = 'extract'
          progress.value.extract.current = payload.current || 0
          progress.value.extract.total = payload.total || 0
        } else if (payload.stage === 'done') {
          progress.value.stage = 'done'
        }
        return
      }
      if (event === 'error') {
        streamError = payload?.error || 'Server error'
        return
      }
      if (event === 'result') {
        result.value = payload
        gotResult = true
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let splitIdx = buffer.indexOf('\n\n')
      while (splitIdx !== -1) {
        const rawEvent = buffer.slice(0, splitIdx)
        buffer = buffer.slice(splitIdx + 2)
        splitIdx = buffer.indexOf('\n\n')

        const lines = rawEvent.split('\n')
        let event = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            event = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            data += line.slice(5).trim()
          }
        }
        if (!data) continue
        try {
          const payload = JSON.parse(data)
          handleEvent(event, payload)
        } catch (err) {
          streamError = 'Invalid stream payload'
        }
        if (streamError || gotResult) {
          await reader.cancel()
          break
        }
      }
      if (streamError || gotResult) {
        break
      }
    }

    if (streamError) {
      throw new Error(streamError)
    }
    if (!gotResult) {
      throw new Error('Stream ended without result')
    }
  } catch (err) {
    error.value = err.message
  } finally {
    isLoading.value = false
  }
}

// Helpers for confidence color
function getConfidenceColor(conf) {
    if (conf >= 0.8) return 'text-green-600 bg-green-50 border-green-200'
    if (conf >= 0.5) return 'text-yellow-600 bg-yellow-50 border-yellow-200'
    return 'text-red-600 bg-red-50 border-red-200'
}
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 overflow-hidden">
    <!-- Header -->
    <header class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between shrink-0">
      <div>
        <h2 class="text-xl font-semibold text-zinc-900 flex items-center gap-2">
          <FileText class="w-5 h-5 text-black" />
          需求获取
        </h2>
        <p class="text-sm text-zinc-500 mt-1">将非结构化文本转换为结构化 L1/L2/L3 需求</p>
      </div>
    </header>

    <div class="flex-1 flex overflow-hidden">
      <!-- Left Panel: Input -->
      <div class="w-1/3 p-6 flex flex-col border-r border-zinc-200 bg-white min-w-[320px]">
        <label class="text-sm font-medium text-zinc-700 mb-2">原始输入文本 (笔记、访谈记录)</label>
        <textarea
          v-model="inputText"
          class="flex-1 w-full p-4 rounded-lg border border-zinc-300 resize-none focus:ring-2 focus:ring-black focus:border-black transition-all text-sm leading-relaxed"
          placeholder="在此粘贴原始会议纪要、访谈记录或粗略描述..."
        ></textarea>
        
        <div class="mt-4 flex flex-col gap-2">
          <!-- Settings -->
          <div class="p-4 bg-zinc-50 rounded-lg border border-zinc-200 space-y-3">
             <div class="flex items-center gap-2 mb-1">
                <Settings2 class="w-4 h-4 text-zinc-500" />
                <span class="text-xs font-semibold text-zinc-500 uppercase tracking-wider">模型设置</span>
             </div>
             <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">推理模型 (抽取)</label>
                <select v-model="extractModel" class="w-full text-sm border-zinc-300 rounded-md focus:ring-black focus:border-black">
                    <option value="deepseek-reasoner">deepseek-reasoner</option>
                    <option value="deepseek-chat">deepseek-chat</option>
                </select>
             </div>
             <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">聊天模型 (清洗)</label>
                <select v-model="cleanModel" class="w-full text-sm border-zinc-300 rounded-md focus:ring-black focus:border-black">
                    <option value="deepseek-chat">deepseek-chat</option>
                    <option value="deepseek-reasoner">deepseek-reasoner</option>
                </select>
             </div>
          </div>

           <div v-if="error" class="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200">
            Error: {{ error }}
          </div>

          <div v-if="isLoading" class="p-3 bg-zinc-50 rounded-md border border-zinc-200 space-y-2">
            <div class="flex items-center justify-between text-xs text-zinc-500">
              <span>清洗 & 润色</span>
              <span>{{ progress.clean.current }}/{{ progress.clean.total }}</span>
            </div>
            <div class="h-2 bg-zinc-200 rounded">
              <div class="h-2 bg-black rounded" :style="{ width: `${cleanPercent}%` }"></div>
            </div>
            <div class="flex items-center justify-between text-xs text-zinc-500 mt-2">
              <span>抽取</span>
              <span>{{ progress.extract.current }}/{{ progress.extract.total }}</span>
            </div>
            <div class="h-2 bg-zinc-200 rounded">
              <div class="h-2 bg-amber-500 rounded" :style="{ width: `${extractPercent}%` }"></div>
            </div>
          </div>
          
          <button
            @click="analyzeRequirements"
            :disabled="isLoading || !inputText"
            class="w-full py-2.5 px-4 bg-black hover:bg-zinc-800 text-white font-medium rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isLoading" class="w-4 h-4 animate-spin" />
            <span v-else>分析 & 抽取</span>
            <ArrowRight v-if="!isLoading" class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Right Panel: Output -->
      <div class="flex-1 overflow-x-auto bg-zinc-50 p-6">
        <div v-if="!result && !isLoading" class="h-full flex flex-col items-center justify-center text-zinc-400">
           <FileText class="w-12 h-12 mb-3 opacity-20" />
           <p>需求工件将显示在此处</p>
        </div>

        <div v-if="isLoading" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-black mb-4" />
            <p>正在清洗文本、润色语义并抽取需求...</p>
        </div>
        
        <!-- Results Grid -->
        <div v-if="result" class="grid grid-cols-3 gap-6 h-full min-w-[1024px]">
          
          <!-- L1 Business -->
          <div
            v-for="column in boardColumns"
            :key="column.id"
            class="flex flex-col rounded-2xl border bg-zinc-100/80 shadow-sm backdrop-blur-sm overflow-hidden h-full transition"
            :class="dragState.overColumnId === column.id ? `ring-2 ${column.ringClass} border-transparent` : 'border-zinc-200'"
            @dragover.prevent="onColumnDragOver($event, column.id, column.items.length)"
            @drop="onDrop(column.id)"
          >
            <div class="px-4 py-3 border-b flex items-center justify-between gap-2" :class="column.headerClass">
                <div class="flex items-center gap-2">
                  <component :is="column.icon" class="w-4 h-4" :class="column.iconClass" />
                  <h3 class="font-semibold text-zinc-800">{{ column.title }}</h3>
                </div>
                <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full border" :class="column.badgeClass">
                  {{ column.items.length }} cards
                </span>
            </div>
            <div class="flex-1 overflow-y-auto p-4 custom-scrollbar">
                <div class="flex flex-col gap-4">
                  <template v-for="(card, index) in column.items" :key="card.id">
                    <div
                      v-if="showDropIndicator(column.id, index)"
                      class="h-2 rounded-full border border-dashed border-zinc-300 bg-zinc-900/10"
                    ></div>
                    <div
                      class="p-4 rounded-xl border border-zinc-300 bg-white shadow-sm hover:shadow-md transition-all cursor-grab active:cursor-grabbing select-none"
                      :class="dragState.cardId === card.id ? 'opacity-50 scale-[0.98]' : ''"
                      draggable="true"
                      @dragstart="onDragStart($event, column.id, card.id)"
                      @dragend="resetDragState"
                      @dragover.prevent="onCardDragOver($event, column.id, index)"
                      @drop.stop="onDrop(column.id)"
                    >
                        <p class="text-zinc-900 font-medium mb-2">{{ card.statement }}</p>
                        <div class="text-xs text-zinc-500 mb-2 space-y-1">
                            <p class="italic" v-if="card.rationale"><span class="font-semibold">Rationale:</span> {{ card.rationale }}</p>
                        </div>
                         <!-- Evidence & Confidence Footer -->
                        <div class="flex items-center justify-between mt-3 pt-3 border-t border-zinc-50">
                            <div class="flex items-center gap-1.5 text-xs text-zinc-400 max-w-[70%] truncate" title="Evidence from source">
                                 <Quote class="w-3 h-3" />
                                 <span>"{{ card.evidence }}"</span>
                            </div>
                            <span class="text-[10px] px-1.5 py-0.5 rounded-full border" :class="getConfidenceColor(card.confidence)">
                                {{ (card.confidence * 100).toFixed(0) }}%
                            </span>
                        </div>
                    </div>
                  </template>
                  <div
                    v-if="showDropIndicator(column.id, column.items.length)"
                    class="h-2 rounded-full border border-dashed border-zinc-300 bg-zinc-900/10"
                  ></div>
                  <div v-if="column.items.length === 0" class="text-sm text-zinc-400 text-center py-10 border border-dashed border-zinc-200 rounded-xl bg-zinc-50/70">
                      将卡片拖拽至此
                  </div>
                </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 20px;
}
</style>
