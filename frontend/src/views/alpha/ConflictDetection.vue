<script setup>
import { ref } from 'vue'
import { conflictApi } from '@/api/requirements'
import { Play, CheckCircle2, AlertCircle, Sparkles } from 'lucide-vue-next'

const reqA = ref('')
const reqB = ref('')
const selectedModel = ref('deepseek-v4-pro')
const useThinking = ref(true)
const isLoading = ref(false)
const result = ref(null) 

const detectConflict = async () => {
  if (!reqA.value || !reqB.value) return
  isLoading.value = true
  // 初始化结果对象，这时 is_conflict 为 null，表示正在分析中
  result.value = { raw_response: '', thinking_content: '', is_conflict: null }
  
  try {
    const stream = await conflictApi.streamCheck(
      reqA.value,
      reqB.value,
      selectedModel.value,
      useThinking.value
    )
    
    // 建立流读取器
    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk
      
      // 按行分割并解析 JSON
      const lines = buffer.split('\n')
      // 最后一个可能不完整，保留在 buffer 中
      buffer = lines.pop()
      
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const msg = JSON.parse(line)
          
          if (msg.type === 'token') {
             // 实时追加 token
             result.value.raw_response += msg.content
          } else if (msg.type === 'thinking') {
             // 实时追加思维链
             result.value.thinking_content = (result.value.thinking_content || '') + msg.content
          } else if (msg.type === 'result') {
             // 收到最终判定结果
             result.value.is_conflict = msg.data.is_conflict
             // 可选：覆盖一次完整文本以确保一致性
             // result.value.raw_response = msg.data.raw_response 
          }
        } catch (err) {
          console.error('JSON parse error', err)
        }
      }
    }
  } catch (e) {
    console.error(e)
    let errorMsg = 'Failed to check conflict.'
    // ... 简化的错误处理 ...
    if (e.message) {
        errorMsg += ` Error: ${e.message}`
    }
    alert(errorMsg)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="h-full w-full overflow-y-auto">
    <div class="flex flex-col min-h-full max-w-5xl mx-auto px-6 py-8">
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
            class="w-full h-40 p-4 rounded-none bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-300 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100 focus:border-zinc-300 transition-all shadow-sm group-hover:shadow-md"
          ></textarea>
        </div>

        <!-- Requirement B -->
        <div class="group relative">
          <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider ml-1">Requirement B</label>
          <textarea 
            v-model="reqB"
            placeholder="e.g. The system response time should be at least 2 seconds."
            class="w-full h-40 p-4 rounded-none bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-300 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100 focus:border-zinc-300 transition-all shadow-sm group-hover:shadow-md"
          ></textarea>
        </div>
      </div>

      <!-- Action Button & Toggle -->
      <div class="flex flex-col items-center gap-4 justify-center mb-12">
        
        <div class="flex items-center gap-3">
          <select
            v-model="selectedModel"
            class="h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-700 focus:border-zinc-500 focus:outline-none"
          >
            <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
            <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
          </select>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="useThinking" class="sr-only peer">
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
            <span class="ml-3 text-sm font-medium text-zinc-600">思考模式</span>
          </label>
        </div>

        <button 
          @click="detectConflict"
          :disabled="isLoading || !reqA || !reqB"
          class="flex items-center gap-2 bg-zinc-900 text-white px-8 py-3 rounded-none font-medium hover:bg-zinc-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-105 active:scale-95 shadow-lg shadow-zinc-200"
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
      <div v-if="result" class="max-w-3xl mx-auto w-full pb-20">
        
        <!-- Result Card -->
        <div class="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div class="flex items-start gap-4">
            <!-- Icon Status -->
            <div :class="`mt-1 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${result.is_conflict === null ? 'bg-zinc-100 text-zinc-500' : result.is_conflict ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`">
              <svg v-if="result.is_conflict === null" class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <Sparkles v-else class="w-5 h-5" />
            </div>
            
            <div class="flex-1 space-y-3">
              <div class="flex items-center gap-3">
                <span class="font-semibold text-zinc-900">Analysis Result</span>
                
                <!-- Analyzing Badge -->
                <span 
                  v-if="result.is_conflict === null" 
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-100 text-zinc-600 border border-zinc-200"
                >
                  Analyzing...
                </span>

                <!-- Result Badges -->
                <span 
                  v-else-if="result.is_conflict" 
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
              
              <!-- Thinking Process Area -->
              <div v-if="result.thinking_content" class="mb-4">
                <div class="text-xs font-semibold text-zinc-400 mb-1 uppercase tracking-wider">Reasoning Process</div>
                <div class="p-4 bg-zinc-100/50 rounded-xl border border-zinc-100 text-zinc-600 text-sm leading-relaxed whitespace-pre-wrap font-mono">
                  {{ result.thinking_content }}
                </div>
              </div>

              <!-- Streaming Text Area -->
              <div class="p-6 bg-zinc-50 rounded-2xl border border-zinc-100 text-zinc-700 leading-relaxed shadow-sm min-h-[100px]">
                {{ result.raw_response }}
                <span v-if="isLoading" class="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-1 align-middle"></span>
              </div>
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
