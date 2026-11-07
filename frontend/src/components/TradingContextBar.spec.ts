import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest'
import {authState} from '../services/auth'
import TradingContextBar from './TradingContextBar.vue'
const mocks=vi.hoisted(()=>({detail:vi.fn(),forSession:vi.fn(),paperSession:vi.fn()}))
vi.mock('../services/decisions',()=>({decisionsApi:mocks}))
vi.mock('../services/api',async original=>({...await original<typeof import('../services/api')>(),api:{paperSession:mocks.paperSession}}))
const id=(n:number)=>'10000000-0000-4000-8000-'+String(n).padStart(12,'0'),stamp='2026-11-07T00:00:00Z'
const seed=()=>({id:id(1),symbol:'RB2701',version:2,origin:{id:42,label:'原始观察',observedAt:stamp,evidence:{triggerSeconds:900}},plans:[{id:id(2),version:2,fields:{}},{id:id(3),version:1,fields:{}}],paper:[{planId:id(3),sessionId:id(4),version:1}],reviews:[],sources:[]})
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{vi.clearAllMocks();authState.user={id:id(9),tenantId:id(10),username:'user',email:null,role:'MEMBER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['market.read','research.read','options.read','paper.read']};mocks.detail.mockResolvedValue(seed());mocks.paperSession.mockResolvedValue({id:id(4),symbol:'RBM',currentContract:'RB2701',mode:'HISTORICAL'});mocks.forSession.mockResolvedValue({caseId:id(1),planId:id(3),version:1})})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());authState.user=null})
async function setup(url:string){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/live',name:'live',component:{template:'<div/>'}},{path:'/paper',component:{template:'<div/>'}},{path:'/strategy/:symbol',name:'research',component:{template:'<div/>'}},{path:'/market/:symbol',name:'instrument',component:{template:'<div/>'}},{path:'/paper/decisions/:id',name:'decision-desk',component:{template:'<div/>'}}]});await router.push(url);const w=mount(TradingContextBar,{global:{plugins:[router]}});wrappers.push(w);await flushPromises();return {w,router}}
describe('verified trading object',()=>{
 it('carries the exact historical plan and chart period into research and chart links',async()=>{const {w}=await setup('/live?symbol=RB2701&period=900&case='+id(1)+'&plan='+id(3));expect(w.text()).toContain('计划 v1');const link=w.findAll('a').find(a=>a.text()==='研究与判断')!;expect(link.attributes('href')).toContain('period=900');expect(link.attributes('href')).toContain('plan='+id(3));expect(w.text()).toContain('15 分钟')})
 it('does not carry a prior plan to another delivery month',async()=>{const {w}=await setup('/live?symbol=RB2705&case='+id(1)+'&plan='+id(3));expect(w.text()).toContain('当前合约不同');expect(w.findAll('a').find(a=>a.text()==='研究与判断')!.attributes('href')).not.toContain('case=')})
 it('uses the authoritative session association and explains a historical-to-live transition',async()=>{const {w}=await setup('/paper?session='+id(4)+'&case='+id(8)+'&plan='+id(7));expect(mocks.detail).toHaveBeenCalledWith(id(1));expect(w.text()).toContain('计划 v1');expect(w.text()).toContain('模拟账本仍保留原回放时点');expect(w.findAll('a').some(a=>a.text()==='查看当前行情')).toBe(true)})
 it('never promotes an unverified URL decision reference into a session association',async()=>{mocks.forSession.mockResolvedValue({});const {w}=await setup('/paper?session='+id(4)+'&case='+id(8)+'&plan='+id(7));expect(mocks.detail).not.toHaveBeenCalled();expect(w.text()).not.toContain('计划 v');expect(w.findAll('a').some(a=>a.text().startsWith('返回计划'))).toBe(false)})
 it('shows a missing version instead of using the latest saved plan',async()=>{const {w}=await setup('/paper/decisions/'+id(1)+'?plan='+id(8));expect(w.get('[role="alert"]').text()).toContain('指定计划版本不在此档案中');expect(w.find('nav').exists()).toBe(false)})
 it('discards a late private response after an identity change',async()=>{let resolve!:(v:unknown)=>void;mocks.detail.mockReturnValueOnce(new Promise(r=>resolve=r));const {w}=await setup('/live?symbol=RB2701&case='+id(1));authState.user={...authState.user!,tenantId:id(8),permissions:[]};await flushPromises();resolve(seed());await flushPromises();expect(w.text()).not.toContain('原档案：');expect(w.text()).toContain('不能核验关联档案')})
})
