import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import ExperienceSwitch from './ExperienceSwitch.vue'
import {useExperience} from '../composables/useExperience'
import {authState} from '../services/auth'
import {privateDocumentCacheKey} from '../composables/usePrivateDocument'
const mocks=vi.hoisted(()=>({read:vi.fn(),write:vi.fn()}))
vi.mock('../services/workspace',async original=>({...await original<typeof import('../services/workspace')>(),workspaceApi:mocks}))
beforeEach(()=>{localStorage.clear();authState.user={id:'owner-a',tenantId:'tenant-a',username:'fixture',email:null,platformAdmin:false,mustChangePassword:false,role:'MEMBER',tenants:[]};mocks.read.mockImplementation(async target=>({ownerId:'owner-a',tenantId:'tenant-a',kind:target.kind,key:target.key,revision:0,content:null}))})
afterEach(()=>{vi.restoreAllMocks();useExperience().setMode('SIMPLE');authState.user=null})
describe('experience preference',()=>{
  it('does not rewrite the previous owners draft when account mode listeners run synchronously',async()=>{
    const w=mount(ExperienceSwitch);await flushPromises();await w.findAll('button')[1]!.trigger('click')
    const key=privateDocumentCacheKey('owner-a','tenant-a','PREFERENCES'),before=localStorage.getItem(key)
    mocks.read.mockImplementation(async target=>({ownerId:'owner-b',tenantId:'tenant-a',kind:target.kind,key:target.key,revision:0,content:null}))
    authState.user={...authState.user!,id:'owner-b'};await flushPromises()
    expect(useExperience().mode.value).toBe('SIMPLE');expect(localStorage.getItem(key)).toBe(before);w.unmount()
  })
  it('defaults to simple mode and shares a saved preference between mounted controls',async()=>{
    const a=mount(ExperienceSwitch),b=mount(ExperienceSwitch)
    await flushPromises()
    expect(useExperience().isSimple.value).toBe(true)
    await a.findAll('button')[1]!.trigger('click')
    expect(b.findAll('button')[1]!.attributes('aria-pressed')).toBe('true')
    expect(localStorage.getItem('aiquant.experience.v2:owner-a:tenant-a')).toBe('PRO');expect(localStorage.getItem('aiquant.experience.v1')).toBeNull();expect(mocks.write).not.toHaveBeenCalled()
    a.unmount();b.unmount()
  })
  it('still switches this session and reports a blocked browser preference store',async()=>{
    const wrapper=mount(ExperienceSwitch)
    await flushPromises()
    vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked')})
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(useExperience().isSimple.value).toBe(false)
    expect(wrapper.text()).toContain('无法保存偏好')
    wrapper.unmount()
  })
})
