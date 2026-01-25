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

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            redirect: '/alpha/conflict'
        },
        {
            path: '/alpha',
            name: 'alpha',
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
                    component: RequirementsManage
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
                }
            ]
        }
    ]
})

export default router


