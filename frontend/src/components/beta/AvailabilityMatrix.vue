<template>
  <div class="card my-work-card">
    <div class="card-header full-header">
      <div class="header-main">
        <p class="card-kicker">My Work</p>
        <h2>我的工作台</h2>
        <p class="header-desc">概览页最关键的是把「人要做的事」放到最短路径：待办、待审、被@、需要补齐的条目。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="filter-btn active">只看我负责</button>
        <button type="button" class="filter-btn">只看今天到期</button>
        <button type="button" class="filter-text">自定义</button>
      </div>
    </div>

    <div class="work-grid">
      <!-- Left Column: My To-do -->
      <div class="work-column">
        <h3 class="column-title">我的待办（To-do）</h3>

        <div class="task-card">
          <div class="task-header">
            <h4>补齐关键字段：验收口径缺失（3 项）</h4>
            <span class="status-tag pending">待补齐</span>
          </div>
          <div class="task-meta">
            <span class="pill">来源：门禁</span>
            <span class="pill">截止：今天 18:00</span>
            <span class="pill highlight">优先级：P1</span>
          </div>
          <div class="task-actions">
            <button class="btn-primary">立即处理</button>
            <button class="btn-ghost">查看详情</button>
          </div>
        </div>

        <div class="task-card">
          <div class="task-header">
            <h4>回答澄清：术语定义不一致（2 条）</h4>
            <span class="status-tag block">阻塞</span>
          </div>
          <div class="task-meta">
            <span class="pill">来源：Q&A</span>
            <span class="pill">责任：你</span>
            <span class="pill item-warn">超时：1 天</span>
          </div>
          <div class="task-actions">
            <button class="btn-primary">去回答</button>
            <button class="btn-ghost">分派</button>
          </div>
        </div>

        <div class="task-card">
          <div class="task-header">
            <h4>更新追踪链接：上游变更影响待确认</h4>
            <span class="status-tag confirm">待确认</span>
          </div>
          <div class="task-meta">
            <span class="pill">来源：变更</span>
            <span class="pill">影响链：4 节点</span>
            <span class="pill">建议：做影响分析</span>
          </div>
          <div class="task-actions">
            <button class="btn-ghost">打开追踪</button>
            <button class="btn-ghost">标记完成</button>
          </div>
        </div>
      </div>

      <!-- Right Column: My Reviews -->
      <div class="work-column">
        <h3 class="column-title">我参与的评审（My Reviews）</h3>

        <div class="task-card">
          <div class="task-header">
            <h4>评审：接口需求（第 2 轮）</h4>
            <span class="status-tag pending">待审</span>
          </div>
          <div class="task-meta">
            <span class="pill">到期：明天</span>
            <span class="pill">参与：5 人</span>
          </div>
          <div class="task-actions">
            <button class="btn-primary">进入评审</button>
            <button class="btn-ghost">评论</button>
          </div>
        </div>

        <div class="task-card">
          <div class="task-header">
            <h4>评审：安全与合规条款</h4>
            <span class="status-tag ok">已提交意见</span>
          </div>
          <div class="task-meta">
            <span class="pill">状态：等待决议</span>
            <span class="pill">@你：1</span>
          </div>
          <div class="task-actions">
            <button class="btn-ghost">查看差异</button>
            <button class="btn-ghost">跟进</button>
          </div>
        </div>

        <div class="task-card">
          <div class="task-header">
            <h4>评审：版本发布候选（Baseline Candidate）</h4>
            <span class="status-tag confirm">需确认</span>
          </div>
          <div class="task-meta">
            <span class="pill">差异：28</span>
            <span class="pill">风险：3</span>
          </div>
          <div class="task-actions">
            <button class="btn-primary">快速批准</button>
            <button class="btn-ghost">请求修改</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.my-work-card {
  padding: 32px;
  background: white;
  border-radius: 0;
}

.full-header {
  display: flex !important;
  flex-direction: row;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 30px;
  border-bottom: 1px solid rgba(28,40,52,0.06);
  padding-bottom: 20px;
}

.header-main h2 {
  font-size: 28px;
  margin: 4px 0 10px;
  font-family: serif;
}

.header-desc {
  font-size: 13px;
  color: #9eabb4;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-btn {
  padding: 6px 16px;
  border: 1px solid rgba(28,40,52,0.1);
  background: white;
  border-radius: 0;
  font-size: 12px;
  color: #5d6b76;
  cursor: pointer;
}
.filter-btn.active {
  background: white;
  border-color: #5d6b76;
  color: #1b2730;
}
.filter-text {
  background: none;
  border: none;
  color: #9eabb4;
  font-size: 12px;
  cursor: pointer;
}

.work-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

.column-title {
  font-size: 16px;
  font-weight: bold;
  font-family: serif;
  margin-bottom: 20px;
  color: #1b2730;
}

.task-card {
  background: #fdfcf9;
  border: 1px solid rgba(28,40,52,0.05);
  border-radius: 0;
  padding: 20px;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.task-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #23323d;
  line-height: 1.4;
}

.status-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 0;
  white-space: nowrap;
  background: #eee;
}
.status-tag.pending { background: #efe6d5; color: #8e7d5e; }
.status-tag.block { background: #ebd5d5; color: #9c5e5e; }
.status-tag.confirm { background: #efe6d5; color: #8e7d5e; }
.status-tag.ok { background: #dcece8; color: #5c8a82; }

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  border: 1px solid rgba(28,40,52,0.1);
  padding: 2px 8px;
  border-radius: 0;
  font-size: 11px;
  color: #9eabb4;
}
.pill.highlight { color: #1b2730; border-color: #1b2730; }
.pill.item-warn { background: #fff5f5; color: #c45b60; border-color: #f0c9ca; }

.task-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.btn-primary {
  background: var(--accent);
  color: white;
  border: none;
  padding: 6px 16px;
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
}
.btn-ghost {
  background: white;
  border: 1px solid rgba(28, 40, 52, 0.2);
  color: #5d6b76;
  padding: 6px 16px;
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
}

@media (max-width: 800px) {
  .work-grid {
    grid-template-columns: 1fr;
  }
}
</style>
