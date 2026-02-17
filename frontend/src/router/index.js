import { createRouter, createWebHistory } from 'vue-router'
import Classification from '../views/alpha/Classification.vue'
import ConflictDetection from '../views/alpha/ConflictDetection.vue'
import Traceability from '../views/alpha/Traceability.vue'
import RequirementsAcquisition from '../views/alpha/RequirementsAcquisition.vue'
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
import AgentCollaboration from '../views/alpha/AgentCollaboration.vue'
import AgentChat from '../views/alpha/AgentChat.vue'

// Main views (migrated from frontend_ref)
import LoginView from '../views/main/LoginView.vue'
import RegisterView from '../views/main/RegisterView.vue'
import DashboardView from '../views/main/DashboardView.vue'
import ProjectManageView from '../views/main/ProjectManageView.vue'
import RequirementsView from '../views/main/RequirementsView.vue'
import RequirementsSessionView from '../views/main/RequirementsSessionView.vue'
import RequirementsAnalysisView from '../views/main/RequirementsAnalysisView.vue'
import RequirementsCollectionView from '../views/main/RequirementsCollectionView.vue'
import ProductManageView from '../views/main/ProductManageView.vue'

// Guide view
import GuideView from '../views/GuideView.vue'

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
            path: '/main',
            name: 'main',
            redirect: '/guide',
            children: [
                {
                    path: 'login',
                    name: 'main-login',
                    component: LoginView,
                    meta: { requiresAuth: false }
                },
                {
                    path: 'register',
                    name: 'main-register',
                    component: RegisterView,
                    meta: { requiresAuth: false }
                },
                {
                    path: 'dashboard',
                    name: 'main-dashboard',
                    component: DashboardView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'project',
                    name: 'main-project',
                    component: ProjectManageView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements',
                    name: 'main-requirements',
                    component: RequirementsView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-session',
                    name: 'main-requirements-session',
                    component: RequirementsSessionView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-analysis',
                    name: 'main-requirements-analysis',
                    component: RequirementsAnalysisView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'requirements-collection',
                    name: 'main-requirements-collection',
                    component: RequirementsCollectionView,
                    meta: { requiresAuth: true }
                },
                {
                    path: 'products',
                    name: 'main-products',
                    component: ProductManageView,
                    meta: { requiresAuth: true }
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
                    path: 'acquisition',
                    name: 'acquisition',
                    component: RequirementsAcquisition
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
                    path: 'agent-collaboration',
                    name: 'agent-collaboration',
                    component: AgentCollaboration,
                    meta: { keepAlive: true }
                },
                {
                    path: 'agent-chat',
                    name: 'agent-chat',
                    component: AgentChat,
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

// 路由守卫：检查认证状态
router.beforeEach((to, from, next) => {
    const token = localStorage.getItem('token')
    const requiresAuth = to.meta?.requiresAuth !== false // 默认需要认证，除非显式设置为 false

    // 如果页面需要认证但没有 token，重定向到登录页
    if (requiresAuth && !token) {
        next({ name: 'main-login', query: { redirect: to.fullPath } })
    } else {
        next()
    }
})

export default router
