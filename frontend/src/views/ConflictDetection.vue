<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { Play, CheckCircle2, AlertCircle, Sparkles } from 'lucide-vue-next'

const reqA = ref('')
const reqB = ref('')
const isLoading = ref(false)
const result = ref(null) 

const detectConflict = async () => {
  if (!reqA.value || !reqB.value) return
  isLoading.value = true
  result.value = null
  
  try {
    const response = await axios.post('/api/conflict/check', {
      requirement_a: reqA.value,
      requirement_b: reqB.value
    })
    result.value = response.data
  } catch (e) {
    console.error(e)
    let errorMsg = 'Failed to check conflict.'
    
    if (e.response && e.response.data) {
        // Backend provided detailed error
        errorMsg += ` Server says: ${e.response.data.detail || JSON.stringify(e.response.data)}`
    } else if (e.message) {
        // Network or other generic error
        errorMsg += ` Error: ${e.message}`
    }
    
    alert(errorMsg)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col h-full w-full max-w-5xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="text-center mb-10">
      <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight flex items-center justify-center gap-2">
        Conflict Detection
      </h2>
      <p class="text-zinc-500 mt-2 text-sm">Compare two requirements for logical inconsistencies using AI.</p>
    </div>

    <!-- Input Area -->
    <div class="grid grid-cols-2 gap-6 mb-8">
      <!-- Requirement A -->
      <div class="group relative">
        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider ml-1">Requirement A</label>
        <textarea 
          v-model="reqA"
          placeholder="e.g. The system must respond within 1 second."
          class="w-full h-40 p-4 rounded-xl bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-300 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100 focus:border-zinc-300 transition-all shadow-sm group-hover:shadow-md"
        ></textarea>
      </div>

      <!-- Requirement B -->
      <div class="group relative">
        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider ml-1">Requirement B</label>
        <textarea 
          v-model="reqB"
          placeholder="e.g. The system response time should be at least 2 seconds."
          class="w-full h-40 p-4 rounded-xl bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-300 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100 focus:border-zinc-300 transition-all shadow-sm group-hover:shadow-md"
        ></textarea>
      </div>
    </div>

    <!-- Action Button -->
    <div class="flex justify-center mb-12">
      <button 
        @click="detectConflict"
        :disabled="isLoading || !reqA || !reqB"
        class="flex items-center gap-2 bg-zinc-900 text-white px-8 py-3 rounded-full font-medium hover:bg-zinc-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-105 active:scale-95 shadow-lg shadow-zinc-200"
      >
        <span v-if="isLoading" class="flex items-center gap-2">
           <svg class="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
             <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
             <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
           </svg>
           Analyzing...
        </span>
        <span v-else class="flex items-center gap-2">
          <Play class="w-4 h-4 fill-white" />
          Start Detection
        </span>
      </button>
    </div>

    <!-- Results Area -->
    <div v-if="isLoading || result" class="max-w-3xl mx-auto w-full">
      
      <!-- Loading State (Breathing dots) -->
      <div v-if="isLoading" class="flex justify-center py-10">
        <div class="flex items-center gap-1">
          <div class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
          <div class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
          <div class="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
        </div>
      </div>

      <!-- Result Card -->
      <div v-else-if="result" class="animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div class="flex items-start gap-4">
          <div :class="`mt-1 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${result.is_conflict ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`">
            <Sparkles class="w-5 h-5" />
          </div>
          
          <div class="flex-1 space-y-3">
            <div class="flex items-center gap-3">
              <span class="font-semibold text-zinc-900">Analysis Result</span>
              <span 
                v-if="result.is_conflict" 
                class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 border border-red-200"
              >
                <AlertCircle class="w-3 h-3" />
                Conflict Detected
              </span>
              <span 
                v-else 
                class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 border border-emerald-200"
              >
                <CheckCircle2 class="w-3 h-3" />
                Compatible
              </span>
            </div>
            
            <div class="p-6 bg-zinc-50 rounded-2xl border border-zinc-100 text-zinc-700 leading-relaxed shadow-sm">
              {{ result.raw_response }}
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* Scoped styles overrides if needed, but Tailwind handles most */
</style>
