/**
 * 用户认证和权限管理 Store
 *
 * 功能：
 * - 用户登录/登出状态管理
 * - 项目级权限上下文缓存
 * - 权限和角色检查
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { AUTH_CLEARED_EVENT, clearAuthStorage } from '@/api/request'

export const useAuthStore = defineStore('auth', () => {
  // ========================
  // 状态
  // ========================
  const user = ref(null)
  const token = ref(localStorage.getItem('token'))
  const sessionValidated = ref(false)
  const projectContexts = ref(new Map()) // projectId -> context

  function applyLoggedOutState() {
    token.value = null
    user.value = null
    sessionValidated.value = false
    clearAllProjectContexts()
  }

  // ========================
  // 计算属性
  // ========================
  const isAuthenticated = computed(() => !!token.value)

  const systemIdentity = computed(() => {
    // 从用户信息中获取系统级身份
    const role = user.value?.role

    if (role === 'super_admin' || role === 'admin') {
      return 'SYS_ADMIN'
    }
    return 'SYS_USER'
  })

  const systemRole = computed(() => user.value?.role || null)

  // 获取身份显示标签（用于侧边栏）
  const identityLabel = computed(() => {
    const role = user.value?.role

    if (role === 'super_admin') {
      return '超级管理员'
    }
    if (role === 'admin') {
      return '管理员'
    }
    if (role === 'member') {
      return '项目成员'
    }
    if (role === 'viewer') {
      return '访客'
    }
    return '未认证'
  })

  const userId = computed(() => user.value?.user_id || user.value?.username)

  // ========================
  // 权限检查方法
  // ========================

  /**
   * 获取用户在项目中的权限列表
   */
  const getProjectPermissions = (projectId) => {
    const context = projectContexts.value.get(projectId)
    return context?.permissions || []
  }

  /**
   * 获取用户在项目中的角色列表
   */
  const getProjectRoles = (projectId) => {
    const context = projectContexts.value.get(projectId)
    return context?.roles || []
  }

  /**
   * 检查用户是否具有指定权限
   */
  const hasPermission = (projectId, permission) => {
    const permissions = getProjectPermissions(projectId)
    return permissions.includes(permission)
  }

  /**
   * 检查用户是否具有任一权限
   */
  const hasAnyPermission = (projectId, permissions) => {
    if (!Array.isArray(permissions)) {
      return hasPermission(projectId, permissions)
    }
    return permissions.some(p => hasPermission(projectId, p))
  }

  /**
   * 检查用户是否具有所有权限
   */
  const hasAllPermissions = (projectId, permissions) => {
    if (!Array.isArray(permissions)) {
      return hasPermission(projectId, permissions)
    }
    return permissions.every(p => hasPermission(projectId, p))
  }

  /**
   * 检查用户是否具有指定角色
   */
  const hasRole = (projectId, role) => {
    const roles = getProjectRoles(projectId)
    return roles.includes(role)
  }

  /**
   * 检查用户是否具有任一角色
   */
  const hasAnyRole = (projectId, roles) => {
    if (!Array.isArray(roles)) {
      return hasRole(projectId, roles)
    }
    return roles.some(r => hasRole(projectId, r))
  }

  // ========================
  // 项目上下文管理
  // ========================

  /**
   * 加载项目权限上下文
   */
  async function loadProjectContext(projectId) {
    if (!projectId) {
      console.warn('loadProjectContext: projectId is empty')
      return null
    }

    // 如果已加载且不是需要刷新的场景，直接返回
    if (projectContexts.value.has(projectId)) {
      return projectContexts.value.get(projectId)
    }

    try {
      const resp = await fetch(`/api/v2/permission/projects/${encodeURIComponent(projectId)}/context`, {
        headers: {
          'Authorization': `Bearer ${token.value}`
        }
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`)
      }

      const result = await resp.json()

      if (result.success === false) {
        throw new Error(result.error || '获取权限上下文失败')
      }

      const context = result.data || {}
      projectContexts.value.set(projectId, context)
      return context
    } catch (error) {
      console.error('Failed to load project context:', error)
      throw error
    }
  }

  /**
   * 预加载多个项目的权限上下文
   */
  async function loadProjectContexts(projectIds) {
    const promises = projectIds
      .filter(id => id && !projectContexts.value.has(id))
      .map(id => loadProjectContext(id).catch(err => {
        console.warn(`Failed to load context for project ${id}:`, err)
        return null
      }))

    await Promise.all(promises)
  }

  /**
   * 清除指定项目的权限上下文
   */
  function clearProjectContext(projectId) {
    projectContexts.value.delete(projectId)
  }

  /**
   * 清除所有项目权限上下文
   */
  function clearAllProjectContexts() {
    projectContexts.value.clear()
  }

  // ========================
  // 认证方法
  // ========================

  /**
   * 登录
   */
  async function login(username, password, role = 'member') {
    const result = await authApi.login(username, password, role)

    token.value = result.token
    user.value = result
    sessionValidated.value = true

    // 保存到 localStorage
    localStorage.setItem('token', result.token)
    localStorage.setItem('user', JSON.stringify(result))

    // 兼容旧字段
    localStorage.setItem('actor', result.username || username)
    localStorage.setItem('role', result.role || role)

    return result
  }

  /**
   * 登出
   */
  async function logout() {
    try {
      await authApi.logout()
    } catch (_e) {
      // ignore
    } finally {
      applyLoggedOutState()
      clearAuthStorage()
    }
  }

  /**
   * 验证当前 token 是否有效
   */
  async function verify() {
    if (!token.value) {
      return false
    }

    try {
      const result = await authApi.verify()
      user.value = result
      sessionValidated.value = true
      localStorage.setItem('user', JSON.stringify(result))
      return true
    } catch (error) {
      console.error('Token verification failed:', error)
      await logout()
      return false
    }
  }

  /**
   * 初始化（从 localStorage 恢复）
   */
  function init() {
    const savedToken = localStorage.getItem('token')
    const savedUser = localStorage.getItem('user')

    if (savedToken && savedUser) {
      try {
        token.value = savedToken
        user.value = JSON.parse(savedUser)
        sessionValidated.value = false
      } catch (_e) {
        console.error('Failed to parse saved user:', _e)
        logout()
      }
      return
    }

    token.value = null
    user.value = null
    sessionValidated.value = false
    clearAllProjectContexts()
  }

  async function ensureValidSession() {
    if (!token.value) {
      return false
    }

    if (sessionValidated.value) {
      return true
    }

    return verify()
  }

  /**
   * 更新用户信息
   */
  function updateUser(userData) {
    user.value = { ...user.value, ...userData }
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  if (typeof window !== 'undefined' && !window.__semanticAtlasAuthClearedListenerBound) {
    window.addEventListener(AUTH_CLEARED_EVENT, () => {
      applyLoggedOutState()
    })
    window.__semanticAtlasAuthClearedListenerBound = true
  }

  return {
    // 状态
    user,
    token,
    projectContexts,
    sessionValidated,

    // 计算属性
    isAuthenticated,
    systemIdentity,
    systemRole,
    identityLabel,
    userId,

    // 权限检查
    getProjectPermissions,
    getProjectRoles,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    hasRole,
    hasAnyRole,

    // 项目上下文
    loadProjectContext,
    loadProjectContexts,
    clearProjectContext,
    clearAllProjectContexts,

    // 认证
    login,
    logout,
    verify,
    ensureValidSession,
    init,
    updateUser,
    applyLoggedOutState,
  }
})
