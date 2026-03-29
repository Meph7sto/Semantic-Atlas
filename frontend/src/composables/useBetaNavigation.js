/**
 * useBetaNavigation — 统一 beta 页面的侧边栏导航逻辑
 *
 * 将各页面重复的 routeNameToPageKey / pageKeyToRouteName / handleNavigate / handleExit
 * 以及 Sidebar 需要的 roleType / roleLabel / timestamp / notificationCount 集中管理。
 *
 * 用法：
 *   const { activePage, handleNavigate, handleExit } = useBetaNavigation('dashboard')
 *   const { currentUser, roleType, roleLabel, timestamp, notificationCount } = useBetaSidebarProps()
 */

import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'

// ---- 双向映射常量 ----

const ROUTE_NAME_TO_PAGE_KEY = Object.freeze({
  'beta-dashboard': 'dashboard',
  'beta-products': 'products',
  'beta-project': 'project-management',
  'beta-requirements': 'requirements',
  'beta-requirements-overview': 'requirements',
  'beta-requirements-session': 'requirements-session',
  'beta-requirements-analysis': 'requirements-analysis',
  'beta-requirements-collection': 'requirements-collection',
  'beta-collection-advanced': 'requirements-collection',
  'beta-multimodal-ingestion': 'multimodal-ingestion',
  'beta-defects': 'defects',
  'beta-user-manage': 'user-management',
  'beta-account': 'account',
  'beta-traceability': 'tracking',
  'beta-reviews': 'reviews',
  'beta-reports': 'reports',
})

const PAGE_KEY_TO_ROUTE_NAME = Object.freeze({
  'dashboard': 'beta-dashboard',
  'products': 'beta-products',
  'project-management': 'beta-project',
  'requirements': 'beta-requirements',
  'requirements-session': 'beta-requirements-session',
  'requirements-analysis': 'beta-requirements-analysis',
  'requirements-collection': 'beta-requirements-collection',
  'multimodal-ingestion': 'beta-multimodal-ingestion',
  'defects': 'beta-defects',
  'user-management': 'beta-user-manage',
  'account': 'beta-account',
  'tracking': 'beta-traceability',
  'reviews': 'beta-reviews',
  'reports': 'beta-reports',
})

// ---- 角色映射 ----

const SYSTEM_IDENTITY_TO_ROLE_TYPE = Object.freeze({
  SYS_ADMIN: 'unified_admin',
  SYS_USER: 'unified_member',
  SYS_CLIENT: 'unified_client',
  SYS_CONTRACTOR: 'unified_contractor',
  admin: 'unified_admin',
  member: 'unified_member',
  viewer: 'unified_viewer',
})

// ---- Composable: 导航逻辑 ----

/**
 * @param {string} defaultPageKey  当 route.name 不在映射表中时回退的 pageKey
 * @returns {{ activePage: import('vue').ComputedRef<string>, handleNavigate: (pageKey: string) => void, handleExit: () => Promise<void> }}
 */
export function useBetaNavigation(defaultPageKey = 'dashboard') {
  const router = useRouter()
  const route = useRoute()
  const authStore = useAuthStore()

  const activePage = computed(() =>
    ROUTE_NAME_TO_PAGE_KEY[route.name] || defaultPageKey,
  )

  function handleNavigate(pageKey) {
    const target = PAGE_KEY_TO_ROUTE_NAME[pageKey]
    if (target && target !== route.name) {
      router.push({ name: target })
    }
  }

  async function handleExit() {
    try {
      await authStore.logout()
    } catch (error) {
      console.error('Failed to logout:', error)
    }
    router.push({ name: 'beta-login' })
  }

  return { activePage, handleNavigate, handleExit }
}

// ---- Composable: Sidebar 通用 Props ----

/**
 * 返回传递给 Sidebar 组件的常用 props
 */
export function useBetaSidebarProps() {
  const authStore = useAuthStore()

  const currentUser = computed(() => authStore.user)

  const roleType = computed(() => {
    const role = authStore.systemIdentity || authStore.systemRole
    return SYSTEM_IDENTITY_TO_ROLE_TYPE[role] || 'unified_member'
  })

  const roleLabel = computed(() =>
    currentUser.value?.display_name || currentUser.value?.username || roleType.value,
  )

  const timestamp = ref(new Date().toLocaleString())
  const notificationCount = ref(0)

  return { currentUser, roleType, roleLabel, timestamp, notificationCount }
}

export { ROUTE_NAME_TO_PAGE_KEY, PAGE_KEY_TO_ROUTE_NAME }
