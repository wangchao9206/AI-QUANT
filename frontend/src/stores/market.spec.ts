import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from './market'

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
})
