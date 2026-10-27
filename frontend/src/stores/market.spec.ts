import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from './market'
import {api,type Quote,type History,type TermStructure,type Prediction} from '../services/api'

describe('market store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it.each(['JM', 'M', 'RM', 'SM', 'PM', 'IM', 'J', 'I', 'RB', 'CJ'])(
    'keeps %s delivery contracts and continuous symbols in their own product curve', async (root) => {
      vi.spyOn(api, 'quote').mockImplementation(async symbol => ({symbol, price: 100}) as Quote)
      vi.spyOn(api, 'history').mockImplementation(async symbol => ({symbol, points: []}) as unknown as History)
      const curve = vi.spyOn(api, 'termStructure').mockResolvedValue({rootSymbol: root, contracts: []} as unknown as TermStructure)
      const store = useMarketStore()
      for (const symbol of [`${root}2701`, `${root}701`, `${root}M`, `${root}0`]) {
        await store.loadMarket(symbol)
        expect(curve).toHaveBeenLastCalledWith(root)
      }
    },
  )

  it('does not display a curve whose returned product or contracts belong to another product', async () => {
    vi.spyOn(api, 'quote').mockResolvedValue({symbol: 'JMM', price: 100} as Quote)
    vi.spyOn(api, 'history').mockResolvedValue({symbol: 'JMM', points: []} as unknown as History)
    const curve = vi.spyOn(api, 'termStructure').mockResolvedValue({rootSymbol: 'J', contracts: [{contract: 'J2701'}]} as TermStructure)
    const store = useMarketStore()
    await store.loadMarket('JMM')
    expect(store.quote?.symbol).toBe('JMM')
    expect(store.termStructure).toBeNull()
    curve.mockResolvedValue({rootSymbol: 'JM', contracts: [{contract: 'J2701'}]} as TermStructure)
    await store.loadMarket('JMM')
    expect(store.termStructure).toBeNull()
  })

  it('clears the previous instrument immediately while a new instrument is loading', async () => {
    let release!: (value: Quote) => void
    vi.spyOn(api, 'quote').mockImplementation(() => new Promise(resolve => {release = resolve}))
    vi.spyOn(api, 'history').mockResolvedValue({symbol: 'JMM', points: []} as unknown as History)
    vi.spyOn(api, 'termStructure').mockRejectedValue(new Error('optional'))
    const store = useMarketStore()
    store.symbol = 'JM'
    store.quote = {symbol: 'JM', price: 2000} as Quote
    store.prediction = {symbol: 'JM'} as Prediction
    const pending = store.loadMarket('JMM')
    expect(store.symbol).toBe('JMM')
    expect(store.quote).toBeNull()
    expect(store.prediction).toBeNull()
    release({symbol: 'JMM', price: 1000} as Quote)
    await pending
  })

  it('keeps successfully loaded market data when browser preference storage is full', async () => {
    vi.spyOn(api, 'quote').mockResolvedValue({symbol: 'JMM', price: 100} as Quote)
    vi.spyOn(api, 'history').mockResolvedValue({symbol: 'JMM', points: []} as unknown as History)
    vi.spyOn(api, 'termStructure').mockRejectedValue(new Error('optional'))
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {throw new DOMException('full', 'QuotaExceededError')})
    const store = useMarketStore()
    await store.loadMarket('JMM')
    expect(store.state).toBe('ready')
    expect(store.quote?.symbol).toBe('JMM')
  })

  it('loads price history without requesting model predictions',async()=>{
    const quote={symbol:'RBM',price:3200} as unknown as Quote
    vi.spyOn(api,'quote').mockResolvedValue(quote)
    vi.spyOn(api,'history').mockResolvedValue({symbol:'RBM'} as unknown as History)
    vi.spyOn(api,'termStructure').mockRejectedValue(new Error('optional source unavailable'))
    const prediction=vi.spyOn(api,'prediction')
    const store=useMarketStore();await store.loadMarket('RBM')
    expect(store.state).toBe('ready');expect(store.quote).toEqual(quote)
    expect(store.termStructure).toBeNull();expect(prediction).not.toHaveBeenCalled()
  })

  it('does not let a slow previous product replace a newly selected product',async()=>{
    let release!:(value:Quote)=>void
    vi.spyOn(api,'quote').mockImplementation(symbol=>symbol==='CJM'?new Promise(resolve=>{release=resolve}):Promise.resolve({symbol:'RBM',price:3200} as unknown as Quote))
    vi.spyOn(api,'history').mockResolvedValue({} as History)
    vi.spyOn(api,'termStructure').mockRejectedValue(new Error('optional source unavailable'))
    const store=useMarketStore();const oldRequest=store.loadMarket('CJM')
    await store.loadMarket('RBM')
    release({symbol:'CJM',price:9000} as unknown as Quote);await oldRequest
    expect(store.symbol).toBe('RBM');expect(store.quote?.symbol).toBe('RBM')
    expect(store.recentSymbols).toEqual(['RBM'])
  })

  it('does not replace failed live requests with demo data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const store = useMarketStore()

    await store.load('cjm')

    expect(store.state).toBe('error')
    expect(store.displayStatus).toBe('DEGRADED')
    expect(store.quote).toBeNull()
    expect(store.prediction).toBeNull()
  })

  it('normalizes symbols before requesting data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const store = useMarketStore()

    await store.load('  cj2701  ')

    expect(store.symbol).toBe('CJ2701')
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/CJ2701/'), expect.any(Object))
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/market/CJ/term-structure'), expect.any(Object))
  })

  it('restores, normalizes, deduplicates, and limits recent successful symbols', () => {
    window.localStorage.setItem('aiquant.recent-symbols', JSON.stringify(['rbm', 'IFM', 'bad!', 'RBM']))
    const store = useMarketStore()

    expect(store.recentSymbols).toEqual(['RBM', 'IFM'])

    for (const symbol of ['TM', 'SIM', 'CJM', 'MM', 'AGM']) store.rememberSymbol(symbol)

    expect(store.recentSymbols).toEqual(['AGM', 'MM', 'CJM', 'SIM', 'TM'])
    expect(JSON.parse(window.localStorage.getItem('aiquant.recent-symbols') ?? '[]')).toEqual(store.recentSymbols)
  })

  it('resolves sidebar entries only from the observed catalog', () => {
    const store = useMarketStore()
    store.catalog = {
      source: 'provider', dataStatus: 'FRESH', dataTimestamp: '2026-10-15T00:00:00Z',
      exchanges: [{
        code: 'CFFEX', name: '中国金融期货交易所', instruments: [{
          exchange: 'CFFEX', exchangeName: '中国金融期货交易所', name: '沪深300股指', node: 'cffex_if',
          rootSymbol: 'IF', mainSymbol: 'IFM', contracts: ['IF2610'],
        }],
      }],
    }
    store.symbol = 'IF2610'

    expect(store.currentInstrument).toMatchObject({ symbol: 'IF2610', name: '沪深300股指', exchange: 'CFFEX' })
    expect(store.sidebarInstruments).toEqual([
      expect.objectContaining({ symbol: 'IF2610' }),
      expect.objectContaining({ symbol: 'IFM' }),
    ])
  })
})
