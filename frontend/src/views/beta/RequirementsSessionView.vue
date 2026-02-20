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
            <span class="nav-title">项目管理 · 会话需求</span>
          </div>
          <div class="nav-center" style="gap: 8px; background: rgba(47, 143, 137, 0.06); padding: 6px 16px; border-radius: 4px; border: 1px solid rgba(47, 143, 137, 0.15);">
            <!-- 项目选择 -->
            <div class="session-indicator">
              <Briefcase class="w-3 h-3" />
              <span class="session-label">项目:</span>
              <select
                v-model="selectedProjectId"
                class="session-input"
                style="width: min(200px, 18vw); padding: 3px 6px;"
              >
                <option value="">未选择</option>
                <option v-for="p in projects" :key="p.project_id" :value="p.project_id">
                  {{ p.name }}
                </option>
              </select>
            </div>
            <!-- Session 输入 -->
            <div class="session-indicator">
              <Database class="w-3 h-3" />
              <span class="session-label">Session:</span>
              <input
                v-model="sessionIdDraft"
                type="text"
                class="session-input"
                placeholder="输入 Session ID"
                spellcheck="false"
                autocomplete="off"
                @keydown.enter.prevent="commitSessionId"
                @blur="commitSessionId"
              />
              <button
                v-if="sessionIdDraft"
                type="button"
                class="session-clear"
                title="清空 Session"
                @click="clearSessionId"
              >
                清空
              </button>
              <button
                v-if="sessionMismatch"
                type="button"
                class="session-clear"
                style="background: rgba(245,158,11,0.12); border-color: rgba(245,158,11,0.3); color: #d97706;"
                title="当前 Session 与项目绑定的不一致"
                @click="useProjectSession"
              >
                切换为项目Session
              </button>
            </div>
          </div>
          <div class="page-actions">
            <button
              type="button"
              class="action-btn white"
              :disabled="!selectedProjectId || !sessionId || isImportingToManage"
              @click="importSessionRequirementsToManage"
            >
              <Database class="w-4 h-4" :class="{ 'animate-pulse': isImportingToManage }" />
              {{ isImportingToManage ? '导入中...' : '导入到项目需求' }}
            </button>
            <button type="button" class="action-btn primary" @click="openAddRequirementModal" :disabled="!selectedProjectId">
              <Plus class="w-4 h-4" />
              新增需求
            </button>
            <button type="button" class="action-btn brown" @click="refreshData" :disabled="isLoading">
              <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
              {{ isLoading ? '加载中' : '刷新' }}
            </button>
          </div>
        </section>

        <!-- 新增需求弹窗 -->
        <div v-if="showAddRequirementModal" class="modal-overlay" @click.self="closeAddRequirementModal">
          <div class="modal-container">
            <div class="modal-header">
              <h3>新增需求</h3>
              <button type="button" class="modal-close" @click="closeAddRequirementModal">
                <X class="w-5 h-5" />
              </button>
            </div>
            <form class="modal-body" @submit.prevent="submitNewRequirement">
              <!-- 需求标题 -->
              <div class="form-group">
                <label class="form-label required">需求标题</label>
                <input
                  v-model="newRequirement.title"
                  type="text"
                  class="form-input"
                  placeholder="输入需求标题"
                  required
                />
              </div>

              <!-- 需求描述 -->
              <div class="form-group">
                <label class="form-label">需求描述</label>
                <textarea
                  v-model="newRequirement.description"
                  class="form-textarea"
                  placeholder="详细描述需求内容..."
                  rows="4"
                ></textarea>
              </div>

              <!-- 需求类型和层级 -->
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label required">需求类型</label>
                  <select v-model="newRequirement.requirement_type" class="form-select" required>
                    <option value="top_level">顶层需求</option>
                    <option value="low_level">底层需求</option>
                    <option value="task">任务</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">层级</label>
                  <select v-model="newRequirement.level" class="form-select">
                    <option value="L1">L1 - 业务需求</option>
                    <option value="L2">L2 - 利益相关者需求</option>
                    <option value="L3">L3 - 系统需求</option>
                    <option value="L4">L4 - 底层需求</option>
                  </select>
                </div>
              </div>

              <!-- 优先级和状态 -->
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">优先级</label>
                  <select v-model="newRequirement.priority" class="form-select">
                    <option value="high">高</option>
                    <option value="medium">中</option>
                    <option value="low">低</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">状态</label>
                  <select v-model="newRequirement.status" class="form-select">
                    <option value="draft">草稿</option>
                    <option value="under_review">审核中</option>
                    <option value="confirmed">已确认</option>
                    <option value="in_progress">进行中</option>
                    <option value="completed">已完成</option>
                  </select>
                </div>
              </div>

              <!-- 父需求（可选） -->
              <div class="form-group">
                <label class="form-label">父需求（可选）</label>
                <select v-model="newRequirement.parent_id" class="form-select">
                  <option value="">无</option>
                  <option v-for="req in parentRequirementOptions" :key="req.req_id" :value="req.req_id">
                    {{ req.title || req.text || req.statement || req.req_id }}
                  </option>
                </select>
              </div>

              <!-- 标签 -->
              <div class="form-group">
                <label class="form-label">标签（用逗号分隔）</label>
                <input
                  v-model="newRequirement.tags"
                  type="text"
                  class="form-input"
                  placeholder="例如: 功能, 性能, 安全"
                />
              </div>

              <!-- 操作按钮 -->
              <div class="modal-footer">
                <button type="button" class="action-btn secondary" @click="closeAddRequirementModal">
                  取消
                </button>
                <button type="submit" class="action-btn primary" :disabled="isSubmitting">
                  <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
                  {{ isSubmitting ? '提交中...' : '确认添加' }}
                </button>
              </div>
            </form>
          </div>
        </div>

        <!-- 编辑需求弹窗 -->
        <div v-if="showEditRequirementModal" class="modal-overlay" @click.self="closeEditRequirementModal">
          <div class="modal-container">
            <div class="modal-header">
              <h3>编辑需求</h3>
              <button type="button" class="modal-close" @click="closeEditRequirementModal">
                <X class="w-5 h-5" />
              </button>
            </div>
            <form class="modal-body" @submit.prevent="submitEditRequirement">
              <!-- 需求标题 -->
              <div class="form-group">
                <label class="form-label required">需求标题</label>
                <input
                  v-model="editRequirement.title"
                  type="text"
                  class="form-input"
                  placeholder="输入需求标题"
                  required
                />
              </div>

              <!-- 需求描述 -->
              <div class="form-group">
                <label class="form-label">需求描述</label>
                <textarea
                  v-model="editRequirement.description"
                  class="form-textarea"
                  placeholder="详细描述需求内容..."
                  rows="4"
                ></textarea>
              </div>

              <!-- 优先级和状态 -->
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">优先级</label>
                  <select v-model="editRequirement.priority" class="form-select">
                    <option value="high">高</option>
                    <option value="medium">中</option>
                    <option value="low">低</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">状态</label>
                  <select v-model="editRequirement.status" class="form-select">
                    <option value="draft">草稿</option>
                    <option value="under_review">审核中</option>
                    <option value="confirmed">已确认</option>
                    <option value="in_progress">进行中</option>
                    <option value="completed">已完成</option>
                  </select>
                </div>
              </div>

              <!-- 标签 -->
              <div class="form-group">
                <label class="form-label">标签（用逗号分隔）</label>
                <input
                  v-model="editRequirement.tags"
                  type="text"
                  class="form-input"
                  placeholder="例如: 功能, 性能, 安全"
                />
              </div>

              <!-- 操作按钮 -->
              <div class="modal-footer">
                <button type="button" class="action-btn secondary" @click="closeEditRequirementModal">
                  取消
                </button>
                <button type="submit" class="action-btn primary" :disabled="isEditSubmitting">
                  <Loader2 v-if="isEditSubmitting" class="w-4 h-4 animate-spin" />
                  {{ isEditSubmitting ? '保存中...' : '保存修改' }}
                </button>
              </div>
            </form>
          </div>
        </div>

        <!-- 筛选和视图切换区域 -->
        <section class="requirements-toolbar" data-animate style="--delay: 0.1s">
          <!-- 左侧: 层级筛选 -->
          <div class="level-tabs">
            <button
              v-for="tab in levelTabs"
              :key="tab.key"
              type="button"
              class="level-tab"
              :class="{ active: activeLevel === tab.key }"
              @click="activeLevel = tab.key"
            >
              {{ tab.label }}
              <span class="tab-count">{{ getCountByLevel(tab.key) }}</span>
            </button>
          </div>
          
          <!-- 右侧: 视图切换 -->
          <div class="view-switcher">
            <button
              type="button"
              class="view-btn"
              :class="{ active: activeView === 'tree' }"
              @click="activeView = 'tree'"
              title="树状视图"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 3v18M3 9l9-6 9 6M3 15l9 6 9-6" />
              </svg>
            </button>
            <button
              type="button"
              class="view-btn"
              :class="{ active: activeView === 'table' }"
              @click="activeView = 'table'"
              title="表格视图"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="3" y1="9" x2="21" y2="9" />
                <line x1="3" y1="15" x2="21" y2="15" />
                <line x1="9" y1="3" x2="9" y2="21" />
              </svg>
            </button>
            <button
              type="button"
              class="view-btn"
              :class="{ active: activeView === 'card' }"
              @click="activeView = 'card'"
              title="卡片视图"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
            </button>
          </div>
        </section>

        <!-- 内容区域 -->
        <section class="requirements-content" data-animate style="--delay: 0.15s">
          <!-- 加载状态 -->
          <div v-if="isLoading" class="loading-state">
            <Loader2 class="animate-spin" />
            <p>正在加载需求数据...</p>
          </div>

          <!-- 空状态 -->
          <div v-else-if="filteredRequirements.length === 0 && !isLoading" class="empty-state">
            <FileText class="empty-icon" />
            <p v-if="!sessionId">未选择 Session ID</p>
            <p v-else>暂无需求数据</p>
            <p class="empty-hint">
              {{ !sessionId ? '请先前往「需求分析」界面选择或输入 Session ID' : '请先在「需求分析」界面进行一键分析' }}
            </p>
            <button 
              v-if="!sessionId"
              type="button" 
              class="action-btn brown mt-4"
              @click="router.push({ name: 'beta-requirements-analysis' })"
            >
              前往需求分析
            </button>
          </div>

          <!-- 树状视图 -->
          <div v-else-if="activeView === 'tree'" class="tree-view-container">
            <RequirementTree 
              :tree-data="filteredTreeData" 
              @hover="handleNodeHover"
              @click-node="handleNodeClick"
            />
            <!-- 悬浮详情 -->
            <div v-if="hoveredNode" class="hover-detail-panel">
              <div class="detail-title">{{ hoveredNode.title || hoveredNode.text }}</div>
              <div class="detail-row">
                <span class="detail-label">类型:</span>
                <span class="detail-value">{{ getTypeLabel(hoveredNode.requirement_type) }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">状态:</span>
                <span class="detail-value">{{ hoveredNode.status || '-' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">优先级:</span>
                <span class="detail-value">{{ hoveredNode.priority || '-' }}</span>
              </div>
            </div>
          </div>

          <!-- 表格视图 -->
          <div v-else-if="activeView === 'table'" class="table-view-container">
            <!-- 工具栏 -->
            <div class="table-toolbar">
              <div class="table-search">
                <Search class="table-search-icon" />
                <input
                  v-model="tableSearchQuery"
                  type="text"
                  placeholder="搜索需求名称、层级、状态..."
                  class="table-search-input"
                />
              </div>
              <div class="table-column-config">
                <button
                  type="button"
                  class="column-config-btn"
                  @click="showColumnSelector = !showColumnSelector"
                >
                  <Filter class="w-4 h-4" />
                  设置展示列
                  <ChevronDown class="w-4 h-4 transition-transform" :class="showColumnSelector ? 'rotate-180' : ''" />
                </button>
                <div v-if="showColumnSelector" class="column-selector">
                  <div
                    v-for="col in availableTableColumns"
                    :key="col.key"
                    class="column-selector-item"
                    @click="toggleColumn(col.key)"
                  >
                    <div class="column-selector-check" :class="tableVisibleColumns.includes(col.key) ? 'checked' : ''">
                      <CheckCircle2 v-if="tableVisibleColumns.includes(col.key)" class="w-3 h-3" />
                    </div>
                    <span>{{ col.label }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 表格 -->
            <div class="table-scroll">
              <table class="requirements-table">
                <thead>
                  <tr>
                    <th
                      v-for="col in availableTableColumns.filter(c => tableVisibleColumns.includes(c.key))"
                      :key="col.key"
                      :class="col.width"
                      @click="toggleSort(col.key)"
                    >
                      <div class="th-content">
                        {{ col.label }}
                        <div class="sort-icons">
                          <ChevronUp class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'asc' ? 'active' : ''" />
                          <ChevronDown class="w-3 h-3" :class="tableSortKey === col.key && tableSortOrder === 'desc' ? 'active' : ''" />
                        </div>
                      </div>
                    </th>
                    <th class="w-16">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="req in tableRequirements" :key="req.id || req.req_id">
                    <td v-if="tableVisibleColumns.includes('name')">
                      <p class="cell-title">{{ req.title || req.text || req.statement }}</p>
                    </td>
                    <td v-if="tableVisibleColumns.includes('type')">
                      <span class="cell-type" :class="req.level === 'L4' ? 'type-low' : 'type-high'">
                        {{ req.level === 'L4' ? '底层需求' : '顶层需求' }}
                      </span>
                    </td>
                    <td v-if="tableVisibleColumns.includes('level')">
                      <span class="cell-level" :class="getLevelBadgeClass(req.level || req.category)">
                        {{ req.level || req.category || '-' }}
                      </span>
                    </td>
                    <td v-if="tableVisibleColumns.includes('status')">
                      <select
                        :value="req.status"
                        @change="updateRequirementStatus(req.id || req.req_id, $event.target.value)"
                        class="cell-status"
                        :class="getStatusColorClass(req.status, 'bg')"
                      >
                        <option v-for="s in requirementStatuses" :key="s.id" :value="s.id">
                          {{ s.name }}
                        </option>
                      </select>
                    </td>
                    <td v-if="tableVisibleColumns.includes('confidence')">
                      <span v-if="req.confidence" class="cell-confidence" :class="getConfidenceClass(req.confidence)">
                        {{ (req.confidence * 100).toFixed(0) }}%
                      </span>
                      <span v-else class="cell-muted">-</span>
                    </td>
                    <td v-if="tableVisibleColumns.includes('evidence')">
                      <span class="cell-truncate" :title="req.evidence || req.anchor_span_id">
                        {{ req.evidence || req.anchor_span_id || '-' }}
                      </span>
                    </td>
                    <td v-if="tableVisibleColumns.includes('rationale')">
                      <span class="cell-truncate" :title="req.rationale">
                        {{ req.rationale || '-' }}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        class="edit-btn"
                        title="编辑需求"
                        @click="openEditRequirementModal(req)"
                      >
                        <Pencil class="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                  <tr v-if="tableRequirements.length === 0">
                    <td :colspan="tableVisibleColumns.length + 1" class="table-empty">
                      暂无需求数据
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="table-footer">
              共 {{ tableRequirements.length }} 条
            </div>
          </div>

          <!-- 卡片视图（可拖动看板） -->
          <div v-else-if="activeView === 'card'" class="card-view-container">
            <div class="kanban-header">
              <span class="kanban-total">共 {{ filteredRequirements.length }} 条需求</span>
            </div>
            <div class="kanban-grid">
              <!-- 待处理列 -->
              <div class="kanban-column backlog-column">
                <div class="kanban-column-header backlog-header">
                  <div class="column-title-group">
                    <Circle class="column-status-icon" />
                    <h3>待处理</h3>
                  </div>
                  <span class="column-badge backlog-badge">{{ backlogRequirements.length }}</span>
                </div>
                <draggable
                  v-model="backlogRequirements"
                  :group="{ name: 'requirements', pull: true, put: true }"
                  item-key="id"
                  :animation="200"
                  class="kanban-column-content"
                  ghost-class="drag-ghost"
                  chosen-class="drag-chosen"
                  drag-class="drag-active"
                  @change="onDragChange($event, 'backlog')"
                >
                  <template #item="{ element }">
                    <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
                      <div class="card-drag-handle">
                        <GripVertical class="grip-icon" />
                      </div>
                      <div class="card-content">
                        <div class="card-tags">
                          <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                            {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                          </span>
                          <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                        <div class="card-meta">
                          <span class="card-id">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                          <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </template>
                </draggable>
                <div v-if="backlogRequirements.length === 0" class="kanban-empty">
                  拖拽需求到此处
                </div>
              </div>

              <!-- 进行中列 -->
              <div class="kanban-column progress-column">
                <div class="kanban-column-header progress-header">
                  <div class="column-title-group">
                    <Clock class="column-status-icon" />
                    <h3>进行中</h3>
                  </div>
                  <span class="column-badge progress-badge">{{ inProgressRequirements.length }}</span>
                </div>
                <draggable
                  v-model="inProgressRequirements"
                  :group="{ name: 'requirements', pull: true, put: true }"
                  item-key="id"
                  :animation="200"
                  class="kanban-column-content"
                  ghost-class="drag-ghost"
                  chosen-class="drag-chosen"
                  drag-class="drag-active"
                  @change="onDragChange($event, 'in_progress')"
                >
                  <template #item="{ element }">
                    <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
                      <div class="card-drag-handle">
                        <GripVertical class="grip-icon" />
                      </div>
                      <div class="card-content">
                        <div class="card-tags">
                          <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                            {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                          </span>
                          <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                        <div class="card-meta">
                          <span class="card-id">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                          <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </template>
                </draggable>
                <div v-if="inProgressRequirements.length === 0" class="kanban-empty">
                  拖拽需求到此处
                </div>
              </div>

              <!-- 已完成列 -->
              <div class="kanban-column completed-column">
                <div class="kanban-column-header completed-header">
                  <div class="column-title-group">
                    <CheckCircle class="column-status-icon" />
                    <h3>已完成</h3>
                  </div>
                  <span class="column-badge completed-badge">{{ completedRequirements.length }}</span>
                </div>
                <draggable
                  v-model="completedRequirements"
                  :group="{ name: 'requirements', pull: true, put: true }"
                  item-key="id"
                  :animation="200"
                  class="kanban-column-content"
                  ghost-class="drag-ghost"
                  chosen-class="drag-chosen"
                  drag-class="drag-active"
                  @change="onDragChange($event, 'completed')"
                >
                  <template #item="{ element }">
                    <div class="kanban-card" :class="element.level === 'L4' ? 'card-l4' : 'card-high'">
                      <div class="card-drag-handle">
                        <GripVertical class="grip-icon" />
                      </div>
                      <div class="card-content">
                        <div class="card-tags">
                          <span class="card-type-tag" :class="element.level === 'L4' ? 'type-low' : 'type-high'">
                            {{ element.level === 'L4' ? '底层需求' : '顶层需求' }}
                          </span>
                          <span class="card-level-tag" :class="getLevelBadgeClass(element.level)">
                            {{ element.level }}
                          </span>
                        </div>
                        <p class="card-statement">{{ element.statement || element.text || element.title }}</p>
                        <div class="card-meta">
                          <span class="card-id">"{{ (element.req_id || element.id || '').slice(0, 18) }}...</span>
                          <span v-if="element.confidence" class="card-confidence" :class="getConfidenceClass(element.confidence)">
                            {{ (element.confidence * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                  </template>
                </draggable>
                <div v-if="completedRequirements.length === 0" class="kanban-empty">
                  拖拽需求到此处
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import draggable from "vuedraggable";
import Sidebar from "../../components/beta/Sidebar.vue";
import RequirementTree from "../../components/charts/RequirementTree.vue";
import { requirementsL123Api, l4RequirementsApi, analysisApi, manageApi } from "../../utils/api";
import { Loader2, FileText, RefreshCw, Briefcase, Users, Layout, Layers, Database, Circle, Clock, CheckCircle, GripVertical, Search, Filter, ChevronDown, ChevronUp, CheckCircle2, Plus, X, Pencil } from "lucide-vue-next";

const router = useRouter();
const route = useRoute();

// 侧边栏状态
const roleType = ref("unified_admin");
const roleLabel = ref("管理员");
const timestamp = ref(new Date().toLocaleString());
const notificationCount = ref(3);
const routeNameToPageKey = {
  "beta-dashboard": "dashboard",
  "beta-products": "products",
  "beta-project": "project-management",
  "beta-requirements": "requirements",
  "beta-requirements-session": "requirements-session",
  "beta-requirements-analysis": "requirements-analysis",
  "beta-requirements-collection": "requirements-collection",
};

const pageKeyToRouteName = {
  "dashboard": "beta-dashboard",
  "products": "beta-products",
  "project-management": "beta-project",
  "requirements": "beta-requirements",
  "requirements-session": "beta-requirements-session",
  "requirements-analysis": "beta-requirements-analysis",
  "requirements-collection": "beta-requirements-collection",
};

const activePage = computed(() => routeNameToPageKey[route.name] || "requirements-session");

// 数据状态
const isLoading = ref(false);
const highLevelRequirements = ref([]);
const lowLevelRequirements = ref([]);
const requirementTree = ref([]);
const traceRelations = ref([]); // 追溯关系用于构建树
const selectedProjectId = ref(localStorage.getItem('lastProjectId') || '');
const manageReqIdMap = ref(new Map());
const manageStatusMap = ref(new Map());
const managePriorityMap = ref(new Map());
const isSyncingStatus = ref(false);
const isImportingToManage = ref(false);
const projects = ref([]);
const isLoadingProjects = ref(false);
const projectSessionId = ref(''); // 项目绑定的 session
const sessionMismatch = ref(false); // session 与项目不一致

// 新增需求相关状态
const showAddRequirementModal = ref(false);
const isSubmitting = ref(false);
const newRequirement = ref({
  title: '',
  description: '',
  requirement_type: 'top_level',
  level: 'L1',
  priority: 'medium',
  status: 'draft',
  parent_id: '',
  tags: ''
});

// 可选的父需求列表
const parentRequirementOptions = computed(() => {
  // 合并高层和低层需求作为可选父需求
  const all = [
    ...highLevelRequirements.value.map(r => ({
      req_id: r.req_id || r.id,
      title: r.text || r.statement || r.title,
      level: normalizeLevel(r.level || r.category)
    })),
    ...lowLevelRequirements.value.map(r => ({
      req_id: r.req_id || r.id,
      title: r.text || r.statement || r.shall_statement,
      level: 'L4'
    }))
  ];
  return all.filter(r => r.req_id);
});

// 打开新增需求弹窗
function openAddRequirementModal() {
  if (!selectedProjectId.value) {
    alert('请先选择项目');
    return;
  }
  // 重置表单
  newRequirement.value = {
    title: '',
    description: '',
    requirement_type: 'top_level',
    level: 'L1',
    priority: 'medium',
    status: 'draft',
    parent_id: '',
    tags: ''
  };
  showAddRequirementModal.value = true;
}

// 关闭新增需求弹窗
function closeAddRequirementModal() {
  showAddRequirementModal.value = false;
}

// 提交新增需求
async function submitNewRequirement() {
  if (!selectedProjectId.value) {
    alert('请先选择项目');
    return;
  }
  if (!newRequirement.value.title.trim()) {
    alert('请输入需求标题');
    return;
  }

  isSubmitting.value = true;
  try {
    const payload = {
      title: newRequirement.value.title.trim(),
      description: newRequirement.value.description.trim(),
      requirement_type: newRequirement.value.requirement_type,
      status: newRequirement.value.status,
      priority: normalizePriority(newRequirement.value.priority, 'medium'),
    };

    if (newRequirement.value.requirement_type === 'top_level') {
      payload.source_level = normalizeLevel(newRequirement.value.level || 'L1');
    } else if (newRequirement.value.requirement_type === 'low_level') {
      payload.source_level = 'L4';
    }

    // 可选字段
    if (newRequirement.value.parent_id) {
      payload.parent_id = newRequirement.value.parent_id;
    }
    if (newRequirement.value.tags.trim()) {
      payload.tags = newRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean);
    }

    await manageApi.createRequirement(selectedProjectId.value, payload);
    
    // 关闭弹窗并刷新数据
    closeAddRequirementModal();
    await loadRequirements();
    await loadManageRequirementMap();
    
  } catch (err) {
    console.error('新增需求失败:', err);
    alert('新增需求失败: ' + (err.message || '未知错误'));
  } finally {
    isSubmitting.value = false;
  }
}

// 编辑需求相关状态
const showEditRequirementModal = ref(false);
const isEditSubmitting = ref(false);
const editRequirementId = ref('');
const editRequirement = ref({
  title: '',
  description: '',
  priority: 'medium',
  status: 'draft',
  tags: ''
});

// 打开编辑需求弹窗
async function openEditRequirementModal(req) {
  if (!selectedProjectId.value) {
    alert('请先选择项目');
    return;
  }

  let reqId = resolveManageReqId(req);
  const hasManageEntry = manageReqIdMap.value.has(req.req_id || req.id);

  // 如果 manage_requirements 中没有对应记录，先自动导入
  if (!hasManageEntry && sessionId.value) {
    try {
      await manageApi.importFromSession(selectedProjectId.value, {
        session_id: sessionId.value,
        mapping_mode: 'tree'
      });
      await loadManageRequirementMap();
      reqId = resolveManageReqId(req);
    } catch (err) {
      console.warn('自动导入失败:', err);
    }
  }

  if (!reqId || !manageReqIdMap.value.has(req.req_id || req.id)) {
    alert('无法关联到项目需求，请确认项目和 Session 已正确绑定');
    return;
  }

  editRequirementId.value = reqId;
  const sourceKey = req.req_id || req.id;
  const mappedPriority = managePriorityMap.value.get(sourceKey) || managePriorityMap.value.get(reqId);
  editRequirement.value = {
    title: req.title || req.text || req.statement || '',
    description: req.description || '',
    priority: normalizePriority(mappedPriority ?? req.priority, 'medium'),
    status: req.status || 'draft',
    tags: Array.isArray(req.tags) ? req.tags.join(', ') : (req.tags || '')
  };
  showEditRequirementModal.value = true;
}

// 关闭编辑需求弹窗
function closeEditRequirementModal() {
  showEditRequirementModal.value = false;
  editRequirementId.value = '';
}

// 提交编辑需求
async function submitEditRequirement() {
  if (!editRequirementId.value) {
    alert('需求 ID 丢失');
    return;
  }
  if (!editRequirement.value.title.trim()) {
    alert('请输入需求标题');
    return;
  }

  isEditSubmitting.value = true;
  try {
    const payload = {
      title: editRequirement.value.title.trim(),
      description: editRequirement.value.description.trim(),
      priority: normalizePriority(editRequirement.value.priority, 'medium'),
      status: editRequirement.value.status,
    };

    if (editRequirement.value.tags.trim()) {
      payload.tags = editRequirement.value.tags.split(',').map(t => t.trim()).filter(Boolean);
    } else {
      payload.tags = [];
    }

    await manageApi.updateRequirement(editRequirementId.value, payload);

    closeEditRequirementModal();
    await loadRequirements();
    await loadManageRequirementMap();

  } catch (err) {
    console.error('编辑需求失败:', err);
    alert('编辑需求失败: ' + (err.message || '未知错误'));
  } finally {
    isEditSubmitting.value = false;
  }
}

async function loadProjects() {
  isLoadingProjects.value = true;
  try {
    const data = await manageApi.listProjects();
    projects.value = data?.projects || [];
  } catch (err) {
    console.warn('加载项目列表失败', err);
    projects.value = [];
  } finally {
    isLoadingProjects.value = false;
  }
}

async function loadProjectSession() {
  if (!selectedProjectId.value) {
    projectSessionId.value = '';
    sessionMismatch.value = false;
    return;
  }
  try {
    const proj = await manageApi.getProject(selectedProjectId.value);
    projectSessionId.value = proj?.current_session_id || '';
    checkSessionMismatch();
  } catch (err) {
    console.warn('加载项目 Session 失败', err);
  }
}

function checkSessionMismatch() {
  if (!selectedProjectId.value || !projectSessionId.value || !sessionId.value) {
    sessionMismatch.value = false;
    return;
  }
  sessionMismatch.value = sessionId.value !== projectSessionId.value;
}

function useProjectSession() {
  if (projectSessionId.value) {
    sessionIdDraft.value = projectSessionId.value;
    sessionId.value = projectSessionId.value;
    sessionMismatch.value = false;
  }
}

// 需求状态定义
const requirementStatuses = [
  { id: 'backlog', name: '待处理', color: 'zinc' },
  { id: 'in_progress', name: '进行中', color: 'blue' },
  { id: 'completed', name: '已完成', color: 'emerald' }
];

// 需求状态管理（卡片拖拽视图）
const requirementStatusMap = ref({}); // { reqId: 'backlog' | 'in_progress' | 'completed' }
const backlogRequirements = ref([]);
const inProgressRequirements = ref([]);
const completedRequirements = ref([]);

// 表格视图配置（复用原界面逻辑）
const tableSearchQuery = ref('');
const tableVisibleColumns = ref(['name', 'type', 'level', 'status', 'confidence', 'evidence']);
const tableSortKey = ref('name');
const tableSortOrder = ref('asc'); // 'asc' | 'desc'
const showColumnSelector = ref(false);

const availableTableColumns = [
  { key: 'name', label: '需求名称', width: 'flex-1 min-w-[280px]' },
  { key: 'type', label: '类型', width: 'w-24' },
  { key: 'level', label: '层级', width: 'w-20' },
  { key: 'status', label: '状态', width: 'w-28' },
  { key: 'confidence', label: '置信度', width: 'w-24' },
  { key: 'evidence', label: '证据', width: 'w-40' },
  { key: 'rationale', label: '原因', width: 'w-40' }
];

// 获取状态名称
function getStatusName(statusId) {
  const status = requirementStatuses.find(s => s.id === statusId);
  return status?.name || '待处理';
}

function getStatusColorClass(statusId, variant = 'bg') {
  const status = requirementStatuses.find(s => s.id === statusId);
  const color = status?.color || 'zinc';
  const colorMap = {
    zinc: { bg: 'bg-zinc-100', text: 'text-zinc-700', border: 'border-zinc-200', dot: 'bg-zinc-400' },
    blue: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200', dot: 'bg-blue-500' },
    emerald: { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' }
  };
  return colorMap[color]?.[variant] || colorMap.zinc[variant];
}

function mapManageStatusToLocal(status) {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'in_progress':
    case 'under_review':
    case 'confirmed':
      return 'in_progress';
    case 'archived':
      return 'completed';
    case 'draft':
    default:
      return 'backlog';
  }
}

function mapLocalStatusToManage(status) {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'in_progress':
      return 'in_progress';
    case 'backlog':
    default:
      return 'draft';
  }
}

async function ensureProjectId() {
  if (selectedProjectId.value) return;
  try {
    const data = await manageApi.listProjects();
    const projects = data?.projects || [];
    if (projects.length === 1) {
      selectedProjectId.value = projects[0].project_id;
      localStorage.setItem('lastProjectId', selectedProjectId.value);
    }
  } catch (err) {
    console.warn('加载项目列表失败，无法同步状态到数据库', err);
  }
}

async function loadManageRequirementMap() {
  if (!selectedProjectId.value) return;
  try {
    const data = await manageApi.listRequirements(selectedProjectId.value);
    const reqs = data?.requirements || [];
    const idMap = new Map();
    const statusMap = new Map();
    const priorityMap = new Map();

    reqs.forEach((req) => {
      if (req.req_id) {
        idMap.set(req.req_id, req.req_id);
        statusMap.set(req.req_id, req.status);
        priorityMap.set(req.req_id, normalizePriority(req.priority, null));
      }
      if (req.source_req_id) {
        idMap.set(req.source_req_id, req.req_id);
        statusMap.set(req.source_req_id, req.status);
        priorityMap.set(req.source_req_id, normalizePriority(req.priority, null));
      }
    });

    manageReqIdMap.value = idMap;
    manageStatusMap.value = statusMap;
    managePriorityMap.value = priorityMap;

    // 同步数据库状态到本地状态映射
    statusMap.forEach((status, key) => {
      requirementStatusMap.value[key] = mapManageStatusToLocal(status);
    });
  } catch (err) {
    console.warn('加载管理需求映射失败，状态同步将不可用', err);
  }
}

// 视图状态
const activeLevel = ref('all');
const activeView = ref('tree');
const hoveredNode = ref(null);

// Session ID (从localStorage获取，与需求分析界面同步)
const sessionId = ref(localStorage.getItem('lastSessionId') || '');
const sessionIdDraft = ref(sessionId.value);

function commitSessionId() {
  const next = String(sessionIdDraft.value || '').trim();
  sessionIdDraft.value = next;
  if (next === sessionId.value) return;
  sessionId.value = next;
}

async function importSessionRequirementsToManage() {
  commitSessionId();
  const sid = String(sessionId.value || "").trim();
  if (!selectedProjectId.value) {
    alert("请先选择要导入的项目");
    return;
  }
  if (!sid) {
    alert("请先输入 Session ID");
    return;
  }

  const targetProject = projects.value.find((p) => p.project_id === selectedProjectId.value);
  const projectLabel = targetProject?.name || selectedProjectId.value;
  const confirmed = window.confirm(
    `确认将 Session ${sid} 的需求导入到项目「${projectLabel}」吗？\n已存在的需求会自动跳过。`
  );
  if (!confirmed) return;

  isImportingToManage.value = true;
  try {
    const result = await manageApi.importFromSession(selectedProjectId.value, {
      session_id: sid,
      mapping_mode: "tree",
    });

    await loadManageRequirementMap();

    localStorage.setItem("lastProjectId", selectedProjectId.value);
    window.dispatchEvent(
      new CustomEvent("project-changed", { detail: { projectId: selectedProjectId.value } })
    );

    const inserted = Number(result?.inserted || 0);
    const insertedL123 = Number(result?.inserted_l123 || 0);
    const insertedL4 = Number(result?.inserted_l4 || 0);
    alert(`导入完成：新增 ${inserted} 条（L1-L3 ${insertedL123} 条，L4 ${insertedL4} 条）`);

    await router.push({
      name: "beta-requirements",
      query: { project_id: selectedProjectId.value },
    });
  } catch (err) {
    console.error("导入会话需求失败:", err);
    alert("导入失败: " + (err.message || "未知错误"));
  } finally {
    isImportingToManage.value = false;
  }
}

function syncProjectFromStorage() {
  const pid = localStorage.getItem('lastProjectId') || '';
  if (pid && pid !== selectedProjectId.value) {
    selectedProjectId.value = pid;
  }
}

function syncProjectFromLocation() {
  try {
    const url = new URL(window.location.href);
    const pid = (url.searchParams.get('project_id') || url.searchParams.get('projectId') || '').trim();
    if (pid && pid !== selectedProjectId.value) {
      selectedProjectId.value = pid;
      localStorage.setItem('lastProjectId', pid);
      window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: pid } }));
    }
  } catch (_) {
    // ignore
  }
}

function clearSessionId() {
  sessionIdDraft.value = '';
  if (sessionId.value) sessionId.value = '';
  localStorage.removeItem('lastSessionId');
}

// 监听 session-changed 事件（来自需求分析界面）
function handleSessionChanged(event) {
  const newSessionId = event.detail?.sessionId;
  if (newSessionId && newSessionId !== sessionId.value) {
    sessionId.value = newSessionId;
    sessionIdDraft.value = newSessionId;
    loadRequirements();
  }
}

// 监听 analysis-completed 事件（分析完成后刷新数据）
function handleAnalysisCompleted(event) {
  const eventSessionId = event.detail?.sessionId;
  if (eventSessionId && eventSessionId === sessionId.value) {
    // 当前 session 的分析完成，重新加载数据
    loadRequirements();
  }
}

// 监听项目切换
watch(selectedProjectId, async (val) => {
  if (val) {
    localStorage.setItem('lastProjectId', val);
    window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: val } }));
    await loadProjectSession();
    // 自动切换到项目 session
    if (projectSessionId.value && projectSessionId.value !== sessionId.value) {
      sessionId.value = projectSessionId.value;
      sessionIdDraft.value = projectSessionId.value;
    }
    // 切换项目后立刻刷新（确保需求数据/映射与项目一致）
    await loadRequirements();
  } else {
    projectSessionId.value = '';
    sessionMismatch.value = false;
    window.dispatchEvent(new CustomEvent('project-changed', { detail: { projectId: '' } }));
  }
});

// 监听 sessionId 变化
watch(sessionId, (newVal) => {
  if (newVal !== sessionIdDraft.value) {
    sessionIdDraft.value = newVal;
  }
  if (newVal && newVal.trim()) {
    localStorage.setItem('lastSessionId', newVal.trim());
    checkSessionMismatch();
    loadRequirements();
  }
});

// 层级标签配置
const levelTabs = [
  { key: 'all', label: '全部需求' },
  { key: 'L1', label: 'L1' },
  { key: 'L2', label: 'L2' },
  { key: 'L3', label: 'L3' },
  { key: 'L4', label: 'L4' },
];

// 计算属性：按层级筛选的需求（包含状态信息）
const filteredRequirements = computed(() => {
  let all = [
    ...highLevelRequirements.value.map(r => {
      const id = r.req_id || r.id;
      return {
        ...r,
        id,
        level: normalizeLevel(r.level || r.category),
        statement: r.text || r.statement || r.title || '',
        status: requirementStatusMap.value[id] || 'backlog',
      };
    }),
    ...lowLevelRequirements.value.map(r => {
      const id = r.req_id || r.id;
      return {
        ...r,
        id,
        level: 'L4',
        statement: r.text || r.statement || r.shall_statement || '',
        status: requirementStatusMap.value[id] || 'backlog',
      };
    }),
  ];
  
  if (activeLevel.value === 'all') {
    return all;
  }
  return all.filter(r => r.level === activeLevel.value);
});

// 表格视图的筛选/排序结果
const tableRequirements = computed(() => {
  let result = [...filteredRequirements.value];

  // 搜索筛选
  if (tableSearchQuery.value.trim()) {
    const query = tableSearchQuery.value.toLowerCase();
    result = result.filter(r =>
      (r.statement || r.text || r.title || '').toLowerCase().includes(query) ||
      (r.level || r.category || '').toLowerCase().includes(query) ||
      (getStatusName(r.status) || '').toLowerCase().includes(query)
    );
  }

  // 排序
  result.sort((a, b) => {
    let aVal = a[tableSortKey.value] || '';
    let bVal = b[tableSortKey.value] || '';
    if (tableSortKey.value === 'name') {
      aVal = a.statement || a.text || a.title || '';
      bVal = b.statement || b.text || b.title || '';
    }
    if (tableSortOrder.value === 'asc') {
      return String(aVal).localeCompare(String(bVal));
    }
    return String(bVal).localeCompare(String(aVal));
  });

  return result;
});

// 计算属性：筛选后的树形数据
const filteredTreeData = computed(() => {
  if (activeLevel.value === 'all') {
    return requirementTree.value;
  }
  // 根据层级过滤树
  return filterTreeByLevel(requirementTree.value, activeLevel.value);
});

// 卡片视图的列配置
const cardColumns = computed(() => {
  const l1Items = highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L1');
  const l2Items = highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L2');
  const l3Items = highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === 'L3');
  const l4Items = lowLevelRequirements.value;

  if (activeLevel.value !== 'all') {
    const levelMap = {
      L1: [{ id: 'L1', title: 'L1 业务需求', items: l1Items, icon: Briefcase, headerClass: 'header-l1', iconClass: 'icon-l1', badgeClass: 'badge-l1' }],
      L2: [{ id: 'L2', title: 'L2 利益相关者需求', items: l2Items, icon: Users, headerClass: 'header-l2', iconClass: 'icon-l2', badgeClass: 'badge-l2' }],
      L3: [{ id: 'L3', title: 'L3 系统需求', items: l3Items, icon: Layout, headerClass: 'header-l3', iconClass: 'icon-l3', badgeClass: 'badge-l3' }],
      L4: [{ id: 'L4', title: 'L4 底层需求', items: l4Items, icon: Layers, headerClass: 'header-l4', iconClass: 'icon-l4', badgeClass: 'badge-l4' }],
    };
    return levelMap[activeLevel.value] || [];
  }

  return [
    { id: 'L1', title: 'L1 业务需求', items: l1Items, icon: Briefcase, headerClass: 'header-l1', iconClass: 'icon-l1', badgeClass: 'badge-l1' },
    { id: 'L2', title: 'L2 利益相关者需求', items: l2Items, icon: Users, headerClass: 'header-l2', iconClass: 'icon-l2', badgeClass: 'badge-l2' },
    { id: 'L3', title: 'L3 系统需求', items: l3Items, icon: Layout, headerClass: 'header-l3', iconClass: 'icon-l3', badgeClass: 'badge-l3' },
    { id: 'L4', title: 'L4 底层需求', items: l4Items, icon: Layers, headerClass: 'header-l4', iconClass: 'icon-l4', badgeClass: 'badge-l4' },
  ];
});

// 辅助函数
function normalizeLevel(raw) {
  const text = String(raw || '').trim().toUpperCase();
  if (!text) return 'L1';
  if (text === '1' || text === 'L1' || text.includes('L1')) return 'L1';
  if (text === '2' || text === 'L2' || text.includes('L2')) return 'L2';
  if (text === '3' || text === 'L3' || text.includes('L3')) return 'L3';
  return 'L1';
}

function normalizePriority(raw, fallback = 'medium') {
  const text = String(raw ?? '').trim();
  if (!text) return fallback;
  const normalized = text.toLowerCase();
  return ['low', 'medium', 'high'].includes(normalized) ? normalized : fallback;
}

function filterTreeByLevel(nodes, level) {
  if (!nodes || nodes.length === 0) return [];
  return nodes.map(node => {
    const req = node.requirement || {};
    const nodeLevel = normalizeLevel(req.requirement_type || req.level || req.category);
    const children = filterTreeByLevel(node.children || [], level);
    
    if (nodeLevel === level || children.length > 0) {
      return { ...node, children };
    }
    return null;
  }).filter(n => n !== null);
}

function getCountByLevel(level) {
  if (level === 'all') {
    return highLevelRequirements.value.length + lowLevelRequirements.value.length;
  }
  if (level === 'L4') {
    return lowLevelRequirements.value.length;
  }
  return highLevelRequirements.value.filter(r => normalizeLevel(r.level || r.category) === level).length;
}

function getTypeLabel(type) {
  const labels = {
    'top_level': '顶层需求',
    'low_level': '底层需求',
    'task': '任务'
  };
  return labels[type] || type || '-';
}

function getLevelClass(level) {
  const classes = {
    'L1': 'level-l1',
    'L2': 'level-l2',
    'L3': 'level-l3',
    'L4': 'level-l4',
  };
  return classes[level] || '';
}

function getStatusClass(status) {
  if (!status || status === 'backlog') return 'status-pending';
  if (status === 'completed') return 'status-completed';
  if (status === 'in_progress') return 'status-active';
  // 兼容旧格式
  const s = status.toLowerCase();
  if (s.includes('complet') || s.includes('done') || s.includes('已完成')) return 'status-completed';
  if (s.includes('progress') || s.includes('active') || s.includes('进行中')) return 'status-active';
  return 'status-pending';
}

function getConfidenceClass(conf) {
  if (conf >= 0.8) return 'conf-high';
  if (conf >= 0.5) return 'conf-medium';
  return 'conf-low';
}

function toggleSort(key) {
  if (tableSortKey.value === key) {
    tableSortOrder.value = tableSortOrder.value === 'asc' ? 'desc' : 'asc';
  } else {
    tableSortKey.value = key;
    tableSortOrder.value = 'asc';
  }
}

function toggleColumn(key) {
  const idx = tableVisibleColumns.value.indexOf(key);
  if (idx >= 0) {
    tableVisibleColumns.value.splice(idx, 1);
  } else {
    tableVisibleColumns.value.push(key);
  }
}

function updateRequirementStatus(reqId, newStatus) {
  requirementStatusMap.value[reqId] = newStatus;
  persistStatusToDb({ id: reqId, req_id: reqId }, newStatus);
}

// 获取层级标签样式
function getLevelBadgeClass(level) {
  const map = {
    L1: 'bg-sky-100 text-sky-700 border-sky-200',
    L2: 'bg-violet-100 text-violet-700 border-violet-200',
    L3: 'bg-amber-100 text-amber-700 border-amber-200',
    L4: 'bg-emerald-100 text-emerald-700 border-emerald-200'
  };
  return map[level] || 'bg-zinc-100 text-zinc-700 border-zinc-200';
}

// 同步需求到各状态列表（从 filteredRequirements 读取，确保状态一致）
function syncRequirementLists() {
  const all = filteredRequirements.value;
  backlogRequirements.value = all.filter(r => r.status === 'backlog');
  inProgressRequirements.value = all.filter(r => r.status === 'in_progress');
  completedRequirements.value = all.filter(r => r.status === 'completed');
}

// 拖拽改变状态处理
function onDragChange(evt, targetStatus) {
  if (evt.added) {
    const item = evt.added.element;
    if (item && item.id) {
      requirementStatusMap.value[item.id] = targetStatus;
      persistStatusToDb(item, targetStatus);
    }
  }
}

function resolveManageReqId(item) {
  const candidates = [
    item.manage_req_id,
    item.req_id,
    item.id,
    item.source_req_id,
    item.source_top_id
  ].filter(Boolean);

  for (const key of candidates) {
    if (manageReqIdMap.value.has(key)) {
      return manageReqIdMap.value.get(key);
    }
  }
  return candidates[0] || '';
}

async function persistStatusToDb(item, targetStatus) {
  const manageReqId = resolveManageReqId(item);
  if (!manageReqId) return;
  const statusPayload = mapLocalStatusToManage(targetStatus);
  try {
    isSyncingStatus.value = true;
    await manageApi.updateRequirement(manageReqId, { status: statusPayload });
  } catch (err) {
    console.warn('同步状态到数据库失败', err);
  } finally {
    isSyncingStatus.value = false;
  }
}

// 监听需求变化，同步状态列表
watch([filteredRequirements, requirementStatusMap], () => {
  syncRequirementLists();
}, { deep: true, immediate: true });

// 事件处理
function handleNodeHover(req) {
  hoveredNode.value = req;
}

function handleNodeClick(req) {
  console.log('Clicked:', req);
}

function viewDetail(req) {
  console.log('View detail:', req);
}

async function refreshData() {
  await loadRequirements();
}

// 数据加载
async function loadRequirements() {
  const sid = sessionId.value?.trim();
  if (!sid) {
    highLevelRequirements.value = [];
    lowLevelRequirements.value = [];
    requirementTree.value = [];
    return;
  }
  
  isLoading.value = true;
  try {
    // 并行加载L1/L2/L3需求、L4需求和追溯关系
    const [l123Data, l4Data, traceData] = await Promise.all([
      requirementsL123Api.listBySession(sid, { page: 1, perPage: 500 }).catch(() => ({ requirements: [] })),
      l4RequirementsApi.getBySession(sid, { perPage: 500 }).catch(() => ({ requirements: [] })),
      analysisApi.getLatestTrace(sid).catch(() => null)
    ]);
    
    // 处理L1/L2/L3需求
    highLevelRequirements.value = (l123Data.requirements || []).map(req => ({
      ...req,
      priority: normalizePriority(req.priority, null),
      level: normalizeLevel(req.level || req.category),
    }));
    
    // 处理L4需求
    lowLevelRequirements.value = (l4Data.requirements || []).map(r => ({
      ...r,
      priority: normalizePriority(r.priority, null),
      level: 'L4',
      statement: r.text || r.shall_statement || r.statement || '',
    }));
    
    // 保存追溯关系
    traceRelations.value = traceData?.relations || [];
    
    // 构建树形结构（包含追溯关系）
    requirementTree.value = buildTreeWithRelations(
      highLevelRequirements.value,
      lowLevelRequirements.value,
      traceRelations.value
    );

    // 同步 manage_requirements 状态映射
    await ensureProjectId();
    await loadManageRequirementMap();
    
  } catch (err) {
    console.error('加载需求失败:', err);
  } finally {
    isLoading.value = false;
  }
}

// 基于 parent_id 和 source_top_id 构建树形结构
function buildTreeWithRelations(highReqs, lowReqs, relations) {
  // 创建所有需求的映射 (用于查找父节点)
  const allReqMap = new Map();
  
  // 处理高层需求
  highReqs.forEach((req, idx) => {
    const id = req.req_id || req.id || `high_${idx}`;
    allReqMap.set(id, {
      id,
      name: req.text || req.statement || req.title || `需求 ${idx + 1}`,
      requirement: { ...req, requirement_type: 'top_level' },
      requirement_type: 'top_level',
      level: normalizeLevel(req.level || req.category),
      parent_id: req.parent_id || null, // 高层需求的父子关系
      children: []
    });
  });
  
  // 处理低层需求 - 使用 parent_id 或 source_top_id 建立关系
  lowReqs.forEach((req, idx) => {
    const id = req.req_id || req.id || `low_${idx}`;
    const parentId = req.parent_id || req.source_top_id || null;
    
    allReqMap.set(id, {
      id,
      name: req.text || req.statement || req.shall_statement || `L4 需求 ${idx + 1}`,
      requirement: { ...req, requirement_type: 'low_level' },
      requirement_type: 'low_level',
      level: 'L4',
      parent_id: parentId,
      children: []
    });
  });
  
  // 如果有追溯关系，补充 parent_id 关系
  if (relations && relations.length > 0) {
    relations.forEach(rel => {
      if (!rel.has_relation) return;
      
      const lowIdx = rel.low_level_index;
      const highIdx = rel.high_level_index;
      
      if (lowIdx !== undefined && highIdx !== undefined) {
        const lowReq = lowReqs[lowIdx];
        const highReq = highReqs[highIdx];
        if (lowReq && highReq) {
          const lowId = lowReq.req_id || lowReq.id;
          const highId = highReq.req_id || highReq.id;
          
          const lowNode = allReqMap.get(lowId);
          // 只在没有 parent_id 时使用追溯关系
          if (lowNode && !lowNode.parent_id) {
            lowNode.parent_id = highId;
          }
        }
      }
    });
  }
  
  // 构建父子关系树
  const roots = [];
  const linkedIds = new Set();
  
  allReqMap.forEach((node, id) => {
    const parentId = node.parent_id;
    if (parentId && allReqMap.has(parentId)) {
      // 有父节点，添加到父节点的 children
      allReqMap.get(parentId).children.push(node);
      linkedIds.add(id);
    }
  });
  
  // 收集根节点（没有父节点或父节点不存在的）
  allReqMap.forEach((node, id) => {
    if (!linkedIds.has(id)) {
      roots.push(node);
    }
  });
  
  // 按层级排序根节点 (L1 > L2 > L3 > L4)
  const levelOrder = { 'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4 };
  roots.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5));
  
  // 递归排序子节点
  const sortChildren = (node) => {
    node.children.sort((a, b) => (levelOrder[a.level] || 5) - (levelOrder[b.level] || 5));
    node.children.forEach(sortChildren);
  };
  roots.forEach(sortChildren);
  
  return roots;
}

// 导航处理
function handleNavigate(page) {
  const target = pageKeyToRouteName[page];
  if (target && target !== route.name) {
    router.push({ name: target });
  }
}

function handleExit() {
  router.push({ name: "beta-login" });
}

onMounted(async () => {
  // 监听来自需求分析界面的事件
  window.addEventListener('session-changed', handleSessionChanged);
  window.addEventListener('analysis-completed', handleAnalysisCompleted);
  window.addEventListener('project-changed', syncProjectFromStorage);

  // 初始同步一次，避免刷新后浮窗与页面项目不一致
  syncProjectFromLocation();
  syncProjectFromStorage();

  // 加载项目列表
  await loadProjects();

  // 如果有项目，尝试从项目获取 session
  if (selectedProjectId.value) {
    await loadProjectSession();
    // 如果当前没有 session 但项目有，使用项目的 session
    if (!sessionId.value && projectSessionId.value) {
      sessionId.value = projectSessionId.value;
      sessionIdDraft.value = projectSessionId.value;
    } else {
      checkSessionMismatch();
    }
  }

  // 初始加载
  loadRequirements();
});

onUnmounted(() => {
  // 清理事件监听
  window.removeEventListener('session-changed', handleSessionChanged);
  window.removeEventListener('analysis-completed', handleAnalysisCompleted);
  window.removeEventListener('project-changed', syncProjectFromStorage);
});
</script>

<style scoped>
/* Session 指示器 */
.session-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(47, 143, 137, 0.1);
  border: 1px solid rgba(47, 143, 137, 0.2);
  font-size: 12px;
  color: #2f8f89;
}

.session-label {
  color: rgba(28, 40, 52, 0.6);
}

.session-id {
  font-family: monospace;
  font-weight: 500;
}

.session-input {
  width: min(520px, 42vw);
  padding: 4px 8px;
  font-size: 12px;
  font-family: monospace;
  border: 1px solid rgba(47, 143, 137, 0.25);
  background: rgba(255, 255, 255, 0.85);
  color: #134e4a;
  outline: none;
}

.session-input:focus {
  border-color: rgba(47, 143, 137, 0.55);
  box-shadow: 0 0 0 3px rgba(47, 143, 137, 0.12);
}

.session-clear {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid rgba(47, 143, 137, 0.25);
  background: rgba(255, 255, 255, 0.85);
  color: rgba(28, 40, 52, 0.7);
  cursor: pointer;
}

.session-clear:hover {
  color: rgba(28, 40, 52, 0.9);
  border-color: rgba(47, 143, 137, 0.45);
}

.jama-pill.warning {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
  color: #d97706;
}

/* 工具栏样式 */
.requirements-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  margin-bottom: 12px;
}

.level-tabs {
  display: flex;
  gap: 4px;
  background: rgba(28, 40, 52, 0.06);
  padding: 4px;
  border-radius: 0;
}

.level-tab {
  padding: 6px 12px;
  font-size: 13px;
  font-family: "BodyWithTimesDigits", "Noto Sans SC", sans-serif;
  background: transparent;
  border: none;
  color: rgba(28, 40, 52, 0.7);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-tab:hover {
  color: var(--ink-950);
}

.level-tab.active {
  background: rgba(255, 255, 255, 0.95);
  color: var(--ink-950);
  font-weight: 500;
}

.tab-count {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(28, 40, 52, 0.1);
  border-radius: 10px;
  color: rgba(28, 40, 52, 0.6);
}

.level-tab.active .tab-count {
  background: var(--accent);
  color: #fff;
}

.view-switcher {
  display: flex;
  gap: 4px;
  background: rgba(28, 40, 52, 0.06);
  padding: 4px;
}

.view-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  color: rgba(28, 40, 52, 0.5);
}

.view-btn:hover {
  color: var(--ink-950);
}

.view-btn.active {
  background: rgba(255, 255, 255, 0.95);
  color: var(--accent);
}

.view-btn svg {
  width: 18px;
  height: 18px;
}

/* 内容区域 */
.requirements-content {
  flex: 1;
  overflow: hidden;
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: rgba(28, 40, 52, 0.5);
}

.loading-state svg,
.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
  opacity: 0.3;
}

.empty-hint {
  font-size: 13px;
  margin-top: 8px;
  color: rgba(28, 40, 52, 0.4);
}

/* 树形视图 */
.tree-view-container {
  position: relative;
  padding: 20px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  min-height: 500px;
}

.hover-detail-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 260px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(28, 40, 52, 0.15);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-950);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 6px;
}

.detail-label {
  color: rgba(28, 40, 52, 0.6);
}

.detail-value {
  color: var(--ink-950);
  font-weight: 500;
}

/* 表格视图 */
.table-view-container {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(255, 255, 255, 0.95);
}

.table-search {
  position: relative;
  flex: 1;
  max-width: 360px;
}

.table-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  width: 14px;
  height: 14px;
  transform: translateY(-50%);
  color: rgba(28, 40, 52, 0.5);
}

.table-search-input {
  width: 100%;
  padding: 8px 12px 8px 32px;
  font-size: 12px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
}

.table-column-config {
  position: relative;
}

.column-config-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 12px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
  color: rgba(28, 40, 52, 0.8);
}

.column-selector {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  width: 200px;
  background: #fff;
  border: 1px solid rgba(28, 40, 52, 0.12);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
  z-index: 20;
  padding: 6px 0;
}

.column-selector-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.column-selector-item:hover {
  background: rgba(28, 40, 52, 0.04);
}

.column-selector-check {
  width: 14px;
  height: 14px;
  border: 1px solid rgba(28, 40, 52, 0.3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.column-selector-check.checked {
  background: #111;
  color: #fff;
  border-color: #111;
}

.table-scroll {
  flex: 1;
  overflow: auto;
}

.requirements-table {
  width: 100%;
  border-collapse: collapse;
}

.requirements-table thead th {
  position: sticky;
  top: 0;
  background: #f8f9fb;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(28, 40, 52, 0.6);
  padding: 10px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  cursor: pointer;
  text-align: left;
}

.requirements-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.06);
  font-size: 12px;
  color: rgba(28, 40, 52, 0.85);
}

.requirements-table tbody tr:hover {
  background: rgba(28, 40, 52, 0.02);
}

.th-content {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sort-icons {
  display: flex;
  flex-direction: column;
  margin-top: -2px;
}

.sort-icons .active {
  color: #111;
}

.cell-title {
  font-weight: 600;
  color: var(--ink-950);
}

.cell-type {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  border: 1px solid transparent;
}

.cell-type.type-high {
  background: rgba(14, 165, 233, 0.1);
  color: #0284c7;
  border-color: rgba(14, 165, 233, 0.2);
}

.cell-type.type-low {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
  border-color: rgba(16, 185, 129, 0.2);
}

.cell-level {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  border: 1px solid transparent;
}

.cell-status {
  padding: 4px 8px;
  font-size: 11px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  background: #fff;
}

.cell-confidence {
  padding: 2px 6px;
  font-size: 10px;
  border: 1px solid rgba(28, 40, 52, 0.1);
}

.cell-muted {
  color: rgba(28, 40, 52, 0.4);
}

.cell-truncate {
  display: inline-block;
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(28, 40, 52, 0.6);
}

.edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid rgba(28, 40, 52, 0.15);
  color: rgba(28, 40, 52, 0.5);
  cursor: pointer;
  transition: all 0.2s ease;
}

.edit-btn:hover {
  background: rgba(47, 143, 137, 0.08);
  border-color: rgba(47, 143, 137, 0.3);
  color: #2f8f89;
}

.table-empty {
  text-align: center;
  padding: 24px 12px;
  color: rgba(28, 40, 52, 0.45);
}

.table-footer {
  padding: 10px 16px;
  border-top: 1px solid rgba(28, 40, 52, 0.1);
  font-size: 12px;
  color: rgba(28, 40, 52, 0.6);
}

/* 卡片视图 - 可拖动看板 */
.card-view-container {
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.kanban-header {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.kanban-total {
  font-size: 12px;
  color: rgba(28, 40, 52, 0.6);
}

.kanban-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  padding: 20px;
  min-height: 0;
  overflow: hidden;
}

.kanban-column {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(28, 40, 52, 0.1);
  overflow: hidden;
  min-height: 400px;
}

.kanban-column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
}

.column-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.column-title-group h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--ink-950);
}

.column-status-icon {
  width: 16px;
  height: 16px;
}

.column-badge {
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 12px;
}

/* 待处理列 */
.backlog-column { background: rgba(250, 250, 250, 0.95); }
.backlog-header { background: rgba(244, 244, 245, 0.9); }
.backlog-header .column-status-icon { color: #71717a; }
.backlog-badge { background: rgba(113, 113, 122, 0.15); color: #52525b; }

/* 进行中列 */
.progress-column { background: rgba(239, 246, 255, 0.5); border-color: rgba(59, 130, 246, 0.2); }
.progress-header { background: rgba(219, 234, 254, 0.6); border-color: rgba(59, 130, 246, 0.2); }
.progress-header .column-status-icon { color: #2563eb; }
.progress-badge { background: rgba(59, 130, 246, 0.15); color: #1d4ed8; }

/* 已完成列 */
.completed-column { background: rgba(236, 253, 245, 0.5); border-color: rgba(16, 185, 129, 0.2); }
.completed-header { background: rgba(209, 250, 229, 0.6); border-color: rgba(16, 185, 129, 0.2); }
.completed-header .column-status-icon { color: #059669; }
.completed-badge { background: rgba(16, 185, 129, 0.15); color: #047857; }

.kanban-column-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.kanban-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(28, 40, 52, 0.35);
  font-size: 13px;
  border: 2px dashed rgba(28, 40, 52, 0.12);
  margin: 12px;
  border-radius: 0;
  min-height: 100px;
}

/* 卡片样式 */
.kanban-card {
  display: flex;
  background: #fff;
  border: 1px solid rgba(28, 40, 52, 0.12);
  transition: all 0.2s ease;
  cursor: grab;
}

.kanban-card:hover {
  border-color: rgba(28, 40, 52, 0.25);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.kanban-card:active {
  cursor: grabbing;
}

.kanban-card.card-high {
  border-left: 3px solid #0ea5e9;
}

.kanban-card.card-l4 {
  border-left: 3px solid #10b981;
}

.card-drag-handle {
  display: flex;
  align-items: center;
  padding: 8px 4px;
  background: rgba(28, 40, 52, 0.03);
  color: rgba(28, 40, 52, 0.3);
}

.card-drag-handle:hover {
  background: rgba(28, 40, 52, 0.06);
  color: rgba(28, 40, 52, 0.5);
}

.grip-icon {
  width: 14px;
  height: 14px;
}

.card-content {
  flex: 1;
  padding: 8px;
  min-width: 0;
}

.card-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.card-type-tag {
  font-size: 10px;
  padding: 2px 8px;
  font-weight: 500;
}

.card-type-tag.type-high {
  background: rgba(14, 165, 233, 0.12);
  color: #0284c7;
  border: 1px solid rgba(14, 165, 233, 0.25);
}

.card-type-tag.type-low {
  background: rgba(16, 185, 129, 0.12);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.card-level-tag {
  font-size: 10px;
  padding: 2px 8px;
  font-weight: 600;
  border: 1px solid;
}

.card-statement {
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-950);
  margin: 0 0 10px;
  word-break: break-word;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
}

.card-id {
  color: rgba(28, 40, 52, 0.4);
  font-family: monospace;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-confidence {
  padding: 2px 6px;
  border-radius: 0;
  border: 1px solid;
  font-weight: 500;
}

/* 拖拽状态样式 */
.drag-ghost {
  opacity: 0.5;
  background: rgba(196, 105, 47, 0.1) !important;
  border: 2px dashed var(--accent) !important;
}

.drag-chosen {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.drag-active {
  opacity: 0.9;
}

/* 置信度颜色 */
.conf-high { background: rgba(34, 197, 94, 0.1); color: #15803d; border-color: rgba(34, 197, 94, 0.3); }
.conf-medium { background: rgba(234, 179, 8, 0.1); color: #a16207; border-color: rgba(234, 179, 8, 0.3); }
.conf-low { background: rgba(239, 68, 68, 0.1); color: #b91c1c; border-color: rgba(239, 68, 68, 0.3); }

/* 自定义滚动条 */
.kanban-column-content::-webkit-scrollbar {
  width: 6px;
}
.kanban-column-content::-webkit-scrollbar-track {
  background: transparent;
}
.kanban-column-content::-webkit-scrollbar-thumb {
  background-color: rgba(28, 40, 52, 0.15);
  border-radius: 3px;
}
.kanban-column-content::-webkit-scrollbar-thumb:hover {
  background-color: rgba(28, 40, 52, 0.25);
}

/* 新增需求弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.modal-container {
  background: #fff;
  width: 90%;
  max-width: 560px;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid rgba(28, 40, 52, 0.15);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(28, 40, 52, 0.1);
  background: rgba(47, 143, 137, 0.05);
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ink-950);
}

.modal-close {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px;
  color: rgba(28, 40, 52, 0.5);
  transition: color 0.2s;
}

.modal-close:hover {
  color: rgba(28, 40, 52, 0.9);
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid rgba(28, 40, 52, 0.1);
}

/* 表单样式 */
.form-group {
  margin-bottom: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: rgba(28, 40, 52, 0.7);
  margin-bottom: 6px;
}

.form-label.required::after {
  content: ' *';
  color: #dc2626;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  border: 1px solid rgba(28, 40, 52, 0.2);
  background: #fff;
  color: var(--ink-950);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: rgba(47, 143, 137, 0.5);
  box-shadow: 0 0 0 3px rgba(47, 143, 137, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-select {
  cursor: pointer;
}

/* 按钮样式 */
.action-btn.primary {
  background: var(--accent);
  color: #fff;
  border: 1px solid var(--accent);
}

.action-btn.primary:hover:not(:disabled) {
  background: #1c6864;
  border-color: #1c6864;
}

.action-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.secondary {
  background: #fff;
  color: rgba(28, 40, 52, 0.8);
  border: 1px solid rgba(28, 40, 52, 0.2);
}

.action-btn.secondary:hover {
  background: rgba(28, 40, 52, 0.04);
  border-color: rgba(28, 40, 52, 0.3);
}
</style>


