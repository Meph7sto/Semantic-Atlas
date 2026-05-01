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
        <!-- Header -->
        <section class="page-header nav-style" data-animate style="--delay: 0.05s">
          <div class="nav-left">
            <span class="nav-title">评审管理 · 发布与处理</span>
          </div>
          <div class="nav-center">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              class="tab-btn"
              :class="{ active: activeTab === tab.key }"
              @click="activeTab = tab.key"
            >
              <component :is="tab.icon" class="tab-icon" />
              {{ tab.label }}
            </button>
          </div>
          <div class="page-actions">
            <button
              v-if="activeTab === 'publish'"
              type="button"
              class="action-btn brown sa-button sa-button--primary"
              @click="showCreateForm = true"
            >
              新建推送
            </button>
            <button type="button" class="action-btn ghost sa-button sa-button--secondary" @click="refreshData" :disabled="isLoading">
              <RefreshCw class="btn-icon" :class="{ 'spin': isLoading }" />
              刷新
            </button>
          </div>
        </section>

        <!-- Tab: 发布评审通知 -->
        <section v-if="activeTab === 'publish'" class="tab-content" data-animate style="--delay: 0.12s">
          <!-- Create Form -->
          <div v-if="showCreateForm" class="create-form-card">
            <h3 class="form-title">创建评审通知</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>消息类型</label>
                <select v-model="newMessage.message_type">
                  <option value="review">待审 (Review)</option>
                  <option value="change">变更 (Change)</option>
                </select>
              </div>
              <div class="form-group">
                <label>优先级</label>
                <select v-model="newMessage.priority">
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>标题 *</label>
              <input
                v-model="newMessage.title"
                type="text"
                placeholder="输入通知标题"
              />
            </div>
            <div class="form-group">
              <label>内容</label>
              <textarea
                v-model="newMessage.content"
                rows="3"
                placeholder="输入通知内容"
              ></textarea>
            </div>
            <!-- 推送对象 -->
            <div class="form-group">
              <label>推送对象 *</label>
              <div class="target-group-options">
                <label
                  v-for="group in targetGroupOptions"
                  :key="group.value"
                  class="target-checkbox"
                >
                  <input
                    type="checkbox"
                    :value="group.value"
                    v-model="newMessage.target_groups"
                  />
                  <span class="target-checkbox-label">{{ group.label }}</span>
                  <span class="target-checkbox-desc">{{ group.desc }}</span>
                </label>
              </div>
            </div>
            <div class="form-grid">
              <div class="form-group">
                <label>来源</label>
                <input
                  v-model="newMessage.source"
                  type="text"
                  placeholder="例：架构评审会议"
                />
              </div>
              <div class="form-group">
                <label>AI 建议</label>
                <input
                  v-model="newMessage.ai_suggestion"
                  type="text"
                  placeholder="例：低风险，合规"
                />
              </div>
            </div>
            <div class="form-actions">
              <button type="button" class="action-btn ghost sa-button sa-button--secondary" @click="showCreateForm = false">取消</button>
              <button
                type="button"
                class="action-btn brown sa-button sa-button--primary"
                :disabled="isCreating || !newMessage.title.trim() || newMessage.target_groups.length === 0"
                @click="handleCreateMessage"
              >
                创建
              </button>
            </div>
          </div>

          <!-- Filters -->
          <div class="filter-bar">
            <div class="filter-group">
              <label>类型：</label>
              <select v-model="filterType" @change="loadPushMessages">
                <option value="">全部</option>
                <option value="review">待审</option>
                <option value="change">变更</option>
              </select>
            </div>
            <div class="filter-group">
              <label>推送状态：</label>
              <select v-model="filterPushed" @change="loadPushMessages">
                <option value="">全部</option>
                <option value="false">未推送</option>
                <option value="true">已推送</option>
              </select>
            </div>
          </div>

          <!-- Messages List -->
          <div v-if="isLoading" class="loading-state">
            <RefreshCw class="spin loading-icon" />
          </div>
          <div v-else-if="pushMessages.length === 0" class="empty-state">
            暂无评审推送消息
          </div>
          <div v-else class="message-list">
            <div v-for="msg in pushMessages" :key="msg.message_id" class="message-card">
              <div class="message-body">
                <div class="message-tags">
                  <span class="tag" :class="msg.message_type === 'review' ? 'tag-review' : 'tag-change'">
                    {{ msg.message_type === 'review' ? '待审' : '变更' }}
                  </span>
                  <span class="tag" :class="priorityTagClass(msg.priority)">
                    {{ priorityLabel(msg.priority) }}
                  </span>
                  <span v-if="msg.pushed" class="tag tag-pushed">
                    <CheckCircle class="tag-icon" /> 已推送
                  </span>
                  <span v-else class="tag tag-pending">
                    <Clock class="tag-icon" /> 待推送
                  </span>
                </div>
                <h4 class="message-title">{{ msg.title }}</h4>
                <p v-if="msg.content" class="message-content">{{ msg.content }}</p>
                <!-- 推送对象标签 -->
                <div v-if="getTargetGroups(msg).length" class="message-targets">
                  <span class="target-label">推送对象：</span>
                  <span
                    v-for="g in getTargetGroups(msg)"
                    :key="g"
                    class="tag tag-target"
                  >{{ targetGroupLabel(g) }}</span>
                </div>
                <div class="message-meta">
                  <span v-if="msg.source">来源：{{ msg.source }}</span>
                  <span>创建：{{ formatTime(msg.created_at) }}</span>
                  <span v-if="msg.pushed_at">推送于：{{ formatTime(msg.pushed_at) }}</span>
                </div>
                <p v-if="msg.ai_suggestion" class="message-ai">
                  AI：{{ msg.ai_suggestion }}
                </p>
              </div>
              <div class="message-actions">
                <button
                  v-if="!msg.pushed"
                  type="button"
                  class="action-btn blue sa-button sa-button--primary"
                  @click="handlePushMessage(msg.message_id)"
                >
                  <Send class="btn-icon" /> 推送
                </button>
                <button
                  type="button"
                  class="action-btn danger-ghost sa-button sa-button--danger-secondary"
                  @click="handleDeleteMessage(msg.message_id)"
                >
                  <Trash2 class="btn-icon" />
                </button>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="totalPages > 1" class="pagination">
            <button
              type="button"
              :disabled="currentPage <= 1"
              @click="currentPage--; loadPushMessages()"
            >上一页</button>
            <span>{{ currentPage }} / {{ totalPages }}</span>
            <button
              type="button"
              :disabled="currentPage >= totalPages"
              @click="currentPage++; loadPushMessages()"
            >下一页</button>
          </div>
        </section>

        <!-- Tab: 处理评审 -->
        <section v-if="activeTab === 'process'" class="tab-content" data-animate style="--delay: 0.12s">
          <div v-if="isLoadingReviews" class="loading-state">
            <RefreshCw class="spin loading-icon" />
          </div>
          <div v-else-if="pendingReviews.length === 0" class="empty-state">
            暂无待处理评审
          </div>
          <div v-else class="review-list">
            <div v-for="review in pendingReviews" :key="review.id" class="review-card">
              <div class="review-header">
                <div class="review-info">
                  <h4>{{ review.requirement_title || '需求 #' + review.requirement_id }}</h4>
                  <div class="review-meta">
                    <span class="tag tag-pending">待审</span>
                    <span class="pill">第 {{ review.seq }} 轮</span>
                    <span class="pill" v-if="review.initiator_display_name || review.initiator_username">
                      发起人：{{ review.initiator_display_name || review.initiator_username }}
                    </span>
                    <span class="pill">创建：{{ formatTime(review.created_at) }}</span>
                    <span class="pill" v-if="review.project_id">项目：{{ review.project_id }}</span>
                  </div>
                </div>
              </div>
              <div v-if="review.comment" class="review-comment">
                <span class="comment-label">评审说明：</span>{{ review.comment }}
              </div>

              <!-- 审批操作区 -->
              <div class="review-action-area">
                <div v-if="expandedReview === review.id" class="review-input-area">
                  <textarea
                    v-model="reviewComment"
                    rows="2"
                    placeholder="输入审批意见（可选）"
                    class="review-textarea"
                  ></textarea>
                  <div class="review-btns">
                    <button
                      type="button"
                      class="action-btn green sa-button sa-button--primary"
                      :disabled="isProcessing"
                      @click="handleApprove(review.id)"
                    >
                      <CheckCircle class="btn-icon" /> 通过
                    </button>
                    <button
                      type="button"
                      class="action-btn red sa-button sa-button--danger"
                      :disabled="isProcessing"
                      @click="handleReject(review.id)"
                    >
                      <XCircle class="btn-icon" /> 驳回
                    </button>
                    <button
                      type="button"
                      class="action-btn ghost sa-button sa-button--secondary"
                      @click="expandedReview = null; reviewComment = ''"
                    >
                      取消
                    </button>
                  </div>
                </div>
                <div v-else class="review-btns">
                  <button
                    type="button"
                    class="action-btn brown sa-button sa-button--primary"
                    @click="expandedReview = review.id; reviewComment = ''"
                  >
                    处理评审
                  </button>
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
import { ref, onMounted } from 'vue'
import Sidebar from '@/components/beta/Sidebar.vue'
import { pushApi } from '@/api/system'
import { permissionApi } from '@/api/permission'
import {
  RefreshCw, Send, Trash2, CheckCircle, Clock, XCircle,
  Bell, ClipboardCheck, Users,
} from 'lucide-vue-next'
import { useBetaNavigation, useBetaSidebarProps } from '@/composables/useBetaNavigation'

const { activePage, handleNavigate, handleExit } = useBetaNavigation('reviews')
const { roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()

// ─── Tabs ───
const tabs = [
  { key: 'publish', label: '发布评审通知', icon: Bell },
  { key: 'process', label: '处理待审任务', icon: ClipboardCheck },
]
const activeTab = ref('publish')

// ─── 发布评审通知 (Push API) ───
const pushMessages = ref([])
const isLoading = ref(false)
const currentPage = ref(1)
const totalPages = ref(0)
const filterType = ref('')
const filterPushed = ref('')

const showCreateForm = ref(false)
const newMessage = ref(createEmptyMessage())
const isCreating = ref(false)

// ─── 推送对象分组 ───
const targetGroupOptions = [
  { value: 'project_members', label: '项目成员', desc: '当前项目的成员' },
  { value: 'admins', label: '管理员', desc: '系统管理员' },
  { value: 'all_project_group', label: '项目组所有成员', desc: '项目组内所有可见人员' },
]

function createEmptyMessage() {
  return {
    message_type: 'review',
    title: '',
    content: '',
    source: '',
    priority: 'medium',
    ai_suggestion: '',
    target_groups: ['project_members'],
  }
}

const loadPushMessages = async () => {
  isLoading.value = true
  try {
    const params = { page: currentPage.value, perPage: 20 }
    if (filterType.value) params.messageType = filterType.value
    if (filterPushed.value !== '') params.pushed = filterPushed.value === 'true'
    const result = await pushApi.listMessages(params)
    pushMessages.value = result.messages || []
    totalPages.value = result.pages || 0
  } catch (e) {
    console.error('加载推送消息失败', e)
    alert('加载推送消息失败: ' + e.message)
  } finally {
    isLoading.value = false
  }
}

const handleCreateMessage = async () => {
  if (!newMessage.value.title.trim()) {
    alert('请输入消息标题')
    return
  }
  isCreating.value = true
  try {
    const { target_groups, ...messageFields } = newMessage.value
    const payload = {
      ...messageFields,
      metadata: { target_groups },
    }
    await pushApi.createMessage(payload)
    newMessage.value = createEmptyMessage()
    showCreateForm.value = false
    await loadPushMessages()
  } catch (e) {
    console.error('创建消息失败', e)
    alert('创建消息失败: ' + e.message)
  } finally {
    isCreating.value = false
  }
}

const handlePushMessage = async (messageId) => {
  try {
    await pushApi.pushMessage(messageId)
    await loadPushMessages()
  } catch (e) {
    console.error('推送消息失败', e)
    alert('推送消息失败: ' + e.message)
  }
}

const handleDeleteMessage = async (messageId) => {
  if (!confirm('确定要删除此消息吗？')) return
  try {
    await pushApi.deleteMessage(messageId)
    await loadPushMessages()
  } catch (e) {
    console.error('删除消息失败', e)
    alert('删除消息失败: ' + e.message)
  }
}

// ─── 处理评审 (Permission API) ───
const pendingReviews = ref([])
const isLoadingReviews = ref(false)
const expandedReview = ref(null)
const reviewComment = ref('')
const isProcessing = ref(false)

const loadPendingReviews = async () => {
  isLoadingReviews.value = true
  try {
    const result = await permissionApi.getPendingReviews()
    pendingReviews.value = result || []
  } catch (e) {
    console.error('获取待处理评审失败', e)
    pendingReviews.value = []
  } finally {
    isLoadingReviews.value = false
  }
}

const handleApprove = async (assignmentId) => {
  isProcessing.value = true
  try {
    await permissionApi.approveReview(assignmentId, reviewComment.value || null)
    expandedReview.value = null
    reviewComment.value = ''
    await loadPendingReviews()
  } catch (e) {
    console.error('审批失败', e)
    alert('审批失败: ' + e.message)
  } finally {
    isProcessing.value = false
  }
}

const handleReject = async (assignmentId) => {
  isProcessing.value = true
  try {
    await permissionApi.rejectReview(assignmentId, reviewComment.value || null)
    expandedReview.value = null
    reviewComment.value = ''
    await loadPendingReviews()
  } catch (e) {
    console.error('驳回失败', e)
    alert('驳回失败: ' + e.message)
  } finally {
    isProcessing.value = false
  }
}

// ─── Utilities ───
const priorityLabel = (p) => {
  const map = { high: '高', medium: '中', low: '低' }
  return map[p] || p
}

const priorityTagClass = (p) => {
  const map = { high: 'tag-high', medium: 'tag-medium', low: 'tag-low' }
  return map[p] || ''
}

const getTargetGroups = (msg) => {
  const groups = msg?.metadata?.target_groups
  return Array.isArray(groups) ? groups : []
}

const targetGroupLabel = (value) => {
  const map = {
    project_members: '项目成员',
    admins: '管理员',
    all_project_group: '项目组所有成员',
  }
  return map[value] || value
}

const formatTime = (isoString) => {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const refreshData = () => {
  if (activeTab.value === 'publish') {
    loadPushMessages()
  } else {
    loadPendingReviews()
  }
}

// ─── Init ───
onMounted(() => {
  loadPushMessages()
  loadPendingReviews()
})
</script>

<style scoped>
/* ── Tabs ── */
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid rgba(28, 40, 52, 0.1);
  background: white;
  border-radius: 0;
  font-size: 13px;
  color: #5d6b76;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn.active {
  background: #1b2730;
  color: #fff;
  border-color: #1b2730;
}
.tab-icon {
  width: 14px;
  height: 14px;
}

/* ── Tab Content ── */
.tab-content {
  padding: 24px 0 0;
}

/* ── Action Buttons ── */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid rgba(28, 40, 52, 0.15);
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
  background: #fff;
  color: #5d6b76;
  transition: all 0.15s;
}
.action-btn.brown {
  background: var(--accent, #c4692f);
  color: #fff;
  border-color: var(--accent, #c4692f);
}
.action-btn.blue {
  background: #2563eb;
  color: #fff;
  border-color: #2563eb;
}
.action-btn.green {
  background: #16a34a;
  color: #fff;
  border-color: #16a34a;
}
.action-btn.red {
  background: #dc2626;
  color: #fff;
  border-color: #dc2626;
}
.action-btn.ghost {
  background: #fff;
}
.action-btn.danger-ghost {
  color: #9eabb4;
}
.action-btn.danger-ghost:hover {
  color: #dc2626;
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-icon {
  width: 14px;
  height: 14px;
}

/* ── Create Form ── */
.create-form-card {
  background: #fdfcf9;
  border: 1px solid rgba(28, 40, 52, 0.08);
  padding: 24px;
  margin-bottom: 20px;
}
.form-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #1b2730;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.form-group {
  margin-bottom: 12px;
}
.form-group label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #9eabb4;
  margin-bottom: 6px;
}
.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 0;
  font-size: 13px;
  color: #1b2730;
  background: #fff;
  outline: none;
  box-sizing: border-box;
}
.form-group textarea {
  resize: none;
}
.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  border-color: rgba(47, 143, 137, 0.5);
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

/* ── Filters ── */
.filter-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.filter-group label {
  font-size: 12px;
  color: #9eabb4;
}
.filter-group select {
  padding: 4px 8px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 0;
  font-size: 12px;
  color: #5d6b76;
  outline: none;
}

/* ── Loading / Empty ── */
.loading-state {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.loading-icon {
  width: 28px;
  height: 28px;
  color: #9eabb4;
}
.empty-state {
  text-align: center;
  padding: 48px 0;
  color: #9eabb4;
  font-size: 14px;
}

/* ── Push Message Cards ── */
.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  background: #fdfcf9;
  border: 1px solid rgba(28, 40, 52, 0.06);
  transition: box-shadow 0.15s;
}
.message-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}
.message-body {
  flex: 1;
  min-width: 0;
}
.message-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
}
.tag-icon {
  width: 12px;
  height: 12px;
}
.tag-review { background: #e0f2fe; color: #0369a1; }
.tag-change { background: #f3e8ff; color: #7c3aed; }
.tag-high { background: #fee2e2; color: #b91c1c; }
.tag-medium { background: #fef3c7; color: #92400e; }
.tag-low { background: #dcfce7; color: #166534; }
.tag-pushed { background: #dcece8; color: #5c8a82; }
.tag-pending { background: #efe6d5; color: #8e7d5e; }
.tag-target { background: #f0f4ff; color: #3b5998; border: 1px solid rgba(59, 89, 152, 0.15); }

/* ── Target Group Selection ── */
.target-group-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.target-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(28, 40, 52, 0.08);
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.target-checkbox:hover {
  border-color: rgba(47, 143, 137, 0.3);
  background: rgba(47, 143, 137, 0.02);
}
.target-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #2f8f89;
  flex-shrink: 0;
}
.target-checkbox-label {
  font-size: 13px;
  font-weight: 600;
  color: #1b2730;
}
.target-checkbox-desc {
  font-size: 11px;
  color: #9eabb4;
}

/* ── Message Targets ── */
.message-targets {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.target-label {
  font-size: 11px;
  color: #9eabb4;
  margin-right: 2px;
}

.message-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: #1b2730;
}
.message-content {
  margin: 0 0 6px;
  font-size: 13px;
  color: #5d6b76;
}
.message-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
  color: #9eabb4;
}
.message-ai {
  margin: 6px 0 0;
  font-size: 12px;
  color: #2563eb;
}
.message-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Pagination ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px 0;
  font-size: 13px;
  color: #5d6b76;
}
.pagination button {
  padding: 4px 12px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  background: #fff;
  border-radius: 0;
  font-size: 12px;
  cursor: pointer;
  color: #5d6b76;
}
.pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Review Cards ── */
.review-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.review-card {
  padding: 20px;
  background: #fdfcf9;
  border: 1px solid rgba(28, 40, 52, 0.06);
}
.review-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.review-info h4 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1b2730;
}
.review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.pill {
  border: 1px solid rgba(28, 40, 52, 0.1);
  padding: 2px 8px;
  font-size: 11px;
  color: #9eabb4;
}
.review-comment {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(47, 143, 137, 0.04);
  border-left: 3px solid rgba(47, 143, 137, 0.3);
  font-size: 13px;
  color: #5d6b76;
}
.comment-label {
  font-weight: 600;
  color: #1b2730;
}

/* ── Review Action Area ── */
.review-action-area {
  margin-top: 14px;
}
.review-input-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.review-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid rgba(28, 40, 52, 0.12);
  border-radius: 0;
  font-size: 13px;
  color: #1b2730;
  resize: none;
  outline: none;
  box-sizing: border-box;
}
.review-textarea:focus {
  border-color: rgba(47, 143, 137, 0.5);
}
.review-btns {
  display: flex;
  gap: 8px;
}

/* ── Spin animation ── */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.spin {
  animation: spin 1s linear infinite;
}

@media (max-width: 800px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
  .filter-bar {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
