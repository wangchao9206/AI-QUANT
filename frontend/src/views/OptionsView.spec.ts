import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,describe,expect,it,vi} from 'vitest'
import OptionsView from './OptionsView.vue'
import type {OptionCatalog,OptionChain,OptionChainSnapshot,OptionContract,OptionScenario} from '../types/options'

const mocks=vi.hoisted(()=>({catalog:vi.fn(),chain:vi.fn(),scenario:vi.fn()}))
vi.mock('../services/options',()=>({optionsApi:mocks}))
const stamp='2026-11-06T10:00:00+08:00'
const chain=(id='first'):OptionChain=>({id,exchange:'DCE',underlyingSymbol:id==='first'?'DCE.m2701':'DCE.m2705',underlyingType:'FUTURE',expiry:'2026-12-05T15:00:00+08:00',product:'m',contractCount:2})
const contract=(kind:'CALL'|'PUT',id='first'):OptionContract=>({symbol:`${id}-${kind}`,name:kind==='CALL'?'豆粕认购':'豆粕认沽',optionClass:kind,strike:3000,expiry:chain().expiry,exerciseType:'A',volumeMultiple:10,priceTick:.5,lastPrice:100,bidPrice:99,askPrice:101,volume:20,openInterest:40,dataTimestamp:stamp,dataStatus:'CACHED',risk:{referencePrice:100,priceBasis:'MID',priceNote:null,spread:2,intrinsicValue:0,timeValue:100,iv:.25,delta:kind==='CALL'?.5:-.5,gamma:.002,theta:-.2,vega:4,model:'BLACK_76',approximation:true,valuationTimestamp:stamp,riskStatus:'EUROPEAN_APPROXIMATION',riskReason:'美式期权的欧式模型参考，未计提前行权价值。'}})
const snapshot=(id='first'):OptionChainSnapshot=>({chain:chain(id),underlying:{lastPrice:3000,dataTimestamp:stamp,dataStatus:'CACHED'},contracts:[contract('CALL',id),contract('PUT',id)],source:'天勤 TqSdk 期权行情',dataStatus:'CACHED',message:'',retrievedAt:stamp,assumptions:{rate:.02,dividend:0,yearBasis:'ACT/365',rateSource:'USER_ASSUMPTION',greekUnits:'每单位'}})
const catalog=():OptionCatalog=>({source:'天勤',dataStatus:'FRESH',dataTimestamp:stamp,message:'',chains:[chain(),chain('second')]})
const scenario=(body:{symbol:string;side:'BUY'|'SELL';lots:number}):OptionScenario=>({symbol:body.symbol,side:body.side,lots:body.lots,referencePrice:100,priceBasis:'MID',priceNote:null,volumeMultiple:10,premiumAmount:1000*body.lots,breakeven:3100,maxLoss:body.side==='SELL'?null:1000*body.lots,maxProfit:body.side==='SELL'?1000*body.lots:null,unlimitedLoss:body.side==='SELL',unlimitedProfit:body.side==='BUY',points:[{underlyingPrice:0,pnl:-1000},{underlyingPrice:3100,pnl:0},{underlyingPrice:4000,pnl:9000}],dataTimestamp:stamp,underlyingTimestamp:stamp,dataStatus:'CACHED',underlyingStatus:'CACHED',note:'单腿到期内在价值情景；不含手续费、滑点、保证金。曲线不是行情预测。'})
const wrappers:ReturnType<typeof mount>[]=[]
async function setup(){const wrapper=mount(OptionsView);wrappers.push(wrapper);await flushPromises();return wrapper}
beforeEach(()=>{vi.useFakeTimers();vi.clearAllMocks();mocks.catalog.mockResolvedValue(catalog());mocks.chain.mockImplementation(async(id:string)=>snapshot(id));mocks.scenario.mockImplementation(async body=>scenario(body))})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.useRealTimers()})

describe('options research',()=>{
  it('shows mirrored observed chains, cached times, model labels and payoff units',async()=>{
    const w=await setup()
    expect(mocks.chain).toHaveBeenCalledWith('first',.02,0)
    expect(w.get('.chain-table').text()).toContain('认购期权')
    expect(w.get('.chain-table').text()).toContain('认沽期权')
    expect(w.text()).toContain('缓存快照')
    expect(w.get('[aria-label="合约风险分析"]').text()).toContain('Black-76')
    expect(w.text()).toContain('美式期权的欧式模型参考')
    expect(w.text()).toContain('Vega / 1 波动率百分点')
    expect(w.find('svg[role="img"]').exists()).toBe(true)
    expect(w.get('[aria-label="单腿到期损益"]').text()).toContain('1,000.00')
  })
  it('changes selected contract, quantity and short-call risk without submitting any trade',async()=>{
    const w=await setup()
    await w.get('[aria-label="查看 豆粕认沽（first-PUT） 风险"]').trigger('click');await flushPromises()
    expect(w.get('[aria-label="合约风险分析"]').text()).toContain('豆粕认沽')
    expect(mocks.scenario.mock.lastCall?.[0].symbol).toBe('first-PUT')
    await w.get('[aria-label="查看 豆粕认购（first-CALL） 风险"]').trigger('click')
    await w.get('[aria-label="情景买卖方向"]').setValue('SELL')
    await w.get('[aria-label="情景手数"]').setValue('3');await flushPromises()
    expect(mocks.scenario.mock.lastCall?.[0]).toEqual({chainId:'first',symbol:'first-CALL',side:'SELL',lots:3})
    expect(w.get('[aria-label="单腿到期损益"]').text()).toContain('理论上无上限')
    const count=mocks.scenario.mock.calls.length
    await w.get('[aria-label="情景手数"]').setValue('1.5');await flushPromises()
    expect(mocks.scenario.mock.calls.length).toBe(count)
    expect(w.text()).toContain('手数需为')
  })
  it('keeps missing values empty and does not calculate scenarios with absent prices',async()=>{
    const data=snapshot()
    data.contracts=data.contracts.map(c=>({...c,lastPrice:null,bidPrice:null,askPrice:null,dataStatus:'UNAVAILABLE',risk:{...c.risk,referencePrice:null,iv:null,delta:null,gamma:null,theta:null,vega:null,riskStatus:'UNAVAILABLE',riskReason:'缺少真实标的价格或报价时点。'}}))
    mocks.chain.mockResolvedValue(data)
    const w=await setup()
    expect(w.get('.chain-table').text()).not.toContain('25.00%')
    expect(w.text()).toContain('缺少真实标的价格')
    expect(mocks.scenario).not.toHaveBeenCalled()
    expect(w.find('svg[role="img"]').exists()).toBe(false)
  })
  it('shows no fabricated contracts when the provider is unavailable and allows retry',async()=>{
    mocks.catalog.mockRejectedValueOnce(new Error('天勤数据通道不可用'))
    const w=await setup()
    expect(w.get('[role="alert"]').text()).toContain('天勤数据通道不可用')
    expect(w.find('.chain-table').exists()).toBe(false)
    await w.findAll('button').find(b=>b.text()==='重试目录')!.trigger('click');await flushPromises()
    expect(w.find('.chain-table').exists()).toBe(true)
  })
  it('ignores a late chain response after switching to a different underlying',async()=>{
    let resolve:((data:OptionChainSnapshot)=>void)|undefined
    mocks.chain.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    const w=await setup()
    await w.get('[aria-label="期权链选择"]').setValue('second');await flushPromises()
    resolve!(snapshot());await flushPromises()
    expect(w.get('.underlying-strip').text()).toContain('DCE.m2705')
    expect(w.get('[aria-label="合约风险分析"]').text()).toContain('second-CALL')
    expect(w.text()).not.toContain('first-CALL')
  })
  it('ignores a late payoff response after changing the position direction',async()=>{
    let resolve:((data:OptionScenario)=>void)|undefined
    mocks.scenario.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    const w=await setup()
    await w.get('[aria-label="情景买卖方向"]').setValue('SELL');await flushPromises()
    resolve!(scenario({symbol:'first-CALL',side:'BUY',lots:1}));await flushPromises()
    expect(w.get('[aria-label="单腿到期损益"]').text()).toContain('收取权利金')
    expect(w.get('[aria-label="单腿到期损益"]').text()).not.toContain('支付权利金')
  })
  it('applies validated user assumptions and retains the actual assumptions beside the Greeks',async()=>{
    const w=await setup()
    await w.get('[aria-label="年化利率百分比"]').setValue('3.5')
    await w.get('.assumptions').trigger('submit');await flushPromises()
    expect(mocks.chain).toHaveBeenLastCalledWith('first',.035,0)
    const count=mocks.chain.mock.calls.length
    await w.get('[aria-label="年化利率百分比"]').setValue('99')
    await w.get('.assumptions').trigger('submit');await flushPromises()
    expect(mocks.chain.mock.calls.length).toBe(count)
  })
  it('refreshes a warming catalog and stops polling when unmounted',async()=>{
    mocks.catalog.mockResolvedValueOnce({...catalog(),chains:[],dataStatus:'WARMING',message:'等待期权目录'})
    const w=await setup()
    expect(w.text()).toContain('等待期权目录')
    expect(mocks.chain).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5000);await flushPromises()
    expect(w.find('.chain-table').exists()).toBe(true)
    w.unmount()
    const count=mocks.chain.mock.calls.length
    await vi.advanceTimersByTimeAsync(10000)
    expect(mocks.chain.mock.calls.length).toBe(count)
  })
})
