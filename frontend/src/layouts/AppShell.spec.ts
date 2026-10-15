import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

import AppShell from './AppShell.vue'
import { useMarketStore } from '../stores/market'

const View = { template: '<div>页面内容</div>' }

describe('AppShell', () => {
  it('provides desktop, mobile, and skip navigation', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/overview', component: View, meta: { title: '总览', eyebrow: '今日决策' } },
        { path: '/market', component: View, meta: { title: '市场', eyebrow: '行情结构' } },
        { path: '/strategy', component: View },
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
    expect(wrapper.findAll('.nav-item')).toHaveLength(4)
    expect(wrapper.findAll('.mobile-nav__item')).toHaveLength(4)
    expect(wrapper.get('.nav-item.router-link-active').text()).toContain('总览')
    expect(wrapper.get('.instrument-trigger').text()).toContain('IFM')
    expect(wrapper.findAll('.sidebar-instrument')).toHaveLength(1)
    expect(wrapper.get('.nav-item').attributes('href')).toContain('symbol=IFM')
  })
})
