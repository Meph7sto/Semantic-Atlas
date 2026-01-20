import { createRouter, createWebHistory } from 'vue-router'
import Classification from '../views/Classification.vue'
import ConflictDetection from '../views/ConflictDetection.vue'
import Traceability from '../views/Traceability.vue'
import RequirementsAcquisition from '../views/RequirementsAcquisition.vue'
import AcquisitionTraceability from '../views/AcquisitionTraceability.vue'

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
        }
    ]
})

export default router


