import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import {validInstrument} from './utils/marketNavigation'

const legacyDetail=(base:string)=>(to:RouteLocationNormalized)=>{
  const symbol=validInstrument(to.query.symbol)
  if(!symbol)return true
  const {symbol:ignored,...query}=to.query
  return {path:`${base}/${symbol}`,query,hash:to.hash}
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('./views/OverviewView.vue'),
      meta: { title: '市场总览', eyebrow: '全市场 · 机会发现 · 跨市场联动' },
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
      beforeEnter:legacyDetail('/market'),
      meta: { title: '行情市场', eyebrow: '浏览品种 · 了解价格变化',guide:'market' },
    },
    {
      path:'/market/:symbol',name:'instrument',component:()=>import('./views/InstrumentView.vue'),
      beforeEnter:to=>validInstrument(to.params.symbol)?true:{path:'/market'},
      meta:{title:'品种详情',eyebrow:'价格走势 · 数据来源',instrument:true,guide:'instrument'},
    },
    {
      path: '/strategy',
      name: 'strategy',
      component: () => import('./views/StrategyView.vue'),
      beforeEnter:legacyDetail('/strategy'),
      meta: { title: '研究工具', eyebrow: '了解方法 · 验证想法',guide:'strategy' },
    },
    {
      path:'/strategy/:symbol',name:'research',component:()=>import('./views/InstrumentResearchView.vue'),
      beforeEnter:to=>validInstrument(to.params.symbol)?true:{path:'/strategy'},
      meta:{title:'品种研究与计划',eyebrow:'依据 · 风险情景 · 复盘',instrument:true,guide:'research'},
    },
    {
      path:'/learn',name:'learn',component:()=>import('./views/LearnView.vue'),
      meta:{title:'学习与入门',eyebrow:'从看懂开始 · 用模拟练习'},
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
  scrollBehavior: to => to.hash ? {el:to.hash,top:16} : { top: 0 },
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '控制台')} · AI-QUANT`
})

export default router
