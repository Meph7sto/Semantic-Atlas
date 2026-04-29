<script setup>
import { ref } from 'vue'
import { chatApi } from '@/api/chat'
import { MessageSquare, Send, Sparkles } from 'lucide-vue-next'

const question = ref('')
const selectedModel = ref('deepseek-v4-pro')
const useThinking = ref(true)
const useAsyncClient = ref(false)
const isLoading = ref(false)
const result = ref(null)
const error = ref(null)

const askQuestion = async () => {
  if (!question.value.trim()) return
  isLoading.value = true
  error.value = null
  result.value = { raw_response: '', thinking_content: '' }

  try {
    const stream = await chatApi.streamAsk(
      question.value.trim(),
      selectedModel.value,
      useThinking.value,
      useAsyncClient.value
    )
    if (!stream) {
      throw new Error('Empty response body')
    }

    const reader = stream.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const msg = JSON.parse(line)
          if (msg.type === 'token') {
            result.value.raw_response += msg.content
          } else if (msg.type === 'thinking') {
             result.value.thinking_content = (result.value.thinking_content || '') + msg.content
          } else if (msg.type === 'result') {
            result.value.raw_response = msg.data?.answer || result.value.raw_response
          }
        } catch (err) {
          console.error('JSON parse error', err)
        }
      }
    }
  } catch (err) {
    console.error(err)
    error.value = err.message || 'Failed to get response.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="flex flex-col h-full w-full max-w-5xl mx-auto px-6 py-8">
    <div class="text-center mb-10">
      <h2 class="text-3xl font-semibold text-zinc-800 tracking-tight flex items-center justify-center gap-2">
        <MessageSquare class="w-6 h-6" />
        General Q&amp;A
      </h2>
      <p class="text-zinc-500 mt-2 text-sm">Ask anything and get a streaming response.</p>
    </div>

    <div class="space-y-6">
      <div class="group relative">
        <label class="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider ml-1">Your Question</label>
        <textarea
          v-model="question"
          placeholder="Type your question here..."
          class="w-full h-40 p-4 rounded-none bg-white border border-zinc-200 text-zinc-800 placeholder-zinc-300 resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100 focus:border-zinc-300 transition-all shadow-sm group-hover:shadow-md"
        ></textarea>
      </div>

      <div class="flex flex-col items-center gap-4 justify-center">
        
        <div class="flex flex-col items-center gap-3">
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
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" v-model="useAsyncClient" class="sr-only peer">
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-zinc-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-zinc-900"></div>
            <span class="ml-3 text-sm font-medium text-zinc-600">DeepSeek Async (aiohttp)</span>
          </label>
        </div>

        <button
          @click="askQuestion"
          :disabled="isLoading || !question"
          class="flex items-center gap-2 bg-zinc-900 text-white px-8 py-3 rounded-none font-medium hover:bg-zinc-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:scale-105 active:scale-95 shadow-lg shadow-zinc-200"
        >
          <span v-if="isLoading" class="flex items-center gap-2">
            <svg class="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Thinking...
          </span>
          <span v-else class="flex items-center gap-2">
            <Send class="w-4 h-4" />
            Ask
          </span>
        </button>
      </div>

      <div v-if="error" class="p-4 bg-red-50 border border-red-200 text-red-600 rounded-none text-sm">
        Error: {{ error }}
      </div>

      <div v-if="result" class="max-w-3xl mx-auto w-full">
        <div class="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div class="flex items-start gap-4">
            <div class="mt-1 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-zinc-100 text-zinc-500">
              <Sparkles class="w-5 h-5" />
            </div>
            <div class="flex-1 space-y-3">
              <div class="flex items-center gap-3">
                <span class="font-semibold text-zinc-900">Answer</span>
                <span
                  v-if="isLoading"
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-100 text-zinc-600 border border-zinc-200"
                >
                  Streaming...
                </span>
              </div>
              <div class="p-6 bg-zinc-50 rounded-2xl border border-zinc-100 text-zinc-700 leading-relaxed shadow-sm min-h-[120px]">
                
                 <!-- Thinking Process Area -->
                <div v-if="result.thinking_content" class="mb-6">
                  <div class="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider flex items-center gap-2">
                    <Sparkles class="w-3 h-3" />
                    DeepSeek Thought Process
                  </div>
                  <div class="p-4 bg-zinc-100/50 rounded-xl border border-zinc-200/50 text-zinc-600 text-sm leading-relaxed whitespace-pre-wrap font-mono relative">
                    {{ result.thinking_content }}
                    <div v-if="isLoading && !result.raw_response" class="inline-block w-1.5 h-3 bg-zinc-400 animate-pulse ml-1 align-middle"></div>
                  </div>
                </div>

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
