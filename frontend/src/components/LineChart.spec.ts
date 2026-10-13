import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LineChart from './LineChart.vue'

describe('LineChart', () => {
  it('exposes an accessible label and renders finite points', () => {
    const wrapper = mount(LineChart, { props: { values: [10, 10, 12], label: '价格走势' } })
    expect(wrapper.get('svg').attributes('aria-label')).toBe('价格走势')
    expect(wrapper.get('polyline').attributes('points')).not.toContain('NaN')
  })
})
