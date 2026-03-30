<script setup>
import { ref } from 'vue'
import { visionApi } from '@/api'
import { CheckCircle2, Database, ImageIcon, UploadCloud } from 'lucide-vue-next'

const prompt = ref('请详细描述图片内容，并总结关键信息。')
const speaker = ref('vision_agent')
const maxNewTokens = ref(256)
const sessionId = ref('')
const defaultSpanMs = ref(8000)
const maxSpansReturned = ref(200)
const estimateTimestamps = ref(true)

const selectedFile = ref(null)
const selectedFileName = ref('')
const isGenerating = ref(false)
const isConfirming = ref(false)
const error = ref('')
const generated = ref(null)
const confirmResult = ref(null)

function normalizeError(err, fallback = '请求失败') {
    if (!err) return fallback
    if (typeof err === 'string') return err
    return err.response?.data?.detail || err.message || fallback
}

function onFileChange(event) {
    const file = event?.target?.files?.[0] || null
    selectedFile.value = file
    selectedFileName.value = file?.name || ''
}

async function generateCaption() {
    if (!selectedFile.value) {
        error.value = '请先选择图片'
        return
    }

    isGenerating.value = true
    error.value = ''
    confirmResult.value = null
    try {
        const data = await visionApi.captionImage(selectedFile.value, {
            prompt: prompt.value,
            speaker: speaker.value,
            maxNewTokens: maxNewTokens.value,
        })
        generated.value = data
    } catch (err) {
        error.value = normalizeError(err, '图生文生成失败')
    } finally {
        isGenerating.value = false
    }
}

async function confirmIngest() {
    const previewId = generated.value?.preview?.preview_id
    if (!previewId) {
        error.value = '请先生成图生文结果'
        return
    }
    isConfirming.value = true
    error.value = ''
    confirmResult.value = null
    try {
        const data = await visionApi.confirmPreview(previewId, {
            sessionId: sessionId.value,
            estimateTimestampsIfMissing: estimateTimestamps.value,
            defaultSpanMs: defaultSpanMs.value,
            maxSpansReturned: maxSpansReturned.value,
        })
        confirmResult.value = data
    } catch (err) {
        error.value = normalizeError(err, '确认入库失败')
    } finally {
        isConfirming.value = false
    }
}
</script>

<template>
    <div class="h-full w-full overflow-y-auto bg-zinc-50">
        <div class="max-w-6xl mx-auto px-6 py-8 space-y-6">
            <header>
                <h2 class="flex items-center gap-2 text-2xl font-semibold text-zinc-900">
                    <ImageIcon class="h-6 w-6" />
                    Alpha 图生文上传与确认入库
                </h2>
                <p class="mt-1 text-sm text-zinc-500">
                    本页面会调用后端已配置的AutoDL图生文服务，先生成文字预览，再由你手动确认写入spans。
                </p>
            </header>

            <section class="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                <h3 class="text-sm font-semibold text-zinc-700">步骤 1：上传图片并生成图生文</h3>

                <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <label class="text-sm">
                        <span class="mb-1 block text-zinc-600">图片文件</span>
                        <input
                            type="file"
                            accept="image/*"
                            class="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm"
                            @change="onFileChange"
                        />
                        <span v-if="selectedFileName" class="mt-1 block text-xs text-zinc-500">已选择：{{ selectedFileName }}</span>
                    </label>
                    <label class="text-sm">
                        <span class="mb-1 block text-zinc-600">speaker</span>
                        <input v-model="speaker" type="text" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
                    </label>
                </div>

                <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <label class="text-sm">
                        <span class="mb-1 block text-zinc-600">prompt</span>
                        <textarea v-model="prompt" rows="4" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
                    </label>
                    <label class="text-sm">
                        <span class="mb-1 block text-zinc-600">max_new_tokens</span>
                        <input v-model.number="maxNewTokens" type="number" min="1" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
                        <span class="mt-1 block text-xs text-zinc-500">若AutoDL服务未预热，首次生成可能耗时较长。</span>
                    </label>
                </div>

                <button
                    :disabled="isGenerating"
                    class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-800 disabled:opacity-50"
                    @click="generateCaption"
                >
                    <UploadCloud class="h-4 w-4" />
                    {{ isGenerating ? '图生文生成中...' : '调用 AutoDL 并生成图生文' }}
                </button>
            </section>

            <section v-if="generated" class="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                <h3 class="text-sm font-semibold text-zinc-700">步骤 2：确认入库 spans</h3>

                <div class="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                    <div class="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                        <div class="text-xs text-zinc-500">preview_id</div>
                        <div class="mt-1 break-all font-mono text-zinc-700">{{ generated.preview?.preview_id }}</div>
                    </div>
                    <div class="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                        <div class="text-xs text-zinc-500">filename</div>
                        <div class="mt-1 text-zinc-700">{{ generated.result?.filename }}</div>
                    </div>
                </div>

                <div>
                    <h4 class="mb-2 text-sm font-semibold text-zinc-700">caption</h4>
                    <div class="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-700">
                        {{ generated.result?.caption }}
                    </div>
                </div>

                <div>
                    <h4 class="mb-2 text-sm font-semibold text-zinc-700">transcript_text（将用于入库）</h4>
                    <div class="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-sm text-zinc-700">
                        {{ generated.result?.transcript_text }}
                    </div>
                </div>

                <div class="space-y-3 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                    <h4 class="flex items-center gap-2 text-sm font-semibold text-zinc-700">
                        <Database class="h-4 w-4" />
                        入库参数
                    </h4>

                    <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
                        <label class="text-sm">
                            <span class="mb-1 block text-zinc-600">session_id（可空）</span>
                            <input
                                v-model="sessionId"
                                type="text"
                                class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                                placeholder="留空则自动生成"
                            />
                        </label>
                        <label class="text-sm">
                            <span class="mb-1 block text-zinc-600">default_span_ms</span>
                            <input v-model.number="defaultSpanMs" type="number" min="1" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
                        </label>
                        <label class="text-sm">
                            <span class="mb-1 block text-zinc-600">max_spans_returned</span>
                            <input v-model.number="maxSpansReturned" type="number" min="1" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" />
                        </label>
                    </div>

                    <label class="inline-flex items-center gap-2 text-sm text-zinc-700">
                        <input v-model="estimateTimestamps" type="checkbox" />
                        estimate_timestamps_if_missing
                    </label>

                    <button
                        :disabled="isConfirming"
                        class="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-800 disabled:opacity-50"
                        @click="confirmIngest"
                    >
                        <CheckCircle2 class="h-4 w-4" />
                        {{ isConfirming ? '确认中...' : '确认并写入 spans' }}
                    </button>
                </div>
            </section>

            <div v-if="confirmResult" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                入库成功：session_id={{ confirmResult.session_id }}，span_total={{ confirmResult.span_total }}
            </div>

            <div v-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                {{ error }}
            </div>
        </div>
    </div>
</template>
