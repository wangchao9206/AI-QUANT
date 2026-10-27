import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import {createRouter,createMemoryHistory} from 'vue-router'
import PersonalSummaryView from './PersonalSummaryView.vue'
import {api} from '../services/api'
import {personalApi,type PersonalRun,type PersonalVersion} from '../services/personal'
import {originalSummary} from '../content/personalStrategy'

vi.mock('../services/api',()=>({api:{backtestPresets:vi.fn(),replayStatus:vi.fn(),paperChart:vi.fn(),paperFills:vi.fn(),paperOrders:vi.fn()}}))
vi.mock('../services/personal',()=>({personalApi:{versions:vi.fn(),runs:vi.fn(),run:vi.fn(),create:vi.fn(),events:vi.fn(),reflections:vi.fn(),step:vi.fn(),reflect:vi.fn(),createVersion:vi.fn()}}))
const version:PersonalVersion={id:'v1',parentId:null,title:'生存优先 v1',hypothesis:'待验证',validationPlan:'保留独立检验区间',engineVersion:'SURVIVAL_RETEST_1.0',createdAt:'2026-10-20T00:00:00Z',rules:{riskPct:.5,maxMarginPct:20,volumeRatio:1.5,maxStopAtr:2,cooldownBars:3}}
function run(mode:'GUIDED'|'RULE_REPLAY'='GUIDED'):PersonalRun {
  return {session:{id:'r1',name:'检查执行',symbol:'M0',mode:'HISTORICAL',status:'ACTIVE',currentMarketTime:'2026-03-03T00:00:00Z',currentContract:'M2605',currentBarIndex:200,totalBars:400,initialCash:100000,equity:100000,position:{contract:'M2605',averagePrice:0,lots:0,direction:0,marginOccupied:0,unrealizedPnl:0},orders:[],fills:[],
      dataSource:'TQSDK_REAL_DOMINANT_DAILY',dataTimestamp:'2026-03-03T00:00:00Z',cashBalance:100000,realizedPnl:0,commissionPaid:0,slippagePaid:0,
      marginRate:.15,feeRate:.0001,slippageTicks:1,autoRoll:false,currentPrice:2840,volumeMultiple:10,priceTick:1,marginPerLot:2000,commissionPerLot:1.5,version:0,createdAt:'2026-10-20T00:00:00Z',updatedAt:'2026-10-20T00:00:00Z'},
    versionId:'v1',trainingMode:mode,trainingStart:'2026-03-04',rules:{...version.rules},peakEquity:100000,riskHalted:false,activeStop:null,
    plan:{state:'ENTRY',action:'ENTER',direction:1,entryPrice:2844,stopPrice:2802,maxLots:1,riskBudget:500,plannedRisk:445,atr:32,ma20:2777,ma60:2773,weeklyMa10:2767,boxLevel:2813,volumeRatio:1.6,reasons:['回踩确认']},
    metrics:{decisions:0,compliant:0,humanAdherencePct:null,closedFillFragments:0,closedTradeCount:0,closedNetPnl:0,maxDrawdownPct:0,lossBeyondBudgetCount:0,validationStatus:'INSUFFICIENT_SAMPLE',sampleWarning:'不足20次完整交易，不判断收益优势'}}
}
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
  vi.mocked(personalApi.versions).mockResolvedValue(structuredClone([version]))
  vi.mocked(personalApi.runs).mockResolvedValue({page:1,pageSize:6,total:0,items:[]})
  vi.mocked(personalApi.run).mockResolvedValue(run())
  vi.mocked(personalApi.create).mockResolvedValue(run())
  vi.mocked(personalApi.events).mockResolvedValue({page:1,pageSize:10,total:0,items:[]})
  vi.mocked(personalApi.reflections).mockResolvedValue({page:1,pageSize:10,total:0,items:[]})
  vi.mocked(personalApi.reflect).mockResolvedValue(undefined)
  vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[{symbol:'M0',name:'豆粕',exchange:'DCE',sector:'农产品'},{symbol:'AG0',name:'白银',exchange:'SHFE',sector:'贵金属'}]} as never)
  vi.mocked(api.replayStatus).mockResolvedValue({totalSymbols:1,symbols:[{symbol:'M0',startDate:'2024-04-25',endDate:'2026-10-16',totalBars:599}]} as never)
  vi.mocked(api.paperChart).mockResolvedValue({asOf:'2026-03-03T00:00:00Z',barIndex:200,source:'observed',contextStatus:'READY',message:'observed',bars:[]})
})
afterEach(()=>wrapper?.unmount())
async function render(path='/personal') {
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/personal',component:PersonalSummaryView}]})
  await router.push(path);await router.isReady()
  wrapper=mount(PersonalSummaryView,{global:{plugins:[router],stubs:{TongdaxinChart:true}}});await flushPromises()
  return wrapper
}
async function tab(name:string){await wrapper!.get('[aria-label="个人总结栏目"]').findAll('button').find(b=>b.text()===name)!.trigger('click');await flushPromises()}

describe('personal playbook and controlled practice',()=>{
  it('shows chart-scoped execution markers in controlled practice without using record pagination',async()=>{
    const timestamp='2026-03-03T00:00:00Z'
    vi.mocked(api.paperChart).mockResolvedValue({asOf:timestamp,barIndex:200,source:'observed',contextStatus:'READY',message:'observed',bars:[{timestamp,contract:'M2605',open:2840,high:2850,low:2830,close:2840,volume:100,openInterest:100}],fills:[{id:'training-fill',contract:'M2605',eventType:'ORDER',side:'BUY',offset:'OPEN',quantity:1,marketTime:timestamp,marketPrice:2840,fillPrice:2841,fee:2,slippageCost:10,realizedPnl:0,reason:'受控训练确认开仓'}]})
    await render('/personal?run=r1')
    expect(wrapper!.getComponent({name:'TongdaxinChart'}).props('trades')).toEqual([
      expect.objectContaining({id:'training-fill',timestamp,reason:'受控训练确认开仓',fillPrice:2841}),
    ])
  })
  it('keeps the complete original text and separates hypotheses from psychological labels',async()=>{
    await render();expect(wrapper!.text()).toContain('执行无效系统')
    expect(wrapper!.text()).toContain('不能写成普遍规律')
    await tab('你的原文')
    expect(wrapper!.findAll('.original li')).toHaveLength(originalSummary.flatMap(s=>s.lines).length)
    for(const section of originalSummary)for(const line of section.lines)expect(wrapper!.text()).toContain(line)
  })
  it('creates only a real-data product with a frozen version and an explicit training mode',async()=>{
    await render();await tab('模拟训练')
    const form=wrapper!.get('.create-training')
    expect(form.text()).toContain('豆粕');expect(form.text()).not.toContain('白银')
    await form.trigger('submit');await flushPromises()
    expect(personalApi.create).toHaveBeenCalledWith(expect.objectContaining({versionId:'v1',symbol:'M0',trainingMode:'GUIDED',startDate:'2025-10-16',endDate:'2026-10-16'}))
    expect(wrapper!.find('.current-training').exists()).toBe(true)
    expect(wrapper!.get('.decision-form').findAll('input[type="checkbox"]').every(e=>!(e.element as HTMLInputElement).checked)).toBe(true)
  })
  it('retries an uncertain step with the same command and original intent',async()=>{
    await render('/personal?run=r1')
    const next=run();next.session.currentBarIndex=201
    vi.mocked(personalApi.step).mockRejectedValueOnce(new Error('响应丢失')).mockResolvedValueOnce(next)
    await wrapper!.get('.decision-form textarea').setValue('先确认风险')
    await wrapper!.get('.decision-form').trigger('submit');await flushPromises()
    expect(wrapper!.text()).toContain('原命令与原决定')
    expect(wrapper!.get('.decision-form select').attributes('disabled')).toBeDefined()
    await wrapper!.get('.decision-form').trigger('submit');await flushPromises()
    const calls=vi.mocked(personalApi.step).mock.calls
    expect(calls).toHaveLength(2);expect(calls[0][1]).toEqual(calls[1][1])
    expect(calls[0][1]).toMatchObject({expectedBarIndex:200,notes:'先确认风险',stopAccepted:false,riskAccepted:false,noRevenge:false})
  })
  it('keeps a failed reflection draft and only clears it after server confirmation',async()=>{
    await render('/personal?run=r1');await tab('复盘与迭代')
    vi.mocked(personalApi.reflect).mockRejectedValueOnce(new Error('保存失败')).mockResolvedValueOnce(undefined)
    await wrapper!.get('.reflection-form textarea').setValue('小额止损守规则，不能用情绪追回。')
    await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    expect((wrapper!.get('.reflection-form textarea').element as HTMLTextAreaElement).value).toContain('小额止损')
    await wrapper!.get('.reflection-form').trigger('submit');await flushPromises()
    expect(personalApi.reflect).toHaveBeenLastCalledWith(expect.objectContaining({sessionId:'r1',category:'EXECUTION',content:'小额止损守规则，不能用情绪追回。'}))
    expect((wrapper!.get('.reflection-form textarea').element as HTMLTextAreaElement).value).toBe('')
  })
  it('does not score automated replay as human discipline and paginates decision history',async()=>{
    vi.mocked(personalApi.run).mockResolvedValue(run('RULE_REPLAY'))
    vi.mocked(personalApi.events).mockResolvedValue({page:1,pageSize:10,total:25,items:[]})
    await render('/personal?run=r1')
    expect(wrapper!.get('.training-stats').text()).toContain('不评价')
    const next=wrapper!.get('[aria-label="训练决策分页"]').findAll('button').find(b=>b.text()==='下一页')!
    await next.trigger('click');await flushPromises()
    expect(personalApi.events).toHaveBeenCalledWith('r1',2)
  })
  it('saves a changed hypothesis as a new version without changing the active training',async()=>{
    await render('/personal?run=r1');await tab('复盘与迭代')
    const changed={...structuredClone(version),id:'v2',parentId:'v1',rules:{...version.rules,riskPct:.7}}
    vi.mocked(personalApi.createVersion).mockResolvedValue([changed,version])
    const form=wrapper!.get('.version-lab form')
    await form.findAll('textarea')[0].setValue('只研究风险率变化，不改变入场')
    await form.findAll('textarea')[1].setValue('在未使用的时间段与另一品种，按相同费用压力核验')
    await form.findAll('input[type="number"]')[0].setValue('0.7')
    await form.trigger('submit');await flushPromises()
    expect(personalApi.createVersion).toHaveBeenCalledWith(expect.objectContaining({parentId:'v1',rules:expect.objectContaining({riskPct:.7})}))
    await tab('模拟训练')
    expect(wrapper!.get('.current-training').text()).toContain('生存优先 v1')
    expect(personalApi.create).not.toHaveBeenCalled()
  })
})
