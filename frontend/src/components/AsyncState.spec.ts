import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AsyncState from './AsyncState.vue'

describe('AsyncState', () => {
  it('announces loading state', () => {
    const wrapper = mount(AsyncState, { props: { state: 'loading' } })
    expect(wrapper.get('[role="status"]').attributes('aria-label')).toBe('正在加载')
  })

  it('renders an explicit empty state', () => {
    const wrapper = mount(AsyncState, { props: { state: 'empty', emptyTitle: '没有历史行情' } })
    expect(wrapper.text()).toContain('没有历史行情')
  })

  it('emits retry from the error state', async () => {
    const wrapper = mount(AsyncState, { props: { state: 'error' } })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('renders content when ready', () => {
    const wrapper = mount(AsyncState, {
      props: { state: 'ready' },
      slots: { default: '<p>可信结果</p>' },
    })
    expect(wrapper.text()).toContain('可信结果')
  })
})
