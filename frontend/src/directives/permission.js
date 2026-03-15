/**
 * 权限控制指令
 *
 * 使用方式：
 * - v-has-permission="{ projectId: 'xxx', permission: 'req:create' }"
 * - v-has-permission="{ projectId: 'xxx', permissions: ['req:create', 'req:edit'], any: true }"
 * - v-has-role="{ projectId: 'xxx', role: 'PO' }"
 * - v-has-role="{ projectId: 'xxx', roles: ['PO', 'BA'], any: true }"
 */

import { useAuthStore } from '@/stores/auth.js'

/**
 * 权限指令：根据权限显示/隐藏元素
 */
export const hasPermission = {
  mounted(el, binding) {
    const { projectId, permission, permissions, any = false } = binding.value
    const authStore = useAuthStore()

    let allowed = false

    if (any) {
      // 检查是否有任一权限
      allowed = authStore.hasAnyPermission(projectId, permissions)
    } else if (permission) {
      // 检查是否有指定权限
      allowed = authStore.hasPermission(projectId, permission)
    } else if (permissions) {
      // 检查是否有所有权限
      allowed = authStore.hasAllPermissions(projectId, permissions)
    }

    if (!allowed) {
      el.style.display = 'none'
    }
  },
  updated(el, binding) {
    // 重新检查权限
    const { projectId, permission, permissions, any = false } = binding.value
    const authStore = useAuthStore()

    let allowed = false

    if (any) {
      allowed = authStore.hasAnyPermission(projectId, permissions)
    } else if (permission) {
      allowed = authStore.hasPermission(projectId, permission)
    } else if (permissions) {
      allowed = authStore.hasAllPermissions(projectId, permissions)
    }

    el.style.display = allowed ? '' : 'none'
  },
}

/**
 * 角色指令：根据角色显示/隐藏元素
 */
export const hasRole = {
  mounted(el, binding) {
    const { projectId, role, roles, any = false } = binding.value
    const authStore = useAuthStore()

    let allowed = false

    if (any) {
      // 检查是否有任一角色
      allowed = authStore.hasAnyRole(projectId, roles)
    } else if (role) {
      // 检查是否有指定角色
      allowed = authStore.hasRole(projectId, role)
    } else if (roles) {
      // 检查是否有所有角色
      const userRoles = authStore.getProjectRoles(projectId)
      allowed = roles.every(r => userRoles.includes(r))
    }

    if (!allowed) {
      el.style.display = 'none'
    }
  },
  updated(el, binding) {
    // 重新检查角色
    const { projectId, role, roles, any = false } = binding.value
    const authStore = useAuthStore()

    let allowed = false

    if (any) {
      allowed = authStore.hasAnyRole(projectId, roles)
    } else if (role) {
      allowed = authStore.hasRole(projectId, role)
    } else if (roles) {
      const userRoles = authStore.getProjectRoles(projectId)
      allowed = roles.every(r => userRoles.includes(r))
    }

    el.style.display = allowed ? '' : 'none'
  },
}
