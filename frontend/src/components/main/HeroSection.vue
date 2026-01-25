<template>
  <section class="hero-overview" data-animate style="--delay: 0.05s">
    <div class="hero-text-full">
      <p class="eyebrow">项目仪表盘 · Overview</p>
      <h1>把「现在该做什么」放在第一屏。</h1>
      <p class="lead">
        这里展示的是一个通用的概览页模型：项目健康摘要、我的待办、评审队列、流程进度、最近活动与风险提示。结构参考企业级项目管理工具（如 Jama Connect）的 Dashboard / My Work 思路，但内容保持中性占位。
      </p>
      <div class="hero-actions">
        <button type="button" class="primary">进入我的待办</button>
        <button type="button" class="ghost">查看评审中心</button>
        <button type="button" class="ghost">打开追踪视图</button>
      </div>
      <div class="ribbon chips-row">
        <span class="chip-status"><i class="dot success"></i> 门禁: 字段完整度 92%</span>
        <span class="chip-status"><i class="dot warn"></i> 待澄清: 12</span>
        <span class="chip-status"><i class="dot risk"></i> 风险: 3 个高优先级</span>
        <span class="chip-status"><i class="dot info"></i> 最新基线: 2 小时前</span>
      </div>
    </div>

    <div class="stats-row">
      <div class="stat-box">
        <div class="stat-header">
          <span>项目总览</span>
          <span class="tag">All</span>
        </div>
        <div class="stat-number">2,138</div>
        <div class="stat-footer">
          <span class="pill">草稿 148</span>
          <span class="pill">待评审 63</span>
        </div>
        <div class="stat-sub">
          <span class="pill">已批准 1,790</span>
        </div>
      </div>

      <div class="stat-box">
        <div class="stat-header">
          <span>评审队列</span>
          <span class="tag">Review</span>
        </div>
        <div class="stat-number">17</div>
        <div class="stat-footer">
          <span class="pill">即将到期 4</span>
          <span class="pill">我参与 6</span>
        </div>
      </div>

      <div class="stat-box">
        <div class="stat-header">
          <span>澄清与问题</span>
          <span class="tag">Q&A</span>
        </div>
        <div class="stat-number">12</div>
        <div class="stat-footer">
          <span class="pill">超时 2</span>
          <span class="pill">未分配 3</span>
        </div>
      </div>

      <div class="stat-box">
        <div class="stat-header">
          <span>基线状态</span>
          <span class="tag">Baseline</span>
        </div>
        <div class="stat-number">Ready</div>
        <div class="stat-footer">
          <span class="pill">差异 28</span>
          <span class="pill">候选 1</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero-overview {
  display: flex;
  flex-direction: column;
  gap: 40px;
}

.hero-text-full {
  max-width: 900px;
}

.hero-text-full h1 {
  font-size: 36px;
  margin: 12px 0 16px;
  font-family:serif;
  color: #1b2730;
}

.hero-text-full .lead {
  max-width: 800px;
  color: #5d6b76;
  font-size: 15px;
  line-height: 1.6;
}

.chips-row {
  margin-top: 24px;
}

.chip-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 0;
  border: 1px solid rgba(28,40,52,0.1);
  font-size: 13px;
  background: white;
  color: #5d6b76;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot.success { background: #88b1a3; }
.dot.warn { background: #d6b77c; }
.dot.risk { background: #c4767a; }
.dot.info { background: #96a6b5; }

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-box {
  background: white;
  border: 1px solid rgba(28,40,52,0.08);
  border-radius: 0;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #5d6b76;
}

.stat-header .tag {
  background: #eee;
  padding: 4px 10px;
  border-radius: 0;
  font-size: 12px;
}

.stat-number {
  font-size: 36px;
  font-weight: bold;
  font-family: serif;
  color: #1b2730;
}

.stat-footer, .stat-sub {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pill {
  background: #f4f4f4;
  padding: 4px 12px;
  border-radius: 0;
  font-size: 12px;
  color: #666;
}

@media (max-width: 1024px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 640px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
}
</style>
