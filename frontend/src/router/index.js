import { createRouter, createWebHistory } from 'vue-router'
import ConflictDetection from '@/views/ConflictDetection.vue'

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
        }
    ]
})

export default router
