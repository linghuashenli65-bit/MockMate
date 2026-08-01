import { createRouter, createWebHistory } from 'vue-router'
import { useSettingsStore } from '../stores/settings'

const routes = [
  { path: '/', name: 'setup', component: () => import('../views/SetupView.vue'), meta: { title: '准备面试' } },
  { path: '/mock-interview', name: 'mock-interview', component: () => import('../views/MockInterviewView.vue'), meta: { title: '拟真面试' } },
  { path: '/interview', name: 'interview', component: () => import('../views/InterviewView.vue'), meta: { title: '模拟面试' } },
  { path: '/favorites', name: 'favorites', component: () => import('../views/FavoritesView.vue'), meta: { title: '题目收藏' } },
  { path: '/custom', name: 'custom', component: () => import('../views/CustomView.vue'), meta: { title: '自定义题目' } },
  { path: '/finetune', name: 'finetune', component: () => import('../views/FinetuneView.vue'), meta: { title: '微调' } },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: '设置' } },
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const settings = useSettingsStore()
  // 已登录时访问登录页 → 回首页
  if (to.name === 'login' && settings.authToken) {
    return { path: '/' }
  }
  return true
})

export default router
