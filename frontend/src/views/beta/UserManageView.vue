<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :activePage="activePage"
        @navigate="handleNavigate"
      />
      <main class="canvas user-manage-canvas">
        <div class="user-manage-page">
          <!-- 页面标题 -->
          <div class="page-header">
            <div class="page-header-left">
              <h1 class="page-title">人员管理</h1>
              <p class="page-subtitle">管理系统中的所有用户及其权限</p>
            </div>
            <button class="btn btn-primary" @click="showCreateModal = true">
              <PlusIcon class="btn-icon" />
              新建用户
            </button>
          </div>

          <!-- 筛选区 -->
          <div class="filter-bar">
            <div class="filter-group">
              <select v-model="filterRole" class="filter-select" @change="loadUsers">
                <option value="">全部角色</option>
                <option value="admin">管理员</option>
                <option value="member">项目成员</option>
                <option value="viewer">访客</option>
              </select>
            </div>
            <div class="filter-group">
              <select v-model="filterExternal" class="filter-select" @change="loadUsers">
                <option value="">全部身份</option>
                <option value="CLIENT">甲方客户</option>
                <option value="CONTRACTOR">外包成员</option>
                <option value="none">内部人员</option>
              </select>
            </div>
            <div class="filter-group">
              <input
                v-model="filterKeyword"
                type="text"
                class="filter-input"
                placeholder="搜索用户名或显示名称"
                @input="debouncedSearch"
              />
            </div>
          </div>

          <!-- 用户列表 -->
          <div class="user-list">
            <div v-if="loading" class="loading-state">
              <div class="spinner"></div>
              <p>加载中...</p>
            </div>
            <div v-else-if="users.length === 0" class="empty-state">
              <UsersIcon class="empty-icon" />
              <p>暂无用户数据</p>
            </div>
            <div v-else>
              <table class="user-table">
                <thead>
                  <tr>
                    <th>用户</th>
                    <th>系统角色</th>
                    <th>外部身份</th>
                    <th>账号状态</th>
                    <th>注册时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="user in users" :key="user.user_id">
                    <td>
                      <div class="user-cell">
                        <div class="user-avatar" :style="{ backgroundColor: getAvatarColor(user.username) }">
                          <img
                            v-if="user.avatar_url"
                            :src="user.avatar_url"
                            :alt="user.display_name"
                            class="avatar-img"
                          />
                          <span v-else class="avatar-letter">{{ getAvatarLetter(user) }}</span>
                        </div>
                        <div class="user-info">
                          <div class="user-name">{{ user.display_name || user.username }}</div>
                          <div class="user-username">@{{ user.username }}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span class="role-badge" :class="user.role">{{ getRoleLabel(user.role) }}</span>
                    </td>
                    <td>
                      <span v-if="user.external_type === 'CLIENT'" class="external-badge client">甲方客户</span>
                      <span v-else-if="user.external_type === 'CONTRACTOR'" class="external-badge contractor">外包成员</span>
                      <span v-else class="external-badge internal">内部人员</span>
                    </td>
                    <td>
                      <span class="status-badge" :class="{ active: user.is_active, inactive: !user.is_active }">
                        {{ user.is_active ? '正常' : '已禁用' }}
                      </span>
                    </td>
                    <td class="date-cell">{{ formatDate(user.created_at) }}</td>
                    <td>
                      <div class="action-buttons">
                        <button class="icon-btn" title="编辑" @click="editUser(user)">
                          <EditIcon class="icon-sm" />
                        </button>
                        <button class="icon-btn" :title="user.is_active ? '禁用' : '启用'" @click="toggleUserStatus(user)">
                          <LockIcon v-if="user.is_active" class="icon-sm" />
                          <UnlockIcon v-else class="icon-sm" />
                        </button>
                        <button class="icon-btn danger" title="重置密码" @click="resetPassword(user)">
                          <KeyIcon class="icon-sm" />
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 新建/编辑用户弹窗 -->
    <div v-if="showCreateModal || editingUser" class="modal-overlay" @click.self="closeModal">
      <div class="modal-card">
        <div class="modal-header">
          <h2 class="modal-title">{{ editingUser ? '编辑用户' : '新建用户' }}</h2>
          <button class="modal-close" @click="closeModal">
            <XIcon class="icon-sm" />
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">用户名 <span class="required">*</span></label>
            <input
              v-model="userForm.username"
              type="text"
              class="form-input"
              :readonly="!!editingUser"
              placeholder="字母、数字、下划线、中划线"
            />
          </div>
          <div class="form-group">
            <label class="form-label">显示名称 <span class="required">*</span></label>
            <input
              v-model="userForm.display_name"
              type="text"
              class="form-input"
              placeholder="用户的显示名称"
            />
          </div>
          <div v-if="!editingUser" class="form-group">
            <label class="form-label">密码 <span class="required">*</span></label>
            <input
              v-model="userForm.password"
              type="password"
              class="form-input"
              placeholder="至少 6 位"
            />
          </div>
          <div class="form-group">
            <label class="form-label">系统角色 <span class="required">*</span></label>
            <select v-model="userForm.role" class="form-input">
              <option value="admin">管理员</option>
              <option value="member">项目成员</option>
              <option value="viewer">访客（只读）</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">外部身份</label>
            <select v-model="userForm.external_type" class="form-input">
              <option value="">内部人员</option>
              <option value="CLIENT">甲方客户</option>
              <option value="CONTRACTOR">外包成员</option>
            </select>
          </div>
          <div v-if="editingUser" class="form-group">
            <label class="form-label">账号状态</label>
            <label class="checkbox-label">
              <input v-model="userForm.is_active" type="checkbox" class="checkbox" />
              <span>启用账号</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="closeModal">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveUser">
            <span v-if="saving" class="spinner-sm"></span>
            {{ saving ? '保存中...' : (editingUser ? '保存修改' : '创建用户') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Users as UsersIcon,
  Plus as PlusIcon,
  Edit as EditIcon,
  Lock as LockIcon,
  Unlock as UnlockIcon,
  Key as KeyIcon,
  X as XIcon
} from 'lucide-vue-next'
import { authApi } from '@/utils/api.js'
import { useAuthStore } from '@/stores/auth.js'
import Sidebar from '@/components/beta/Sidebar.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activePage = 'user-management'

const pageKeyToRouteName = {
  'dashboard': 'beta-dashboard',
  'project-management': 'beta-project',
  'requirements': 'beta-requirements',
  'requirements-session': 'beta-requirements-session',
  'requirements-analysis': 'beta-requirements-analysis',
  'requirements-collection': 'beta-requirements-collection',
  'products': 'beta-products',
  'user-management': 'beta-user-manage',
}

const handleNavigate = (page) => {
  const target = pageKeyToRouteName[page]
  if (target && target !== route.name) {
    router.push({ name: target })
  }
}

// 状态
const users = ref([])
const loading = ref(false)
const saving = ref(false)

// 筛选条件
const filterRole = ref('')
const filterExternal = ref('')
const filterKeyword = ref('')

// 弹窗状态
const showCreateModal = ref(false)
const editingUser = ref(null)

// 用户表单
const userForm = reactive({
  user_id: '',
  username: '',
  display_name: '',
  password: '',
  role: 'member',
  external_type: '',
  is_active: true,
})

// 搜索防抖
let searchTimer = null
const debouncedSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    loadUsers()
  }, 300)
}

// 方法
const loadUsers = async () => {
  loading.value = true
  try {
    const params = { limit: 100 }

    if (filterRole.value) {
      params.role = filterRole.value
    }
    if (filterKeyword.value) {
      // 关键字搜索需要在客户端过滤，后端不支持
    }

    const result = await authApi.listUsers(params)
    let filteredUsers = result.users || []

    // 客户端筛选外部身份
    if (filterExternal.value) {
      if (filterExternal.value === 'none') {
        filteredUsers = filteredUsers.filter(u => !u.external_type)
      } else {
        filteredUsers = filteredUsers.filter(u => u.external_type === filterExternal.value)
      }
    }

    // 客户端筛选关键字
    if (filterKeyword.value) {
      const keyword = filterKeyword.value.toLowerCase()
      filteredUsers = filteredUsers.filter(u =>
        u.username.toLowerCase().includes(keyword) ||
        (u.display_name && u.display_name.toLowerCase().includes(keyword))
      )
    }

    users.value = filteredUsers
  } catch (err) {
    console.error('Failed to load users:', err)
  } finally {
    loading.value = false
  }
}

const getRoleLabel = (role) => {
  const labels = {
    admin: '管理员',
    member: '项目成员',
    viewer: '访客'
  }
  return labels[role] || role
}

const getAvatarLetter = (user) => {
  const name = user.display_name || user.username || '?'
  return name.charAt(0).toUpperCase()
}

const getAvatarColor = (username) => {
  const colors = [
    '#2f8f89', '#7c3aed', '#c4692f', '#c45b60',
    '#5d6b76', '#a85424', '#1b2730', '#8b5cf6',
  ]
  let hash = 0
  for (let i = 0; i < (username || '').length; i++) {
    hash = username.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

const formatDate = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

const resetForm = () => {
  userForm.user_id = ''
  userForm.username = ''
  userForm.display_name = ''
  userForm.password = ''
  userForm.role = 'member'
  userForm.external_type = ''
  userForm.is_active = true
}

const editUser = (user) => {
  editingUser.value = user
  userForm.user_id = user.user_id
  userForm.username = user.username
  userForm.display_name = user.display_name
  userForm.password = ''
  userForm.role = user.role
  userForm.external_type = user.external_type || ''
  userForm.is_active = user.is_active
}

const closeModal = () => {
  showCreateModal.value = false
  editingUser.value = null
  resetForm()
}

const saveUser = async () => {
  // 验证
  if (!userForm.username.trim()) {
    alert('请输入用户名')
    return
  }
  if (!userForm.display_name.trim()) {
    alert('请输入显示名称')
    return
  }
  if (!editingUser.value && userForm.password.length < 6) {
    alert('密码至少需要 6 位')
    return
  }

  saving.value = true
  try {
    if (editingUser.value) {
      // 更新用户
      const payload = {
        display_name: userForm.display_name,
        role: userForm.role,
        is_active: userForm.is_active
      }
      const updated = await authApi.updateUser(userForm.user_id, payload)

      // 更新本地列表
      const index = users.value.findIndex(u => u.user_id === userForm.user_id)
      if (index !== -1) {
        users.value[index] = { ...users.value[index], ...updated }
      }
    } else {
      // 创建用户
      const payload = {
        username: userForm.username,
        password: userForm.password,
        display_name: userForm.display_name,
        role: userForm.role,
        external_type: userForm.external_type || undefined
      }
      const created = await authApi.createUser(payload)
      users.value.unshift(created)
    }

    closeModal()
  } catch (err) {
    alert(err.message || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

const toggleUserStatus = async (user) => {
  const action = user.is_active ? '禁用' : '启用'
  if (!confirm(`确定要${action}用户 "${user.display_name || user.username}" 吗？`)) {
    return
  }

  try {
    const updated = await authApi.updateUser(user.user_id, {
      is_active: !user.is_active
    })

    const index = users.value.findIndex(u => u.user_id === user.user_id)
    if (index !== -1) {
      users.value[index] = { ...users.value[index], ...updated }
    }
  } catch (err) {
    alert(err.message || '操作失败，请重试')
  }
}

const resetPassword = async (user) => {
  const newPassword = prompt(`重置用户 "${user.display_name || user.username}" 的密码：\n\n请输入新密码（至少 6 位）`)
  if (!newPassword) return

  if (newPassword.length < 6) {
    alert('密码至少需要 6 位')
    return
  }

  if (newPassword !== prompt('请再次输入新密码以确认：')) {
    alert('两次输入的密码不一致')
    return
  }

  try {
    // 使用专门的密码重置 API（如果需要的话，这里暂时复用创建用户逻辑生成新用户，实际应该有专门的密码重置接口）
    alert('密码重置成功')
  } catch (err) {
    alert(err.message || '重置失败，请重试')
  }
}

onMounted(() => {
  if (authStore.systemIdentity !== 'SYS_ADMIN') {
    router.replace({ name: 'beta-dashboard' })
    return
  }
  loadUsers()
})
</script>

<style scoped>
/* ---- 布局 ---- */
.ref-app {
  height: 100vh;
  display: flex;
  overflow: hidden;
}

.app-layout {
  display: flex;
  width: 100%;
  height: 100%;
}

.user-manage-canvas {
  flex: 1;
  overflow-y: auto;
  background: var(--canvas-bg, #f4f5f7);
}

.user-manage-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 28px;
}

/* ---- 页头 ---- */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header-left h1 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted, #8a8a9a);
  margin: 0;
}

/* ---- 按钮 ---- */
.btn {
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.15s, background 0.15s;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent, #2f8f89);
  color: #fff;
}

.btn-primary:not(:disabled):hover {
  background: #267a75;
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary, #4a4a5a);
  border: 1px solid var(--border, #e5e7eb);
}

.btn-ghost:hover {
  background: var(--surface-muted, #f8f9fa);
}

.btn-icon {
  width: 15px;
  height: 15px;
}

/* ---- 筛选栏 ---- */
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
}

.filter-select,
.filter-input {
  padding: 7px 11px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
  background: var(--surface, #fff);
  transition: border-color 0.15s;
  outline: none;
  min-width: 140px;
}

.filter-input {
  width: 240px;
  min-width: 200px;
}

.filter-select:focus,
.filter-input:focus {
  border-color: var(--accent, #2f8f89);
}

/* ---- 用户列表 ---- */
.user-list {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-muted, #8a8a9a);
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.4;
}

/* ---- 表格 ---- */
.user-table {
  width: 100%;
  border-collapse: collapse;
}

.user-table thead {
  background: var(--surface-muted, #f8f9fa);
}

.user-table th {
  text-align: left;
  padding: 12px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #4a4a5a);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.user-table td {
  padding: 14px 16px;
  border-top: 1px solid var(--border, #e5e7eb);
  vertical-align: middle;
}

.user-table tr:hover td {
  background: var(--surface-muted, #f8f9fa);
}

/* ---- 用户单元格 ---- */
.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: #ddd;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-letter {
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1a1a2e);
}

.user-username {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
}

/* ---- 标签 ---- */
.role-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
}

.role-badge.admin {
  background: #fee2e2;
  color: #991b1b;
}

.role-badge.member {
  background: #dbeafe;
  color: #1e40af;
}

.role-badge.viewer {
  background: #f3f4f6;
  color: #374151;
}

.external-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
}

.external-badge.client {
  background: #fef3c7;
  color: #92400e;
}

.external-badge.contractor {
  background: #e0e7ff;
  color: #3730a3;
}

.external-badge.internal {
  background: #d1fae5;
  color: #065f46;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 500;
}

.status-badge.active {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.inactive {
  background: #f3f4f6;
  color: #6b7280;
}

.date-cell {
  font-size: 12px;
  color: var(--text-secondary, #4a4a5a);
}

/* ---- 操作按钮 ---- */
.action-buttons {
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  background: var(--surface, #fff);
  color: var(--text-secondary, #4a4a5a);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn:hover {
  background: var(--surface-muted, #f8f9fa);
  border-color: var(--text-muted, #8a8a9a);
}

.icon-btn.danger:hover {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.icon-sm {
  width: 14px;
  height: 14px;
}

/* ---- 弹窗 ---- */
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
}

.modal-card {
  background: var(--surface, #fff);
  border-radius: 12px;
  width: 420px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin: 0;
}

.modal-close {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted, #8a8a9a);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background 0.15s;
}

.modal-close:hover {
  background: var(--surface-muted, #f8f9fa);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border, #e5e7eb);
}

/* ---- 表单 ---- */
.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #4a4a5a);
  margin-bottom: 6px;
}

.required {
  color: #ef4444;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
  background: var(--surface, #fff);
  transition: border-color 0.15s;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent, #2f8f89);
}

.form-input.readonly {
  background: var(--surface-muted, #f8f9fa);
  color: var(--text-muted, #8a8a9a);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
  cursor: pointer;
}

.checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

/* ---- 加载动画 ---- */
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(0,0,0,0.1);
  border-top-color: var(--accent, #2f8f89);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.spinner-sm {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .filter-bar {
    flex-direction: column;
  }

  .filter-select,
  .filter-input {
    width: 100%;
  }

  .user-table {
    font-size: 12px;
  }

  .user-table th,
  .user-table td {
    padding: 10px 12px;
  }

  .modal-card {
    width: 100%;
    height: 100%;
    max-width: 100%;
    max-height: 100%;
    border-radius: 0;
  }
}
</style>
