import {mount} from '@vue/test-utils'
import {afterEach,describe,it,expect,vi} from 'vitest'
import ExperienceSwitch from './ExperienceSwitch.vue'
import {useExperience} from '../composables/useExperience'
afterEach(()=>{vi.restoreAllMocks();useExperience().setMode('SIMPLE')})
describe('experience preference',()=>{
  it('defaults to simple mode and shares a saved preference between mounted controls',async()=>{
    const a=mount(ExperienceSwitch),b=mount(ExperienceSwitch)
    expect(useExperience().isSimple.value).toBe(true)
    await a.findAll('button')[1]!.trigger('click')
    expect(b.findAll('button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(localStorage.getItem('aiquant.experience.v1')).toBe('PRO')
    a.unmount();b.unmount()
  })
  it('still switches this session and reports a blocked browser preference store',async()=>{
    const wrapper=mount(ExperienceSwitch)
    vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked')})
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(useExperience().isSimple.value).toBe(false)
    expect(wrapper.text()).toContain('无法保存偏好')
    wrapper.unmount()
  })
})
