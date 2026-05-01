<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar :activePage="activePage" @navigate="handleNavigate" />
      <main class="canvas user-manage-canvas">
        <div class="user-manage-page">
          <div class="page-header">
            <div>
              <h1 class="page-title">人员管理</h1>
              <p class="page-subtitle">
                {{ activeTab === 'users' ? '管理系统中的所有用户及其权限' : '审核注册申请并分配身份权限' }}
              </p>
            </div>
            <button v-if="activeTab === 'users'" class="btn btn-primary sa-button sa-button--primary" @click="showCreateModal = true">新建用户</button>
            <button v-else class="btn btn-ghost sa-button sa-button--secondary" :disabled="registrationsLoading" @click="refreshRegistrations">刷新申请</button>
          </div>

          <div class="tab-switcher">
            <button class="tab-btn" :class="{ active: activeTab === 'users' }" @click="switchTab('users')">用户列表</button>
            <button class="tab-btn" :class="{ active: activeTab === 'registrations' }" @click="switchTab('registrations')">
              注册申请
              <span v-if="pendingRegistrationCount > 0" class="pending-badge">{{ pendingRegistrationCount }}</span>
            </button>
          </div>

          <template v-if="activeTab === 'users'">
            <div class="filter-bar">
              <select v-model="filterRole" class="filter-input sa-input" @change="loadUsers">
                <option value="">全部角色</option>
                <option value="super_admin">高级管理员</option>
                <option value="admin">管理员</option>
                <option value="member">项目成员</option>
                <option value="viewer">访客</option>
              </select>
              <select v-model="filterExternal" class="filter-input sa-input" @change="loadUsers">
                <option value="">全部身份</option>
                <option value="CLIENT">甲方客户</option>
                <option value="CONTRACTOR">外包成员</option>
                <option value="none">内部人员</option>
              </select>
              <input v-model="filterKeyword" type="text" class="filter-input keyword sa-input" placeholder="搜索用户名或显示名称" @input="debouncedSearch" />
            </div>

            <div class="card sa-card">
              <div v-if="loading" class="state">加载中...</div>
              <div v-else-if="users.length === 0" class="state">暂无用户数据</div>
              <table v-else class="table">
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
                    <td>{{ user.display_name || user.username }}（@{{ user.username }}）</td>
                    <td>{{ getRoleLabel(user.role) }}</td>
                    <td>{{ getExternalLabel(user.external_type) }}</td>
                    <td>{{ user.is_active ? '正常' : '已禁用' }}</td>
                    <td>{{ formatDate(user.created_at) }}</td>
                    <td class="ops">
                      <button class="link-btn sa-button sa-button--secondary" :disabled="!canManageUser(user)" @click="openScopeModal(user)">范围权限</button>
                      <button class="link-btn sa-button sa-button--secondary" :disabled="!canManageUser(user)" @click="editUser(user)">编辑</button>
                      <button class="link-btn sa-button sa-button--secondary" :disabled="!canManageUser(user)" @click="toggleUserStatus(user)">{{ user.is_active ? '禁用' : '启用' }}</button>
                      <button class="link-btn sa-button sa-button--secondary" :disabled="!canManageUser(user)" @click="resetPassword(user)">重置密码</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>

          <template v-else>
            <div class="filter-bar">
              <select v-model="registrationStatusFilter" class="filter-input sa-input" @change="loadRegistrations">
                <option value="pending">待审批</option>
                <option value="approved">已通过</option>
                <option value="rejected">已拒绝</option>
              </select>
            </div>

            <div class="card sa-card">
              <div v-if="registrationsLoading" class="state">加载中...</div>
              <div v-else-if="registrations.length === 0" class="state">暂无注册申请</div>
              <table v-else class="table">
                <thead>
                  <tr>
                    <th>申请用户</th>
                    <th>申请状态</th>
                    <th>申请时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="registration in registrations" :key="registration.user_id">
                    <td>{{ registration.display_name || registration.username }}（@{{ registration.username }}）</td>
                    <td>{{ registrationStatusLabel(registration.registration_status) }}</td>
                    <td>{{ formatDate(registration.created_at) }}</td>
                    <td class="ops">
                      <template v-if="registration.registration_status === 'pending'">
                        <button class="link-btn ok sa-button sa-button--primary" @click="openApproveModal(registration)">通过</button>
                        <button class="link-btn danger sa-button sa-button--danger-secondary" @click="openRejectModal(registration)">拒绝</button>
                      </template>
                      <span v-else>已处理</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </main>
    </div>

    <div v-if="showCreateModal || editingUser" class="modal-overlay" @click.self="closeModal">
      <div class="modal-card sa-card">
        <div class="modal-header">
          <h2>{{ editingUser ? '编辑用户' : '新建用户' }}</h2>
          <button class="link-btn sa-button sa-button--secondary" @click="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户名 *</label>
            <input v-model="userForm.username" type="text" class="filter-input sa-input" :readonly="!!editingUser" />
          </div>
          <div class="form-group">
            <label>显示名称 *</label>
            <input v-model="userForm.display_name" type="text" class="filter-input sa-input" />
          </div>
          <div v-if="!editingUser" class="form-group">
            <label>密码 *</label>
            <input v-model="userForm.password" type="password" class="filter-input sa-input" />
          </div>
          <div class="form-group">
            <label>系统角色 *</label>
            <select v-model="userForm.role" class="filter-input sa-input">
              <option v-for="r in manageableRoleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>外部身份</label>
            <select v-model="userForm.external_type" class="filter-input sa-input">
              <option value="">内部人员</option>
              <option value="CLIENT">甲方客户</option>
              <option value="CONTRACTOR">外包成员</option>
            </select>
          </div>
          <div v-if="editingUser" class="form-group">
            <label><input v-model="userForm.is_active" type="checkbox" /> 启用账号</label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost sa-button sa-button--secondary" @click="closeModal">取消</button>
          <button class="btn btn-primary sa-button sa-button--primary" :disabled="saving" @click="saveUser">{{ saving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showApproveModal && selectedRegistration" class="modal-overlay" @click.self="closeApproveModal">
      <div class="modal-card sa-card">
        <div class="modal-header">
          <h2>通过注册申请</h2>
          <button class="link-btn sa-button sa-button--secondary" @click="closeApproveModal">关闭</button>
        </div>
        <div class="modal-body">
          <p>用户：{{ selectedRegistration.display_name || selectedRegistration.username }}</p>
          <div class="form-group">
            <label>系统角色 *</label>
            <select v-model="approvalForm.role" class="filter-input sa-input">
              <option v-for="r in manageableRoleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>外部身份</label>
            <select v-model="approvalForm.external_type" class="filter-input sa-input">
              <option value="">内部人员</option>
              <option value="CLIENT">甲方客户</option>
              <option value="CONTRACTOR">外包成员</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost sa-button sa-button--secondary" :disabled="registrationSaving" @click="closeApproveModal">取消</button>
          <button class="btn btn-primary sa-button sa-button--primary" :disabled="registrationSaving" @click="submitApproval">{{ registrationSaving ? '处理中...' : '确认通过' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showRejectModal && selectedRegistration" class="modal-overlay" @click.self="closeRejectModal">
      <div class="modal-card sa-card">
        <div class="modal-header">
          <h2>拒绝注册申请</h2>
          <button class="link-btn sa-button sa-button--secondary" @click="closeRejectModal">关闭</button>
        </div>
        <div class="modal-body">
          <p>用户：{{ selectedRegistration.display_name || selectedRegistration.username }}</p>
          <div class="form-group">
            <label>拒绝原因 *</label>
            <textarea v-model="rejectForm.reason" class="filter-input sa-input" rows="4" maxlength="500"></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost sa-button sa-button--secondary" :disabled="registrationSaving" @click="closeRejectModal">取消</button>
          <button class="btn btn-danger sa-button sa-button--danger" :disabled="registrationSaving" @click="submitRejection">{{ registrationSaving ? '处理中...' : '确认拒绝' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showScopeModal && selectedScopeUser" class="modal-overlay" @click.self="closeScopeModal">
      <div class="modal-card scope-modal sa-card">
        <div class="modal-header">
          <h2>范围权限配置 · {{ selectedScopeUser.display_name || selectedScopeUser.username }}</h2>
          <button class="link-btn sa-button sa-button--secondary" @click="closeScopeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div v-if="scopeLoading" class="state">加载中...</div>
          <template v-else>
            <p class="page-subtitle">产品授权会自动推导该产品下项目可见。项目授权用于补充或覆盖可编辑权限。</p>
            <div class="scope-section">
              <h3>产品范围</h3>
              <table class="table scope-table">
                <thead>
                  <tr>
                    <th>产品</th>
                    <th>可见</th>
                    <th>可编辑</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in scopeProducts" :key="item.product_id">
                    <td>{{ item.name }}</td>
                    <td><input v-model="item.visible" type="checkbox" /></td>
                    <td><input v-model="item.can_edit" type="checkbox" :disabled="!item.visible" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="scope-section">
              <h3>项目范围</h3>
              <table class="table scope-table">
                <thead>
                  <tr>
                    <th>项目</th>
                    <th>所属产品</th>
                    <th>可见</th>
                    <th>可编辑</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in scopeProjects" :key="item.project_id">
                    <td>{{ item.name }}</td>
                    <td>{{ item.product_name || '—' }}</td>
                    <td><input v-model="item.visible" type="checkbox" /></td>
                    <td><input v-model="item.can_edit" type="checkbox" :disabled="!item.visible" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost sa-button sa-button--secondary" :disabled="scopeSaving" @click="closeScopeModal">取消</button>
          <button class="btn btn-primary sa-button sa-button--primary" :disabled="scopeSaving || scopeLoading" @click="saveUserScopes">{{ scopeSaving ? '保存中...' : '保存配置' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Sidebar from '@/components/beta/Sidebar.vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth.js'
import { useBetaNavigation } from '@/composables/useBetaNavigation'

const router = useRouter()
const authStore = useAuthStore()

const { activePage, handleNavigate } = useBetaNavigation('user-management')
const activeTab = ref('users')

const users = ref([])
const loading = ref(false)
const saving = ref(false)
const filterRole = ref('')
const filterExternal = ref('')
const filterKeyword = ref('')
const showCreateModal = ref(false)
const editingUser = ref(null)
const showScopeModal = ref(false)
const selectedScopeUser = ref(null)
const scopeLoading = ref(false)
const scopeSaving = ref(false)
const scopeProducts = ref([])
const scopeProjects = ref([])
// Track programmatic updates to prevent infinite loops
const isUpdatingFromParent = ref(false)
const isUpdatingFromChild = ref(false)

const userForm = reactive({
  user_id: '',
  username: '',
  display_name: '',
  password: '',
  role: 'member',
  external_type: '',
  is_active: true,
})

const registrations = ref([])
const registrationStatusFilter = ref('pending')
const registrationsLoading = ref(false)
const registrationSaving = ref(false)
const pendingRegistrationCount = ref(0)
const showApproveModal = ref(false)
const showRejectModal = ref(false)
const selectedRegistration = ref(null)
const approvalForm = reactive({ role: 'member', external_type: '' })
const rejectForm = reactive({ reason: '' })

const manageableRoleOptions = computed(() => {
  const currentRole = authStore.user?.role
  if (currentRole === 'super_admin') {
    return [
      { value: 'admin', label: '管理员' },
      { value: 'member', label: '项目成员' },
      { value: 'viewer', label: '访客（只读）' },
    ]
  }
  return [
    { value: 'member', label: '项目成员' },
    { value: 'viewer', label: '访客（只读）' },
  ]
})

let searchTimer = null
const debouncedSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadUsers, 300)
}

const switchTab = (tab) => {
  activeTab.value = tab
  if (tab === 'users') loadUsers()
  else loadRegistrations()
}

const getRoleLabel = (role) => ({ super_admin: '高级管理员', admin: '管理员', member: '项目成员', viewer: '访客' }[role] || role)
const getExternalLabel = (externalType) => ({ CLIENT: '甲方客户', CONTRACTOR: '外包成员' }[externalType] || '内部人员')
const registrationStatusLabel = (status) => ({ pending: '待审批', approved: '已通过', rejected: '已拒绝' }[status] || status)
const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString('zh-CN') : '—')

const canManageUser = (targetUser) => {
  const operatorRole = authStore.user?.role
  const targetRole = targetUser?.role

  if (!operatorRole || !targetRole) return false
  if (targetRole === 'super_admin') return false
  if (operatorRole === 'super_admin') return ['admin', 'member', 'viewer'].includes(targetRole)
  if (operatorRole === 'admin') return ['member', 'viewer'].includes(targetRole)
  return false
}

const loadUsers = async () => {
  loading.value = true
  try {
    const params = { limit: 100 }
    if (filterRole.value) params.role = filterRole.value
    const result = await authApi.listUsers(params)
    let list = result.users || []
    if (filterExternal.value === 'none') list = list.filter((u) => !u.external_type)
    else if (filterExternal.value) list = list.filter((u) => u.external_type === filterExternal.value)
    if (filterKeyword.value) {
      const keyword = filterKeyword.value.toLowerCase()
      list = list.filter((u) => u.username.toLowerCase().includes(keyword) || (u.display_name || '').toLowerCase().includes(keyword))
    }
    users.value = list
  } catch (err) {
    console.error(err)
  } finally {
    loading.value = false
  }
}

const loadRegistrations = async () => {
  registrationsLoading.value = true
  try {
    const result = await authApi.listRegistrations({ status: registrationStatusFilter.value, limit: 200, offset: 0 })
    registrations.value = result.registrations || []
  } catch (err) {
    alert(err.message || '加载注册申请失败')
  } finally {
    registrationsLoading.value = false
  }
}

const loadPendingRegistrationCount = async () => {
  try {
    pendingRegistrationCount.value = await authApi.getPendingRegistrationCount()
  } catch (_) {
    pendingRegistrationCount.value = 0
  }
}

const refreshRegistrations = async () => {
  await Promise.all([loadRegistrations(), loadPendingRegistrationCount()])
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
  if (!userForm.username.trim() || !userForm.display_name.trim()) return alert('请补全用户信息')
  if (!editingUser.value && userForm.password.length < 6) return alert('密码至少需要 6 位')
  saving.value = true
  try {
    if (editingUser.value) {
      await authApi.updateUser(userForm.user_id, {
        display_name: userForm.display_name,
        role: userForm.role,
        is_active: userForm.is_active,
      })
    } else {
      await authApi.createUser({
        username: userForm.username,
        password: userForm.password,
        display_name: userForm.display_name,
        role: userForm.role,
        external_type: userForm.external_type || undefined,
      })
    }
    closeModal()
    await loadUsers()
  } catch (err) {
    alert(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const openScopeModal = async (user) => {
  if (!canManageUser(user)) return alert('无权限配置该用户范围')
  selectedScopeUser.value = user
  showScopeModal.value = true
  scopeLoading.value = true
  try {
    const [options, scopes] = await Promise.all([
      authApi.getScopeOptions(),
      authApi.getUserScopes(user.user_id),
    ])

    const productMap = new Map((scopes.product_scopes || []).map((item) => [item.product_id, item]))
    const projectMap = new Map((scopes.project_scopes || []).map((item) => [item.project_id, item]))
    const productNameMap = new Map((options.products || []).map((item) => [item.product_id, item.name]))

    scopeProducts.value = (options.products || []).map((item) => {
      const scoped = productMap.get(item.product_id)
      return {
        product_id: item.product_id,
        name: item.name,
        visible: !!scoped,
        can_edit: scoped ? !!scoped.can_edit : false,
      }
    })

    scopeProjects.value = (options.projects || []).map((item) => {
      const scoped = projectMap.get(item.project_id)
      return {
        project_id: item.project_id,
        name: item.name,
        product_id: item.product_id || '',
        product_name: item.product_id ? productNameMap.get(item.product_id) || '' : '',
        visible: !!scoped,
        can_edit: scoped ? !!scoped.can_edit : false,
      }
    })
  } catch (err) {
    alert(err.message || '加载范围配置失败')
    showScopeModal.value = false
  } finally {
    scopeLoading.value = false
  }
}

const closeScopeModal = () => {
  if (scopeSaving.value) return
  showScopeModal.value = false
  selectedScopeUser.value = null
  scopeProducts.value = []
  scopeProjects.value = []
}

// Watch for product visibility changes - cascade uncheck to child projects
watch(
  () => scopeProducts.value.map((p) => ({ id: p.product_id, visible: p.visible })),
  (newProducts, oldProducts) => {
    // Skip if this change came from a child update
    if (isUpdatingFromChild.value) return

    // Find products that changed from checked to unchecked
    const changes = newProducts.filter((newP, index) => {
      const oldP = oldProducts[index]
      return oldP && oldP.visible === true && newP.visible === false
    })

    // If any product was unchecked, uncheck all its projects
    if (changes.length > 0) {
      isUpdatingFromParent.value = true

      changes.forEach((changedProduct) => {
        scopeProjects.value.forEach((project) => {
          if (project.product_id === changedProduct.id) {
            project.visible = false
            project.can_edit = false
          }
        })
      })

      // Reset flag on next tick to allow future updates
      nextTick(() => {
        isUpdatingFromParent.value = false
      })
    }
  },
  { deep: true },
)

// Watch for project visibility changes - cascade check to parent product
watch(
  () => scopeProjects.value.map((p) => ({ id: p.project_id, productId: p.product_id, visible: p.visible })),
  (newProjects, oldProjects) => {
    // Skip if this change came from a parent update
    if (isUpdatingFromParent.value) return

    // Find projects that changed from unchecked to checked
    const changes = newProjects.filter((newP, index) => {
      const oldP = oldProjects[index]
      return oldP && oldP.visible === false && newP.visible === true
    })

    // If any project was checked, check its parent product
    if (changes.length > 0) {
      isUpdatingFromChild.value = true

      changes.forEach((changedProject) => {
        const parentProduct = scopeProducts.value.find((p) => p.product_id === changedProject.productId)
        if (parentProduct) {
          parentProduct.visible = true
        }
      })

      // Reset flag on next tick to allow future updates
      nextTick(() => {
        isUpdatingFromChild.value = false
      })
    }
  },
  { deep: true },
)

const saveUserScopes = async () => {
  if (!selectedScopeUser.value) return
  scopeSaving.value = true
  try {
    const payload = {
      product_scopes: scopeProducts.value
        .filter((item) => item.visible)
        .map((item) => ({ product_id: item.product_id, can_edit: !!item.can_edit })),
      project_scopes: scopeProjects.value
        .filter((item) => item.visible)
        .map((item) => ({ project_id: item.project_id, can_edit: !!item.can_edit })),
    }
    await authApi.updateUserScopes(selectedScopeUser.value.user_id, payload)
    closeScopeModal()
  } catch (err) {
    alert(err.message || '保存范围配置失败')
  } finally {
    scopeSaving.value = false
  }
}

const toggleUserStatus = async (user) => {
  if (!confirm(`确定要${user.is_active ? '禁用' : '启用'}用户 "${user.display_name || user.username}" 吗？`)) return
  try {
    await authApi.updateUser(user.user_id, { is_active: !user.is_active })
    await loadUsers()
  } catch (err) {
    alert(err.message || '操作失败')
  }
}

const resetPassword = async (user) => {
  const newPassword = prompt(`重置用户 "${user.display_name || user.username}" 的密码：\n\n请输入新密码（至少 6 位）`)
  if (!newPassword) return
  if (newPassword.length < 6) return alert('密码至少需要 6 位')
  if (newPassword !== prompt('请再次输入新密码以确认：')) return alert('两次输入的密码不一致')
  alert('当前后端未提供管理员重置密码接口，页面已保留交互入口')
}

const openApproveModal = (registration) => {
  selectedRegistration.value = registration
  approvalForm.role = 'member'
  approvalForm.external_type = ''
  showApproveModal.value = true
}

const closeApproveModal = () => {
  if (registrationSaving.value) return
  showApproveModal.value = false
  selectedRegistration.value = null
}

const submitApproval = async () => {
  if (!selectedRegistration.value) return
  registrationSaving.value = true
  try {
    await authApi.approveRegistration(selectedRegistration.value.user_id, {
      role: approvalForm.role,
      external_type: approvalForm.external_type || undefined,
    })
    closeApproveModal()
    await Promise.all([loadRegistrations(), loadPendingRegistrationCount(), loadUsers()])
  } catch (err) {
    alert(err.message || '审批失败')
  } finally {
    registrationSaving.value = false
  }
}

const openRejectModal = (registration) => {
  selectedRegistration.value = registration
  rejectForm.reason = ''
  showRejectModal.value = true
}

const closeRejectModal = () => {
  if (registrationSaving.value) return
  showRejectModal.value = false
  selectedRegistration.value = null
  rejectForm.reason = ''
}

const submitRejection = async () => {
  if (!selectedRegistration.value) return
  const reason = rejectForm.reason.trim()
  if (!reason) return alert('请填写拒绝原因')
  registrationSaving.value = true
  try {
    await authApi.rejectRegistration(selectedRegistration.value.user_id, reason)
    closeRejectModal()
    await Promise.all([loadRegistrations(), loadPendingRegistrationCount(), loadUsers()])
  } catch (err) {
    alert(err.message || '拒绝失败')
  } finally {
    registrationSaving.value = false
  }
}

onMounted(async () => {
  if (authStore.systemIdentity !== 'SYS_ADMIN') {
    router.replace({ name: 'beta-dashboard' })
    return
  }
  await Promise.all([loadUsers(), loadPendingRegistrationCount()])
})
</script>

<style scoped>
.ref-app,.app-layout{height:100%}
.app-layout{display:flex}
.user-manage-canvas{flex:1;overflow:auto;background:#f4f5f7}
.user-manage-page{max-width:1200px;margin:0 auto;padding:24px}
.page-header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.page-title{margin:0 0 6px;font-size:20px}
.page-subtitle{margin:0;color:#6b7280;font-size:13px}
.tab-switcher{display:flex;gap:8px;margin:16px 0}
.tab-btn{border:1px solid #d1d5db;background:#fff;border-radius:20px;padding:6px 12px;cursor:pointer}
.tab-btn.active{background:#2f8f89;color:#fff;border-color:#2f8f89}
.pending-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;border-radius:999px;background:#dc2626;color:#fff;font-size:11px;padding:0 5px}
.filter-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.filter-input{border:1px solid #d1d5db;border-radius:6px;padding:8px 10px;background:#fff}
.keyword{min-width:240px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}
.state{padding:40px;text-align:center;color:#6b7280}
.table{width:100%;border-collapse:collapse}
.table th,.table td{padding:12px;border-top:1px solid #e5e7eb;text-align:left}
.table th{background:#f8f9fa;border-top:none;font-size:12px;color:#4b5563}
.ops{display:flex;gap:10px;align-items:center}
.link-btn{border:none;background:transparent;color:#2563eb;cursor:pointer;padding:0}
.link-btn:disabled{color:#9ca3af;cursor:not-allowed}
.link-btn.ok{color:#047857}
.link-btn.danger{color:#dc2626}
.btn{border:none;border-radius:6px;padding:8px 12px;cursor:pointer}
.btn-primary{background:#2f8f89;color:#fff}
.btn-ghost{background:#fff;border:1px solid #d1d5db}
.btn-danger{background:#dc2626;color:#fff}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:1000}
.modal-card{width:420px;max-width:90vw;background:#fff;border-radius:10px;overflow:hidden}
.scope-modal{width:min(980px,96vw)}
.modal-header,.modal-footer{padding:14px 16px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center}
.modal-footer{border-bottom:none;border-top:1px solid #e5e7eb;justify-content:flex-end;gap:8px}
.modal-body{padding:14px 16px}
.form-group{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.scope-section{margin-top:14px}
.scope-section h3{margin:0 0 8px;font-size:14px}
.scope-table input[type='checkbox']{transform:scale(1.05)}
@media (max-width: 768px){.user-manage-page{padding:16px}.modal-card{width:100%;max-width:none;height:100%;border-radius:0}}
</style>
