<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :roleType="roleType"
        :roleLabel="roleLabel"
        :timestamp="timestamp"
        :notificationCount="notificationCount"
        :activePage="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas">
        <!-- 页面头部 -->
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">需求采集 · 高级选项</span>
          </div>
          <div class="nav-center">
            <span class="adv-subtitle">所有参数修改会实时同步到采集流程</span>
          </div>
          <div class="page-actions">
            <button type="button" class="close-btn" title="返回需求采集" @click="goBack">
              <X class="w-5 h-5" />
            </button>
          </div>
        </section>

        <!-- 参数面板 -->
        <section class="adv-content" data-animate style="--delay: 0.1s">
          <!-- Phase 2: 上下文构建 -->
          <div class="param-card">
            <div class="param-card-header">
              <div class="param-card-icon phase2-icon">2</div>
              <div>
                <h3 class="param-card-title">上下文构建参数</h3>
                <p class="param-card-desc">Phase 2 — 构建语义关联图，生成 Bundles</p>
              </div>
            </div>
            <div class="param-grid cols-3">
              <ParamNumber label="窗口大小" v-model="options.window_size" :min="3" :max="20" />
              <ParamNumber label="步长" v-model="options.step_size" :min="1" :max="options.window_size - 1" />
              <ParamNumber label="置信度阈值 τ" v-model="options.tau" :min="0" :max="1" :step="0.05" />
              <ParamNumber label="Top-K" v-model="options.top_k" :min="1" :max="20" />
              <ParamNumber label="Bundle Token 上限" v-model="options.token_limit_per_bundle" :min="500" :max="16000" :step="500" />
            </div>
            <div class="param-toggles">
              <ParamToggle label="并行处理窗口" desc="并行处理多个语义窗口" v-model="options.enable_parallel_windows" />
            </div>
            <div v-if="options.enable_parallel_windows" class="param-grid cols-2 indent-section">
              <ParamNumber label="最大并发数" v-model="options.max_concurrent_windows" :min="1" :max="20" />
            </div>
            <div class="param-toggles">
              <ParamToggle label="Mock 模式" desc="使用假数据跳过 LLM 调用" v-model="options.mock_llm" />
            </div>
          </div>

          <!-- Phase 3: 需求抽取 -->
          <div class="param-card">
            <div class="param-card-header">
              <div class="param-card-icon phase3-icon">3</div>
              <div>
                <h3 class="param-card-title">需求抽取参数</h3>
                <p class="param-card-desc">Phase 3 — EgoBundle → L1/L2/L3 需求抽取</p>
              </div>
            </div>
            <div class="param-grid cols-3">
              <div class="param-item">
                <label class="param-label">Bundle 策略</label>
                <select v-model="options.bundle_strategy" class="param-select">
                  <option value="graph">graph（基于 span_links）</option>
                  <option value="sequence">sequence（按时间窗口）</option>
                </select>
              </div>
              <div class="param-item">
                <label class="param-label">锚点策略</label>
                <select v-model="options.anchor_strategy" class="param-select">
                  <option value="informative">informative</option>
                  <option value="keyword">keyword</option>
                  <option value="all">all</option>
                </select>
              </div>
              <div class="param-item">
                <label class="param-label">r（max 跳数）</label>
                <select v-model.number="options.r" class="param-select">
                  <option :value="1">1</option>
                  <option :value="2">2</option>
                </select>
              </div>
              <div class="param-item">
                <label class="param-label">模型</label>
                <select v-model="options.model" class="param-select">
                  <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
                  <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
                </select>
              </div>
              <ParamNumber label="Max Spans / Bundle" v-model="options.max_spans_per_bundle" :min="1" :max="64" />
              <ParamNumber label="Token 限制" v-model="options.token_limit" :min="0" :max="8000" :step="100" hint="0 = 不限制" />
              <ParamNumber label="Top-M 2-Hop" v-model="options.top_m_2hop" :min="1" :max="50" />
            </div>
            <div class="param-item" style="margin-top: 12px;">
              <label class="param-label">关键词（逗号分隔）</label>
              <input v-model="options.keywords" type="text" class="param-input" placeholder="要,需要,必须,应该..." />
            </div>
            <div class="param-toggles">
              <ParamToggle label="r=2 自适应重试" desc="先尝试 r=1，不足再 r=2" v-model="options.adaptive_retry_r2" />
              <ParamToggle label="思考模式" desc="独立控制 DeepSeek thinking" v-model="options.use_thinking_mode" />
              <ParamToggle label="使用 Tool-Call" desc="使用 tool-call 模式（需要 deepseek provider）" v-model="options.use_toolcall" />
              <ParamToggle label="重跑前清理历史" desc="每次抽取前删除该 session 的历史 L1/L2/L3" v-model="options.reset_before_extract" />
              <ParamToggle label="并行处理锚点" desc="并行抽取多个锚点" v-model="options.enable_parallel_windows" />
            </div>
            <div v-if="options.enable_parallel_windows" class="param-grid cols-2 indent-section">
              <ParamNumber label="最大并发锚点数" v-model="options.max_concurrent_windows" :min="1" :max="20" />
            </div>
            <div v-if="!options.enable_parallel_windows" class="param-toggles indent-section">
              <ParamToggle label="串行记忆（History Aware）" desc="大模型看到前面已生成的需求，避免重复" v-model="options.history_aware" />
            </div>
          </div>



          <!-- Phase 3: Planner 超时 -->
          <div class="param-card">
            <div class="param-card-header">
              <div class="param-card-icon phase3-icon">⏱</div>
              <div>
                <h3 class="param-card-title">Planner 超时与重试</h3>
                <p class="param-card-desc">Phase 3 LLM/Tool-Call 的超时配置</p>
              </div>
            </div>
            <div class="param-grid cols-3">
              <ParamNumber label="连接超时（秒）" v-model="options.planner_connect_timeout_seconds" :min="1" :max="600" />
              <ParamNumber label="读超时（秒）" v-model="options.planner_read_timeout_seconds" :min="1" :max="7200" :step="10" />
              <ParamNumber label="重试次数" v-model="options.planner_max_retries" :min="0" :max="5" />
            </div>
          </div>

          <!-- Phase 3: 后处理去重 -->
          <div class="param-card">
            <div class="param-card-header">
              <div class="param-card-icon dedup-icon">🔄</div>
              <div>
                <h3 class="param-card-title">抽取后去重</h3>
                <p class="param-card-desc">Phase 3 后处理 — 相似需求检测、LLM 裁决与合并</p>
              </div>
            </div>
            <div class="param-toggles">
              <ParamToggle label="启用去重" desc="抽取完成后进行相似需求去重" v-model="options.post_dedup" />
            </div>
            <template v-if="options.post_dedup">
              <div class="param-grid cols-2 indent-section">
                <ParamNumber label="相似度阈值" v-model="options.dedup_threshold" :min="0.5" :max="0.99" :step="0.01" hint="越高越严格，默认 0.85" />
              </div>
              <div class="param-toggles indent-section">
                <ParamToggle label="LLM 去重建议" desc="使用 LLM 判断是否合并及输出合并文本" v-model="options.dedup_with_llm" />
                <ParamToggle label="自动合并（写库）" desc="按 LLM 决策自动合并并删除重复项" v-model="options.dedup_auto_merge" />
                <ParamToggle label="2v2 Pairwise 裁决" desc="同层级两两比对，合并或重写为互不重叠的需求" v-model="options.pairwise_dedup" />
              </div>
              <template v-if="options.pairwise_dedup">
                <div class="param-grid cols-2 indent-section">
                  <ParamNumber label="2v2 最大配对数" v-model="options.pairwise_max_pairs" :min="1" :max="5000" hint="避免大 session 耗时失控" />
                </div>
                <div class="param-toggles indent-section">
                  <ParamToggle label="2v2 自动应用（写库）" desc="自动 merge 或改写；冲突项会跳过" v-model="options.pairwise_auto_apply" />
                </div>
              </template>
            </template>
          </div>

          <!-- Phase 4: L4 生成 -->
          <div class="param-card">
            <div class="param-card-header">
              <div class="param-card-icon phase4-icon">4</div>
              <div>
                <h3 class="param-card-title">L4 底层需求生成</h3>
                <p class="param-card-desc">Phase 4 — 基于高层需求生成可实现、可测试的软件需求</p>
              </div>
            </div>
            <div class="param-grid cols-3">
              <ParamNumber label="Top-K Pattern" v-model="options.l4_top_k_pattern" :min="1" :max="20" />
              <ParamNumber label="Top-K Spec" v-model="options.l4_top_k_spec" :min="1" :max="20" />
              <ParamNumber label="Top-K NFR" v-model="options.l4_top_k_nfr" :min="1" :max="20" />
              <ParamNumber label="Max L4 / Top Req" v-model="options.l4_max_per_top_req" :min="1" :max="20" />
              <ParamNumber label="Min L4 / Top Req" v-model="options.l4_min_per_top_req" :min="0" :max="10" />
              <ParamNumber label="置信度阈值" v-model="options.l4_confidence_threshold" :min="0" :max="1" :step="0.1" />
              <ParamNumber label="并发数" v-model="options.l4_max_concurrent" :min="1" :max="8" />
            </div>
            <div class="param-toggles">
              <div class="param-item">
                <label class="param-label">L4 模型</label>
                <select v-model="options.l4_model" class="param-select">
                  <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
                  <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
                </select>
              </div>
              <ParamToggle label="L4 思考模式" desc="独立控制 DeepSeek thinking" v-model="options.l4_use_thinking_mode" />
              <ParamToggle label="生成前清空历史 L4" desc="开始前删除该 session 的所有 L4 记录" v-model="options.l4_clear_existing" danger />
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { X } from 'lucide-vue-next'
import Sidebar from '../../components/beta/Sidebar.vue'
import ParamNumber from '../../components/beta/collection/ParamNumber.vue'
import ParamToggle from '../../components/beta/collection/ParamToggle.vue'
import { useCollectionPipeline } from '../../composables/useCollectionPipeline'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const router = useRouter()
const { activePage, handleNavigate, handleExit } = useBetaNavigation('requirements-collection')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()
const { options } = useCollectionPipeline()

function goBack() {
  router.push({ name: 'beta-requirements-collection' })
}
</script>

<style scoped>
.adv-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.adv-subtitle {
  font-size: 13px;
  color: var(--teal);
  font-weight: 500;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  border-radius: 0;
  background: rgba(255, 255, 255, 0.9);
  color: var(--ink-700);
  cursor: pointer;
  transition: all 0.2s ease;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

/* 参数卡片 */
.param-card {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(28, 40, 52, 0.1);
  border-radius: 0;
  padding: 20px;
}


.param-card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
}

.param-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
}

.phase2-icon { background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); }
.phase3-icon { background: rgba(196, 105, 47, 0.1); color: var(--accent); border: 1px solid rgba(196, 105, 47, 0.2); }
.phase4-icon { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.2); }
.dedup-icon { background: rgba(168, 85, 247, 0.1); color: #a855f7; border: 1px solid rgba(168, 85, 247, 0.2); }

.param-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-950);
  margin: 0;
}

.param-card-desc {
  font-size: 12px;
  color: var(--ink-500);
  margin: 4px 0 0 0;
}

/* 参数网格 */
.param-grid {
  display: grid;
  gap: 14px;
}

.param-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }
.param-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }

@media (max-width: 900px) {
  .param-grid.cols-3 { grid-template-columns: repeat(2, 1fr); }
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-600);
  letter-spacing: 0.3px;
}

.param-select,
.param-input {
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
  color: var(--ink-950);
  border-radius: 0;
  transition: all 0.2s ease;
}

.param-select:focus,
.param-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(196, 105, 47, 0.1);
}

.param-toggles {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.indent-section {
  margin-top: 10px;
  padding-left: 16px;
  border-left: 3px solid rgba(28, 40, 52, 0.08);
}
</style>
