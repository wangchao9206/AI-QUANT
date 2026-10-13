import { defineStore } from 'pinia'

import { api, ApiError, type History, type Prediction, type Quote, type TermStructure } from '../services/api'
import { demoBundle } from '../services/demo'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error'
export type Resource = 'quote' | 'history' | 'termStructure' | 'prediction'
type ResourceState = LoadState | 'empty'

const demoEnabled = import.meta.env.DEV || import.meta.env.VITE_ENABLE_DEMO_FALLBACK === 'true'

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'CJ2701',
    state: 'idle' as LoadState,
    quote: null as Quote | null,
    history: null as History | null,
    termStructure: null as TermStructure | null,
    prediction: null as Prediction | null,
    sourceMode: 'live' as 'live' | 'demo',
    error: '',
    lastLoadedAt: '' as string,
    loadGeneration: 0,
    resourceStates: { quote: 'idle', history: 'idle', termStructure: 'idle', prediction: 'idle' } as Record<Resource, ResourceState>,
    resourceErrors: { quote: '', history: '', termStructure: '', prediction: '' } as Record<Resource, string>,
  }),
  getters: {
    isEmpty: (state) => !state.quote && !state.prediction,
    displayStatus: (state) => state.sourceMode === 'demo' ? 'DEGRADED' : (state.prediction?.dataStatus ?? state.quote?.dataStatus ?? 'DEGRADED'),
    panelState: (state) => (name: Resource) => {
      const value = state.resourceStates[name]
      return value === 'idle' ? 'loading' : value
    },
  },
  actions: {
    async load(symbol?: string) {
      const generation = ++this.loadGeneration
      this.symbol = (symbol ?? this.symbol).trim().toUpperCase()
      this.state = 'loading'
      this.error = ''
      this.quote = null
      this.history = null
      this.termStructure = null
      this.prediction = null
      this.sourceMode = 'live'
      for (const name of Object.keys(this.resourceStates) as Resource[]) {
        this.resourceStates[name] = 'loading'
        this.resourceErrors[name] = ''
      }
      const loadResource = async <T>(name: Resource, request: Promise<T>, assign: (value: T) => void, empty?: (value: T) => boolean) => {
        try {
          const value = await request
          if (generation !== this.loadGeneration) return false
          assign(value)
          this.resourceStates[name] = empty?.(value) ? 'empty' : 'ready'
          this.state = 'ready'
          return true
        } catch (error) {
          if (generation !== this.loadGeneration) return false
          this.resourceStates[name] = error instanceof ApiError && error.status === 404 ? 'empty' : 'error'
          this.resourceErrors[name] = error instanceof Error ? error.message : '服务暂不可用'
          return false
        }
      }
      const rootSymbol = this.symbol.replace(/\d+$/, '')
      const successes = await Promise.all([
          loadResource('quote', api.quote(this.symbol), value => { this.quote = value }),
          loadResource('history', api.history(this.symbol), value => { this.history = value }, value => value.points.length === 0),
          loadResource('termStructure', api.termStructure(rootSymbol), value => { this.termStructure = value }, value => value.contracts.length === 0),
          loadResource('prediction', api.prediction(this.symbol), value => { this.prediction = value }),
      ])
      if (generation !== this.loadGeneration) return
      if (!successes.some(Boolean)) {
        if (demoEnabled) {
          this.quote = demoBundle.quote
          this.history = demoBundle.history
          this.termStructure = demoBundle.termStructure
          this.prediction = demoBundle.prediction
          this.sourceMode = 'demo'
          this.state = 'ready'
          for (const name of Object.keys(this.resourceStates) as Resource[]) this.resourceStates[name] = 'ready'
          this.error = this.resourceErrors.quote
        } else {
          this.state = 'error'
          this.error = this.resourceErrors.quote || this.resourceErrors.prediction
        }
      }
      this.lastLoadedAt = new Date().toISOString()
    },
  },
})
