import { defineStore } from 'pinia'

import { ApiError, api, type History, type InstrumentCatalog, type Prediction, type Quote, type TermStructure } from '../services/api'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error'

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'CJM',
    state: 'idle' as LoadState,
    quote: null as Quote | null,
    history: null as History | null,
    termStructure: null as TermStructure | null,
    prediction: null as Prediction | null,
    catalog: null as InstrumentCatalog | null,
    catalogError: '',
    error: '',
    lastLoadedAt: '' as string,
  }),
  getters: {
    isEmpty: (state) => !state.quote && !state.prediction,
    displayStatus: (state) => state.prediction?.dataStatus ?? state.quote?.dataStatus ?? 'DEGRADED',
    instrumentCount: (state) => state.catalog?.exchanges.reduce((total, group) => total + group.instruments.length, 0) ?? 0,
    contractCount: (state) => state.catalog?.exchanges.reduce(
      (total, group) => total + group.instruments.reduce((sum, item) => sum + item.contracts.length, 0), 0,
    ) ?? 0,
  },
  actions: {
    async loadCatalog() {
      try {
        this.catalog = await api.instruments()
        this.catalogError = ''
      } catch (error) {
        this.catalogError = error instanceof Error ? error.message : '合约目录暂不可用'
      }
    },
    async load(symbol?: string) {
      this.symbol = (symbol ?? this.symbol).trim().toUpperCase()
      this.state = 'loading'
      this.error = ''
      try {
        const rootSymbol = this.symbol.replace(/\d+$/, '').replace(/[M0]$/, '')
        const termPromise = api.termStructure(rootSymbol).catch(() => null)
        const loadObserved = async () => Promise.all([
          api.quote(this.symbol), api.history(this.symbol), api.prediction(this.symbol),
        ] as const)
        let observed: Awaited<ReturnType<typeof loadObserved>> | undefined
        for (const delay of [0, 1200, 2200, 3200]) {
          if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay))
          try {
            observed = await loadObserved()
            break
          } catch (error) {
            if (!(error instanceof ApiError) || error.status !== 503 || delay === 3200) throw error
          }
        }
        if (!observed) throw new ApiError('真实行情仍在载入，请稍后重试', 503)
        const [quote, history, prediction] = observed
        const termStructure = await termPromise
        this.quote = quote
        this.history = history
        this.termStructure = termStructure
        this.prediction = prediction
        this.state = 'ready'
      } catch (error) {
        this.quote = null
        this.history = null
        this.termStructure = null
        this.prediction = null
        this.state = 'error'
        this.error = error instanceof Error ? error.message : '实时服务暂不可用'
      } finally {
        this.lastLoadedAt = new Date().toISOString()
      }
    },
  },
})
