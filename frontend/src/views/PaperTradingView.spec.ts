import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import PaperTradingView from './PaperTradingView.vue'
import {api,type BacktestPresets,type PaperSession,type PaperFill} from '../services/api'
vi.mock('../services/api',()=>({api:{paperSessions:vi.fn(),backtestPresets:vi.fn(),replayStatus:vi.fn(),createPaperSession:vi.fn(),paperSession:vi.fn(),paperChart:vi.fn(),paperFills:vi.fn(),paperOrders:vi.fn(),advancePaperSession:vi.fn(),placePaperOrder:vi.fn()}}))
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
  vi.mocked(api.paperChart).mockResolvedValue({asOf:'2025-01-02T07:00:00Z',barIndex:0,source:'observed',contextStatus:'READY',message:'cutoff',bars:[]})
  vi.mocked(api.paperFills).mockResolvedValue({page:1,pageSize:20,total:0,items:[]})
  vi.mocked(api.paperOrders).mockResolvedValue({page:1,pageSize:20,total:0,items:[]})
  vi.mocked(api.paperSessions).mockResolvedValue([])
  vi.mocked(api.backtestPresets).mockResolvedValue({symbols:[{symbol:'CJ0',name:'红枣'},{symbol:'AP0',name:'苹果'}]} as BacktestPresets)
  vi.mocked(api.replayStatus).mockResolvedValue({totalSymbols:1,source:'OBSERVED_DELIVERY_CONTRACT',message:'observed',symbols:[{symbol:'CJ0',displayName:'红枣',totalBars:200,startDate:'2025-01-02',endDate:'2026-10-16',source:'TQSDK_REAL_DOMINANT_DAILY',generatedAt:'2026-10-17'}]})
})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers();vi.unstubAllGlobals()})
async function render(){wrapper=mount(PaperTradingView,{global:{stubs:{RouterLink:true}}});await flushPromises()}

function session(id: string, price = 100): PaperSession {
  return {id, name: id, mode: 'HISTORICAL', status: 'ACTIVE', symbol: 'JM0',
    initialCash: 1_000_000, equity: 1_000_000, currentPrice: price, currentContract: 'JM2701',
    currentMarketTime: '2026-10-16T07:00:00Z', totalBars: 200, currentBarIndex: 0,
    position: {marginOccupied: 0, lots: 0, direction: 0, unrealizedPnl: 0}, orders: [], fills: [],
  } as unknown as PaperSession
}

describe('paper account identity', () => {
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
