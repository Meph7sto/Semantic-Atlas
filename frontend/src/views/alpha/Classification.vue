<script setup>
import { ref, computed, watch } from 'vue'
import { classifyTexts, classifyCsv } from '@/api/requirements'
import { UploadCloud, FileText, BarChart3, AlertCircle, CheckCircle2 } from 'lucide-vue-next'

const textInput = ref('')
const predictions = ref([])
const labelDistribution = ref({})
const textLoading = ref(false)

// 示例数据
const exampleRequirements = [
  '系统应在 1 秒内响应用户请求',
  '用户可以在系统中创建和管理项目',
  '系统支持批量导入需求数据',
  '系统应提供数据导出功能',
  '用户权限应由管理员统一管理',
  '系统应支持多级需求分类',
  '需求变更需要审批流程',
  '系统应记录所有操作日志',
  '支持实时需求追踪和状态查询'
]

const loadExample = () => {
  textInput.value = exampleRequirements.join('\n')
}

const selectedFile = ref(null)
const fileInputRef = ref(null)
const filePreview = ref('未选择文件')
const resultPreview = ref('还没有返回文件')
const groupedBlocks = ref([])
const downloadName = ref('predictions.csv')
const uploading = ref(false)
const hasHeader = ref(true)
const showN = ref(3)
const placeholderMax = ref(20)
const errorMsg = ref('')
const lastCsvText = ref('')

const totalPredictions = computed(() => predictions.value.length)

const distributionPairs = computed(() => {
  const entries = Object.entries(labelDistribution.value || {})
  return entries.sort((a, b) => b[1] - a[1])
})

const onClassifyTexts = async () => {
  errorMsg.value = ''
  predictions.value = []
  labelDistribution.value = {}
  const lines = textInput.value
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (!lines.length) {
    errorMsg.value = '请至少输入一条需求文本（每行一条）'
    return
  }
  textLoading.value = true
  try {
    const { data } = await classifyTexts({ requirements: lines })
    predictions.value = data.predictions || []
    labelDistribution.value = data.label_distribution || {}
  } catch (err) {
    errorMsg.value = parseError(err, '文本分类失败')
  } finally {
    textLoading.value = false
  }
}

const onFileChange = (event) => {
  errorMsg.value = ''
  resultPreview.value = '还没有返回文件'
  groupedBlocks.value = []
  const file = event.target.files?.[0]
  if (!file) {
    selectedFile.value = null
    filePreview.value = '未选择文件'
    return
  }
  if (!file.name.toLowerCase().endsWith('.csv')) {
    errorMsg.value = '请上传 .csv 文件'
    event.target.value = ''
    return
  }
  selectedFile.value = file
  const reader = new FileReader()
  reader.onload = () => {
    const text = reader.result || ''
    const lines = String(text).split(/\r?\n/).slice(0, 10)
    filePreview.value = lines.join('\n') || '文件为空'
  }
  reader.onerror = () => {
    filePreview.value = '无法读取文件'
  }
  reader.readAsText(file.slice(0, 100 * 1024))
}

const resetFile = () => {
  selectedFile.value = null
  filePreview.value = '未选择文件'
  resultPreview.value = '还没有返回文件'
  groupedBlocks.value = []
  downloadName.value = 'predictions.csv'
  errorMsg.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const onUploadCsv = async () => {
  errorMsg.value = ''
  if (!selectedFile.value) {
    errorMsg.value = '请先选择 CSV 文件'
    return
  }
  uploading.value = true
  try {
    const response = await classifyCsv(selectedFile.value)
    const disposition = response.headers?.['content-disposition'] || ''
    downloadName.value = parseFilename(disposition) || 'predictions.csv'

    const blob = response.data
    triggerDownload(blob, downloadName.value)
    await previewCsvResult(blob)
  } catch (err) {
    errorMsg.value = parseError(err, '上传分类失败')
  } finally {
    uploading.value = false
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

const previewCsvResult = async (blob) => {
  const text = await blob.text()
  lastCsvText.value = text
  const lines = text.split(/\r?\n/).slice(0, 10)
  resultPreview.value = lines.join('\n') || '返回文件为空'
  groupedBlocks.value = buildGroupsFromCsv(text, {
    hasHeader: hasHeader.value,
    showN: Number(showN.value) || 3,
    placeholderMax: Number(placeholderMax.value) || 20,
  })
}

watch([hasHeader, showN, placeholderMax], () => {
  if (!lastCsvText.value) return
  groupedBlocks.value = buildGroupsFromCsv(lastCsvText.value, {
    hasHeader: hasHeader.value,
    showN: Number(showN.value) || 3,
    placeholderMax: Number(placeholderMax.value) || 20,
  })
})

const parseFilename = (disposition) => {
  const m = disposition.match(/filename\*=UTF-8''([^;\n\r]+)/i)
  if (m?.[1]) return decodeURIComponent(m[1])
  const m2 = disposition.match(/filename="?([^";\n\r]+)"?/i)
  if (m2?.[1]) return m2[1]
  return null
}

const triggerDownload = (blob, filename) => {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

const parseError = (err, fallback) => {
  if (err?.response?.data?.detail) return String(err.response.data.detail)
  if (err?.message) return `${fallback}: ${err.message}`
  return fallback
}

const parseCSV = (text) => {
  const rows = []
  let cur = ''
  let row = []
  let inQuotes = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cur += '"'
          i += 1
        } else {
          inQuotes = false
        }
      } else {
        cur += ch
      }
    } else if (ch === '"') {
      inQuotes = true
    } else if (ch === ',') {
      row.push(cur)
      cur = ''
    } else if (ch === '\n') {
      row.push(cur)
      rows.push(row)
      row = []
      cur = ''
    } else if (ch === '\r') {
      // skip
    } else {
      cur += ch
    }
  }
  if (inQuotes) throw new Error('CSV 引号未闭合')
  if (cur !== '' || row.length > 0) {
    row.push(cur)
    rows.push(row)
  }
  return rows
}

const buildGroupsFromCsv = (text, opts) => {
  const rows = parseCSV(text).map((r) => r.map((c) => (c == null ? '' : String(c))))
  if (!rows.length) return []
  const header = opts.hasHeader ? rows[0] : null
  const dataRows = opts.hasHeader ? rows.slice(1) : rows
  const items = dataRows.map((r, idx) => ({
    rowIndex: opts.hasHeader ? idx + 2 : idx + 1,
    text: (r[0] || '').trim(),
    label: (r[1] || '').trim() || '(空类)',
  }))
  const groups = {}
  items.forEach((it) => {
    if (!groups[it.label]) groups[it.label] = []
    groups[it.label].push(it)
  })
  return Object.entries(groups)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, arr]) => {
      const first = arr.slice(0, opts.showN)
      const rest = arr.slice(opts.showN)
      return {
        label,
        total: arr.length,
        first,
        rest,
        restDisplayCount: Math.min(rest.length, opts.placeholderMax),
      }
    })
}
</script>

<template>
  <div class="flex-1 h-full overflow-y-auto bg-white">
    <div class="max-w-6xl mx-auto px-6 py-8">
      <header class="flex items-center justify-between mb-8">
        <div>
          <p class="text-xs uppercase tracking-[0.2em] text-zinc-400">Requirement Engineering</p>
          <h1 class="text-3xl font-semibold text-zinc-900 mt-2">Requirement Classification</h1>
          <p class="text-sm text-zinc-500 mt-1">支持文本列表与 CSV 文件的离线推理与结果分组展示。</p>
        </div>
        <div class="hidden md:flex items-center gap-2 text-zinc-400 text-xs">
          <FileText class="w-4 h-4" />
          <span>Model-backed inference</span>
        </div>
      </header>

      <div v-if="errorMsg" class="mb-4 flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-none px-3 py-2">
        <AlertCircle class="w-4 h-4" />
        <span>{{ errorMsg }}</span>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <section class="p-5 rounded-none border border-zinc-100 shadow-sm bg-white">
          <div class="flex items-center gap-2 mb-3">
            <BarChart3 class="w-5 h-5 text-black" />
            <h2 class="text-lg font-semibold text-zinc-900">文本批量分类</h2>
          </div>
          <p class="text-sm text-zinc-500 mb-4">每行一条需求，点击分类获取标签与分布。</p>
          <div class="mb-4">
            <button
              @click="loadExample"
              class="text-xs text-blue-600 hover:text-blue-700 underline"
            >
              加载示例数据（10 条）
            </button>
            <button
              @click="textInput = ''"
              class="text-xs text-zinc-500 hover:text-zinc-700 underline ml-4"
            >
              清空
            </button>
          </div>
          <textarea
            v-model="textInput"
            rows="10"
            class="w-full rounded-none border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-800 placeholder-zinc-300 focus:outline-none focus:ring-2 focus:ring-zinc-200 focus:border-zinc-300 transition"
            placeholder="例如：系统应在 1 秒内响应用户请求。"
          ></textarea>
          <div class="flex items-center justify-between mt-4">
            <button
              @click="onClassifyTexts"
              :disabled="textLoading"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-none text-sm font-medium text-white bg-zinc-900 hover:bg-zinc-800 transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <span v-if="textLoading" class="flex items-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                正在分类...
              </span>
              <span v-else class="flex items-center gap-2">
                <BarChart3 class="w-4 h-4" />
                开始分类
              </span>
            </button>
            <p class="text-xs text-zinc-400">分发至 /api/v2/classification/predict-texts</p>
          </div>

          <div v-if="predictions.length" class="mt-5 space-y-4">
            <div class="flex flex-wrap gap-2">
              <span class="inline-flex items-center gap-2 px-3 py-1 rounded-none text-xs font-medium bg-zinc-100 text-zinc-700 border border-zinc-200">
                <CheckCircle2 class="w-3 h-3" />
                {{ totalPredictions }} 条已分类
              </span>
              <span
                v-for="([label, count]) in distributionPairs"
                :key="label"
                class="inline-flex items-center gap-2 px-3 py-1 rounded-none text-xs font-medium bg-zinc-50 text-zinc-700 border border-zinc-200"
              >
                <span class="w-2 h-2 rounded-none bg-black"></span>
                {{ label || '(空类)' }} · {{ count }}
              </span>
            </div>
            <div class="border border-zinc-100 rounded-none divide-y divide-zinc-100">
              <div
                v-for="item in predictions"
                :key="item.index"
                class="flex items-start gap-3 px-4 py-3 hover:bg-zinc-50 transition"
              >
                <span class="text-xs text-zinc-400 mt-1">#{{ item.index + 1 }}</span>
                <div class="flex-1 space-y-1">
                  <p class="text-sm text-zinc-800 leading-relaxed">{{ item.requirement }}</p>
                  <span class="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-none text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    {{ item.predicted_label || 'N/A' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="p-5 rounded-none border border-zinc-100 shadow-sm bg-white">
          <div class="flex items-center gap-2 mb-3">
            <UploadCloud class="w-5 h-5 text-black" />
            <h2 class="text-lg font-semibold text-zinc-900">CSV 上传分类</h2>
          </div>
          <p class="text-sm text-zinc-500 mb-4">第一列为需求文本，返回的 CSV 第二列为预测标签。</p>

          <div class="space-y-3">
            <div>
              <label class="text-xs font-semibold text-zinc-500">选择 CSV</label>
              <input
                ref="fileInputRef"
                type="file"
                accept=".csv"
                class="mt-1 block w-full text-sm"
                @change="onFileChange"
              />
            </div>
            <div>
              <p class="text-xs text-zinc-400 mb-1">本地文件预览（前 10 行）</p>
              <pre class="bg-zinc-50 border border-zinc-100 rounded-none p-3 text-xs text-zinc-700 max-h-48 overflow-auto whitespace-pre-wrap">{{ filePreview }}</pre>
            </div>
          </div>

          <div class="flex flex-wrap gap-3 items-center mt-3">
            <div class="flex items-center gap-2 text-sm text-zinc-600">
              <input id="hasHeader" type="checkbox" class="rounded-none border-zinc-300" v-model="hasHeader" />
              <label for="hasHeader">结果含表头</label>
            </div>
            <div class="flex items-center gap-2 text-sm text-zinc-600">
              <span>每组显示</span>
              <input type="number" v-model.number="showN" min="1" class="w-16 px-2 py-1 border border-zinc-200 rounded-none" />
              <span>条</span>
            </div>
            <div class="flex items-center gap-2 text-sm text-zinc-600">
              <span>占位上限</span>
              <input type="number" v-model.number="placeholderMax" min="1" class="w-16 px-2 py-1 border border-zinc-200 rounded-none" />
            </div>
          </div>

          <div class="flex items-center gap-3 mt-4">
            <button
              @click="onUploadCsv"
              :disabled="uploading"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-none text-sm font-medium text-white bg-black hover:bg-zinc-800 transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <span v-if="uploading" class="flex items-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                正在上传...
              </span>
              <span v-else class="flex items-center gap-2">
                <UploadCloud class="w-4 h-4" />
                上传并分类
              </span>
            </button>
            <button
              @click="resetFile"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-none text-sm font-medium text-zinc-600 border border-zinc-200 hover:border-zinc-300"
            >
              重置
            </button>
            <p class="text-xs text-zinc-400">分发至 /api/v2/classification/predict-csv</p>
          </div>

          <div class="mt-4">
            <p class="text-xs text-zinc-400 mb-1">返回文件预览（前 10 行）</p>
            <pre class="bg-zinc-50 border border-zinc-100 rounded-none p-3 text-xs text-zinc-700 max-h-48 overflow-auto whitespace-pre-wrap">{{ resultPreview }}</pre>
          </div>

          <div class="mt-4">
            <div class="flex items-center gap-2 mb-2">
              <BarChart3 class="w-4 h-4 text-black" />
              <span class="text-sm text-zinc-700 font-semibold">按类别分组</span>
            </div>
            <div v-if="!groupedBlocks.length" class="text-xs text-zinc-400">还没有返回文件</div>
            <div v-else class="space-y-3">
              <div v-for="group in groupedBlocks" :key="group.label" class="border border-zinc-100 rounded-none p-3 bg-zinc-50">
                <div class="flex items-center justify-between mb-2">
                  <div class="text-sm font-semibold text-zinc-800">{{ group.label }}</div>
                  <div class="text-xs text-zinc-500">{{ group.total }} 条</div>
                </div>
                <div class="space-y-2">
                  <p
                    v-for="item in group.first"
                    :key="item.rowIndex"
                    class="text-xs text-zinc-700 bg-white border border-zinc-100 rounded-none px-2 py-1"
                  >
                    #{{ item.rowIndex }} — {{ item.text }}
                  </p>
                  <div v-if="group.rest.length" class="flex flex-wrap gap-1 items-center text-[11px] text-zinc-500">
                    <span
                      v-for="badge in group.rest.slice(0, group.restDisplayCount)"
                      :key="badge.rowIndex"
                      class="inline-flex items-center px-2 py-0.5 bg-white border border-zinc-200 rounded-none"
                      :title="badge.text"
                    >
                      #{{ badge.rowIndex }}
                    </span>
                    <span v-if="group.rest.length > group.restDisplayCount">
                      ... 还有 {{ group.rest.length - group.restDisplayCount }} 条
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

