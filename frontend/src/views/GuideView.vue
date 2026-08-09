<template>
  <div class="ref-app sa-page">
    <div class="guide-layout sa-page-surface">
      <!-- 主内容区 -->
      <main class="guide-canvas">
        <section class="hero-overview" data-animate style="--delay: 0.05s">
          <!-- 品牌标识 -->
          <div class="brand-header">
            <div class="brand-logo">
              <div class="brand-mark">Semantic</div>
              <div class="brand-sub">Atlas</div>
            </div>
          </div>

          <div class="hero-text-full">
            <p class="eyebrow">系统入口选择 · Entry Selection</p>
            <h1>欢迎使用 Semantic Atlas</h1>
            <p class="lead">
              请根据您的需求选择对应的系统入口。正式版提供完整的生产环境功能，包含语义图谱分析与业务流管理；测试版提供最新的实验性功能，包含冲突检测、需求提取等 Alpha 特性。
            </p>
          </div>

          <!-- 入口卡片 -->
          <div class="entry-cards">
            <div
              class="entry-card main-card sa-card sa-card--interactive"
              @click="navigateTo('/beta/login')"
            >
              <div class="card-header">
                <div class="card-icon main-icon">
                  <Home class="icon-svg" />
                </div>
                <div class="card-badge production">Production</div>
              </div>
              <div class="card-content">
                <h3>正式版系统</h3>
                <p>生产环境入口，提供完整的企业级项目管理能力</p>
                <ul class="feature-list">
                  <li>
                    <CheckCircle2 class="check-icon" />
                    <span>项目仪表盘与概览</span>
                  </li>
                  <li>
                    <CheckCircle2 class="check-icon" />
                    <span>需求管理与分析</span>
                  </li>
                  <li>
                    <CheckCircle2 class="check-icon" />
                    <span>评审与追踪流程</span>
                  </li>
                  <li>
                    <CheckCircle2 class="check-icon" />
                    <span>报告生成与导出</span>
                  </li>
                </ul>
              </div>
              <div class="card-footer">
                <button type="button" class="primary card-btn sa-button sa-button--primary">
                  进入正式版
                  <ArrowRight class="btn-icon" />
                </button>
              </div>
            </div>

            <div
              class="entry-card alpha-card sa-card sa-card--interactive sa-card--accent"
              @click="navigateTo('/alpha/conflict')"
            >
              <div class="card-header">
                <div class="card-icon alpha-icon">
                  <Beaker class="icon-svg" />
                </div>
                <div class="card-badge alpha">Alpha</div>
              </div>
              <div class="card-content">
                <h3>测试版系统</h3>
                <p>功能实验室，包含最新的 AI 驱动特性</p>
                <ul class="feature-list">
                  <li>
                    <Sparkles class="check-icon" />
                    <span>需求冲突智能检测</span>
                  </li>
                  <li>
                    <Sparkles class="check-icon" />
                    <span>录音解析与上下文构建</span>
                  </li>
                  <li>
                    <Sparkles class="check-icon" />
                    <span>智能需求抽取</span>
                  </li>
                  <li>
                    <Sparkles class="check-icon" />
                    <span>需求追溯与分类</span>
                  </li>
                </ul>
              </div>
              <div class="card-footer">
                <button type="button" class="primary card-btn alpha-btn sa-button sa-button--primary">
                  进入测试版
                  <ArrowRight class="btn-icon" />
                </button>
              </div>
            </div>

            <div
              class="entry-card video-card sa-card sa-card--interactive"
              @click="navigateTo('/guide/videos')"
            >
              <div class="card-header">
                <div class="card-icon video-icon">
                  <Clapperboard class="icon-svg" />
                </div>
                <div class="card-badge video">Video</div>
              </div>
              <div class="card-content">
                <h3>演示视频</h3>
                <p>观看系统从录音采集到需求分析的操作过程</p>
                <ul class="feature-list">
                  <li>
                    <PlayCircle class="check-icon" />
                    <span>音频转文字</span>
                  </li>
                  <li>
                    <PlayCircle class="check-icon" />
                    <span>需求条目化</span>
                  </li>
                  <li>
                    <PlayCircle class="check-icon" />
                    <span>需求分析</span>
                  </li>
                </ul>
              </div>
              <div class="card-footer">
                <button type="button" class="primary card-btn video-btn sa-button sa-button--primary">
                  查看演示视频
                  <ArrowRight class="btn-icon" />
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import {
  Home,
  Beaker,
  Clapperboard,
  PlayCircle,
  ArrowRight,
  CheckCircle2,
  Sparkles
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

const navigateTo = (path) => {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''

  if (path === '/beta/login' && redirect) {
    router.push({ path, query: { redirect } })
    return
  }

  router.push(path)
}
</script>

<style scoped>
/* 引导页布局 */
.guide-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f9f9f8;
  padding: 40px 20px;
}

.guide-canvas {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

/* 品牌标识 */
.brand-header {
  display: flex;
  justify-content: center;
  margin-bottom: 20px;
}

.brand-logo {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.brand-mark {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #1b2730;
}

.brand-sub {
  font-size: 18px;
  font-weight: 300;
  color: #9eabb4;
  letter-spacing: 0.1em;
}

/* 复用 main 的样式结构 */
.hero-overview {
  display: flex;
  flex-direction: column;
  gap: 40px;
}

.hero-text-full {
  max-width: 900px;
  text-align: center;
  margin: 0 auto;
}

.hero-text-full h1 {
  font-size: 36px;
  margin: 12px 0 16px;
  font-family: serif;
  color: #1b2730;
}

.hero-text-full .lead {
  max-width: 800px;
  color: #5d6b76;
  font-size: 15px;
  line-height: 1.6;
  margin: 0 auto;
}

/* 入口卡片样式 */
.entry-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.entry-card {
  background: white;
  border: 1px solid rgba(28, 40, 52, 0.08);
  border-radius: 0;
  padding: 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.entry-card:hover {
  border-color: rgba(28, 40, 52, 0.15);
  box-shadow: 0 8px 24px rgba(28, 40, 52, 0.08);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.card-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0;
}

.icon-svg {
  width: 32px;
  height: 32px;
  color: white;
  stroke-width: 1.5;
}

.main-icon {
  background: linear-gradient(135deg, #2f8f89 0%, #1f5f5a 100%);
}

.alpha-icon {
  background: linear-gradient(135deg, #c4692f 0%, #8b4a21 100%);
}

.video-icon {
  background: #1b2730;
}

.card-badge {
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-radius: 0;
}

.card-badge.production {
  background: #e8f4f3;
  color: #2f8f89;
  border: 1px solid #2f8f89;
}

.card-badge.alpha {
  background: #f9ede6;
  color: #c4692f;
  border: 1px solid #c4692f;
}

.card-badge.video {
  background: #eef2f1;
  color: #315c57;
  border: 1px solid #7ca19b;
}

.card-content h3 {
  font-size: 24px;
  font-weight: 600;
  font-family: serif;
  color: #1b2730;
  margin: 0 0 8px;
}

.card-content > p {
  color: #5d6b76;
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 20px;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #5d6b76;
}

.check-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke-width: 2;
  color: #88b1a3;
}

.alpha-card .check-icon {
  color: #d6b77c;
}

.video-card .check-icon {
  color: #2f8f89;
}

.card-footer {
  margin-top: auto;
}

.card-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 500;
}

.btn-icon {
  width: 16px;
  height: 16px;
  transition: transform 0.3s ease;
}

.entry-card:hover .btn-icon {
  transform: translateX(4px);
}

.alpha-btn {
  background: #c4692f;
}

.alpha-btn:hover {
  background: #a85424;
}

.video-btn {
  background: #1b2730;
}

.video-btn:hover {
  background: #31414c;
}

/* 响应式 */
@media (max-width: 1024px) {
  .entry-cards {
    grid-template-columns: 1fr;
  }
}
</style>
