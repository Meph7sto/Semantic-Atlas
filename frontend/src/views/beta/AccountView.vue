<template>
  <div class="ref-app">
    <div class="app-layout">
      <Sidebar
        :activePage="activePage"
        @navigate="handleNavigate"
      />
      <main class="canvas account-canvas">
        <div class="account-page">
          <!-- 页面标题 -->
          <div class="page-header">
            <h1 class="page-title">个人账户</h1>
            <p class="page-subtitle">管理您的个人信息和安全设置</p>
          </div>

          <div class="account-content">
            <!-- 左侧：用户信息卡片 -->
            <div class="avatar-card card">
              <div class="avatar-area">
                <div class="avatar-wrap">
                  <img
                    v-if="profile.avatar_url"
                    :src="profile.avatar_url"
                    :alt="profile.display_name"
                    class="avatar-img"
                    @error="onAvatarError"
                  />
                  <div v-else class="avatar-letter" :style="{ backgroundColor: avatarColor }">
                    {{ avatarLetter }}
                  </div>
                </div>
                <div class="avatar-info">
                  <div class="avatar-name">{{ profile.display_name || profile.username }}</div>
                  <div class="avatar-role">{{ roleLabel }}</div>
                </div>
              </div>

              <div class="divider" />

              <div class="meta-list">
                <div class="meta-item">
                  <span class="meta-label">用户名</span>
                  <span class="meta-value mono">{{ profile.username }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">账号状态</span>
                  <span class="meta-value status-badge active">正常</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">注册时间</span>
                  <span class="meta-value">{{ formatDate(profile.created_at) }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">最近更新</span>
                  <span class="meta-value">{{ formatDate(profile.updated_at) }}</span>
                </div>
              </div>
            </div>

            <!-- 右侧：表单区 -->
            <div class="forms-col">

              <!-- 基本信息 -->
              <section class="card form-card">
                <div class="card-header">
                  <UserIcon class="card-header-icon" />
                  <h2 class="card-title">基本信息</h2>
                </div>

                <div class="form-group">
                  <label class="form-label">显示名称</label>
                  <input
                    v-model="profileForm.display_name"
                    type="text"
                    class="form-input"
                    placeholder="输入显示名称"
                    maxlength="50"
                  />
                  <span class="form-hint">最多 50 个字符，显示在侧边栏和协作场景中</span>
                </div>

                <div class="form-group">
                  <label class="form-label">头像 URL <span class="optional">（可选）</span></label>
                  <input
                    v-model="profileForm.avatar_url"
                    type="url"
                    class="form-input"
                    placeholder="https://example.com/avatar.jpg"
                  />
                  <span class="form-hint">填入图片地址作为头像，不填则显示名称首字母</span>
                  <!-- 预览 -->
                  <div v-if="profileForm.avatar_url" class="avatar-preview">
                    <img
                      :src="profileForm.avatar_url"
                      alt="预览"
                      class="avatar-preview-img"
                      @error="onPreviewError"
                    />
                    <span class="avatar-preview-label">预览</span>
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label">用户名</label>
                  <input
                    :value="profile.username"
                    type="text"
                    class="form-input readonly"
                    readonly
                  />
                  <span class="form-hint">用户名不可修改</span>
                </div>

                <div class="form-group">
                  <label class="form-label">系统角色</label>
                  <input
                    :value="roleLabel"
                    type="text"
                    class="form-input readonly"
                    readonly
                  />
                  <span class="form-hint">角色由管理员分配，不可自行修改</span>
                </div>

                <div class="form-actions">
                  <button
                    class="btn btn-primary"
                    :disabled="profileSaving || !profileDirty"
                    @click="saveProfile"
                  >
                    <span v-if="profileSaving" class="spinner" />
                    {{ profileSaving ? '保存中…' : '保存修改' }}
                  </button>
                  <span v-if="profileSaveMsg" class="save-msg" :class="profileSaveMsgType">
                    {{ profileSaveMsg }}
                  </span>
                </div>
              </section>

              <!-- 修改密码 -->
              <section class="card form-card">
                <div class="card-header">
                  <LockIcon class="card-header-icon" />
                  <h2 class="card-title">修改密码</h2>
                </div>

                <div class="form-group">
                  <label class="form-label">当前密码</label>
                  <div class="input-wrap">
                    <input
                      v-model="pwdForm.old_password"
                      :type="showOld ? 'text' : 'password'"
                      class="form-input"
                      placeholder="输入当前密码"
                      autocomplete="current-password"
                    />
                    <button type="button" class="eye-btn" @click="showOld = !showOld">
                      <EyeIcon v-if="!showOld" class="eye-icon" />
                      <EyeOffIcon v-else class="eye-icon" />
                    </button>
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label">新密码</label>
                  <div class="input-wrap">
                    <input
                      v-model="pwdForm.new_password"
                      :type="showNew ? 'text' : 'password'"
                      class="form-input"
                      placeholder="至少 6 位"
                      autocomplete="new-password"
                    />
                    <button type="button" class="eye-btn" @click="showNew = !showNew">
                      <EyeIcon v-if="!showNew" class="eye-icon" />
                      <EyeOffIcon v-else class="eye-icon" />
                    </button>
                  </div>
                  <div v-if="pwdForm.new_password" class="pwd-strength">
                    <div class="pwd-bar" :class="pwdStrengthClass" />
                    <span class="pwd-strength-label">{{ pwdStrengthLabel }}</span>
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label">确认新密码</label>
                  <div class="input-wrap">
                    <input
                      v-model="pwdForm.confirm_password"
                      :type="showConfirm ? 'text' : 'password'"
                      class="form-input"
                      :class="{ error: pwdMismatch }"
                      placeholder="再次输入新密码"
                      autocomplete="new-password"
                    />
                    <button type="button" class="eye-btn" @click="showConfirm = !showConfirm">
                      <EyeIcon v-if="!showConfirm" class="eye-icon" />
                      <EyeOffIcon v-else class="eye-icon" />
                    </button>
                  </div>
                  <span v-if="pwdMismatch" class="form-error">两次密码不一致</span>
                </div>

                <div class="form-actions">
                  <button
                    class="btn btn-primary"
                    :disabled="pwdSaving || !pwdFormValid"
                    @click="changePassword"
                  >
                    <span v-if="pwdSaving" class="spinner" />
                    {{ pwdSaving ? '修改中…' : '修改密码' }}
                  </button>
                  <span v-if="pwdSaveMsg" class="save-msg" :class="pwdSaveMsgType">
                    {{ pwdSaveMsg }}
                  </span>
                </div>
              </section>

            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User as UserIcon, Lock as LockIcon, Eye as EyeIcon, EyeOff as EyeOffIcon } from 'lucide-vue-next'
import { authApi } from '@/utils/api.js'
import Sidebar from '@/components/beta/Sidebar.vue'

const router = useRouter()
const route = useRoute()

const activePage = 'account'

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

// ---- 用户资料状态 ----
const profile = reactive({
  user_id: '',
  username: '',
  display_name: '',
  role: '',
  external_type: null,
  avatar_url: null,
  created_at: null,
  updated_at: null,
})

const profileForm = reactive({
  display_name: '',
  avatar_url: '',
})

const profileSaving = ref(false)
const profileSaveMsg = ref('')
const profileSaveMsgType = ref('success')

// ---- 密码表单状态 ----
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const showOld = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)
const pwdSaving = ref(false)
const pwdSaveMsg = ref('')
const pwdSaveMsgType = ref('success')

// ---- 计算属性 ----
const avatarLetter = computed(() => {
  const name = profile.display_name || profile.username || '?'
  return name.charAt(0).toUpperCase()
})

const avatarColor = computed(() => {
  const colors = [
    '#2f8f89', '#7c3aed', '#c4692f', '#c45b60',
    '#5d6b76', '#a85424', '#1b2730', '#8b5cf6',
  ]
  const name = profile.username || ''
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
})

const roleLabel = computed(() => {
  const role = profile.role
  const ext = profile.external_type
  if (role === 'super_admin') return '高级管理员'
  if (role === 'admin') return '管理员'
  if (ext === 'CLIENT') return '甲方客户'
  if (ext === 'CONTRACTOR') return '外包成员'
  if (role === 'viewer') return '访客（只读）'
  return '项目成员'
})

const profileDirty = computed(() =>
  profileForm.display_name !== (profile.display_name || '') ||
  profileForm.avatar_url !== (profile.avatar_url || '')
)

const pwdMismatch = computed(() =>
  pwdForm.confirm_password.length > 0 &&
  pwdForm.new_password !== pwdForm.confirm_password
)

const pwdFormValid = computed(() =>
  pwdForm.old_password.length > 0 &&
  pwdForm.new_password.length >= 6 &&
  pwdForm.new_password === pwdForm.confirm_password
)

const pwdStrength = computed(() => {
  const p = pwdForm.new_password
  if (!p) return 0
  let score = 0
  if (p.length >= 8) score++
  if (/[A-Z]/.test(p)) score++
  if (/[0-9]/.test(p)) score++
  if (/[^A-Za-z0-9]/.test(p)) score++
  return score
})

const pwdStrengthClass = computed(() => {
  const s = pwdStrength.value
  if (s <= 1) return 'weak'
  if (s === 2) return 'medium'
  if (s === 3) return 'strong'
  return 'very-strong'
})

const pwdStrengthLabel = computed(() => {
  const s = pwdStrength.value
  if (s <= 1) return '弱'
  if (s === 2) return '中'
  if (s === 3) return '强'
  return '非常强'
})

// ---- 方法 ----
const loadProfile = async () => {
  try {
    const data = await authApi.getProfile()
    Object.assign(profile, data)
    profileForm.display_name = data.display_name || ''
    profileForm.avatar_url = data.avatar_url || ''
  } catch (err) {
    console.error('Failed to load profile:', err)
  }
}

const saveProfile = async () => {
  if (!profileDirty.value || profileSaving.value) return
  profileSaving.value = true
  profileSaveMsg.value = ''
  try {
    const payload = {}
    if (profileForm.display_name !== (profile.display_name || '')) {
      payload.display_name = profileForm.display_name
    }
    if (profileForm.avatar_url !== (profile.avatar_url || '')) {
      payload.avatar_url = profileForm.avatar_url
    }
    const updated = await authApi.updateProfile(payload)
    Object.assign(profile, updated)
    profileForm.display_name = updated.display_name || ''
    profileForm.avatar_url = updated.avatar_url || ''
    // 同步到 localStorage 使侧边栏头像立即刷新
    const stored = localStorage.getItem('user')
    if (stored) {
      try {
        const u = JSON.parse(stored)
        u.display_name = updated.display_name
        u.avatar_url = updated.avatar_url
        localStorage.setItem('user', JSON.stringify(u))
      } catch { /* ignore parse errors */ }
    }
    profileSaveMsg.value = '保存成功'
    profileSaveMsgType.value = 'success'
  } catch (err) {
    profileSaveMsg.value = err.message || '保存失败，请重试'
    profileSaveMsgType.value = 'error'
  } finally {
    profileSaving.value = false
    setTimeout(() => { profileSaveMsg.value = '' }, 3000)
  }
}

const changePassword = async () => {
  if (!pwdFormValid.value || pwdSaving.value) return
  pwdSaving.value = true
  pwdSaveMsg.value = ''
  try {
    await authApi.changePassword(pwdForm.old_password, pwdForm.new_password)
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    pwdSaveMsg.value = '密码修改成功'
    pwdSaveMsgType.value = 'success'
  } catch (err) {
    pwdSaveMsg.value = err.message || '修改失败，请重试'
    pwdSaveMsgType.value = 'error'
  } finally {
    pwdSaving.value = false
    setTimeout(() => { pwdSaveMsg.value = '' }, 3000)
  }
}

const onAvatarError = () => {
  profile.avatar_url = null
}

const onPreviewError = (e) => {
  e.target.style.display = 'none'
}

const formatDate = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

onMounted(() => {
  loadProfile()
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

.account-canvas {
  flex: 1;
  overflow-y: auto;
  background: var(--canvas-bg, #f4f5f7);
}

.account-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 28px;
}

/* ---- 页头 ---- */
.page-header {
  margin-bottom: 24px;
}

.page-title {
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

/* ---- 主内容区 ---- */
.account-content {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

/* ---- 通用卡片 ---- */
.card {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 20px;
}

/* ---- 左侧头像卡片 ---- */
.avatar-card {
  width: 210px;
  flex-shrink: 0;
  position: sticky;
  top: 20px;
}

.avatar-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-bottom: 16px;
}

.avatar-wrap {
  width: 76px;
  height: 76px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-letter {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 700;
  color: #fff;
}

.avatar-info {
  text-align: center;
}

.avatar-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  word-break: break-all;
}

.avatar-role {
  font-size: 12px;
  color: var(--text-muted, #8a8a9a);
  margin-top: 2px;
}

.divider {
  height: 1px;
  background: var(--border, #e5e7eb);
  margin: 4px 0 12px;
}

.meta-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 10px;
  color: var(--text-muted, #8a8a9a);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.meta-value {
  font-size: 12px;
  color: var(--text-primary, #1a1a2e);
}

.meta-value.mono {
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.status-badge.active {
  display: inline-block;
  background: #d1fae5;
  color: #065f46;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 20px;
  font-weight: 500;
}

/* ---- 右侧表单列 ---- */
.forms-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-card {
  padding: 20px 22px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
}

.card-header-icon {
  width: 17px;
  height: 17px;
  color: var(--accent, #2f8f89);
  flex-shrink: 0;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #1a1a2e);
  margin: 0;
}

/* ---- 表单元素 ---- */
.form-group {
  margin-bottom: 14px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #4a4a5a);
  margin-bottom: 5px;
}

.optional {
  font-weight: 400;
  color: var(--text-muted, #8a8a9a);
}

.form-input {
  width: 100%;
  padding: 7px 11px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary, #1a1a2e);
  background: var(--surface, #fff);
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
  outline: none;
}

.form-input:focus {
  border-color: var(--accent, #2f8f89);
  box-shadow: 0 0 0 2px rgba(47, 143, 137, 0.12);
}

.form-input.readonly {
  background: var(--surface-muted, #f8f9fa);
  color: var(--text-muted, #8a8a9a);
  cursor: default;
}

.form-input.error {
  border-color: #ef4444;
}

.form-hint {
  display: block;
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
  margin-top: 4px;
}

.form-error {
  display: block;
  font-size: 11px;
  color: #ef4444;
  margin-top: 4px;
}

/* ---- 头像预览 ---- */
.avatar-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.avatar-preview-img {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--border, #e5e7eb);
}

.avatar-preview-label {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
}

/* ---- 密码输入包装 ---- */
.input-wrap {
  position: relative;
}

.input-wrap .form-input {
  padding-right: 38px;
}

.eye-btn {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  color: var(--text-muted, #8a8a9a);
  display: flex;
  align-items: center;
}

.eye-btn:hover {
  color: var(--text-secondary, #4a4a5a);
}

.eye-icon {
  width: 15px;
  height: 15px;
}

/* ---- 密码强度 ---- */
.pwd-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.pwd-bar {
  flex: 1;
  height: 3px;
  border-radius: 2px;
  background: var(--border, #e5e7eb);
  position: relative;
  overflow: hidden;
}

.pwd-bar::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0; left: 0;
  border-radius: 2px;
  transition: width 0.3s, background 0.3s;
}

.pwd-bar.weak::after        { width: 25%; background: #ef4444; }
.pwd-bar.medium::after      { width: 50%; background: #f59e0b; }
.pwd-bar.strong::after      { width: 75%; background: #10b981; }
.pwd-bar.very-strong::after { width: 100%; background: #059669; }

.pwd-strength-label {
  font-size: 11px;
  color: var(--text-muted, #8a8a9a);
  white-space: nowrap;
  min-width: 32px;
}

/* ---- 按钮和提示 ---- */
.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}

.btn {
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  display: flex;
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

.spinner {
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

.save-msg {
  font-size: 12px;
}

.save-msg.success { color: #059669; }
.save-msg.error   { color: #ef4444; }

/* ---- 响应式 ---- */
@media (max-width: 700px) {
  .account-content {
    flex-direction: column;
  }
  .avatar-card {
    width: 100%;
    position: static;
  }
  .avatar-area {
    flex-direction: row;
    align-items: center;
    text-align: left;
  }
  .avatar-info { text-align: left; }
}
</style>
