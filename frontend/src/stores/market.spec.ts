import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from './market'

describe('market store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
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
})
