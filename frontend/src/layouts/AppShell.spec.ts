import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

import AppShell from './AppShell.vue'

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

    const wrapper = mount(AppShell, { global: { plugins: [router] } })

    expect(wrapper.get('.skip-link').attributes('href')).toBe('#main-content')
    expect(wrapper.get('h1').text()).toBe('总览')
    expect(wrapper.findAll('.nav-item')).toHaveLength(4)
    expect(wrapper.findAll('.mobile-nav__item')).toHaveLength(4)
    expect(wrapper.get('.nav-item.router-link-active').text()).toContain('总览')
  })
})
