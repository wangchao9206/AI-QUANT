import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import LearnView from './LearnView.vue'
describe('learning tools',()=>{
  it('compares long and short gains and losses without changing margin, and explains quiz answers',async()=>{
    const wrapper=mount(LearnView,{global:{stubs:{RouterLink:true}}})
    await wrapper.get('input[type="range"]').setValue('5')
    expect(wrapper.get('.example-output').text()).toContain('+50.00 元')
    await wrapper.get('select').setValue('SHORT')
    expect(wrapper.get('.example-output').text()).toContain('-50.00 元')
    expect(wrapper.get('.example-output').text()).toContain('200.00 元')
    await wrapper.findAll('.quiz-grid button')[0]!.trigger('click')
    expect(wrapper.get('.revisit').text()).toContain('不是最大亏损承诺')
    await wrapper.findAll('.quiz-grid button')[1]!.trigger('click')
    expect(wrapper.get('.understood').text()).toContain('理解正确')
    wrapper.unmount()
  })
})
