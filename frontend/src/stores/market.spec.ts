import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from './market'
import { api, ApiError } from '../services/api'
import { demoBundle } from '../services/demo'

describe('market store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('marks development fallback as demo and degraded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const store = useMarketStore()

    await store.load('rb2505')

    expect(store.state).toBe('ready')
    expect(store.sourceMode).toBe('demo')
    expect(store.displayStatus).toBe('DEGRADED')
    expect(store.quote?.source).toContain('演示快照')
    expect(store.prediction?.traceId).toContain('demo')
  })

  it('normalizes symbols before requesting data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const store = useMarketStore()

    await store.load('  rb2505  ')

    expect(store.symbol).toBe('RB2505')
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/RB2505/'), expect.any(Object))
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/market/RB/term-structure'), expect.any(Object))
  })

  it('keeps prediction available when quote is missing, without using demo data', async () => {
    vi.spyOn(api, 'quote').mockRejectedValue(new ApiError('No quote', 404))
    vi.spyOn(api, 'history').mockResolvedValue({ ...demoBundle.history, points: [] })
    vi.spyOn(api, 'termStructure').mockResolvedValue({ ...demoBundle.termStructure, contracts: [] })
    vi.spyOn(api, 'prediction').mockResolvedValue({ ...demoBundle.prediction, symbol: 'CJ2701', traceId: 'real-api-result' })
    const store = useMarketStore()
    await store.load()
    expect(store.symbol).toBe('CJ2701')
    expect(store.state).toBe('ready')
    expect(store.sourceMode).toBe('live')
    expect(store.quote).toBeNull()
    expect(store.resourceStates.quote).toBe('empty')
    expect(store.resourceStates.history).toBe('empty')
    expect(store.resourceStates.prediction).toBe('ready')
    expect(store.prediction?.traceId).toBe('real-api-result')
  })

  it('renders successful quote before a slow prediction finishes', async () => {
    vi.spyOn(api, 'quote').mockResolvedValue(demoBundle.quote)
    vi.spyOn(api, 'history').mockResolvedValue(demoBundle.history)
    vi.spyOn(api, 'termStructure').mockResolvedValue(demoBundle.termStructure)
    let finish!: (value: typeof demoBundle.prediction) => void
    vi.spyOn(api, 'prediction').mockReturnValue(new Promise(resolve => { finish = resolve }))
    const store = useMarketStore()
    const loading = store.load()
    await vi.waitFor(() => expect(store.resourceStates.quote).toBe('ready'))
    expect(store.resourceStates.prediction).toBe('loading')
    expect(store.quote).not.toBeNull()
    finish(demoBundle.prediction)
    await loading
  })

  it('discards responses from a previous symbol after switching contracts', async () => {
    vi.spyOn(api, 'quote').mockRejectedValue(new ApiError('No quote', 404))
    vi.spyOn(api, 'history').mockResolvedValue({ ...demoBundle.history, points: [] })
    vi.spyOn(api, 'termStructure').mockResolvedValue({ ...demoBundle.termStructure, contracts: [] })
    let finishOld!: (value: typeof demoBundle.prediction) => void
    vi.spyOn(api, 'prediction')
      .mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
      .mockResolvedValueOnce({ ...demoBundle.prediction, symbol: 'CJ2703' })
    const store = useMarketStore()
    const oldLoading = store.load('CJ2701')
    await store.load('CJ2703')
    finishOld({ ...demoBundle.prediction, symbol: 'CJ2701' })
    await oldLoading
    expect(store.symbol).toBe('CJ2703')
    expect(store.prediction?.symbol).toBe('CJ2703')
  })
})
