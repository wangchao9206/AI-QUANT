import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import {defineComponent,h,nextTick,ref} from 'vue'
import {authState,type Identity} from '../services/auth'

import AppShell from './AppShell.vue'
import { useMarketStore } from '../stores/market'

const View = { template: '<div>页面内容</div>' }

describe('AppShell', () => {
  it('provides desktop, mobile, and skip navigation', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path:'/today',component:View },
        { path:'/strategy/workflows',component:View },
        { path:'/paper/decisions',component:View },
        { path: '/overview', component: View, meta: { title: '总览', eyebrow: '今日决策' } },
        { path: '/leads', component: View, meta: { title: '线索池', eyebrow: '实时机会雷达' } },
        { path: '/market', component: View, meta: { title: '市场', eyebrow: '行情结构' } },
        { path: '/live', component: View },
        { path: '/options', component: View },
        { path: '/chanlun', component: View },
        { path: '/market/:symbol', component: View, meta: { instrument: true } },
        { path: '/learn', component: View },
        { path: '/research', component: View },
        { path: '/books', component: View },
        { path: '/personal', component: View },
        { path: '/news', component: View },
        { path: '/mentors', component: View },
        { path: '/strategy', component: View },
        { path: '/backtest', component: View },
        { path: '/paper', component: View },
        { path: '/system', component: View },
      ],
    })
    await router.push('/overview')
    await router.isReady()
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useMarketStore()
    store.catalog = {
      source: 'provider', dataStatus: 'FRESH', dataTimestamp: '2026-10-15T00:00:00Z',
      exchanges: [{ code: 'CFFEX', name: '中金所', instruments: [{ exchange: 'CFFEX', exchangeName: '中金所', name: '沪深300股指', node: 'if', rootSymbol: 'IF', mainSymbol: 'IFM', contracts: ['IF2610'] }] }],
    }
    store.symbol = 'IFM'

    const wrapper = mount(AppShell, { global: { plugins: [pinia, router] } })

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.get('h1').text()).toBe('总览')
    expect(wrapper.findAll('.nav-item').map(a=>a.text())).toEqual(['今日','机会','交易台','策略','复盘'])
    expect(wrapper.get('.nav-item[aria-label="交易台"]').attributes('href')).toBe('/live')
    expect(wrapper.get('.secondary-menu a[href="/books"]').text()).toBe('书籍感悟')
    expect(wrapper.find('.secondary-menu a[href="/mentors"]').exists()).toBe(true)
    expect(wrapper.find('.workspace-tabs a[href="/news"]').exists()).toBe(true)
    expect(wrapper.findAll('.mobile-nav__item')).toHaveLength(5)
    expect(wrapper.get('.nav-item.workspace-active').text()).toContain('机会')
    expect(wrapper.find('.instrument-trigger').exists()).toBe(false)
    expect(wrapper.get('.overview-scope').text()).toBe('全市场视图')
    expect(wrapper.findAll('.sidebar-instrument')).toHaveLength(1)
    expect(wrapper.get('.nav-item').attributes('href')).toBe('/today')
    await router.push('/options')
    expect(wrapper.get('.nav-item.workspace-active').text()).toBe('交易台')
    expect(wrapper.find('.workspace-tabs a[href="/chanlun"]').exists()).toBe(true)
    expect(wrapper.find('.workspace-tabs a[href="/paper"]').exists()).toBe(true)
    await router.push('/market')
    expect(wrapper.find('.instrument-trigger').exists()).toBe(false)
    await router.push('/market/IFM')
    expect(wrapper.get('.instrument-trigger').text()).toContain('IFM')
    wrapper.unmount()
  })
  it('discards private route state on account, tenant or permission changes and ignores old component responses',async()=>{
    const identity=(id:string,tenantId:string,permissions=['paper.read','market.read']):Identity=>({id,tenantId,permissions,username:id,email:null,platformAdmin:false,mustChangePassword:false,role:'MEMBER',tenants:[]})
    authState.user=identity('owner-a','workspace-a')
    let mounts=0;const delayed:(()=>void)[]=[]
    const Protected=defineComponent({setup(){const index=++mounts,value=ref('private-cache-'+index);delayed.push(()=>{value.value='late-private-cache-'+index});return()=>h('p',{class:'private-cache'},value.value)}})
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/paper',component:Protected}]});await router.push('/paper');await router.isReady()
    const pinia=createPinia();setActivePinia(pinia)
    const wrapper=mount(AppShell,{global:{plugins:[pinia,router],stubs:{TradingContextBar:true}}})
    try{
      expect(wrapper.get('.private-cache').text()).toBe('private-cache-1')
      authState.user=identity('owner-a','workspace-a',['market.read','paper.read']);await nextTick();expect(mounts).toBe(1)
      authState.user=identity('owner-b','workspace-a');await nextTick();expect(wrapper.get('.private-cache').text()).toBe('private-cache-2')
      delayed[0]!();await nextTick();expect(wrapper.get('.private-cache').text()).toBe('private-cache-2')
      authState.user=identity('owner-b','workspace-b');await nextTick();expect(wrapper.get('.private-cache').text()).toBe('private-cache-3')
      authState.user=identity('owner-b','workspace-b',['paper.read']);await nextTick();expect(wrapper.get('.private-cache').text()).toBe('private-cache-4')
      authState.user=null;await nextTick();expect(wrapper.get('.private-cache').text()).toBe('private-cache-5')
    }finally{wrapper.unmount();authState.user=null}
  })
})
