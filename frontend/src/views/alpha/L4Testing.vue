<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { 
  Database, 
  Sparkles, 
  CheckCircle, 
  AlertTriangle, 
  Loader2, 
  Play, 
  RefreshCw, 
  Trash2, 
  ChevronRight,
  ChevronDown,
  Info,
  Check
} from 'lucide-vue-next'
import { requirementsL123Api, l4Api, l4RequirementsApi } from '@/utils/api'

// --- State ---
const sessionId = ref('')
const isLoadingReqs = ref(false)
const reqError = ref('')
const reqData = ref([])
const reqStats = ref(null)
const reqLevelFilter = ref('')
const selectedReqIds = ref(new Set())

const isGenerating = ref(false)
const generationError = ref('')
const generationResults = ref([])
const kbVersion = ref('')
const useReasoningModel = ref(false)

const config = ref({
  top_k_pattern: 5,
  top_k_spec: 3,
  top_k_nfr: 3,
  max_l4_per_top_req: 5,
  min_l4_per_top_req: 1,
  confidence_threshold: 0.6
})

// --- Computed ---
const modelId = computed(() => (useReasoningModel.value ? 'deepseek-reasoner' : 'deepseek-chat'))
const selectedReqsForApi = computed(() => {
  return reqData.value
    .filter(req => selectedReqIds.value.has(req.req_id))
    .map(req => ({
      id: req.req_id,
      text: req.text
    }))
})

const canGenerate = computed(() => {
  return selectedReqIds.value.size > 0 && !isGenerating.value
})

// --- Methods ---
async function refreshRequirements() {
  if (!sessionId.value.trim()) {
    reqData.value = []
    reqStats.value = null
    return
  }

  reqError.value = ''
  isLoadingReqs.value = true
  try {
    const data = await requirementsL123Api.listBySession(sessionId.value.trim(), {
      level: reqLevelFilter.value || null,
      page: 1,
      perPage: 1000 // Get many for testing
    })
    reqData.value = data.requirements || []
    reqStats.value = await requirementsL123Api.stats(sessionId.value.trim())
  } catch (err) {
    reqError.value = err?.message || '加载需求列表失败'
  } finally {
    isLoadingReqs.value = false
  }
}

function toggleSelectReq(reqId) {
  if (selectedReqIds.value.has(reqId)) {
    selectedReqIds.value.delete(reqId)
  } else {
    selectedReqIds.value.add(reqId)
  }
}

function selectAll() {
  reqData.value.forEach(req => selectedReqIds.value.add(req.req_id))
}

function clearSelection() {
  selectedReqIds.value.clear()
}

async function startGeneration() {
  if (!canGenerate.value) return
  if (!sessionId.value.trim()) {
    generationError.value = '请先填写 Session ID'
    return
  }

  generationError.value = ''
  isGenerating.value = true
  generationResults.value = []

  try {
    const resp = await l4RequirementsApi.generate(
      sessionId.value.trim(),
      selectedReqsForApi.value,
      {
        config: config.value,
        model: modelId.value,
      }
    )

    const requirements = resp.requirements || []
    const grouped = {}
    requirements.forEach((req) => {
      const topId = req.source_top_id || 'unknown'
      if (!grouped[topId]) {
        grouped[topId] = {
          source_top_id: topId,
          l4_requirements: [],
          open_questions: [],
        }
      }
      grouped[topId].l4_requirements.push({
        l4_id: req.req_id,
        source_top_id: req.source_top_id,
        source_top_text: req.source_top_text,
        component: req.component || 'TBD',
        shall_statement: req.text,
        acceptance_criteria: req.acceptance_criteria || [],
        test_method: req.test_method || 'TBD',
        interfaces: req.interfaces || [],
        data_contracts: req.data_contracts || [],
        error_handling: req.error_handling || [],
        nfr: req.nfr || [],
        open_questions: req.open_questions || [],
        evidence_ids: req.evidence_ids || [],
        confidence: req.confidence ?? 0.6,
        validator_status: { passed: false, issues: [] },
      })
    })

    generationResults.value = Object.values(grouped)
    kbVersion.value = resp.kb_version || kbVersion.value
  } catch (err) {
    generationError.value = err?.message || '生成失败'
  } finally {
    isGenerating.value = false
  }
}

async function getKbStatus() {
  try {
    const status = await l4Api.getKbStatus()
    if (status.is_loaded) {
      kbVersion.value = status.kb_version
    }
  } catch (err) {
    console.error('Fetch KB status failed', err)
  }
}

onMounted(() => {
  getKbStatus()
})

watch(reqLevelFilter, () => {
  refreshRequirements()
})
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50">
    <!-- Header -->
    <header class="bg-white border-b border-zinc-200 px-6 py-4 flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-zinc-900">Phase 4: 底层需求测试 (L4 Generation)</h2>
        <p class="text-sm text-zinc-500 mt-1">
          基于库中的高层需求 (L1-L3)，引用知识库 (KB) 证据，生成可实现、可测试的 L4 软件需求。
        </p>
      </div>
      <div v-if="kbVersion" class="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 rounded-full border border-zinc-200">
        <Database class="w-3.5 h-3.5 text-zinc-500" />
        <span class="text-xs font-medium text-zinc-600">KB Version: {{ kbVersion }}</span>
      </div>
    </header>

    <!-- Main Content Split Layout -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left: Requirement Selection -->
      <aside class="w-1/3 border-r border-zinc-200 bg-white flex flex-col overflow-hidden">
        <div class="p-4 border-b border-zinc-100 space-y-4">
          <div>
            <label class="block text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Session Selection</label>
            <div class="flex gap-2">
              <input
                v-model="sessionId"
                type="text"
                placeholder="Enter Session ID"
                class="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-black focus:ring-black"
                @keyup.enter="refreshRequirements"
              />
              <button
                @click="refreshRequirements"
                class="p-2 border border-zinc-300 rounded-lg hover:bg-zinc-50 transition-colors"
                title="Refresh"
              >
                <RefreshCw class="w-4 h-4 text-zinc-600" :class="{ 'animate-spin': isLoadingReqs }" />
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between">
            <div class="flex gap-2">
              <select
                v-model="reqLevelFilter"
                class="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-800"
              >
                <option value="">All Levels</option>
                <option value="L1">L1 Only</option>
                <option value="L2">L2 Only</option>
                <option value="L3">L3 Only</option>
              </select>
            </div>
            <div class="flex gap-2">
              <button @click="selectAll" class="text-[11px] text-zinc-500 hover:text-zinc-900 transition-colors">Select All</button>
              <span class="text-zinc-300 text-[11px]">|</span>
              <button @click="clearSelection" class="text-[11px] text-zinc-500 hover:text-zinc-900 transition-colors">Clear</button>
            </div>
          </div>
        </div>

        <!-- Requirement List -->
        <div class="flex-1 overflow-y-auto p-2 space-y-1">
          <div v-if="isLoadingReqs" class="flex flex-col items-center justify-center py-12 text-zinc-400">
            <Loader2 class="w-8 h-8 animate-spin mb-2" />
            <p class="text-sm">Loading Requirements...</p>
          </div>
          <div v-else-if="reqData.length === 0" class="flex flex-col items-center justify-center py-12 text-zinc-400">
            <Database class="w-8 h-8 mb-2 opacity-20" />
            <p class="text-sm">No requirements found.</p>
            <p class="text-xs mt-1">Check Session ID or filter.</p>
          </div>
          <div
            v-for="req in reqData"
            :key="req.req_id"
            @click="toggleSelectReq(req.req_id)"
            class="group p-3 rounded-lg border transition-all cursor-pointer relative"
            :class="selectedReqIds.has(req.req_id) 
              ? 'bg-zinc-900 border-zinc-900 text-white shadow-md' 
              : 'bg-white border-zinc-200 text-zinc-700 hover:border-zinc-400'"
          >
            <div class="flex items-start gap-3">
              <div 
                class="flex-shrink-0 w-4 h-4 mt-0.5 rounded border flex items-center justify-center transition-colors"
                :class="selectedReqIds.has(req.req_id) ? 'bg-white border-white' : 'border-zinc-300 group-hover:border-zinc-500'"
              >
                <Check v-if="selectedReqIds.has(req.req_id)" class="w-3 h-3 text-zinc-900" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <span 
                    class="text-[10px] font-bold px-1.5 py-0.5 rounded uppercase"
                    :class="selectedReqIds.has(req.req_id) ? 'bg-zinc-700 text-zinc-300' : 'bg-zinc-100 text-zinc-500'"
                  >
                    {{ req.level }}
                  </span>
                  <span class="text-[10px] opacity-60 truncate">ID: {{ req.req_id }}</span>
                </div>
                <p class="text-sm leading-relaxed break-words">{{ req.text }}</p>
              </div>
            </div>
          </div>
        </div>

        <div class="p-4 border-t border-zinc-100 bg-zinc-50/50 flex items-center justify-between">
          <span class="text-sm font-medium text-zinc-600">{{ selectedReqIds.size }} Selected</span>
          <button 
            @click="startGeneration"
            :disabled="!canGenerate"
            class="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white rounded-lg text-sm font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
          >
            <Loader2 v-if="isGenerating" class="w-4 h-4 animate-spin" />
            <Sparkles v-else class="w-4 h-4" />
            Generate L4
          </button>
        </div>
      </aside>

      <!-- Right: Settings & Results -->
      <main class="flex-1 flex flex-col bg-zinc-50 overflow-hidden">
        <!-- Config Section -->
        <div class="p-6 border-b border-zinc-200 bg-white shadow-sm shrink-0">
          <h3 class="text-sm font-semibold text-zinc-900 flex items-center gap-2 mb-4">
            <Info class="w-4 h-4 text-zinc-400" />
            Generation Parameters
          </h3>
          <div class="flex items-center gap-3 mb-4">
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="useReasoningModel" class="sr-only peer">
              <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
              <span class="ml-3 text-sm font-medium text-zinc-600">DeepSeek R1 (Reasoning Mode)</span>
            </label>
          </div>
          <div class="grid grid-cols-3 xl:grid-cols-6 gap-4">
            <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Top-k Pattern</label>
              <input v-model.number="config.top_k_pattern" type="number" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
            <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Top-k Spec</label>
              <input v-model.number="config.top_k_spec" type="number" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
            <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Top-k NFR</label>
              <input v-model.number="config.top_k_nfr" type="number" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
             <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Max L4 / Top</label>
              <input v-model.number="config.max_l4_per_top_req" type="number" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
            <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Min L4 / Top</label>
              <input v-model.number="config.min_l4_per_top_req" type="number" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
            <div>
              <label class="block text-[10px] font-semibold text-zinc-500 uppercase mb-1">Confidence</label>
              <input v-model.number="config.confidence_threshold" type="number" step="0.1" max="1" min="0" class="w-full text-sm bg-zinc-50 border border-zinc-200 rounded p-1.5 px-2 focus:ring-1 focus:ring-black outline-none" />
            </div>
          </div>
        </div>

        <!-- Results Area -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6">
          <div v-if="generationError" class="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
            <AlertTriangle class="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <p class="text-sm font-semibold text-red-900">Error during generation</p>
              <p class="text-xs text-red-700 mt-1">{{ generationError }}</p>
            </div>
          </div>

          <div v-if="isGenerating" class="flex flex-col items-center justify-center py-20 text-zinc-400">
            <Loader2 class="w-12 h-12 animate-spin mb-4" />
            <h4 class="text-lg font-medium text-zinc-900">Generating L4 Requirements...</h4>
            <p class="text-sm mt-2">Connecting to DeepSeek and LlamaIndex KB</p>
          </div>

          <div v-if="generationResults.length === 0 && !isGenerating && !generationError" class="flex flex-col items-center justify-center py-20 text-zinc-300">
            <Sparkles class="w-20 h-20 mb-4 opacity-10" />
            <p class="text-lg font-medium">Results will appear here</p>
            <p class="text-sm mt-1">Select high-level requirements on the left to begin.</p>
          </div>

          <!-- Result Cards -->
          <div v-for="result in generationResults" :key="result.source_top_id" class="space-y-4">
            <div class="flex items-center gap-3 px-2">
              <div class="h-px flex-1 bg-zinc-200"></div>
              <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Source: {{ result.source_top_id }}</span>
              <div class="h-px flex-1 bg-zinc-200"></div>
            </div>

            <!-- Top Req Summary -->
            <!-- <div class="bg-zinc-100/50 p-4 rounded-lg border border-zinc-200 mb-2">
               <p class="text-sm text-zinc-600 italic">"{{ getSourceText(result.source_top_id) }}"</p>
            </div> -->

            <div v-if="result.l4_requirements.length === 0 && result.open_questions.length > 0" class="bg-amber-50 border border-amber-200 rounded-xl p-5">
               <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-amber-600 mt-1 shrink-0" />
                  <div>
                    <h4 class="text-sm font-semibold text-amber-900">Coverage Failed (Open Questions)</h4>
                    <p class="text-xs text-amber-700 mt-1">The model could not generate valid L4 requirements without more information.</p>
                    <ul class="mt-3 space-y-2">
                      <li v-for="(q, idx) in result.open_questions" :key="idx" class="flex items-start gap-2 text-xs text-amber-800 bg-white/50 p-2 rounded-md border border-amber-100">
                        <span class="font-bold text-amber-600">?</span>
                        {{ q }}
                      </li>
                    </ul>
                  </div>
               </div>
            </div>

            <div v-else class="grid grid-cols-1 gap-4">
              <div v-for="l4 in result.l4_requirements" :key="l4.l4_id" class="bg-white border border-zinc-200 rounded-xl shadow-sm hover:shadow-md transition-shadow overflow-hidden">
                <div class="flex">
                   <!-- Status Bar -->
                    <div class="w-1.5 flex-shrink-0" :class="l4.validator_status.passed ? 'bg-emerald-500' : 'bg-rose-500'"></div>
                    
                    <div class="p-5 flex-1 space-y-4">
                       <!-- Header -->
                       <div class="flex items-start justify-between">
                          <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-zinc-900 bg-zinc-100 px-2 py-0.5 rounded border border-zinc-200">{{ l4.l4_id }}</span>
                            <span class="text-xs font-medium text-zinc-500 px-2 py-0.5 bg-zinc-50 rounded border border-zinc-100">{{ l4.component }}</span>
                          </div>
                          <div class="flex items-center gap-2">
                            <div class="flex items-center gap-1.5 px-2 py-1 rounded-full border" :class="l4.validator_status.passed ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : 'bg-rose-50 border-rose-100 text-rose-700'">
                              <CheckCircle v-if="l4.validator_status.passed" class="w-3.5 h-3.5" />
                              <AlertTriangle v-else class="w-3.5 h-3.5" />
                              <span class="text-[10px] font-bold uppercase tracking-tight">{{ l4.validator_status.passed ? 'Pass' : 'Rejected' }}</span>
                            </div>
                            <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-zinc-100 border border-zinc-200 text-zinc-600">
                               <span class="text-[10px] font-bold">Conf: {{ (l4.confidence * 100).toFixed(0) }}%</span>
                            </div>
                          </div>
                       </div>

                       <!-- Shall Statement -->
                       <div>
                          <p class="text-sm font-semibold text-zinc-900 leading-relaxed">{{ l4.shall_statement }}</p>
                       </div>

                       <!-- Elements Grid -->
                       <div class="grid grid-cols-2 gap-x-6 gap-y-4 pt-2">
                          <div>
                            <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-2">Acceptance Criteria</span>
                            <ul class="space-y-1.5">
                               <li v-for="(ac, idx) in l4.acceptance_criteria" :key="idx" class="flex items-start gap-2 text-xs text-zinc-600">
                                  <div class="w-1.5 h-1.5 bg-zinc-300 rounded-full mt-1 flex-shrink-0"></div>
                                  {{ ac }}
                               </li>
                            </ul>
                          </div>
                          <div class="space-y-4">
                            <div v-if="l4.interfaces?.length">
                              <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">Interfaces</span>
                              <div class="flex flex-wrap gap-1">
                                <span v-for="inf in l4.interfaces" :key="inf" class="text-[10px] bg-blue-50 text-blue-700 border border-blue-100 rounded px-1.5 py-0.5">{{ inf }}</span>
                              </div>
                            </div>
                            <div v-if="l4.data_contracts?.length">
                              <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">Data Contracts</span>
                              <div class="flex flex-wrap gap-1">
                                <span v-for="dt in l4.data_contracts" :key="dt" class="text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-100 rounded px-1.5 py-0.5">{{ dt }}</span>
                              </div>
                            </div>
                             <div v-if="l4.error_handling?.length">
                              <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">Error Handling</span>
                              <div class="flex flex-wrap gap-1">
                                <span v-for="eh in l4.error_handling" :key="eh" class="text-[10px] bg-orange-50 text-orange-700 border border-orange-100 rounded px-1.5 py-0.5">{{ eh }}</span>
                              </div>
                            </div>
                             <div v-if="l4.nfr?.length">
                              <span class="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">NFR</span>
                              <div class="flex flex-wrap gap-1">
                                <span v-for="n in l4.nfr" :key="n" class="text-[10px] bg-purple-50 text-purple-700 border border-purple-100 rounded px-1.5 py-0.5">{{ n }}</span>
                              </div>
                            </div>
                          </div>
                       </div>

                       <!-- Validation Issues -->
                       <div v-if="l4.validator_status.issues.length > 0" class="mt-4 p-3 bg-rose-50 border border-rose-100 rounded-lg">
                          <span class="text-[10px] font-bold text-rose-500 uppercase tracking-wider block mb-2">Validation Issues</span>
                          <ul class="space-y-1.5">
                            <li v-for="(issue, idx) in l4.validator_status.issues" :key="idx" class="flex items-start gap-2 text-[11px] text-rose-700 font-medium">
                               <AlertTriangle class="w-3.5 h-3.5 shrink-0" />
                               {{ issue.rule }}: {{ issue.message }}
                            </li>
                          </ul>
                       </div>

                       <!-- Evidence -->
                       <div class="flex items-center gap-2 pt-2 border-t border-zinc-100">
                          <Database class="w-3 h-3 text-zinc-400" />
                          <span class="text-[10px] font-bold text-zinc-400 uppercase">Evidence:</span>
                          <div class="flex flex-wrap gap-1">
                              <span v-for="eid in l4.evidence_ids" :key="eid" class="text-[10px] text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">{{ eid }}</span>
                          </div>
                       </div>
                    </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* Scrollbar styling */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #e4e4e7;
  border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
  background: #d4d4d8;
}
</style>
