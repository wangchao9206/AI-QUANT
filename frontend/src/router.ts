import { createRouter, createWebHistory } from 'vue-router'

import PlaceholderView from './views/PlaceholderView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    {
      path: '/overview',
      name: 'overview',
      component: PlaceholderView,
      meta: { title: '总览', eyebrow: '今日决策' },
    },
    {
      path: '/market',
      name: 'market',
      component: PlaceholderView,
      meta: { title: '市场', eyebrow: '行情结构' },
    },
    {
      path: '/strategy',
      name: 'strategy',
      component: PlaceholderView,
      meta: { title: '策略', eyebrow: '十一维模型' },
    },
    {
      path: '/system',
      name: 'system',
      component: PlaceholderView,
      meta: { title: '系统', eyebrow: '运行状态' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '控制台')} · AI-QUANT`
})

export default router
