<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :role-type="roleType"
        :role-label="roleLabel"
        :timestamp="timestamp"
        :notification-count="notificationCount"
        :active-page="activePage"
        @navigate="handleNavigate"
        @exit="handleExit"
      />
      <main class="canvas leaderboard-canvas">
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">用量排行榜</span>
            <span class="nav-subtitle">按自然周期汇总所有用户的实际美元用量和 Token 用量</span>
          </div>
          <div class="period-control" role="tablist" aria-label="排行榜时间范围">
            <button
              v-for="item in periods"
              :key="item.key"
              type="button"
              class="period-btn"
              :class="{ active: selectedPeriod === item.key }"
              :aria-pressed="selectedPeriod === item.key"
              @click="selectedPeriod = item.key"
            >
              {{ item.label }}
            </button>
          </div>
          <div class="page-actions">
            <button type="button" class="action-btn ghost sa-button sa-button--secondary" :disabled="loading" @click="loadLeaderboard">
              <RefreshCw class="btn-icon" :class="{ spin: loading }" />
              刷新
            </button>
          </div>
        </section>

        <section class="summary-grid" data-animate style="--delay: 0.1s">
          <article class="summary-card">
            <span>总实际用量</span>
            <strong>{{ formatCurrency(leaderboard.total_actual_cost) }}</strong>
          </article>
          <article class="summary-card">
            <span>总 Tokens</span>
            <strong>{{ formatNumber(leaderboard.total_tokens) }}</strong>
          </article>
          <article class="summary-card">
            <span>总请求数</span>
            <strong>{{ formatNumber(leaderboard.total_requests) }}</strong>
          </article>
          <article class="summary-card subtle">
            <span>统计范围</span>
            <strong>{{ rangeLabel }}</strong>
          </article>
        </section>

        <div v-if="errorMessage" class="state-banner error" data-animate style="--delay: 0.12s">
          {{ errorMessage }}
        </div>

        <section class="rankings-grid" data-animate style="--delay: 0.15s">
          <RankingPanel
            title="实际美元用量榜"
            metric-label="实际用量"
            metric-kind="cost"
            :rows="leaderboard.cost_ranking"
            :loading="loading"
          />
          <RankingPanel
            title="Token 用量榜"
            metric-label="Tokens"
            metric-kind="tokens"
            :rows="leaderboard.token_ranking"
            :loading="loading"
          />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import Sidebar from '@/components/beta/Sidebar.vue'
import { usageApi } from '@/api/usage'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const periods = [
  { key: 'day', label: '1天' },
  { key: 'seven_days', label: '7天' },
  { key: 'year', label: '一年' },
  { key: 'all', label: '全部' },
]

const emptyLeaderboard = () => ({
  period: 'day',
  start_date: null,
  end_date: null,
  generated_at: null,
  total_actual_cost: 0,
  total_tokens: 0,
  total_requests: 0,
  cost_ranking: [],
  token_ranking: [],
})

const { activePage, handleNavigate, handleExit } = useBetaNavigation('leaderboard')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()
const selectedPeriod = ref('day')
const leaderboard = ref(emptyLeaderboard())
const loading = ref(false)
const errorMessage = ref('')

const userTimezone = computed(() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
})

const rangeLabel = computed(() => {
  if (!leaderboard.value.start_date) {
    return '全部'
  }
  return `${formatDate(leaderboard.value.start_date)} - ${formatDate(leaderboard.value.end_date)}`
})

async function loadLeaderboard() {
  loading.value = true
  errorMessage.value = ''
  try {
    leaderboard.value = await usageApi.getLeaderboard({
      period: selectedPeriod.value,
      limit: 50,
      timezone: userTimezone.value,
    })
  } catch (err) {
    errorMessage.value = err.message || '排行榜加载失败'
    leaderboard.value = emptyLeaderboard()
  } finally {
    loading.value = false
  }
}

function formatCurrency(value) {
  return `$${Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })}`
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

const RankingPanel = defineComponent({
  name: 'RankingPanel',
  props: {
    title: { type: String, required: true },
    metricLabel: { type: String, required: true },
    metricKind: { type: String, required: true },
    rows: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
  },
  setup(props) {
    const renderRows = () => {
      if (props.loading) {
        return h('div', { class: 'ranking-state' }, '加载中...')
      }
      if (!props.rows.length) {
        return h('div', { class: 'ranking-state' }, '暂无用量数据')
      }
      return h(
        'div',
        { class: 'ranking-list' },
        props.rows.map((row) =>
          h(
            'div',
            {
              class: ['ranking-row', { current: row.is_current_user }],
              key: `${props.metricKind}-${row.rank}-${row.display_name}`,
            },
            [
              h('span', { class: 'rank-number' }, row.rank),
              h('div', { class: 'rank-user' }, [
                h('strong', row.display_name || '用户'),
                row.is_current_user ? h('span', { class: 'current-badge' }, '我') : null,
              ]),
              h('div', { class: 'rank-metric' }, [
                h(
                  'strong',
                  props.metricKind === 'cost'
                    ? formatCurrency(row.actual_cost)
                    : formatNumber(row.tokens),
                ),
                h(
                  'span',
                  `${formatNumber(row.requests)} 次 · ${
                    props.metricKind === 'cost'
                      ? `${formatNumber(row.tokens)} tokens`
                      : formatCurrency(row.actual_cost)
                  }`,
                ),
              ]),
            ],
          ),
        ),
      )
    }

    return () =>
      h('article', { class: 'ranking-panel sa-card' }, [
        h('header', { class: 'ranking-header' }, [
          h('h2', props.title),
          h('span', props.metricLabel),
        ]),
        renderRows(),
      ])
  },
})

watch(selectedPeriod, () => {
  loadLeaderboard()
})

onMounted(() => {
  loadLeaderboard()
})
</script>

<style scoped>
.leaderboard-canvas {
  overflow-y: auto;
}

.period-control {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  background: #fff;
}

.period-btn {
  min-width: 58px;
  border: 0;
  background: transparent;
  color: #5d6b76;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  padding: 8px 12px;
}

.period-btn.active {
  background: #1b2730;
  color: #fff;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 24px;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 92px;
  padding: 18px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: #fdfcf9;
}

.summary-card span {
  color: #5d6b76;
  font-size: 12px;
  font-weight: 700;
}

.summary-card strong {
  color: #1b2730;
  font-size: 28px;
  line-height: 1;
}

.summary-card.subtle strong {
  font-size: 14px;
  line-height: 1.35;
}

.rankings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
}

.ranking-panel {
  border-radius: 8px;
  padding: 0;
  overflow: hidden;
}

.ranking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.08);
}

.ranking-header h2 {
  margin: 0;
  color: #1b2730;
  font-size: 15px;
  font-weight: 700;
}

.ranking-header span {
  color: #9eabb4;
  font-size: 12px;
  font-weight: 700;
}

.ranking-list {
  display: flex;
  flex-direction: column;
}

.ranking-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) minmax(150px, auto);
  gap: 12px;
  align-items: center;
  min-height: 66px;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
}

.ranking-row:last-child {
  border-bottom: 0;
}

.ranking-row.current {
  background: rgba(47, 143, 137, 0.08);
  box-shadow: inset 3px 0 0 #2f8f89;
}

.rank-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid rgba(28, 40, 52, 0.1);
  color: #5d6b76;
  font-size: 12px;
  font-weight: 800;
}

.rank-user {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.rank-user strong {
  overflow: hidden;
  color: #1b2730;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-badge {
  flex-shrink: 0;
  border: 1px solid rgba(47, 143, 137, 0.25);
  background: rgba(47, 143, 137, 0.12);
  color: #1f706c;
  font-size: 11px;
  font-weight: 800;
  padding: 2px 7px;
}

.rank-metric {
  min-width: 0;
  text-align: right;
}

.rank-metric strong {
  display: block;
  color: #1b2730;
  font-size: 15px;
}

.rank-metric span {
  display: block;
  margin-top: 3px;
  color: #9eabb4;
  font-size: 11px;
  white-space: nowrap;
}

.ranking-state {
  padding: 42px 20px;
  text-align: center;
  color: #9eabb4;
  font-size: 14px;
}

.state-banner {
  margin-top: 18px;
  padding: 12px 14px;
  border: 1px solid rgba(220, 38, 38, 0.18);
  background: rgba(220, 38, 38, 0.06);
  color: #b91c1c;
  font-size: 13px;
}

.btn-icon {
  width: 14px;
  height: 14px;
}

.spin {
  animation: leaderboard-spin 1s linear infinite;
}

@keyframes leaderboard-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .rankings-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .period-control {
    width: 100%;
  }

  .period-btn {
    flex: 1;
  }

  .ranking-row {
    grid-template-columns: 36px minmax(0, 1fr);
  }

  .rank-metric {
    grid-column: 2;
    text-align: left;
  }
}
</style>
