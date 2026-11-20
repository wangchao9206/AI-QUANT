import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import type { FlowGraph } from '../services/workflows'
import { chanTemplate, customTemplate, template } from '../utils/workflowGraph'
import WorkflowRuleForm from './WorkflowRuleForm.vue'

describe('guided workflow rules', () => {
  test('updates a connected indicator and retains all graph links', async () => {
    const graph = customTemplate()
    const wrapper = mount(WorkflowRuleForm, { props: { graph } })

    expect(wrapper.get('section[aria-label="入场规则"]').text()).toContain('20 日')
    expect(wrapper.get('section[aria-label="退出规则"]').text()).toContain('没有单独的平仓信号')
    await wrapper.get('input[min="2"][max="250"]').setValue('30')

    const next = wrapper.emitted('update:graph')?.[0]?.[0] as FlowGraph
    expect(next.nodes.find(node => node.type === 'INDICATOR')?.params.period).toBe(30)
    expect(graph.nodes.find(node => node.type === 'INDICATOR')?.params.period).toBe(20)
    expect(next.edges).toEqual(graph.edges)
    expect(next.edges).not.toBe(graph.edges)
    await wrapper.setProps({ graph: next })
    expect(wrapper.get('section[aria-label="入场规则"]').text()).toContain('30 日')
  })

  test('shows the new preset in action rules without changing connections', async () => {
    const graph = template()
    const wrapper = mount(WorkflowRuleForm, { props: { graph } })

    await wrapper.get('select').setValue('BOLLINGER_REVERSAL')

    const next = wrapper.emitted('update:graph')?.[0]?.[0] as FlowGraph
    expect(next.edges).toEqual(graph.edges)
    await wrapper.setProps({ graph: next })
    expect(wrapper.get('section[aria-label="入场规则"]').text()).toContain('布林均值回归')
    expect(wrapper.get('section[aria-label="退出规则"]').text()).toContain('布林均值回归')
  })

  test('changes a Chan candidate filter without overwriting its bound profile', async () => {
    const graph = chanTemplate({profileVersion: 'frozen-version', priceBasis: 'DELIVERY'})
    const wrapper = mount(WorkflowRuleForm, { props: { graph } })

    await wrapper.get('select').setValue('ALL')

    const next = wrapper.emitted('update:graph')?.[0]?.[0] as FlowGraph
    expect(next.schemaVersion).toBe(2)
    expect(next.nodes.find(node => node.type === 'CHAN_SIGNAL')?.params)
      .toEqual({ profileVersion: 'frozen-version', priceBasis: 'DELIVERY', group: 'ALL' })
    expect(next.edges).toEqual(graph.edges)
  })

  test('guides bad links to the canvas and does not commit invalid or disabled risk edits', async () => {
    const graph = customTemplate()
    graph.edges = graph.edges.filter(edge => edge.target !== 'compare' || edge.targetPort !== 'left')
    const wrapper = mount(WorkflowRuleForm, { props: { graph } })

    expect(wrapper.text()).toContain('高级画布')
    expect(wrapper.find('input[min="2"][max="250"]').exists()).toBe(false)
    const lots = wrapper.get<HTMLInputElement>('input[min="1"][max="1000000"]')
    await lots.setValue('0')
    expect(wrapper.get('[role="alert"]').text()).toContain('开仓手数')
    expect(lots.element.value).toBe('1')
    await wrapper.setProps({ disabled: true })
    await lots.setValue('3')
    expect(wrapper.emitted('update:graph')).toBeUndefined()
  })
})
