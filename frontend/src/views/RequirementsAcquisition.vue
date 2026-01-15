
<script setup>
import { ref, computed } from 'vue'
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

const extractModel = ref('deepseek-reasoner')
const cleanModel = ref('deepseek-chat')

// Configure base URL roughly based on dev setup
const INFERENCE_BASE = '/inference'

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
    const response = await fetch(`${INFERENCE_BASE}/acquisition/extract/stream`, {
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
          Requirement Acquisition
        </h2>
        <p class="text-sm text-zinc-500 mt-1">Transform unstructured text into structured L1/L2/L3 requirements</p>
      </div>
    </header>

    <div class="flex-1 flex overflow-hidden">
      <!-- Left Panel: Input -->
      <div class="w-1/3 p-6 flex flex-col border-r border-zinc-200 bg-white min-w-[320px]">
        <label class="text-sm font-medium text-zinc-700 mb-2">Raw Input Text (Notes, Transcript)</label>
        <textarea
          v-model="inputText"
          class="flex-1 w-full p-4 rounded-lg border border-zinc-300 resize-none focus:ring-2 focus:ring-black focus:border-black transition-all text-sm leading-relaxed"
          placeholder="Paste raw meeting notes, interview transcripts, or rough descriptions here..."
        ></textarea>
        
        <div class="mt-4 flex flex-col gap-2">
          <!-- Settings -->
          <div class="p-4 bg-zinc-50 rounded-lg border border-zinc-200 space-y-3">
             <div class="flex items-center gap-2 mb-1">
                <Settings2 class="w-4 h-4 text-zinc-500" />
                <span class="text-xs font-semibold text-zinc-500 uppercase tracking-wider">Model Settings</span>
             </div>
             <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">Inference Model (Extraction)</label>
                <select v-model="extractModel" class="w-full text-sm border-zinc-300 rounded-md focus:ring-black focus:border-black">
                    <option value="deepseek-reasoner">deepseek-reasoner</option>
                    <option value="deepseek-chat">deepseek-chat</option>
                </select>
             </div>
             <div>
                <label class="text-xs font-medium text-zinc-600 block mb-1">Chat Model (Cleaning)</label>
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
              <span>Clean & Polish</span>
              <span>{{ progress.clean.current }}/{{ progress.clean.total }}</span>
            </div>
            <div class="h-2 bg-zinc-200 rounded">
              <div class="h-2 bg-black rounded" :style="{ width: `${cleanPercent}%` }"></div>
            </div>
            <div class="flex items-center justify-between text-xs text-zinc-500 mt-2">
              <span>Extract</span>
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
            <span v-else>Analyze & Extract</span>
            <ArrowRight v-if="!isLoading" class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Right Panel: Output -->
      <div class="flex-1 overflow-x-auto bg-zinc-50 p-6">
        <div v-if="!result && !isLoading" class="h-full flex flex-col items-center justify-center text-zinc-400">
           <FileText class="w-12 h-12 mb-3 opacity-20" />
           <p>Requirement artifacts will appear here</p>
        </div>

        <div v-if="isLoading" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <Loader2 class="w-10 h-10 animate-spin text-black mb-4" />
            <p>Cleaning text, polishing semantics, and extracting requirements...</p>
        </div>
        
        <!-- Results Grid -->
        <div v-if="result" class="grid grid-cols-3 gap-6 h-full min-w-[1024px]">
          
          <!-- L1 Business -->
          <div class="flex flex-col bg-white rounded-xl shadow-sm border border-zinc-200 overflow-hidden h-full">
            <div class="px-4 py-3 bg-blue-50/50 border-b border-zinc-200 flex items-center gap-2">
                <Briefcase class="w-4 h-4 text-blue-600" />
                <h3 class="font-semibold text-zinc-800">L1 Business (Mission)</h3>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
                <div v-for="(req, idx) in result.business_requirements" :key="idx" 
                     class="p-4 rounded-lg border border-zinc-100 bg-white hover:shadow-md transition-shadow group relative">
                    <p class="text-zinc-900 font-medium mb-2">{{ req.statement }}</p>
                    <div class="text-xs text-zinc-500 mb-2 space-y-1">
                        <p class="italic" v-if="req.rationale"><span class="font-semibold">Rationale:</span> {{ req.rationale }}</p>
                    </div>
                     <!-- Evidence & Confidence Footer -->
                    <div class="flex items-center justify-between mt-3 pt-3 border-t border-zinc-50">
                        <div class="flex items-center gap-1.5 text-xs text-zinc-400 max-w-[70%] truncate" title="Evidence from source">
                             <Quote class="w-3 h-3" />
                             <span>"{{ req.evidence }}"</span>
                        </div>
                        <span class="text-[10px] px-1.5 py-0.5 rounded-full border" :class="getConfidenceColor(req.confidence)">
                            {{ (req.confidence * 100).toFixed(0) }}%
                        </span>
                    </div>
                </div>
                <div v-if="result.business_requirements.length === 0" class="text-sm text-zinc-400 text-center py-10">
                    No L1 requirements found.
                </div>
            </div>
          </div>

          <!-- L2 Stakeholder -->
          <div class="flex flex-col bg-white rounded-xl shadow-sm border border-zinc-200 overflow-hidden h-full">
            <div class="px-4 py-3 bg-zinc-100 border-b border-zinc-200 flex items-center gap-2">
                <Users class="w-4 h-4 text-black" />
                <h3 class="font-semibold text-zinc-800">L2 Stakeholder</h3>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
                <div v-for="(req, idx) in result.stakeholder_requirements" :key="idx" 
                     class="p-4 rounded-lg border border-zinc-100 bg-white hover:shadow-md transition-shadow">
                    <p class="text-zinc-900 font-medium mb-2">{{ req.statement }}</p>
                     <div class="text-xs text-zinc-500 mb-2 space-y-1">
                        <p class="italic" v-if="req.rationale"><span class="font-semibold">Rationale:</span> {{ req.rationale }}</p>
                    </div>
                     <!-- Evidence & Confidence Footer -->
                    <div class="flex items-center justify-between mt-3 pt-3 border-t border-zinc-50">
                        <div class="flex items-center gap-1.5 text-xs text-zinc-400 max-w-[70%] truncate" title="Evidence from source">
                             <Quote class="w-3 h-3" />
                             <span>"{{ req.evidence }}"</span>
                        </div>
                         <span class="text-[10px] px-1.5 py-0.5 rounded-full border" :class="getConfidenceColor(req.confidence)">
                            {{ (req.confidence * 100).toFixed(0) }}%
                        </span>
                    </div>
                </div>
                 <div v-if="result.stakeholder_requirements.length === 0" class="text-sm text-zinc-400 text-center py-10">
                    No L2 requirements found.
                </div>
            </div>
          </div>

          <!-- L3 System -->
          <div class="flex flex-col bg-white rounded-xl shadow-sm border border-zinc-200 overflow-hidden h-full">
            <div class="px-4 py-3 bg-amber-50/50 border-b border-zinc-200 flex items-center gap-2">
                <Layout class="w-4 h-4 text-amber-600" />
                <h3 class="font-semibold text-zinc-800">L3 System</h3>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
                 <div v-for="(req, idx) in result.system_requirements" :key="idx" 
                     class="p-4 rounded-lg border border-zinc-100 bg-white hover:shadow-md transition-shadow">
                    <p class="text-zinc-900 font-medium mb-2">{{ req.statement }}</p>
                     <div class="text-xs text-zinc-500 mb-2 space-y-1">
                        <p class="italic" v-if="req.rationale"><span class="font-semibold">Rationale:</span> {{ req.rationale }}</p>
                    </div>
                     <!-- Evidence & Confidence Footer -->
                    <div class="flex items-center justify-between mt-3 pt-3 border-t border-zinc-50">
                        <div class="flex items-center gap-1.5 text-xs text-zinc-400 max-w-[70%] truncate" title="Evidence from source">
                             <Quote class="w-3 h-3" />
                             <span>"{{ req.evidence }}"</span>
                        </div>
                         <span class="text-[10px] px-1.5 py-0.5 rounded-full border" :class="getConfidenceColor(req.confidence)">
                            {{ (req.confidence * 100).toFixed(0) }}%
                        </span>
                    </div>
                </div>
                 <div v-if="result.system_requirements.length === 0" class="text-sm text-zinc-400 text-center py-10">
                    No L3 requirements found.
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
