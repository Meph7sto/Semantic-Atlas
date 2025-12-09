import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import AnalysisHistory from '../views/AnalysisHistory.vue'
import Statistics from '../views/Statistics.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { title: '需求分析' }
  },
  {
    path: '/history',
    name: 'AnalysisHistory',
    component: AnalysisHistory,
    meta: { title: '分析历史' }
  },
  {
    path: '/statistics',
    name: 'Statistics',
    component: Statistics,
    meta: { title: '统计数据' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - 需求追溯系统` : '需求追溯系统'
  next()
})

export default router
