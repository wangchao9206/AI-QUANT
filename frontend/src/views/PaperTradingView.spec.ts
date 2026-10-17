import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import PaperTradingView from './PaperTradingView.vue'
import {api,type BacktestPresets,type PaperSession} from '../services/api'
vi.mock('../services/api',()=>({api:{paperSessions:vi.fn(),backtestPresets:vi.fn(),replayStatus:vi.fn(),createPaperSession:vi.fn(),paperSession:vi.fn()}}))
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
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
})
