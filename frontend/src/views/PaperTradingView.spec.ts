import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import PaperTradingView from './PaperTradingView.vue'
import {api,type BacktestPresets,type PaperSession,type PaperFill} from '../services/api'
import {workflowTrialsApi,workflowsApi,type WorkflowVersion} from '../services/workflows'
vi.mock('../services/api',()=>({api:{selectPaperInstrument:vi.fn(),microstructure:vi.fn(),intradayCatalog:vi.fn(),paperFillNote:vi.fn(),savePaperFillNote:vi.fn(),paperSessions:vi.fn(),backtestPresets:vi.fn(),replayStatus:vi.fn(),createPaperSession:vi.fn(),paperSession:vi.fn(),paperChart:vi.fn(),paperFills:vi.fn(),paperOrders:vi.fn(),advancePaperSession:vi.fn(),placePaperOrder:vi.fn()}}))
vi.mock('../services/workflows',async load=>{const source=await load<typeof import('../services/workflows')>();return {...source,workflowsApi:{...source.workflowsApi,versions:vi.fn(),maTrendVersions:vi.fn()},workflowTrialsApi:{list:vi.fn(),get:vi.fn(),create:vi.fn()}}})
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
  vi.mocked(workflowsApi.versions).mockResolvedValue([])
  vi.mocked(workflowsApi.maTrendVersions).mockResolvedValue([])
  vi.mocked(workflowTrialsApi.list).mockResolvedValue([])
  vi.mocked(api.microstructure).mockResolvedValue({symbol:'JM2701',bids:[],asks:[],trades:[],source:'TEST',dataStatus:'FRESH',dataTimestamp:'2026-11-18T01:30:30Z',lastPrice:100})
  vi.mocked(api.intradayCatalog).mockResolvedValue({symbols:[],periods:[60,180,300,900],unavailable:[]})
  vi.mocked(api.paperChart).mockResolvedValue({asOf:'2025-01-02T07:00:00Z',barIndex:0,source:'observed',contextStatus:'READY',message:'cutoff',bars:[]})
  vi.mocked(api.paperFills).mockResolvedValue({page:1,pageSize:20,total:0,items:[]})
  vi.mocked(api.paperOrders).mockResolvedValue({page:1,pageSize:20,total:0,items:[]})
  vi.mocked(api.paperSessions).mockResolvedValue([])
  vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[{symbol:'CJ0',name:'红枣'},{symbol:'AP0',name:'苹果'}]} as BacktestPresets)
  vi.mocked(api.replayStatus).mockResolvedValue({totalSymbols:1,source:'OBSERVED_DELIVERY_CONTRACT',message:'observed',symbols:[{symbol:'CJ0',displayName:'红枣',totalBars:200,startDate:'2025-01-02',endDate:'2026-10-16',source:'TQSDK_REAL_DOMINANT_DAILY',generatedAt:'2026-10-17'}]})
})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers();vi.unstubAllGlobals()})
async function render(){wrapper=mount(PaperTradingView,{global:{stubs:{RouterLink:true,PaperAutomationPanel:true}}});await flushPromises()}

function session(id: string, price = 100): PaperSession {
  return {id, name: id, mode: 'HISTORICAL', status: 'ACTIVE', symbol: 'JM0',
    initialCash: 1_000_000, equity: 1_000_000, currentPrice: price, currentContract: 'JM2701',
    currentMarketTime: '2026-10-16T07:00:00Z', totalBars: 200, currentBarIndex: 0,
    position: {marginOccupied: 0, lots: 0, direction: 0, unrealizedPnl: 0}, orders: [], fills: [],
  } as unknown as PaperSession
}

describe('paper account identity', () => {
  it('switches instruments within the same wallet and sends an explicit contract with orders',async()=>{
    const jm={contract:'JM2701',symbol:'JM0',direction:1 as const,lots:1,averagePrice:100,currentPrice:101,marginOccupied:1000,unrealizedPnl:60,marketState:'LIVE',marketTime:'2026-11-18T02:30:00Z',dataSource:'TEST',volumeMultiple:60,priceTick:.5}
    const fg={...jm,contract:'FG701',symbol:'FG0',direction:-1 as const,currentPrice:900,averagePrice:899,marginOccupied:2160,unrealizedPnl:-20,volumeMultiple:20,priceTick:1}
    const account={...session('shared-wallet'),mode:'LIVE' as const,strategyId:'MANUAL',multiInstrument:true,positions:[jm,fg],instruments:[jm,fg],position:jm,totalMargin:3160,totalUnrealized:40,reservedCash:1003,availableCash:95837,equity:100000}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.selectPaperInstrument).mockResolvedValue({...account,currentContract:'FG701',position:fg})
    vi.mocked(api.placePaperOrder).mockResolvedValue({...account,currentContract:'FG701',position:fg})
    await render()
    expect(wrapper!.get('[aria-label="全部品种持仓"]').findAll('tbody tr')).toHaveLength(2)
    expect(wrapper!.get('.metrics').text()).toContain('95,837');expect(wrapper!.get('.metrics').text()).toContain('3,160')
    await wrapper!.get('[aria-label="添加或切换品种"]').setValue('FG0')
    await wrapper!.get('.instrument-picker').trigger('submit');await flushPromises()
    expect(api.selectPaperInstrument).toHaveBeenCalledWith('shared-wallet','FG0')
    expect(api.createPaperSession).not.toHaveBeenCalled();expect(api.placePaperOrder).not.toHaveBeenCalled()
    expect(wrapper!.get('.market-header h2').text()).toContain('FG701')
    await wrapper!.get('.submit-order').trigger('click');await flushPromises()
    expect(api.placePaperOrder).toHaveBeenCalledWith('shared-wallet',expect.objectContaining({contract:'FG701',quantity:1}))
  })
  it('selecting a position to close only prepares its own ticket and preserves all other positions',async()=>{
    const pos={contract:'FG701',symbol:'FG0',direction:-1 as const,lots:2,averagePrice:900,currentPrice:900,marginOccupied:4000,unrealizedPnl:0,marketState:'LIVE',marketTime:'2026-11-18T02:30:00Z',dataSource:'TEST',volumeMultiple:20,priceTick:1}
    const account={...session('shared-close'),mode:'LIVE' as const,strategyId:'MANUAL',multiInstrument:true,positions:[pos],instruments:[pos]}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.selectPaperInstrument).mockResolvedValue({...account,currentContract:'FG701',position:pos})
    await render()
    await wrapper!.get('[aria-label="全部品种持仓"] tbody button').trigger('click');await flushPromises()
    await wrapper!.findAll('button').find(b=>b.text()==='选择平仓')!.trigger('click');await flushPromises()
    expect(wrapper!.get('.submit-order').text()).toContain('买入平仓')
    expect((wrapper!.get('.order-ticket input[type="number"]').element as HTMLInputElement).value).toBe('2')
    expect(api.placePaperOrder).not.toHaveBeenCalled();expect(api.createPaperSession).not.toHaveBeenCalled()
  })
  it('retains the current account and contract when adding an unavailable instrument fails',async()=>{
    const account={...session('retain-wallet'),mode:'LIVE' as const,strategyId:'MANUAL'}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.selectPaperInstrument).mockRejectedValue(new Error('真实合约行情尚未就绪'))
    await render();await wrapper!.get('[aria-label="添加或切换品种"]').setValue('RB0')
    await wrapper!.get('.instrument-picker').trigger('submit');await flushPromises()
    expect(wrapper!.get('.market-header h2').text()).toContain('JM2701')
    expect(wrapper!.get('[role="alert"]').text()).toContain('尚未就绪');expect(api.createPaperSession).not.toHaveBeenCalled()
  })
  it('live mode defaults to the forming minute and polls read-only even when the account valuation is old',async()=>{
    vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-18T01:30:30Z'))
    const visibility=vi.spyOn(document,'hidden','get').mockReturnValue(false)
    const account={...session('live'),mode:'LIVE' as const,barSeconds:86400}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.paperChart).mockImplementation(async(_id,_limit,seconds)=>({snapshotKind:'LIVE',asOf:new Date().toISOString(),barIndex:0,barSeconds:seconds,source:'PRIMARY_LIVE',contextStatus:'READY',message:'current',connected:true,dataStatus:'FRESH',marketState:'LIVE',dataTimestamp:new Date().toISOString(),displayTradingDate:'2026-11-18',lastPrice:906,lastBarProvisional:true,bars:[{timestamp:'2026-11-18T01:30:00Z',tradingDate:'2026-11-18',contract:'JM2701',open:905,high:907,low:904,close:906,volume:10,openInterest:20,provisional:true}]}))
    await render()
    expect(api.paperChart).toHaveBeenLastCalledWith('live',720,60)
    expect(wrapper!.get('[aria-label="实时行情状态"]').text()).toContain('实时更新')
    expect(wrapper!.get('.market-header h2').text()).toContain('906')
    expect(wrapper!.find('[aria-label="模拟分时图"] svg').exists()).toBe(true)
    expect(wrapper!.text()).not.toContain('历史日线背景')
    const before=vi.mocked(api.paperChart).mock.calls.length
    await vi.advanceTimersByTimeAsync(2000);await flushPromises()
    expect(vi.mocked(api.paperChart).mock.calls.length).toBeGreaterThan(before)
    expect(api.advancePaperSession).not.toHaveBeenCalled();expect(api.placePaperOrder).not.toHaveBeenCalled()
    wrapper!.unmount();const stopped=vi.mocked(api.paperChart).mock.calls.length;await vi.advanceTimersByTimeAsync(3000)
    expect(api.paperChart).toHaveBeenCalledTimes(stopped);visibility.mockRestore()
  })
  it('labels stale live data by its original time instead of treating a new fetch as fresh',async()=>{
    const account={...session('stale'),mode:'LIVE' as const,barSeconds:86400}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.paperChart).mockResolvedValue({snapshotKind:'LIVE',asOf:new Date().toISOString(),barIndex:0,barSeconds:60,source:'PRIMARY_LIVE',contextStatus:'READY',message:'stale',connected:true,dataStatus:'FRESH',marketState:'LIVE',dataTimestamp:'2025-01-02T07:00:00Z',displayTradingDate:'2026-11-18',bars:[]})
    await render()
    expect(wrapper!.get('[aria-label="实时行情状态"]').text()).toContain('数据过期')
    expect(wrapper!.get('[aria-label="实时行情状态"]').classes()).not.toContain('fresh')
  })
  it('switches minute replay between intraday and every candle period without placing orders or advancing',async()=>{
    const account={...session('switch-view'),barSeconds:60}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    await render()
    expect(wrapper!.get('[aria-label="模拟图表类型"]').text()).toContain('分时图')
    expect(api.paperChart).toHaveBeenLastCalledWith('switch-view',720,60)
    await wrapper!.findAll('[aria-label="模拟图表类型"] button').find(b=>b.text()==='K线图')!.trigger('click');await flushPromises()
    for(const seconds of [60,180,300,900,1800,3600,86400]){
      await wrapper!.get('[aria-label="图表K线周期"]').setValue(seconds);await flushPromises()
      expect(api.paperChart).toHaveBeenLastCalledWith('switch-view',240,seconds)
    }
    await wrapper!.findAll('[aria-label="模拟图表类型"] button').find(b=>b.text()==='分时图')!.trigger('click');await flushPromises()
    expect(api.paperChart).toHaveBeenLastCalledWith('switch-view',720,60)
    expect(api.advancePaperSession).not.toHaveBeenCalled();expect(api.placePaperOrder).not.toHaveBeenCalled()
  })
  it('defaults to real minute manual replay when the actual contract archive is available',async()=>{
    vi.mocked(api.intradayCatalog).mockResolvedValue({symbols:[{symbol:'FG701',name:'玻璃2701',exchange:'CZCE',sector:'分时回放',startDate:'2026-10-19',endDate:'2026-11-16',totalBars:7245,periods:[60,180,300,900]}],periods:[60,180,300,900],unavailable:[]})
    vi.mocked(api.createPaperSession).mockResolvedValue({...session('minute'),symbol:'FG701',barSeconds:60})
    await render()
    expect((wrapper!.get('[aria-label="回放K线周期"]').element as HTMLSelectElement).value).toBe('60')
    expect((wrapper!.get('[aria-label="期货品种"]').element as HTMLSelectElement).value).toBe('FG701')
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).toHaveBeenCalledWith(expect.objectContaining({symbol:'FG701',barSeconds:60,strategyId:'MANUAL',stopLossTicks:10,intradayOnly:true,autoRoll:false,startDate:'2026-10-19',endDate:'2026-11-16'}))
  })
  it('shows owner plan limits and leaves closing available when opening is blocked',async()=>{
    const account={...session('guarded'),decisionGuarded:true,planGuard:{enabled:true,ownerVisible:true,openingAllowed:false,version:2,side:'SHORT' as const,lots:3,budget:1500,message:'计划已过期：停止新增开仓，仍可平仓和撤单。'}}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    await render()
    const notice=wrapper!.get('[aria-label="计划开仓约束"]')
    expect(notice.text()).toContain('仅空头开仓');expect(notice.text()).toContain('最多 3 手');expect(notice.text()).toContain('不会自动止损或止盈')
    expect(wrapper!.get('.submit-order').attributes('disabled')).toBeDefined()
    expect(wrapper!.get('.submit-order').text()).toContain('卖出')
    await wrapper!.findAll('.order-ticket button').find(button=>button.text()==='平仓')!.trigger('click')
    expect(wrapper!.get('.submit-order').attributes('disabled')).toBeUndefined()
  })
  it('does not show private plan parameters when the server cannot reveal the owner binding',async()=>{
    const account={...session('shared'),decisionGuarded:true,planGuard:{enabled:true,ownerVisible:false,openingAllowed:false,message:'仅计划本人可新增开仓和撮合开仓挂单。'}}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    await render()
    const notice=wrapper!.get('[aria-label="计划开仓约束"]')
    expect(notice.text()).toContain('仅计划本人');expect(notice.text()).not.toContain('风险预算');expect(wrapper!.get('.submit-order').attributes('disabled')).toBeDefined()
  })
  it('retains remote managed-training restrictions alongside automatic strategy accounts',async()=>{
    const account={...session('managed'),managedTraining:true}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    await render()
    expect(wrapper!.find('.order-ticket').exists()).toBe(false)
    expect(wrapper!.get('button[title="推进一根K线"]').attributes('disabled')).toBeDefined()
    expect(wrapper!.find('.delete-trigger').exists()).toBe(false)
    expect(wrapper!.text()).toContain('此账户属于个人策略受控训练')
  })
  it('plots chart-scoped fills instead of the paginated records or account snapshot',async()=>{
    const account=session('A'),timestamp='2026-10-16T00:00:00+08:00'
    const fill:PaperFill={id:'chart-fill',marketTime:account.currentMarketTime,contract:'JM2701',side:'SELL',offset:'OPEN',eventType:'ORDER',quantity:2,fillPrice:99.5,marketPrice:100,fee:6,slippageCost:60,realizedPnl:0,reason:'策略动量开空'}
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.paperChart).mockResolvedValue({asOf:account.currentMarketTime,barIndex:0,source:'observed',contextStatus:'READY',message:'cutoff',bars:[{timestamp,contract:'JM2701',open:100,high:102,low:98,close:100,volume:100,openInterest:100}],fills:[fill]})
    await render()
    expect(wrapper!.get('.trade-marker').text()).toContain('卖开空')
    await wrapper!.get('.trade-marker').trigger('click')
    expect(wrapper!.get('[aria-label="买卖点成交详情"]').text()).toContain('策略动量开空')
    expect(account.fills).toEqual([])
  })
  it('keeps an existing historical account usable when the strategy catalog fails',async()=>{
    const account=session('A')
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.backtestPresets).mockRejectedValue(new Error('算法服务暂不可用'))
    await render()
    expect(wrapper!.find('.terminal-grid').exists()).toBe(true)
    expect(wrapper!.find('.submit-order').exists()).toBe(true)
    expect(wrapper!.text()).toContain('已有账户可继续使用')
  })
  it('submits on HTTP origins without randomUUID and retries an uncertain order with the same id',async()=>{
    const account=session('A')
    vi.mocked(api.paperSessions).mockResolvedValue([account]);vi.mocked(api.paperSession).mockResolvedValue(account)
    vi.mocked(api.placePaperOrder).mockRejectedValueOnce(new Error('请求超时')).mockResolvedValue(account)
    vi.stubGlobal('crypto',{})
    await render()
    await wrapper!.get('.submit-order').trigger('click');await flushPromises()
    expect(wrapper!.text()).toContain('请求超时')
    await wrapper!.get('.submit-order').trigger('click');await flushPromises()
    const first=vi.mocked(api.placePaperOrder).mock.calls[0]!,second=vi.mocked(api.placePaperOrder).mock.calls[1]!
    expect(first[1].clientOrderId.length).toBeGreaterThanOrEqual(8)
    expect(second[1].clientOrderId).toBe(first[1].clientOrderId)
  })
  it('keeps the latest selected account when a previous account response arrives late', async () => {
    const a = session('A'), b = session('B'), c = session('C')
    vi.mocked(api.paperSessions).mockResolvedValue([a, b, c])
    let release!: (value: PaperSession) => void
    vi.mocked(api.paperSession).mockImplementation(async id => id === 'B'
      ? new Promise(resolve => {release = resolve}) : id === 'C' ? c : a)
    await render()
    const tabs = wrapper!.findAll('.session-tabs button')
    await tabs[1]!.trigger('click')
    expect(wrapper!.find('.terminal-grid').exists()).toBe(false)
    await tabs[2]!.trigger('click'); await flushPromises()
    release(b); await flushPromises()
    expect(wrapper!.findAll('.session-tabs button').find(t => t.attributes('aria-selected') === 'true')?.text()).toContain('C')
  })

  it('stops historical playback when switching to another account', async () => {
    vi.useFakeTimers({toFake: ['setInterval', 'clearInterval']})
    const a = session('A'), b = session('B')
    vi.mocked(api.paperSessions).mockResolvedValue([a, b])
    vi.mocked(api.paperSession).mockImplementation(async id => id === 'B' ? b : a)
    vi.mocked(api.advancePaperSession).mockResolvedValue(b)
    await render()
    await wrapper!.findAll('button').find(button => button.text() === '播放')!.trigger('click')
    await wrapper!.findAll('.session-tabs button')[1]!.trigger('click'); await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.advancePaperSession).not.toHaveBeenCalled()
  })

  it('preserves a user-entered limit price when the same account market is refreshed', async () => {
    const a = session('A', 100)
    vi.mocked(api.paperSessions).mockResolvedValue([a])
    vi.mocked(api.paperSession).mockResolvedValue(a)
    vi.mocked(api.advancePaperSession).mockResolvedValue({...a, currentPrice: 110, currentBarIndex: 1})
    await render()
    const type = wrapper!.findAll('select').find(select => select.find('option[value="LIMIT"]').exists())!
    await type.setValue('LIMIT')
    const price = wrapper!.findAll('.order-ticket input[type="number"]').at(-1)!
    await price.setValue(90)
    await wrapper!.get('button[title="推进一根K线"]').trigger('click'); await flushPromises()
    expect((wrapper!.findAll('.order-ticket input[type="number"]').at(-1)!.element as HTMLInputElement).value).toBe('90')
  })
})
describe('paper account creation',()=>{
  it('keeps the strategy picker available in the default minute replay and switches to daily for automatic strategies',async()=>{
    vi.mocked(api.intradayCatalog).mockResolvedValue({
      symbols:[{symbol:'FG701',name:'玻璃',exchange:'CZCE',sector:'建材',startDate:'2026-10-19',endDate:'2026-11-16',totalBars:950,periods:[60,180,300,900]}],
      periods:[60,180,300,900],unavailable:[],
    })
    vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[{symbol:'CJ0',name:'红枣'}],strategies:[{id:'BUY_AND_HOLD',name:'买入持有'}]} as BacktestPresets)
    await render()
    const strategy=wrapper!.get('[aria-label="模拟策略"]')
    expect(strategy.attributes('disabled')).toBeUndefined()
    expect(wrapper!.get('[aria-label="回放K线周期"]').element).toHaveProperty('value','60')
    await strategy.setValue('BUY_AND_HOLD')
    expect(wrapper!.get('[aria-label="回放K线周期"]').element).toHaveProperty('value','86400')
    expect(wrapper!.get('[aria-label="期货品种"]').element).toHaveProperty('value','CJ0')
  })

  it('lists published MA strategies in the workflow version picker when no daily workflows are published',async()=>{
    const version={id:'version-15m',workflowId:'draft',version:3,name:'我的均线',engineVersion:'workflow-ma-trend-15m-v1',definition:{maTrendExecution:{takeProfitPct:1}}} as WorkflowVersion
    const older={...version,id:'version-15m-older',version:2,definition:{maTrendExecution:{takeProfitPct:2}}} as WorkflowVersion
    vi.mocked(workflowsApi.maTrendVersions).mockResolvedValue([version,older])
    await render()
    await wrapper!.get('button[aria-controls="create-experiment"]').trigger('click')
    expect(wrapper!.get('#create-experiment').element.closest('template')).toBeNull()
    await wrapper!.get('[aria-label="模拟策略"]').setValue('WORKFLOW');await flushPromises()
    const picker=wrapper!.get('[aria-label="模拟工作流版本"]')
    expect(picker.attributes('disabled')).toBeUndefined()
    expect(picker.findAll('optgroup option').map(option=>option.text())).toEqual(['我的均线 · v3','我的均线 · v2'])
    await picker.setValue(older.id)
    expect(wrapper!.get('[aria-label="历史模拟"]').text()).toContain('止盈目标为 2%')
    expect(wrapper!.text()).toContain('试验名称')
    expect(wrapper!.text()).toContain('创建试验并开始回放')
    expect(wrapper!.text()).not.toContain('创建账户')
    expect(api.createPaperSession).not.toHaveBeenCalled()
  })
  it('freezes the selected strategy settings and shows its automated account rather than a manual ticket',async()=>{
    vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[{symbol:'CJ0',name:'红枣'}],strategies:[{
      id:'BOLLINGER_REVERSAL',name:'布林均值回归',recommendedParams:{stopLossAtr:2,takeProfitAtr:3},
    }]} as BacktestPresets)
    const account={...session('strategy'),symbol:'CJ0',strategyId:'BOLLINGER_REVERSAL',strategyLots:2,
      stopLossAtr:2,takeProfitAtr:3,strategyDecisions:[]}
    vi.mocked(api.createPaperSession).mockResolvedValue(account)
    await render()
    await wrapper!.get('[aria-label="模拟策略"]').setValue('BOLLINGER_REVERSAL')
    await wrapper!.get('[aria-label="策略开仓手数"]').setValue(2)
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).toHaveBeenCalledWith(expect.objectContaining({strategyId:'BOLLINGER_REVERSAL',strategyLots:2,stopLossAtr:2,takeProfitAtr:3}))
    expect(wrapper!.get('[aria-label="当前模拟策略"]').text()).toContain('布林均值回归')
    expect(wrapper!.find('.order-ticket').exists()).toBe(false)
    expect(wrapper!.text()).toContain('策略决策记录')
  })
  it('offers executable historical data and sends its range instead of public continuous history',async()=>{
    vi.mocked(api.createPaperSession).mockResolvedValue({id:'test',mode:'HISTORICAL',name:'test',status:'ACTIVE',symbol:'CJ0',initialCash:1000000,equity:1000000,currentPrice:6400,currentContract:'CJ701',totalBars:200,currentBarIndex:0,position:{marginOccupied:0,lots:0,direction:0,unrealizedPnl:0},orders:[],fills:[]} as unknown as PaperSession)
    await render()
    expect(wrapper!.get('select').element.value).toBe('HISTORICAL')
    expect(wrapper!.get('[aria-label="期货品种"]').findAll('option')).toHaveLength(1)
    expect((wrapper!.get('input[type="date"]').element as HTMLInputElement).value).toBe('2025-01-02')
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).toHaveBeenCalledWith(expect.objectContaining({symbol:'CJ0',startDate:'2025-01-02',endDate:'2026-10-16'}))
    expect(wrapper!.find('.terminal-grid').exists()).toBe(true)
  })
  it('keeps the form and displays the actionable error when creation fails',async()=>{
    vi.mocked(api.createPaperSession).mockRejectedValue(new Error('真实合约数据尚未就绪'))
    await render();await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(wrapper!.get('[role="alert"]').text()).toContain('真实合约数据尚未就绪')
    expect(wrapper!.find('form').exists()).toBe(true)
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeUndefined()
  })
  it('prevents empty historical submissions and keeps live mode available when the archive is offline',async()=>{
    vi.mocked(api.replayStatus).mockRejectedValue(new Error('offline'))
    await render();expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeDefined()
    await wrapper!.get('select').setValue('LIVE')
    expect(wrapper!.get('[aria-label="期货品种"]').findAll('option')).toHaveLength(2)
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeUndefined()
  })
  it('expands the default date range when refreshed history extends the selected product',async()=>{
    await render()
    const initial=await api.replayStatus()
    vi.mocked(api.replayStatus).mockResolvedValue({...initial,symbols:initial.symbols.map(item=>({...item,
      startDate:'2019-04-30',endDate:'2026-10-30',totalBars:1819}))})
    await wrapper!.findAll('button').find(button=>button.text().includes('刷新数据目录'))!.trigger('click')
    await flushPromises()
    const dates=wrapper!.findAll('input[type="date"]')
    expect((dates[0]!.element as HTMLInputElement).value).toBe('2019-04-30')
    expect((dates[1]!.element as HTMLInputElement).value).toBe('2026-10-30')
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).toHaveBeenCalledWith(expect.objectContaining({startDate:'2019-04-30',endDate:'2026-10-30'}))
  })
  it('preserves a custom date range when history is expanded',async()=>{
    await render()
    await wrapper!.get('input[type="date"]').setValue('2025-05-06')
    const initial=await api.replayStatus()
    vi.mocked(api.replayStatus).mockResolvedValue({...initial,symbols:initial.symbols.map(item=>({...item,
      startDate:'2019-04-30',endDate:'2026-10-30',totalBars:1819}))})
    await wrapper!.findAll('button').find(button=>button.text().includes('刷新数据目录'))!.trigger('click')
    await flushPromises()
    const start=wrapper!.get('input[type="date"]')
    expect(start.attributes('min')).toBe('2019-04-30')
    expect((start.element as HTMLInputElement).value).toBe('2025-05-06')
  })
  it('discovers a newly collected product on refresh and keeps filters, dates and creation consistent',async()=>{
    vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[
      {symbol:'CJ0',name:'红枣',exchange:'CZCE',sector:'农产品'},
      {symbol:'AG0',name:'白银',exchange:'SHFE',sector:'贵金属'},
    ]} as BacktestPresets)
    await render()
    const initial=await api.replayStatus()
    vi.mocked(api.replayStatus).mockResolvedValue({...initial,totalSymbols:2,symbols:[...initial.symbols,
      {symbol:'AG0',displayName:'白银',totalBars:599,startDate:'2024-04-25',endDate:'2026-10-16',source:'TQSDK_REAL_DOMINANT_DAILY',generatedAt:'2026-10-18'}]})
    await wrapper!.findAll('button').find(button=>button.text().includes('刷新数据目录'))!.trigger('click')
    await flushPromises()
    expect(wrapper!.get('[aria-label="模拟品种筛选"]').text()).toContain('可回放品种 2 / 2')
    await wrapper!.get('[aria-label="按板块筛选品种"]').findAll('button').find(button=>button.text()==='贵金属')!.trigger('click')
    expect((wrapper!.get('[aria-label="期货品种"]').element as HTMLSelectElement).value).toBe('AG0')
    expect(wrapper!.get('[aria-label="期货品种"]').get('optgroup').attributes('label')).toBe('上期所')
    expect((wrapper!.get('input[type="date"]').element as HTMLInputElement).value).toBe('2024-04-25')
    await wrapper!.get('input[type="search"]').setValue('不存在')
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeDefined()
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).not.toHaveBeenCalled()
    await wrapper!.get('input[type="search"]').setValue('ag')
    expect((wrapper!.get('[aria-label="期货品种"]').element as HTMLSelectElement).value).toBe('AG0')
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeUndefined()
  })
})
