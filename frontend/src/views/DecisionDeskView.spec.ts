import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import DecisionDeskView from './DecisionDeskView.vue'
import type {DecisionCase} from '../services/decisions'
const mocks=vi.hoisted(()=>({detail:vi.fn(),list:vi.fn(),save:vi.fn(),check:vi.fn(),paper:vi.fn(),review:vi.fn(),bars:vi.fn(),write:true}))
vi.mock('../services/decisions',()=>({decisionsApi:mocks}))
vi.mock('../services/live',async original=>({...await original<typeof import('../services/live')>(),liveApi:{bars:mocks.bars}}))
vi.mock('../services/auth',()=>({hasPermission:(p:string)=>!p.endsWith('.write')||mocks.write}))
const stamp='2026-11-06T07:00:00Z'
const seed:DecisionCase={id:'case-one',symbol:'RB2701',version:1,createdAt:stamp,updatedAt:stamp,origin:{id:42,monitorId:'monitor',rule:'LINES',label:'原通道条件',symbol:'RB2701',assetType:'FUTURE',observedAt:stamp,createdAt:stamp,acknowledgedAt:null,algorithmVersion:'frozen-v1',evidence:{triggerSeconds:900,featureAt:stamp,availableAt:stamp}},plans:[{id:'plan-v1',version:1,createdAt:stamp,fields:{side:'LONG',entry:100,stop:98,target:105,lots:1,equity:100000,budget:1000,hypothesis:'原判断',invalidation:'保护条件失效',validUntil:'2030-01-01T00:00:00Z'}}],reviews:[],paper:[]}
const wrappers:ReturnType<typeof mount>[]=[]
async function setup(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/paper/decisions/:id?',component:DecisionDeskView},{path:'/paper',component:{template:'<div/>'}},{path:'/live',component:{template:'<div/>'}}]});await router.push('/paper/decisions/case-one');await router.isReady();const w=mount(DecisionDeskView,{global:{plugins:[router],stubs:{TongdaxinChart:{props:['points'],template:'<div data-test="chart">{{points.map(p=>p.timestamp).join(",")}}</div>'}}}});wrappers.push(w);await flushPromises();return {w,router}}
beforeEach(()=>{vi.clearAllMocks();mocks.write=true;mocks.detail.mockResolvedValue(structuredClone(seed));mocks.bars.mockResolvedValue({symbol:'RB2701',seconds:900,points:[{timestamp:stamp,price:100},{timestamp:'2026-11-06T07:15:00Z',price:110}]});mocks.check.mockResolvedValue({planId:'plan-v1',version:1,ready:true,reasons:[],meaning:'仅手动模拟',checkedAt:stamp})})
afterEach(()=>wrappers.splice(0).forEach(w=>w.unmount()))
const button=(w:ReturnType<typeof mount>,text:string)=>w.findAll('button').find(b=>b.text()===text)!
describe('decision desk',()=>{
 it('reconstructs only the original cutoff and separates the current view',async()=>{const {w}=await setup();expect(w.get('[data-test="chart"]').text()).toBe(stamp);await button(w,'现在').trigger('click');expect(w.get('[data-test="chart"]').text()).toContain('07:15:00');expect(w.text()).toContain('frozen-v1');await button(w,'当时').trigger('click');expect(w.text()).toContain('不是触发时保存的完整行情快照')})
 it('invalidates readiness when editing and saves a new expected version with a stable command',async()=>{const {w}=await setup();await button(w,'核验当前保存版本').trigger('click');await flushPromises();expect(button(w,'创建关联的手动模拟账户').attributes('disabled')).toBeUndefined();const input=w.findAll('input').find(n=>n.element.value==='1000')!;await input.setValue('100');expect(button(w,'创建关联的手动模拟账户').attributes('disabled')).toBeDefined();mocks.save.mockRejectedValue(new Error('计划已被另一页面修改'));await w.findAll('form').at(-1)!.trigger('submit');await flushPromises();expect(mocks.save).toHaveBeenCalledWith('case-one',1,expect.objectContaining({budget:100}),expect.any(String));expect(w.text()).toContain('另一页面修改');expect(mocks.paper).not.toHaveBeenCalled()})
 it('keeps review-only users read-only and preserves original evidence',async()=>{mocks.write=false;const {w}=await setup();expect(w.get('fieldset').attributes('disabled')).toBeDefined();expect(w.findAll('button').some(b=>b.text()==='核验当前保存版本')).toBe(false);expect(w.text()).toContain('原事件 #42');expect(mocks.paper).not.toHaveBeenCalled()})
})
