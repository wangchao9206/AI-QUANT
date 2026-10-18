import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import PaperTradingView from './PaperTradingView.vue'
import {api,type BacktestPresets,type PaperSession} from '../services/api'
vi.mock('../services/api',()=>({api:{paperSessions:vi.fn(),backtestPresets:vi.fn(),replayStatus:vi.fn(),createPaperSession:vi.fn(),paperSession:vi.fn(),paperChart:vi.fn(),paperFills:vi.fn(),paperOrders:vi.fn()}}))
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
afterEach(()=>wrapper?.unmount())
async function render(){wrapper=mount(PaperTradingView,{global:{stubs:{RouterLink:true}}});await flushPromises()}
describe('paper account creation',()=>{
  it('offers executable historical data and sends its range instead of public continuous history',async()=>{
    vi.mocked(api.createPaperSession).mockResolvedValue({id:'test',mode:'HISTORICAL',name:'test',status:'ACTIVE',symbol:'CJ0',initialCash:1000000,equity:1000000,currentPrice:6400,currentContract:'CJ701',totalBars:200,currentBarIndex:0,position:{marginOccupied:0,lots:0,direction:0,unrealizedPnl:0},orders:[],fills:[]} as unknown as PaperSession)
    await render()
    expect(wrapper!.get('select').element.value).toBe('HISTORICAL')
    expect(wrapper!.findAll('select')[1]!.findAll('option')).toHaveLength(1)
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
    expect(wrapper!.findAll('select')[1]!.findAll('option')).toHaveLength(2)
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
    expect(wrapper!.findAll('select')[1]!.element.value).toBe('AG0')
    expect(wrapper!.findAll('select')[1]!.get('optgroup').attributes('label')).toBe('上期所')
    expect((wrapper!.get('input[type="date"]').element as HTMLInputElement).value).toBe('2024-04-25')
    await wrapper!.get('input[type="search"]').setValue('不存在')
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeDefined()
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(api.createPaperSession).not.toHaveBeenCalled()
    await wrapper!.get('input[type="search"]').setValue('ag')
    expect(wrapper!.findAll('select')[1]!.element.value).toBe('AG0')
    expect(wrapper!.get('.create-actions button').attributes('disabled')).toBeUndefined()
  })
})
