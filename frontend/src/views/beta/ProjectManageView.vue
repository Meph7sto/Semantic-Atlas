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
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">项目管理 · 项目内容（Explorer）</span>
          </div>
          <div class="nav-center">
            <span class="jama-pill">Jama 思路：先 Project，再 Explorer Tree</span>
          </div>
          <div class="page-actions">
            <button type="button" class="action-btn brown sa-button sa-button--primary">新建条目</button>
            <button type="button" class="action-btn white sa-button sa-button--secondary">导入</button>
            <button type="button" class="action-btn white sa-button sa-button--secondary">发起评审</button>
            <button type="button" class="action-btn white sa-button sa-button--secondary">创建基线</button>
            <span class="nav-text">通知 · 3</span>
          </div>
        </section>

        <section class="grid split-layout" data-animate style="--delay: 0.12s">
          <!-- Left Column: Explorer Tree -->
          <div class="card sa-card">
            <div class="card-header no-border">
              <div>
                <p class="card-kicker">Project Content</p>
                <h2 class="section-title">Explorer Tree (项目结构)</h2>
              </div>
              <button type="button" class="ghost-small square sa-button sa-button--secondary">+ 文件夹</button>
            </div>

            <div class="form-group">
              <input type="text" placeholder="搜索文件夹/条目（原型）" class="search-input full-width sa-input" />
            </div>

            <div class="tree-list">
              <div class="tree-item">
                <span class="tree-toggle">-</span>
                <span class="tree-icon">📂</span>
                <span class="tree-label">项目总览</span>
                <span class="chip-neutral small">All</span>
              </div>
              <div class="tree-item">
                <span class="tree-toggle">+</span>
                <span class="tree-icon">📂</span>
                <span class="tree-label">系统需求</span>
                <span class="chip-neutral small">342</span>
              </div>
              <div class="tree-item active">
                <span class="tree-toggle">-</span>
                <span class="tree-icon">📂</span>
                <span class="tree-label">测试资产</span>
                <span class="chip-neutral small">214</span>
              </div>
              <!-- Sub Items -->
              <div class="tree-sub-list">
                <div class="tree-item sub">
                  <span class="tree-icon">📊</span>
                  <span class="tree-label">测试计划</span>
                  <span class="chip-neutral small">12</span>
                </div>
                <div class="tree-item sub selected">
                  <span class="tree-icon">📝</span>
                  <span class="tree-label">测试用例</span>
                  <span class="chip-neutral small">202</span>
                </div>
              </div>

              <div class="tree-item">
                <span class="tree-toggle">-</span>
                <span class="tree-icon">📂</span>
                <span class="tree-label">风险与合规</span>
                <span class="chip-neutral small">56</span>
              </div>
              <div class="tree-item">
                <span class="tree-toggle">+</span>
                <span class="tree-icon">📂</span>
                <span class="tree-label">架构与接口</span>
                <span class="chip-neutral small">98</span>
              </div>
            </div>
          </div>

          <!-- Right Column: Items List -->
          <div class="card sa-card">
            <div class="card-header no-border">
              <div>
                <p class="card-kicker">Items</p>
                <h2 class="section-title">条目列表（按类型筛选）</h2>
              </div>
              <button type="button" class="ghost-small square sa-button sa-button--secondary">批量操作</button>
            </div>

            <div class="filter-bar">
              <select class="select-clean sa-input">
                <option>全部类型 (All Item Types)</option>
              </select>
              <select class="select-clean sa-input">
                <option>全部状态</option>
              </select>
            </div>

            <div class="search-legend-bar">
              <input type="text" placeholder="搜索标题 / ID / 关键词（原型）" class="search-input flex-grow sa-input" />
              <div class="legend-group">
                <span class="legend-item"><span class="dot approved"></span>已批准</span>
                <span class="legend-item"><span class="dot review"></span>待评审</span>
                <span class="legend-item"><span class="dot block"></span>阻塞</span>
              </div>
            </div>

            <div class="data-table">
              <div class="table-header">
                <span>标题</span>
                <span>类型</span>
                <span>状态</span>
                <span>负责人</span>
                <span>更新</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>REQ-0012 · 支持基线冻结：发布候选需满足门禁条件</strong>
                </div>
                <span>需求</span>
                <span><span class="status-pill review">待评审</span></span>
                <span>User A</span>
                <span>2 小时前</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>REQ-0007 · 提供追踪视图：支持上游/下游影响分析</strong>
                </div>
                <span>需求</span>
                <span><span class="status-pill approved">已批准</span></span>
                <span>User B</span>
                <span>昨天</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>TC-0201 · 验证：基线候选未通过门禁时禁止发布</strong>
                </div>
                <span>测试用例</span>
                <span><span class="status-pill draft">草稿</span></span>
                <span>QA-1</span>
                <span>4 天前</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>RISK-0003 · 潜在冲突：两条需求目标互斥导致实现不可行</strong>
                </div>
                <span>风险</span>
                <span><span class="status-pill block">阻塞</span></span>
                <span>Owner?</span>
                <span>1 天前</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>REG-0011 · 法规条款：审计应提供可追溯变更记录与签核证据</strong>
                </div>
                <span>法规条款</span>
                <span><span class="status-pill review">待评审</span></span>
                <span>Compliance</span>
                <span>3 天前</span>
              </div>

              <div class="table-row">
                <div class="cell-main">
                  <strong>API-0044 · 接口规格：/items/{id} 需返回追踪链接与审计字段</strong>
                </div>
                <span>接口规格</span>
                <span><span class="status-pill approved">已批准</span></span>
                <span>API Team</span>
                <span>上周</span>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import Sidebar from "../../components/beta/Sidebar.vue";
import { useBetaNavigation, useBetaSidebarProps } from "@/composables/useBetaNavigation";

const { activePage, handleNavigate, handleExit } = useBetaNavigation("project-management");
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps();
</script>
