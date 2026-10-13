import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FreshnessBadge from './FreshnessBadge.vue'

describe('FreshnessBadge', () => {
  it.each([
    ['FRESH', '实时'],
    ['CACHED', '缓存'],
    ['DEGRADED', '降级'],
  ] as const)('renders %s as a non-color-only label', (status, label) => {
    const wrapper = mount(FreshnessBadge, { props: { status } })

    expect(wrapper.text()).toContain(label)
    expect(wrapper.classes()).toContain(`freshness--${status.toLowerCase()}`)
  })
})
