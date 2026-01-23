import { createRouter, createWebHistory } from 'vue-router'
import Classification from '../views/Classification.vue'
import ConflictDetection from '../views/ConflictDetection.vue'
import Traceability from '../views/Traceability.vue'
import RequirementsAcquisition from '../views/RequirementsAcquisition.vue'
import AcquisitionTraceability from '../views/AcquisitionTraceability.vue'
import GeneralChat from '../views/GeneralChat.vue'
import TranscriptIngestion from '../views/TranscriptIngestion.vue'
import ContextBuilder from '../views/ContextBuilder.vue'
import RequirementsExtraction from '../views/RequirementsExtraction.vue'
import L4Testing from '../views/L4Testing.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            redirect: '/conflict'
        },
        {
            path: '/conflict',
            name: 'conflict',
            component: ConflictDetection
        },
        {
            path: '/transcript-ingestion',
            name: 'transcript-ingestion',
            component: TranscriptIngestion
        },
        {
            path: '/context-builder',
            name: 'context-builder',
            component: ContextBuilder
        },
        {
            path: '/requirements-extraction',
            name: 'requirements-extraction',
            component: RequirementsExtraction
        },
        {
            path: '/l4-testing',
            name: 'l4-testing',
            component: L4Testing
        },
        {
            path: '/traceability',
            name: 'traceability',
            component: Traceability
        },
        {
            path: '/classification',
            name: 'classification',
            component: Classification
        },
        {
            path: '/acquisition',
            name: 'acquisition',
            component: RequirementsAcquisition
        },
        {
            path: '/acquisition-trace',
            name: 'acquisition-trace',
            component: AcquisitionTraceability
        },
        {
            path: '/chat',
            name: 'chat',
            component: GeneralChat
        }
    ]
})

export default router


