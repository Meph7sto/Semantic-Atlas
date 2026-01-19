import { createRouter, createWebHistory } from 'vue-router'
import Classification from '../views/Classification.vue'
import ConflictDetection from '../views/ConflictDetection.vue'
import Traceability from '../views/Traceability.vue'
import RequirementsAcquisition from '../views/RequirementsAcquisition.vue'
import GeneralChat from '../views/GeneralChat.vue'
import BlankPage1 from '../views/BlankPage1.vue'
import BlankPage2 from '../views/BlankPage2.vue'
import BlankPage3 from '../views/BlankPage3.vue'

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
            path: '/blank-1',
            name: 'blank-1',
            component: BlankPage1
        },
        {
            path: '/blank-2',
            name: 'blank-2',
            component: BlankPage2
        },
        {
            path: '/blank-3',
            name: 'blank-3',
            component: BlankPage3
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
            path: '/chat',
            name: 'chat',
            component: GeneralChat
        }
    ]
})

export default router


