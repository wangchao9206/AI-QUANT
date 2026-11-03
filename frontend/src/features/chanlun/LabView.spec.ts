import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import LabView from './LabView.vue'
import {labApi,type LabExperiment} from './lab'
vi.mock('./lab',()=>({labApi:{recent:vi.fn(),create:vi.fn(),get:vi.fn()}}))
const id='11111111-1111-4111-8111-111111111111'
function experiment():LabExperiment{return {id,status:'SUCCEEDED',error:null,createdAt:'2026-10-31',request:{clientRequestId:id,group:'THIRD',initialCash:1000000},report:{engineVersion:'v1',configHash:'config',config:{group:'THIRD',initialCash:1000000,profileHash:'profile',datasetHash:'dataset',implementationHash:'code',window:['2019','2026']},candidateTape:[],invalidationObservations:{},variants:['NATIVE_BASE','NATIVE_DOUBLE_COST','NATIVE_DELAY_ONE','RANGE_RETEST','CHANNEL_BREAKOUT'].map((id,i)=>({id,metrics:{initialCash:1000000,finalEquity:999000-i,netPnl:-1000-i,returnPct:-.1,maxDrawdownPct:1,closedTrades:1,winRatePct:0,fees:2,slippageCost:20,overBudgetExits:0,denials:{}},trades:[],decisions:[],excluded:[],curve:[]})),assumptions:['冻结历史，不是前向业绩'],executable:false}}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.resetAllMocks();vi.mocked(labApi.recent).mockResolvedValue([]);vi.mocked(labApi.create).mockResolvedValue(experiment());vi.mocked(labApi.get).mockResolvedValue(experiment())})
afterEach(()=>wrapper?.unmount())
async function setup(path='/chanlun/lab'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/lab',component:LabView},...['workbench','compare','replay','academy','judgments','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div />'}}))]})
  await router.push(path);await router.isReady();wrapper=mount(LabView,{global:{plugins:[router],stubs:{ChanlunReader:true}}});await flushPromises();return router
}
describe('native cost lab',()=>{
  it('runs only on explicit action and displays all five scenarios including losses',async()=>{
    await setup();expect(labApi.create).not.toHaveBeenCalled();await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(labApi.create).toHaveBeenCalledWith(expect.objectContaining({group:'THIRD',initialCash:1000000}))
    expect(wrapper!.findAll('.results> .scroll tbody tr')).toHaveLength(5)
    expect(wrapper!.text()).toContain('-1,000.00');expect(wrapper!.text()).toContain('双倍费用与滑点');expect(wrapper!.text()).toContain('普通直接突破')
  })
  it('restores frozen report from URL without recalculating',async()=>{
    await setup(`/chanlun/lab?experiment=${id}`);expect(labApi.get).toHaveBeenCalledWith(id);expect(labApi.create).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('冻结历史，不是前向业绩')
  })
  it('shows the first observation date and later invalidation and reads the original locally',async()=>{
    const value=experiment();value.report!.candidateTape=[{structureId:'candidate',source:'B3',confirmedIndex:100,pivotIndex:95,invalidation:3000,direction:1,firstObservationDate:'2019-06-01',pivotDate:'2019-05-25',evidence:{referenceLessons:[21]}}];value.report!.invalidationObservations={candidate:110};vi.mocked(labApi.get).mockResolvedValue(value)
    await setup(`/chanlun/lab?experiment=${id}`);expect(wrapper!.text()).toContain('首次观察 2019-06-01');expect(wrapper!.text()).toContain('后来失效，观察索引 110')
    await wrapper!.findAll('button').find(b=>b.text()==='阅读对应原文')!.trigger('click');expect(wrapper!.find('chanlun-reader-stub').attributes('initialchapter')).toBe('21');expect(wrapper!.find('iframe').exists()).toBe(false)
  })
  it('reuses the same command after an uncertain network response',async()=>{
    vi.mocked(labApi.create).mockRejectedValueOnce(new Error('连接中断'));await setup()
    await wrapper!.get('form').trigger('submit');await flushPromises();const original=vi.mocked(labApi.create).mock.calls[0]![0]
    expect(wrapper!.get('[role=alert]').text()).toContain('沿用同一请求编号')
    await wrapper!.get('form').trigger('submit');await flushPromises();expect(vi.mocked(labApi.create).mock.calls[1]![0]).toEqual(original)
  })
})
