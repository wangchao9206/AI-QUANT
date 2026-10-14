import { defineStore } from 'pinia'

import { api, type History, type Prediction, type Quote, type TermStructure } from '../services/api'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error'

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'CJM',
    state: 'idle' as LoadState,
    quote: null as Quote | null,
    history: null as History | null,
    termStructure: null as TermStructure | null,
    prediction: null as Prediction | null,
    error: '',
    lastLoadedAt: '' as string,
  }),
  getters: {
    isEmpty: (state) => !state.quote && !state.prediction,
    displayStatus: (state) => state.prediction?.dataStatus ?? state.quote?.dataStatus ?? 'DEGRADED',
  },
  actions: {
    async load(symbol?: string) {
      this.symbol = (symbol ?? this.symbol).trim().toUpperCase()
      this.state = 'loading'
      this.error = ''
      try {
        const rootSymbol = this.symbol.replace(/\d+$/, '').replace(/[M0]$/, '')
        const [quote, history, termStructure, prediction] = await Promise.all([
          api.quote(this.symbol), api.history(this.symbol), api.termStructure(rootSymbol), api.prediction(this.symbol),
        ])
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
