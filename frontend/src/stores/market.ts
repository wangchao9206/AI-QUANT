import { defineStore } from 'pinia'

import { ApiError, api, type History, type InstrumentCatalog, type Prediction, type Quote, type TermStructure } from '../services/api'
import { instrumentRoot } from '../utils/marketNavigation'

export type LoadState = 'idle' | 'loading' | 'ready' | 'error'

const RECENT_SYMBOLS_KEY = 'aiquant.recent-symbols'
const DEFAULT_SIDEBAR_SYMBOLS = ['IFM', 'RBM', 'MM', 'CJM', 'SIM', 'TM']
const VALID_SYMBOL = /^[A-Z]{1,4}[A-Z0-9]{0,8}$/

function normalizeSymbol(value: unknown) {
  const symbol = String(value ?? '').trim().toUpperCase()
  return VALID_SYMBOL.test(symbol) ? symbol : ''
}

function loadRecentSymbols() {
  if (typeof window === 'undefined') return [] as string[]
  try {
    const stored = JSON.parse(window.localStorage.getItem(RECENT_SYMBOLS_KEY) ?? '[]')
    if (!Array.isArray(stored)) return []
    return [...new Set(stored.map(normalizeSymbol).filter(Boolean))].slice(0, 5)
  } catch {
    return []
  }
}

function catalogEntry(catalog: InstrumentCatalog | null, symbol: string) {
  for (const group of catalog?.exchanges ?? []) {
    for (const instrument of group.instruments) {
      if (instrument.mainSymbol === symbol || instrument.contracts.includes(symbol)) {
        return { symbol, name: instrument.name, exchange: group.code, mainSymbol: instrument.mainSymbol }
      }
    }
  }
  return null
}

export const useMarketStore = defineStore('market', {
  state: () => ({
    symbol: 'CJM',
    state: 'idle' as LoadState,
    quote: null as Quote | null,
    history: null as History | null,
    termStructure: null as TermStructure | null,
    termStructureError: '',
    prediction: null as Prediction | null,
    catalog: null as InstrumentCatalog | null,
    catalogError: '',
    recentSymbols: loadRecentSymbols(),
    recentSymbolsError: '',
    error: '',
    lastLoadedAt: '' as string,
    requestId:0,
  }),
  getters: {
    isEmpty: (state) => !state.quote && !state.prediction,
    displayStatus: (state) => state.prediction?.dataStatus ?? state.quote?.dataStatus ?? 'DEGRADED',
    instrumentCount: (state) => state.catalog?.exchanges.reduce((total, group) => total + group.instruments.length, 0) ?? 0,
    contractCount: (state) => state.catalog?.exchanges.reduce(
      (total, group) => total + group.instruments.reduce((sum, item) => sum + item.contracts.length, 0), 0,
    ) ?? 0,
    currentInstrument: (state) => catalogEntry(state.catalog, state.symbol),
    sidebarInstruments: (state) => {
      const symbols = [...new Set([state.symbol, ...state.recentSymbols, ...DEFAULT_SIDEBAR_SYMBOLS])]
      return symbols.map((symbol) => catalogEntry(state.catalog, symbol)).filter((item) => item !== null).slice(0, 6)
    },
  },
  actions: {
    rememberSymbol(symbol: string) {
      const normalized = normalizeSymbol(symbol)
      if (!normalized) return
      this.recentSymbols = [normalized, ...this.recentSymbols.filter((item) => item !== normalized)].slice(0, 5)
      if (typeof window !== 'undefined') {
        try {
          window.localStorage.setItem(RECENT_SYMBOLS_KEY, JSON.stringify(this.recentSymbols))
          this.recentSymbolsError = ''
        } catch {
          this.recentSymbolsError = '最近访问已更新，浏览器无法保存；刷新后可能丢失。'
        }
      }
    },
    async loadCatalog() {
      try {
        this.catalog = await api.instruments()
        this.catalogError = ''
      } catch (error) {
        this.catalogError = error instanceof Error ? error.message : '合约目录暂不可用'
      }
    },
    async loadMarket(symbol?:string) { return this.load(symbol,false) },
    async load(symbol?: string,withPrediction=true) {
      const target=(symbol ?? this.symbol).trim().toUpperCase()
      const generation=++this.requestId
      if (target !== this.symbol) {
        this.quote = null
        this.history = null
        this.termStructure = null
        this.prediction = null
      }
      this.symbol = target
      this.state = 'loading'
      this.error = ''
      this.termStructureError = ''
      try {
        const rootSymbol = instrumentRoot(target)
        const termPromise = api.termStructure(rootSymbol).then(curve => {
          if (curve.rootSymbol !== rootSymbol || curve.contracts.some(item => instrumentRoot(item.contract) !== rootSymbol)) {
            throw new Error('合约梯度与当前品种不一致，已停止展示，请刷新或检查行情源。')
          }
          return {curve, error: ''}
        }).catch(error => ({curve: null, error: error instanceof Error ? error.message : '期限结构暂不可用'}))
        const loadObserved = async () => Promise.all([
          api.quote(target), api.history(target), withPrediction?api.prediction(target):Promise.resolve(null),
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
        const term = await termPromise
        if(generation!==this.requestId)return
        this.quote = quote
        this.history = history
        this.termStructure = term.curve
        this.termStructureError = term.error
        this.prediction = prediction
        this.state = 'ready'
        this.rememberSymbol(this.symbol)
      } catch (error) {
        if(generation!==this.requestId)return
        this.quote = null
        this.history = null
        this.termStructure = null
        this.prediction = null
        this.state = 'error'
        this.error = error instanceof Error ? error.message : '实时服务暂不可用'
      } finally {
        if(generation===this.requestId)this.lastLoadedAt = new Date().toISOString()
      }
    },
  },
})
