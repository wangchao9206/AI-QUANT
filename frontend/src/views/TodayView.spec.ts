import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import {authState} from '../services/auth'
import TodayView from './TodayView.vue'
const mocks=vi.hoisted(()=>({inbox:vi.fn()}))
vi.mock('../services/decisions',()=>({decisionsApi:mocks}))
const stamp='2026-11-07T02:00:00Z'
const empty=()=>({asOf:stamp,counts:{all:0,unplanned:0,expiring:0,expired:0,review:0},total:0,page:1,size:20,filter:'ALL',items:[]})
const task={id:'case-1',symbol:'RB2701',label:'原始突破观察',sourceKind:'MONITOR_EVENT',updatedAt:stamp,planId:'p1',version:1,validUntil:'2026-11-07T04:00:00Z',sessionId:'s1',latestOutcome:null,reviewedAt:null,timing:'EXPIRING',needsReview:true}
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{vi.clearAllMocks();authState.user={id:'owner',tenantId:'tenant',username:'owner',email:null,role:'VIEWER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['paper.read','market.read']};mocks.inbox.mockResolvedValue(empty())})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());authState.user=null})
async function setup(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/today',component:TodayView},{path:'/paper/:pathMatch(.*)*',component:{template:'<div/>'}},{path:'/market',component:{template:'<div/>'}},{path:'/live',component:{template:'<div/>'}}]});await router.push('/today');const w=mount(TodayView,{global:{plugins:[router]}});wrappers.push(w);await flushPromises();return w}
describe('today task desk',()=>{
 it('shows an honest empty state and scope',async()=>{const w=await setup();expect(mocks.inbox).toHaveBeenCalledWith('ALL',1);expect(w.text()).toContain('还没有保存的决策档案');expect(w.text()).toContain('不含外部账户');expect(w.get('a[href="/paper/decisions"]').text()).toContain('打开我的档案')})
 it('links the exact plan context and requests server-side filters',async()=>{mocks.inbox.mockResolvedValueOnce({...empty(),counts:{all:31,unplanned:29,expiring:2,expired:0,review:1},total:31,items:[task]});const w=await setup();expect(w.get('.task-title').attributes('href')).toBe('/paper/decisions/case-1');expect(w.get('a[href^="/paper?"]').attributes('href')).toContain('session=s1');expect(w.text()).toContain('不表示已经成交或平仓');mocks.inbox.mockResolvedValue({...empty(),counts:{...empty().counts,all:31},filter:'REVIEW'});await w.findAll('.task-counts button')[3]!.trigger('click');await flushPromises();expect(mocks.inbox).toHaveBeenLastCalledWith('REVIEW',1);expect(w.text()).toContain('这一类暂时没有待办')})
 it('shows failures without reporting zero tasks and retries',async()=>{mocks.inbox.mockRejectedValueOnce(new Error('待办服务不可用'));const w=await setup();expect(w.get('[role="alert"]').text()).toContain('待办服务不可用');expect(w.get('.task-counts strong').text()).toBe('—');await w.findAll('button').find(b=>b.text()==='重新载入')!.trigger('click');await flushPromises();expect(w.text()).toContain('还没有保存的决策档案')})
 it('does not fetch private data for a user without both permissions',async()=>{authState.user!.permissions=['paper.read'];const w=await setup();expect(mocks.inbox).not.toHaveBeenCalled();expect(w.text()).toContain('暂不能读取决策待办')})
 it('clears old identity data and ignores late results when workspace changes',async()=>{let resolve!:(v:unknown)=>void;mocks.inbox.mockReturnValueOnce(new Promise(r=>resolve=r));const w=await setup();authState.user={...authState.user!,tenantId:'another',permissions:[]};await flushPromises();resolve({...empty(),items:[task],total:1});await flushPromises();expect(w.text()).not.toContain('原始突破观察');expect(w.text()).toContain('暂不能读取决策待办')})
 it('rejects malformed summaries before rendering them',async()=>{mocks.inbox.mockResolvedValue({items:[],total:0});const w=await setup();expect(w.get('[role="alert"]').text()).toContain('数据结构异常');expect(w.text()).not.toContain('还没有保存的决策档案')})
})
