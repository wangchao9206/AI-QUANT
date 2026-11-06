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
    {path:'/admin',name:'administration',component:()=>import('./views/AdminView.vue'),meta:{standalone:true,title:'后台管理'}},
    {path:'/access-denied',name:'access-denied',component:()=>import('./views/AccessDeniedView.vue'),meta:{standalone:true,title:'暂无访问权限'}},
    ...['login','register','verify','verify-email','forgot','reset','resend'].map(mode=>({path:`/auth/${mode}`,name:`auth-${mode}`,component:()=>import('./views/AuthView.vue'),meta:{public:true,title:'账号与验证'}})),
    {path:'/auth/change-password',component:()=>import('./views/AuthView.vue'),meta:{title:'修改初始密码'}},
    {path:'/account',name:'account',component:()=>import('./views/AccountView.vue'),meta:{title:'账号与工作空间',eyebrow:'安全 · 成员 · 平台接入'}},
    {path:'/chanlun',redirect:'/chanlun/workbench'},
    {path:'/chanlun/replay',name:'chanlun-replay',component:()=>import('./features/chanlun/ReplayView.vue'),meta:{title:'缠论中心',eyebrow:'逐根训练 · 先判断再展开 · 当时证据'}},
    {path:'/chanlun/radar',name:'chanlun-radar',component:()=>import('./features/chanlun/RadarView.vue'),meta:{title:'缠论中心',eyebrow:'后台监控 · 已封存行情 · 候选证据'}},
    {path:'/chanlun/multiframe',name:'chanlun-multiframe',component:()=>import('./features/chanlun/MultiframeView.vue'),meta:{title:'缠论中心',eyebrow:'独立原始周期 · 共同重建界限 · 冻结观察'}},
    {path:'/chanlun/reviews',name:'chanlun-reviews',component:()=>import('./features/chanlun/MonitorReviewsView.vue'),meta:{title:'缠论中心',eyebrow:'监控复盘 · 当时证据 · 原文引用'}},
    {path:'/chanlun/lab',name:'chanlun-lab',component:()=>import('./features/chanlun/LabView.vue'),meta:{title:'缠论中心',eyebrow:'策略实验 · 真实合约 · 成本与对照'}},
    {path:'/chanlun/compare',name:'chanlun-compare',component:()=>import('./features/chanlun/CompareView.vue'),meta:{title:'缠论中心',eyebrow:'首次分歧 · 观察事件 · 原文取证'}},
    ...['workbench','academy','judgments','settings'].map(tab=>({path:`/chanlun/${tab}`,name:`chanlun-${tab}`,component:()=>import('./features/chanlun/ChanlunView.vue'),meta:{title:'缠论中心',eyebrow:'结构 · 当时证据 · 原文 · 独立判断'}})),
    {path:"/research",name:"research-library",component:()=>import("./views/ResearchLibraryView.vue"),meta:{title:"自主研究",eyebrow:"真实日线 · 失败复盘 · 新数据观察"}},
    {path:'/books',name:'books',component:()=>import('./views/BookReflectionsView.vue'),meta:{title:'书籍感悟',eyebrow:'阅读 · 独立思考 · 实践与反思'}},
    {path:'/personal',name:'personal',component:()=>import('./views/PersonalSummaryView.vue'),meta:{title:'个人总结',eyebrow:'生存优先 · 规则训练 · 持续复盘'}},
    {path:'/mentors',name:'mentors',component:()=>import('./views/MentorsView.vue'),meta:{title:'大佬解读',eyebrow:'真实人物 · 实盘证据 · 可借鉴性'}},
    {path:'/news',name:'news',component:()=>import('./views/NewsView.vue'),meta:{title:'消息与事件',eyebrow:'原始发布 · 条件解读 · 历史溯源'}},
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
    {path:'/strategy/workflows',name:'workflows',component:()=>import('./views/StrategyWorkflowView.vue'),meta:{title:'策略工作流',eyebrow:'可视化编排 · 节点试算 · 版本化运行'}},
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
    {path:'/live',name:'live',component:()=>import('./views/LiveView.vue'),meta:{title:'实盘看盘',eyebrow:'小周期 K 线 · 真实盘口 · 成交雷达'}},
    {path:'/options',name:'options',component:()=>import('./views/OptionsView.vue'),meta:{title:'期权研究',eyebrow:'真实期权链 · 波动率 · 到期风险'}},
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
