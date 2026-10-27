import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {describe,it,expect,vi,beforeEach} from 'vitest'
import ResearchLibraryView from './ResearchLibraryView.vue'
const mocks=vi.hoisted(()=>({catalog:vi.fn(),detail:vi.fn(),runs:vi.fn(),run:vi.fn(),observation:vi.fn(),asset:vi.fn(()=>'/asset')}))
vi.mock('../services/researchLibrary',()=>({researchLibrary:mocks}))
const metrics={initialCash:1000000,finalEquity:990000,returnPct:-1,maxDrawdownPct:2,closedTrades:1}
const row={id:1,stage:'VALIDATION',family:'RANGE_REVERSION',mode:'REGIME_EXIT',scale:1,capital:1000000,cost:1,metrics}
const summary=(id:string)=>({id,title:id==='fu-regime'?'燃油第二轮':'多品种初筛',badge:'事后探索',count:116,defaultFamily:'RANGE_REVERSION',scope:'FU',conclusion:'未通过门槛'})
const detail=(id:string)=>({...summary(id),revision:'abc',assets:[],filters:{family:['RANGE_REVERSION'],capital:[10000,1000000],stage:['VALIDATION'],cost:[1,2],symbol:['FU0']},comparisons:[row],results:{},report:'# 完整报告\n\n保留全部失败。',reportLinks:{},journal:[],observation:id==='fu-regime'})
async function setup(query=''){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/research',component:ResearchLibraryView}]})
  await router.push('/research'+query);await router.isReady()
  const wrapper=mount(ResearchLibraryView,{global:{plugins:[router],stubs:{ResearchEquity:true}}});await flushPromises();return {wrapper,router}
}
beforeEach(()=>{
  vi.clearAllMocks()
  mocks.catalog.mockResolvedValue({revision:'abc',date:'2026-10-27',totalRuns:1390,qualifiedCount:0,studies:[summary('fu-regime'),summary('daily-screen')]})
  mocks.detail.mockImplementation(async(id:string)=>detail(id))
  mocks.runs.mockResolvedValue({total:116,items:[row]})
  mocks.run.mockResolvedValue({...row,curve:[{date:'2025-01-02',equity:990000}],trades:[{entryDate:'2025-01-02',exitDate:'2025-01-03',contract:'FU2505',direction:-1,lots:1,entryPrice:3200,exitPrice:3300,netPnl:-1001,exitReason:'STOP'}],decisions:[]})
  mocks.observation.mockResolvedValue({message:'刷新只读取已保存记录',state:{asOf:'2026-10-27',revision:0,cash:1000000,equity:1000000,trades:[],curve:[],events:[],config:{initialCash:1000000},position:null,ordersSubmittedToBroker:0,nextSignal:{signal:'HOLD',reason:'等待',maxPlannedEntryLots:0,nodeTrace:[]},configHash:'hash'}})
})
describe('research library',()=>{
  it('opens actual scenario ledger, keeps losses and paginates without writing',async()=>{
    const {wrapper}=await setup()
    expect(wrapper.text()).toContain('1,390')
    await wrapper.get('[aria-label="查看场景 1 账本"]').trigger('click');await flushPromises()
    expect(mocks.run).toHaveBeenCalledWith('fu-regime','abc',1)
    expect(wrapper.get('.run-detail').text()).toContain('FU2505')
    expect(wrapper.get('.run-detail').text()).toContain('-1,001.00')
    await wrapper.get('.pagination button:last-child').trigger('click');await flushPromises()
    expect(mocks.runs.mock.lastCall?.[2].page).toBe(6)
    await wrapper.get('.filters select').setValue('');await flushPromises()
    expect(mocks.runs.mock.lastCall?.[2].page).toBe(1)
    wrapper.unmount()
  })
  it('reads saved observation and clearly identifies manual refresh',async()=>{
    const {wrapper}=await setup()
    await wrapper.findAll('.tabs button').find(b=>b.text()==='观察账本')!.trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('未开启后台自动更新')
    expect(wrapper.text()).toContain('空仓')
    await wrapper.findAll('button').find(b=>b.text()==='刷新已保存记录')!.trigger('click');await flushPromises()
    expect(mocks.observation).toHaveBeenCalledTimes(2)
    expect(mocks.run).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('rejects unknown deep links and lets the user select a real study',async()=>{
    const {wrapper}=await setup('?study=unknown')
    expect(wrapper.get('[role="alert"]').text()).toContain('找不到')
    await wrapper.findAll('.study-rail button')[1]!.trigger('click');await flushPromises()
    expect(mocks.detail).toHaveBeenLastCalledWith('daily-screen','abc')
    expect(wrapper.findAll('.tabs button').some(b=>b.text()==='观察账本')).toBe(false)
    wrapper.unmount()
  })
  it('ignores late responses when switching studies',async()=>{
    let resolve:((value:unknown)=>void)|undefined
    mocks.detail.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    const {wrapper,router}=await setup()
    await router.replace('/research?study=daily-screen');await flushPromises()
    resolve?.(detail('fu-regime'));await flushPromises()
    expect(wrapper.get('.study-heading').text()).toContain('多品种初筛')
    wrapper.unmount()
  })
})
