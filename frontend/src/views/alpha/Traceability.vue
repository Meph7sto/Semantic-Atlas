<script setup>
  import { ref, computed } from 'vue'
  import { traceabilityApi } from '@/api/requirements'
  import TraceNetworkChart from '../../components/charts/TraceNetworkChart.vue'
  import { FileSearch, Plus, Trash2, Sparkles } from 'lucide-vue-next'
  
  const analysisMode = ref('relation') // 'relation' 或 'batch'
  const highLevelRequirements = ref(['', ''])
  const lowLevelRequirements = ref(['', ''])
  const batchHighLevelRequirements = ref('')
  const batchLowLevelRequirements = ref('')
  const loading = ref(false)
  const analysisResult = ref(null)
  const batchResult = ref(null)
  
  const hasValidRequirements = computed(() => {
    if (analysisMode.value === 'relation') {
      const hasHigh = highLevelRequirements.value.some(r => r.trim())
      const hasLow = lowLevelRequirements.value.some(r => r.trim())
      return hasHigh && hasLow
    } else {
      return batchHighLevelRequirements.value.trim() && batchLowLevelRequirements.value.trim()
    }
  })
  
  const addHighLevelRequirement = () => {
    highLevelRequirements.value.push('')
  }
  
  const removeHighLevelRequirement = (index) => {
    if (highLevelRequirements.value.length > 1) {
      highLevelRequirements.value.splice(index, 1)
    }
  }
  
  const addLowLevelRequirement = () => {
    lowLevelRequirements.value.push('')
  }
  
  const removeLowLevelRequirement = (index) => {
    if (lowLevelRequirements.value.length > 1) {
      lowLevelRequirements.value.splice(index, 1)
    }
  }
  
  const analyzeRelation = async () => {
    if (!hasValidRequirements.value) return
  
    const validHigh = highLevelRequirements.value.filter(r => r.trim())
    const validLow = lowLevelRequirements.value.filter(r => r.trim())
  
    if (validHigh.length === 0 || validLow.length === 0) return
  
    loading.value = true
    analysisResult.value = null
    batchResult.value = null
  
    try {
      if (validHigh.length === 1 && validLow.length === 1) {
        // 单对分析
        const result = await traceabilityApi.analyzeRelation(validHigh[0].trim(), validLow[0].trim())
        analysisResult.value = result
      } else {
        // 多对自动转批量
        const result = await traceabilityApi.batchAnalyzeRelation(
          validHigh.map(r => r.trim()),
          validLow.map(r => r.trim())
        )
        console.log('关系追溯模式批量分析结果:', result)
        // 确保结果包含必要字段
        if (!result || typeof result !== 'object') {
          throw new Error('批量分析返回数据格式错误')
        }
        batchResult.value = result
      }
    } catch (e) {
      console.error('分析错误:', e)
      const errorMsg = e?.response?.data?.error || e?.response?.data?.detail || e?.message || '分析失败'
      alert(`分析失败: ${errorMsg}`)
    } finally {
      loading.value = false
    }
  }
  
  const analyzeBatch = async () => {
    if (!hasValidRequirements.value) return
  
    const highReqs = batchHighLevelRequirements.value.trim().split('\n').filter(r => r.trim())
    const lowReqs = batchLowLevelRequirements.value.trim().split('\n').filter(r => r.trim())
  
    if (highReqs.length === 0 || lowReqs.length === 0) {
      alert('请确保每行输入一个需求')
      return
    }
  
    if (highReqs.length * lowReqs.length > 50) {
      alert('批量分析组合数量过多，建议不超过50个组合')
      return
    }
  
    loading.value = true
    batchResult.value = null
    analysisResult.value = null
  
    try {
      const result = await traceabilityApi.batchAnalyzeRelation(highReqs, lowReqs)
      console.log('批量分析结果:', result)
      // 确保结果包含必要字段
      if (!result || typeof result !== 'object') {
        throw new Error('批量分析返回数据格式错误')
      }
      batchResult.value = result
    } catch (e) {
      console.error('批量分析错误:', e)
      const errorMsg = e?.response?.data?.error || e?.response?.data?.detail || e?.message || '批量分析失败'
      alert(`批量分析失败: ${errorMsg}`)
    } finally {
      loading.value = false
    }
  }
  
  const getRelationTypeLabel = (type) => {
    const labels = {
      'implementation': '实现关系',
      'support': '支持关系',
      'dependency': '依赖关系',
      'decomposition': '分解关系',
      'general': '追溯关系',
      'unknown': '未知关系'
    }
    return labels[type] || '追溯关系'
  }
  
  const getRelationTypeColor = (type) => {
    const colors = {
      'implementation': 'bg-green-100 text-green-700 border-green-200',
      'support': 'bg-blue-100 text-blue-700 border-blue-200',
      'dependency': 'bg-red-100 text-red-700 border-red-200',
      'decomposition': 'bg-yellow-100 text-yellow-700 border-yellow-200',
      'general': 'bg-gray-100 text-gray-700 border-gray-200'
    }
    return colors[type] || 'bg-gray-100 text-gray-700 border-gray-200'
  }
  
  const getConfidenceColor = (conf) => {
    if (conf >= 0.8) return 'bg-green-500'
    if (conf >= 0.6) return 'bg-yellow-500'
    if (conf >= 0.4) return 'bg-orange-500'
    return 'bg-red-500'
  }
  
  const selectExample = (example) => {
    if (analysisMode.value === 'relation') {
      highLevelRequirements.value = [example.highLevel]
      lowLevelRequirements.value = [example.lowLevel]
    } else {
      batchHighLevelRequirements.value = example.highLevel
      batchLowLevelRequirements.value = example.lowLevel
    }
  }
  
  const relationExamples = [
    {
      title: '登录与校验',
      highLevel: '系统应提供用户登录功能。',
      lowLevel: '实现用户名密码校验与会话管理。'
    },
    {
      title: '权限与角色',
      highLevel: '系统应支持用户权限管理。',
      lowLevel: '实现角色权限分配功能。'
    }
  ]
  
  const batchExamples = [
    {
      title: '用户系统批量分析',
      highLevel: '系统应提供用户登录功能\n系统应支持用户权限管理',
      lowLevel: '实现用户名密码验证机制\n实现角色权限分配功能'
    }
  ]
  </script>
  
  <template>
  <div class="flex flex-col h-full w-full max-w-7xl mx-auto px-6 py-8 overflow-y-auto">
      <div class="mb-8">
        <div class="text-3xl font-semibold text-zinc-900 flex items-center gap-2">
          <FileSearch class="w-8 h-8" />
          需求追溯
        </div>
        <div class="text-sm text-zinc-500 mt-2">分析高层需求与底层需求之间的追溯关系</div>
      </div>
  
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- 左侧：输入区域 -->
        <div class="lg:col-span-1">
          <div class="bg-white rounded-none border border-zinc-200 p-6 shadow-sm">
            <div class="mb-4">
              <div class="flex gap-2 border-b border-zinc-200 pb-2">
                <button
                  @click="analysisMode = 'relation'"
                  :class="analysisMode === 'relation' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700'"
                  class="flex-1 px-4 py-2 rounded-none text-sm font-medium transition-colors"
                >
                  关系追溯
                </button>
                <button
                  @click="analysisMode = 'batch'"
                  :class="analysisMode === 'batch' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700'"
                  class="flex-1 px-4 py-2 rounded-none text-sm font-medium transition-colors"
                >
                  批量分析
                </button>
              </div>
            </div>
  
            <!-- 关系追溯模式 -->
            <div v-if="analysisMode === 'relation'">
              <div class="mb-4">
                <div class="text-xs font-semibold text-zinc-500 mb-2 uppercase">顶层需求</div>
                <div class="space-y-2">
                  <div v-for="(req, idx) in highLevelRequirements" :key="`high-${idx}`" class="flex gap-2">
                    <textarea
                      v-model="highLevelRequirements[idx]"
                      :placeholder="`顶层需求 ${idx + 1}`"
                      class="flex-1 p-3 rounded-none border border-zinc-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100"
                      rows="2"
                      maxlength="1500"
                    />
                    <button
                      @click="removeHighLevelRequirement(idx)"
                      :disabled="highLevelRequirements.length <= 1"
                      class="p-2 text-red-500 hover:bg-red-50 rounded-none disabled:opacity-50"
                    >
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                  <button
                    @click="addHighLevelRequirement"
                    class="w-full px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-none border border-blue-200 flex items-center justify-center gap-2"
                  >
                    <Plus class="w-4 h-4" />
                    添加顶层需求
                  </button>
                </div>
              </div>
  
              <div class="mb-4">
                <div class="text-xs font-semibold text-zinc-500 mb-2 uppercase">底层需求</div>
                <div class="space-y-2">
                  <div v-for="(req, idx) in lowLevelRequirements" :key="`low-${idx}`" class="flex gap-2">
                    <textarea
                      v-model="lowLevelRequirements[idx]"
                      :placeholder="`底层需求 ${idx + 1}`"
                      class="flex-1 p-3 rounded-none border border-zinc-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100"
                      rows="2"
                      maxlength="1500"
                    />
                    <button
                      @click="removeLowLevelRequirement(idx)"
                      :disabled="lowLevelRequirements.length <= 1"
                      class="p-2 text-red-500 hover:bg-red-50 rounded-none disabled:opacity-50"
                    >
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                  <button
                    @click="addLowLevelRequirement"
                    class="w-full px-3 py-2 text-sm text-green-600 hover:bg-green-50 rounded-none border border-green-200 flex items-center justify-center gap-2"
                  >
                    <Plus class="w-4 h-4" />
                    添加底层需求
                  </button>
                </div>
              </div>
            </div>
  
            <!-- 批量分析模式 -->
            <div v-else>
              <div class="mb-4">
                <div class="text-xs font-semibold text-zinc-500 mb-2 uppercase">顶层需求列表</div>
                <textarea
                  v-model="batchHighLevelRequirements"
                  placeholder="请输入多个顶层需求，每行一个..."
                  class="w-full p-3 rounded-none border border-zinc-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100"
                  rows="6"
                  maxlength="3000"
                />
                <div class="text-xs text-zinc-400 mt-1">每行输入一个顶层需求</div>
              </div>
  
              <div class="mb-4">
                <div class="text-xs font-semibold text-zinc-500 mb-2 uppercase">底层需求列表</div>
                <textarea
                  v-model="batchLowLevelRequirements"
                  placeholder="请输入多个底层需求，每行一个..."
                  class="w-full p-3 rounded-none border border-zinc-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-zinc-100"
                  rows="6"
                  maxlength="3000"
                />
                <div class="text-xs text-zinc-400 mt-1">每行输入一个底层需求</div>
              </div>
            </div>
  
            <button
              @click="analysisMode === 'relation' ? analyzeRelation() : analyzeBatch()"
              :disabled="!hasValidRequirements || loading"
              class="w-full px-6 py-3 bg-zinc-900 text-white rounded-none font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Sparkles v-if="!loading" class="w-4 h-4" />
              <span v-if="loading" class="animate-spin">⏳</span>
              <span>{{ loading ? '分析中...' : '开始分析' }}</span>
            </button>
  
            <!-- 快速示例 -->
            <div class="mt-6 pt-6 border-t border-zinc-200">
              <div class="text-xs font-semibold text-zinc-500 mb-3 uppercase">快速示例</div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="example in (analysisMode === 'relation' ? relationExamples : batchExamples)"
                  :key="example.title"
                  @click="selectExample(example)"
                  class="px-3 py-1.5 text-xs bg-zinc-100 text-zinc-700 rounded-none hover:bg-zinc-200 transition-colors"
                >
                  {{ example.title }}
                </button>
              </div>
            </div>
          </div>
        </div>
  
        <!-- 右侧：结果区域 -->
        <div class="lg:col-span-2">
          <div class="bg-white rounded-none border border-zinc-200 p-6 shadow-sm">
            <div class="text-lg font-semibold text-zinc-900 mb-4 flex items-center gap-2">
              <FileSearch class="w-5 h-5" />
              分析结果
            </div>
  
            <!-- 加载状态 -->
            <div v-if="loading" class="flex flex-col items-center justify-center py-12">
              <div class="animate-spin w-8 h-8 border-4 border-zinc-200 border-t-zinc-900 rounded-full mb-4"></div>
              <div class="text-sm text-zinc-500">AI正在分析您的需求，请稍候...</div>
            </div>
  
            <!-- 单对分析结果 -->
            <div v-else-if="analysisResult" class="space-y-6">
              <div :class="analysisResult.has_relation ? 'bg-green-50 border-green-200' : 'bg-zinc-50 border-zinc-200'" class="p-4 rounded-none border">
                <div class="text-sm font-semibold mb-1">{{ analysisResult.summary || (analysisResult.has_relation ? '检测到追溯关系' : '未检测到直接的追溯关系') }}</div>
              </div>
  
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <div class="text-xs text-zinc-500 mb-1">关系状态</div>
                  <div :class="analysisResult.has_relation ? 'bg-green-100 text-green-700' : 'bg-zinc-100 text-zinc-700'" class="px-3 py-1 rounded-none text-sm font-medium inline-block">
                    {{ analysisResult.has_relation ? '存在关系' : '无直接关系' }}
                  </div>
                </div>
                <div>
                  <div class="text-xs text-zinc-500 mb-1">关系类型</div>
                  <div class="text-sm font-semibold">{{ getRelationTypeLabel(analysisResult.relation_type) }}</div>
                </div>
                <div>
                  <div class="text-xs text-zinc-500 mb-1">置信度</div>
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-2 bg-zinc-200 rounded-none overflow-hidden">
                      <div :class="getConfidenceColor(analysisResult.confidence)" class="h-full" :style="{ width: `${analysisResult.confidence * 100}%` }"></div>
                    </div>
                    <span class="text-sm font-semibold">{{ Math.round(analysisResult.confidence * 100) }}%</span>
                  </div>
                </div>
              </div>
  
              <div v-if="analysisResult.analysis_details" class="p-4 bg-zinc-50 rounded-none">
                <div class="text-xs font-semibold text-zinc-500 mb-2 uppercase">详细分析</div>
                <div class="text-sm text-zinc-700 whitespace-pre-wrap">{{ analysisResult.analysis_details }}</div>
              </div>
  
              <div v-if="analysisResult.trace_network">
                <div class="text-sm font-semibold text-zinc-900 mb-3">追溯网络</div>
                <TraceNetworkChart :trace-data="analysisResult" />
              </div>
            </div>
  
            <!-- 批量分析结果 -->
            <div v-else-if="batchResult" class="space-y-6">
              <div class="bg-blue-50 border border-blue-200 p-4 rounded-none">
                <div class="text-sm font-semibold text-blue-900">
                  批量分析了{{ batchResult.high_level_requirements?.length || 0 }}个顶层需求和{{ batchResult.low_level_requirements?.length || 0 }}个底层需求，
                  共{{ batchResult.statistics?.total_combinations || 0 }}个组合，发现{{ batchResult.statistics?.relations_found || 0 }}个追溯关系
                </div>
              </div>
  
              <div class="grid grid-cols-3 gap-4">
                <div class="p-4 bg-zinc-50 rounded-none">
                  <div class="text-xs text-zinc-500 mb-1">分析组合数</div>
                  <div class="text-2xl font-bold text-zinc-900">{{ batchResult.statistics?.total_combinations || 0 }}</div>
                </div>
                <div class="p-4 bg-zinc-50 rounded-none">
                  <div class="text-xs text-zinc-500 mb-1">发现关系数</div>
                  <div class="text-2xl font-bold text-green-600">{{ batchResult.statistics?.relations_found || 0 }}</div>
                </div>
                <div class="p-4 bg-zinc-50 rounded-none">
                  <div class="text-xs text-zinc-500 mb-1">关系发现率</div>
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-2 bg-zinc-200 rounded-none overflow-hidden">
                      <div class="bg-green-500 h-full" :style="{ width: `${(batchResult.statistics?.relation_rate || 0) * 100}%` }"></div>
                    </div>
                    <span class="text-sm font-semibold">{{ Math.round((batchResult.statistics?.relation_rate || 0) * 100) }}%</span>
                  </div>
                </div>
              </div>
  
              <!-- 关系类型统计 -->
              <div v-if="batchResult.relation_types_count && Object.keys(batchResult.relation_types_count).length > 0">
                <div class="text-sm font-semibold text-zinc-900 mb-3">关系类型统计</div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div v-for="(count, type) in batchResult.relation_types_count" :key="type" class="p-4 bg-white border border-zinc-200 rounded-none text-center">
                    <div class="text-2xl font-bold text-zinc-900 mb-1">{{ count }}</div>
                    <div class="text-xs text-zinc-500">{{ getRelationTypeLabel(type) }}</div>
                  </div>
                </div>
              </div>
  
              <!-- 关系详情表格 -->
              <div v-if="batchResult.relations && batchResult.relations.filter(r => r.has_relation).length > 0">
                <div class="text-sm font-semibold text-zinc-900 mb-3">关系详情 (仅显示存在关系)</div>
                <div class="overflow-x-auto">
                  <table class="w-full text-sm">
                    <thead class="bg-zinc-50">
                      <tr>
                        <th class="px-4 py-2 text-left text-xs font-semibold text-zinc-600">顶层需求</th>
                        <th class="px-4 py-2 text-left text-xs font-semibold text-zinc-600">底层需求</th>
                        <th class="px-4 py-2 text-left text-xs font-semibold text-zinc-600">关系类型</th>
                        <th class="px-4 py-2 text-left text-xs font-semibold text-zinc-600">置信度</th>
                        <th class="px-4 py-2 text-left text-xs font-semibold text-zinc-600">摘要</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-zinc-200">
                      <tr v-for="(rel, idx) in batchResult.relations.filter(r => r.has_relation)" :key="idx" class="hover:bg-zinc-50">
                        <td class="px-4 py-3">
                          <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded-none text-xs font-medium">#{{ rel.high_level_index + 1 }}</span>
                        </td>
                        <td class="px-4 py-3">
                          <span class="px-2 py-1 bg-green-100 text-green-700 rounded-none text-xs font-medium">#{{ rel.low_level_index + 1 }}</span>
                        </td>
                        <td class="px-4 py-3">
                          <span :class="getRelationTypeColor(rel.relation_type)" class="px-2 py-1 rounded-none text-xs font-medium border">
                            {{ getRelationTypeLabel(rel.relation_type) }}
                          </span>
                        </td>
                        <td class="px-4 py-3">
                          <div class="flex items-center gap-2">
                            <div class="flex-1 h-1.5 bg-zinc-200 rounded-none overflow-hidden">
                              <div :class="getConfidenceColor(rel.confidence)" class="h-full" :style="{ width: `${rel.confidence * 100}%` }"></div>
                            </div>
                            <span class="text-xs font-semibold">{{ Math.round(rel.confidence * 100) }}%</span>
                          </div>
                        </td>
                        <td class="px-4 py-3 text-xs text-zinc-600">{{ rel.summary || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
  
              <!-- 追溯网络 -->
              <div v-if="batchResult">
                <div class="text-sm font-semibold text-zinc-900 mb-3">追溯网络</div>
                <TraceNetworkChart :trace-data="batchResult" />
              </div>
            </div>
  
            <!-- 空状态 -->
            <div v-else class="flex flex-col items-center justify-center py-12 text-zinc-400">
              <FileSearch class="w-12 h-12 mb-4 opacity-50" />
              <div class="text-sm">请在左侧输入需求描述，点击分析按钮开始AI智能分析</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
  

