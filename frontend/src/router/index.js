import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth.js'
import Classification from '../views/alpha/Classification.vue'
import ConflictDetection from '../views/alpha/ConflictDetection.vue'
import Traceability from '../views/alpha/Traceability.vue'
import AcquisitionTraceability from '../views/alpha/AcquisitionTraceability.vue'
import GeneralChat from '../views/alpha/GeneralChat.vue'
import TranscriptIngestion from '../views/alpha/TranscriptIngestion.vue'
import ContextBuilder from '../views/alpha/ContextBuilder.vue'
import RequirementsExtraction from '../views/alpha/RequirementsExtraction.vue'
import L4Testing from '../views/alpha/L4Testing.vue'
import RequirementsManage from '../views/alpha/RequirementsManage.vue'
import RequirementsManageTableDebug from '../views/alpha/RequirementsManageTableDebug.vue'
import MessagePush from '../views/alpha/MessagePush.vue'
import MobileBridge from '../views/alpha/MobileBridge.vue'
import FileReceive from '../views/alpha/FileReceive.vue'
import ExecutionTopologyTemplate from '../views/alpha/ExecutionTopologyTemplate.vue'
import ActorVisualTester from '../views/alpha/ActorVisualTester.vue'
import RequirementReplay from '../views/alpha/RequirementReplay.vue'
import ImageCaptionPreview from '../views/alpha/ImageCaptionPreview.vue'

// Main views (migrated from frontend_ref)
import LoginView from '../views/beta/LoginView.vue'
import RegisterView from '../views/beta/RegisterView.vue'
import DashboardView from '../views/beta/DashboardView.vue'
import ProjectManageView from '../views/beta/ProjectManageView.vue'
import RequirementsView from '../views/beta/RequirementsView.vue'
import RequirementsSessionView from '../views/beta/RequirementsSessionView.vue'
import RequirementsAnalysisView from '../views/beta/RequirementsAnalysisView.vue'
import RequirementsCollectionView from '../views/beta/RequirementsCollectionView.vue'
import ProductManageView from '../views/beta/ProductManageView.vue'
import AccountView from '../views/beta/AccountView.vue'
import UserManageView from '../views/beta/UserManageView.vue'
import AsrTranscriptionView from '../views/beta/AsrTranscriptionView.vue'

// Guide view
import GuideView from '../views/GuideView.vue'
import RequirementsAcquisitionView from '../views/beta/RequirementsAcquisitionView.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            redirect: '/guide'
        },
        {
            path: '/guide',
            name: 'guide',
            component: GuideView
        },
        // Main routes (migrated from frontend_ref)
        {
            path: '/beta',
            name: 'beta',
            redirect: '/guide',
            children: [
                {
                    path: 'login',
                    name: 'beta-login',
                    component: LoginView,
                    meta: { requiresAuth: false }
                },
                {
                    path: 'register',
                    name: 'beta-register',
                    component: RegisterView,
                    meta: { requiresAuth: false }
                },
                {
                    path: 'dashboard',
                    name: 'beta-dashboard',
                    component: DashboardView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'project',
                    name: 'beta-project',
                    component: ProjectManageView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements',
                    name: 'beta-requirements',
                    component: RequirementsView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-session',
                    name: 'beta-requirements-session',
                    component: RequirementsSessionView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-analysis',
                    name: 'beta-requirements-analysis',
                    component: RequirementsAnalysisView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-collection',
                    name: 'beta-requirements-collection',
                    component: RequirementsCollectionView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'asr',
                    name: 'beta-asr',
                    component: AsrTranscriptionView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'products',
                    name: 'beta-products',
                    component: ProductManageView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'account',
                    name: 'beta-account',
                    component: AccountView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'user-manage',
                    name: 'beta-user-manage',
                    component: UserManageView,
                    meta: {
                        requiresAuth: true,
                        requiredSystemIdentities: ['SYS_ADMIN']
                    }
                }
            ]
        },
        {
            path: '/alpha',
            name: 'alpha',
            redirect: '/alpha/transcript-ingestion',
            meta: { requiresAuth: true },
            children: [
                {
                    path: 'conflict',
                    name: 'conflict',
                    component: ConflictDetection
                },
                {
                    path: 'transcript-ingestion',
                    name: 'transcript-ingestion',
                    component: TranscriptIngestion
                },
                {
                    path: 'context-builder',
                    name: 'context-builder',
                    component: ContextBuilder
                },
                {
                    path: 'requirements-extraction',
                    name: 'requirements-extraction',
                    component: RequirementsExtraction
                },
                {
                    path: 'l4-testing',
                    name: 'l4-testing',
                    component: L4Testing
                },
                {
                    path: 'requirements-manage',
                    name: 'requirements-manage',
                    component: RequirementsManage,
                    meta: { keepAlive: true }
                },
                {
                    path: 'requirements-manage-table',
                    name: 'requirements-manage-table',
                    component: RequirementsManageTableDebug,
                    meta: { keepAlive: true }
                },
                {
                    path: 'traceability',
                    name: 'traceability',
                    component: Traceability
                },
                {
                    path: 'classification',
                    name: 'classification',
                    component: Classification
                },
                {
                    path: 'acquisition-trace',
                    name: 'acquisition-trace',
                    component: AcquisitionTraceability
                },
                {
                    path: 'chat',
                    name: 'chat',
                    component: GeneralChat
                },
                {
                    path: 'message-push',
                    name: 'message-push',
                    component: MessagePush
                },
                {
                    path: 'mobile-bridge',
                    name: 'mobile-bridge',
                    component: MobileBridge
                },
                {
                    path: 'file-receive',
                    name: 'file-receive',
                    component: FileReceive,
                    meta: { keepAlive: true }
                },
                {
                    path: 'execution-topology',
                    name: 'execution-topology',
                    component: ExecutionTopologyTemplate,
                    meta: { keepAlive: true }
                },
                {
                    path: 'actor-visual-tester',
                    name: 'actor-visual-tester',
                    component: ActorVisualTester
                },
                {
                    path: 'requirement-replay',
                    name: 'requirement-replay',
                    component: RequirementReplay
                },
                {
                    path: 'image-caption',
                    name: 'image-caption',
                    component: ImageCaptionPreview,
                    meta: { keepAlive: true }
                }
            ]
        },
        // Fallback: keep layout predictable on bad URLs
        {
            path: '/:pathMatch(.*)*',
            redirect: '/guide'
        }
    ]
})

// 路由守卫：检查认证状态和权限
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()

    // 初始化 authStore（从 localStorage 恢复）
    authStore.init()

    // 检查是否需要认证
    const requiresAuth = to.meta?.requiresAuth !== false // 默认需要认证，除非显式设置为 false

    if (requiresAuth && !authStore.isAuthenticated) {
        next({ name: 'beta-login', query: { redirect: to.fullPath } })
        return
    }

    // 检查系统级身份访问控制（如仅超级管理员可访问）
    if (Array.isArray(to.meta?.requiredSystemIdentities) && to.meta.requiredSystemIdentities.length > 0) {
        const currentIdentity = authStore.systemIdentity
        const allowed = to.meta.requiredSystemIdentities
        if (!allowed.includes(currentIdentity)) {
            console.warn('Access denied: insufficient system identity', {
                route: to.name,
                requiredSystemIdentities: allowed,
                currentIdentity
            })
            next({ name: 'beta-dashboard' })
            return
        }
    }

    // 检查项目级权限（如果路由定义了 requiredPermissions）
    if (to.meta?.requiredPermissions) {
        const projectId = to.params.projectId || to.query.projectId
        if (!projectId) {
            next({ name: 'beta-dashboard' }) // 没有 projectId，回退
            return
        }

        // 加载项目上下文（如果未加载）
        if (!authStore.projectContexts.has(projectId)) {
            try {
                await authStore.loadProjectContext(projectId)
            } catch (e) {
                console.error('Failed to load project context:', e)
                next({ name: 'beta-dashboard' })
                return
            }
        }

        // 检查权限
        const required = to.meta.requiredPermissions
        const hasAccess = authStore.hasAnyPermission(projectId, required)

        if (!hasAccess) {
            console.warn(`Access denied: missing required permissions`, { required, projectId })
            next({ name: 'beta-dashboard' }) // 无权限，回退
            return
        }
    }

    next()
})

export default router
