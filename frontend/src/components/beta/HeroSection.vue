<template>
  <section class="hero-overview" data-animate style="--delay: 0.05s">
    <div class="hero-text-full">
      <p class="eyebrow">项目仪表盘 · Overview</p>
      <h1>把「现在该做什么」放在第一屏。</h1>
      <p class="lead">
        项目健康摘要、需求状态分布、评审队列、缺陷跟踪、基线进度 — 所有关键指标的实时聚合。
      </p>
      <div class="hero-actions">
        <button
          type="button"
          class="primary sa-button sa-button--primary"
          @click="$emit('navigate', 'requirements')"
        >
          进入需求管理
        </button>
        <button
          type="button"
          class="ghost sa-button sa-button--secondary"
          @click="$emit('navigate', 'reviews')"
        >
          查看评审中心
        </button>
        <button
          type="button"
          class="ghost sa-button sa-button--secondary"
          @click="$emit('navigate', 'tracking')"
        >
          打开追踪视图
        </button>
      </div>
      <div class="ribbon chips-row">
        <span class="chip-status">
          <i class="dot success"></i>
          门禁: 字段完整度 {{ gateMetrics.completeness }}%
        </span>
        <span class="chip-status">
          <i class="dot warn"></i>
          待澄清: {{ gateMetrics.pendingClarification }}
        </span>
        <span class="chip-status">
          <i class="dot risk"></i>
          风险: {{ gateMetrics.highRiskCount }} 个高优先级
        </span>
        <span class="chip-status">
          <i class="dot info"></i>
          最新活动: {{ latestActivityLabel }}
        </span>
      </div>
    </div>

    <!-- 骨架屏 -->
    <div v-if="loading" class="stats-row">
      <div v-for="i in 4" :key="i" class="stat-box skeleton-box sa-card">
        <div class="skeleton-line short"></div>
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line medium"></div>
      </div>
    </div>

    <!-- 真实数据 -->
    <div v-else class="stats-row">
      <div class="stat-box sa-card">
        <div class="stat-header">
          <span>项目总览</span>
          <span class="tag">All</span>
        </div>
        <div class="stat-number">{{ reqStats.total.toLocaleString() }}</div>
        <div class="stat-footer">
          <span class="pill">草稿 {{ reqStats.draft }}</span>
          <span class="pill">待评审 {{ reqStats.underReview }}</span>
        </div>
        <div class="stat-sub">
          <span class="pill">已确认 {{ reqStats.confirmed }}</span>
          <span class="pill">已完成 {{ reqStats.completed }}</span>
        </div>
      </div>

      <div class="stat-box sa-card">
        <div class="stat-header">
          <span>评审队列</span>
          <span class="tag">Review</span>
        </div>
        <div class="stat-number">{{ reviewStats.total }}</div>
        <div class="stat-footer">
          <span class="pill">即将到期 {{ reviewStats.dueSoon }}</span>
          <span class="pill">我参与 {{ reviewStats.myParticipation }}</span>
        </div>
      </div>

      <div class="stat-box sa-card">
        <div class="stat-header">
          <span>缺陷跟踪</span>
          <span class="tag">Defects</span>
        </div>
        <div class="stat-number">{{ defectStats.total }}</div>
        <div class="stat-footer">
          <span class="pill" :class="{ 'pill-warn': defectStats.overdue > 0 }">超时 {{ defectStats.overdue }}</span>
          <span class="pill">未分配 {{ defectStats.unassigned }}</span>
        </div>
      </div>

      <div class="stat-box sa-card">
        <div class="stat-header">
          <span>基线状态</span>
          <span class="tag">Baseline</span>
        </div>
        <div class="stat-number">{{ baselineInfo.status }}</div>
        <div class="stat-footer">
          <span class="pill">里程碑 {{ baselineInfo.diffCount }}</span>
          <span class="pill">候选 {{ baselineInfo.candidateCount }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  reqStats: {
    type: Object,
    default: () => ({ total: 0, draft: 0, underReview: 0, confirmed: 0, inProgress: 0, completed: 0 }),
  },
  reviewStats: {
    type: Object,
    default: () => ({ total: 0, dueSoon: 0, myParticipation: 0 }),
  },
  defectStats: {
    type: Object,
    default: () => ({ total: 0, overdue: 0, unassigned: 0 }),
  },
  baselineInfo: {
    type: Object,
    default: () => ({ status: 'N/A', diffCount: 0, candidateCount: 0 }),
  },
  gateMetrics: {
    type: Object,
    default: () => ({ completeness: 0, pendingClarification: 0, highRiskCount: 0 }),
  },
  latestActivityLabel: {
    type: String,
    default: '—',
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['navigate'])
</script>

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

.pill-warn {
  background: #fff5f5;
  color: #c45b60;
  border: 1px solid #f0c9ca;
}

/* 骨架屏 */
.skeleton-box {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  height: 16px;
  background: #eee;
  border-radius: 4px;
}
.skeleton-line.short { width: 60%; }
.skeleton-line.wide { width: 40%; height: 32px; }
.skeleton-line.medium { width: 80%; }

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 按钮 */
button.primary {
  background: var(--accent, #c4692f);
  color: white;
  border: none;
  padding: 8px 20px;
  font-size: 13px;
  cursor: pointer;
}
button.ghost {
  background: white;
  border: 1px solid rgba(28,40,52,0.15);
  padding: 8px 20px;
  font-size: 13px;
  color: #5d6b76;
  cursor: pointer;
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
