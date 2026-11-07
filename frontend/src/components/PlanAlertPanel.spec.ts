import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest'
import {authState} from '../services/auth'
import PlanAlertPanel from './PlanAlertPanel.vue'
import PlanAlertFeed from './PlanAlertFeed.vue'
const mocks=vi.hoisted(()=>({read:vi.fn(),edit:vi.fn(),events:vi.fn(),ack:vi.fn()}))
vi.mock('../services/planAlerts',()=>({planAlertsApi:mocks}))
const sub={revision:1,enabled:true,entryMode:'BREAKOUT',status:'STARTING',message:'未补发历史触发',checkedAt:null}
const event={id:'e1',caseId:'c1',planId:'p1',version:1,symbol:'RB2701',kind:'ENTRY',observedAt:'2026-11-07T00:00:00Z',createdAt:'2026-11-07T00:00:01Z',acknowledgedAt:null,evidence:{confirmation:'OBSERVED_PRICE_CROSS',quote:{price:100}}}
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{vi.clearAllMocks();vi.useFakeTimers();authState.user={id:'u1',tenantId:'t1',username:'user',email:null,role:'MEMBER',tenants:[],platformAdmin:false,mustChangePassword:false,permissions:['market.read','paper.read','paper.write']};mocks.read.mockResolvedValue({subscription:null,events:[]});mocks.edit.mockResolvedValue({subscription:sub,events:[]});mocks.events.mockResolvedValue({items:[event],total:1,page:1,size:20});mocks.ack.mockResolvedValue({})})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());authState.user=null;vi.useRealTimers()})
async function setup(feed=false){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div/>'}},{path:'/paper/decisions/:id',component:{template:'<div/>'}}]});await router.push('/');const w=mount(feed?PlanAlertFeed:PlanAlertPanel,{props:feed?{}:{caseId:'c1',planId:'p1',editable:true},global:{plugins:[router]}});wrappers.push(w);await flushPromises();return w}
describe('private plan alerts',()=>{
 it('explicitly enables a saved plan with selected entry mode and revision',async()=>{const w=await setup();await w.find('select').setValue('PULLBACK');await w.findAll('button').find(b=>b.text()==='启用本计划提醒')!.trigger('click');await flushPromises();expect(mocks.edit).toHaveBeenCalledWith('c1','p1',true,'PULLBACK',0);expect(w.text()).toContain('暂停本计划提醒');expect(w.text()).toContain('不代表逐笔触达')})
 it('blocks starting with dirty/historical plans but permits pausing an existing subscription',async()=>{mocks.read.mockResolvedValue({subscription:sub,events:[]});const w=await setup();await w.setProps({editable:false});await w.findAll('button').find(b=>b.text()==='暂停本计划提醒')!.trigger('click');await flushPromises();expect(mocks.edit).toHaveBeenCalledWith('c1','p1',false,'BREAKOUT',1)})
 it('does not offer mutation controls to read-only users',async()=>{authState.user!.permissions=['market.read','paper.read'];const w=await setup();expect(w.findAll('button').some(b=>b.text().includes('启用本计划'))).toBe(false)})
 it('clears private data when identity changes and rejects late results',async()=>{let resolve!:(v:unknown)=>void;mocks.read.mockReturnValueOnce(new Promise(r=>resolve=r));const w=await setup();authState.user={...authState.user!,tenantId:'t2',permissions:[]};await flushPromises();resolve({subscription:sub,events:[event]});await flushPromises();expect(w.text()).not.toContain('入场参考穿越');expect(w.text()).toContain('需要行情与档案读取权限')})
 it('shows authoritative event links and acknowledges server records',async()=>{const w=await setup(true);expect(w.find('a').attributes('href')).toBe('/paper/decisions/c1?plan=p1');await w.findAll('button').find(b=>b.text()==='标记已读')!.trigger('click');await flushPromises();expect(mocks.ack).toHaveBeenCalledWith('e1');expect(w.text()).toContain('不表示已成交')})
 it('keeps feed failures visible without claiming no unread alerts',async()=>{mocks.events.mockRejectedValue(new Error('提醒服务不可用'));const w=await setup(true);expect(w.get('[role="alert"]').text()).toContain('提醒服务不可用');expect(w.text()).not.toContain('暂无未读')})
})
