import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from './market'
import {api,type Quote,type History} from '../services/api'

describe('market store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    window.localStorage.clear()
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
