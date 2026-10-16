import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('./views/OverviewView.vue'),
      meta: { title: '总览', eyebrow: '今日决策' },
    },
    {
      path: '/leads',
      name: 'leads',
      component: () => import('./views/LeadsView.vue'),
      meta: { title: '线索池', eyebrow: '多维智能雷达' },
    },
    {
      path: '/market',
      name: 'market',
      component: () => import('./views/MarketView.vue'),
      meta: { title: '市场', eyebrow: '行情结构' },
    },
    {
      path: '/strategy',
      name: 'strategy',
      component: () => import('./views/StrategyView.vue'),
      meta: { title: '策略', eyebrow: '真实量价模型' },
    },
    {
      path: '/backtest',
      name: 'backtest',
      component: () => import('./views/BacktestView.vue'),
      meta: { title: '回测模拟', eyebrow: '历史回溯与量化仿真' },
    },
    {
      path: '/paper',
      name: 'paper',
      component: () => import('./views/PaperTradingView.vue'),
      meta: { title: '模拟交易', eyebrow: '真实行情 · 独立试验账本' },
    },
    {
      path: '/system',
      name: 'system',
      component: () => import('./views/SystemView.vue'),
      meta: { title: '系统', eyebrow: '运行状态' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '控制台')} · AI-QUANT`
})

export default router
