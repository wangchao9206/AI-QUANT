import { defineStore } from 'pinia'

import { api, type History, type Prediction, type Quote, type TermStructure } from '../services/api'
import { demoBundle } from '../services/demo'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error'

const demoEnabled = import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEMO_FALLBACK === 'true'

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'RB2505',
    state: 'idle' as LoadState,
    quote: null as Quote | null,
    history: null as History | null,
    termStructure: null as TermStructure | null,
    prediction: null as Prediction | null,
    sourceMode: 'live' as 'live' | 'demo',
    error: '',
    lastLoadedAt: '' as string,
  }),
  getters: {
    isEmpty: (state) => !state.quote && !state.prediction,
    displayStatus: (state) => state.sourceMode === 'demo' ? 'DEGRADED' : (state.prediction?.dataStatus ?? state.quote?.dataStatus ?? 'DEGRADED'),
  },
  actions: {
    async load(symbol?: string) {
      this.symbol = (symbol ?? this.symbol).trim().toUpperCase()
      this.state = 'loading'
      this.error = ''
      try {
        const rootSymbol = this.symbol.replace(/\d+$/, '')
        const [quote, history, termStructure, prediction] = await Promise.all([
          api.quote(this.symbol), api.history(this.symbol), api.termStructure(rootSymbol), api.prediction(this.symbol),
        ])
        this.quote = quote
        this.history = history
        this.termStructure = termStructure
        this.prediction = prediction
        this.sourceMode = 'live'
        this.state = 'ready'
      } catch (error) {
        if (demoEnabled) {
          this.quote = demoBundle.quote
          this.history = demoBundle.history
          this.termStructure = demoBundle.termStructure
          this.prediction = demoBundle.prediction
          this.sourceMode = 'demo'
          this.state = 'ready'
          this.error = error instanceof Error ? error.message : '实时服务暂不可用'
        } else {
          this.state = 'error'
          this.error = error instanceof Error ? error.message : '实时服务暂不可用'
        }
      } finally {
        this.lastLoadedAt = new Date().toISOString()
      }
    },
  },
})
