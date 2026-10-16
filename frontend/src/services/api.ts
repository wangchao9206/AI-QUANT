export type DataStatus = 'FRESH' | 'CACHED' | 'DEGRADED'

export interface Quote {
  symbol: string
  displayName: string
  price: number
  change: number
  changePct: number
  source: string
  dataStatus: DataStatus
  dataTimestamp: string
}

export interface HistoryPoint {
  timestamp: string
  price: number
  changePct: number
  open?: number
  high?: number
  low?: number
  volume?: number
  openInterest?: number
}

export interface History {
  symbol: string
  seriesSymbol: string
  seriesType: 'CONTINUOUS' | 'CONTRACT' | 'LIVE_SNAPSHOT'
  source: string
  dataStatus: DataStatus
  dataTimestamp: string
  points: HistoryPoint[]
}

export interface TermContract {
  contract: string
  maturityDate: string
  price: number
}

export interface TermStructure {
  rootSymbol: string
  dataStatus: DataStatus
  dataTimestamp: string
  contracts: TermContract[]
}

export interface DepthLevel {
  level: number
  price: number | null
  volume: number
}

export interface MarketTrade {
  id: string
  timestamp: string
  price: number
  volume: number
  amount: number
  openInterest: number
  openInterestChange: number
  side: 'BUY' | 'SELL' | 'NEUTRAL'
}

export interface MarketMicrostructure {
  symbol: string
  source: string
  dataStatus: DataStatus
  dataTimestamp: string
  lastPrice: number | null
  bids: DepthLevel[]
  asks: DepthLevel[]
  trades: MarketTrade[]
}

export interface Instrument {
  exchange: string
  exchangeName: string
  name: string
  node: string
  rootSymbol: string
  mainSymbol: string
  contracts: string[]
}

export interface InstrumentExchange {
  code: string
  name: string
  instruments: Instrument[]
}

export interface InstrumentCatalog {
  source: string
  dataStatus: DataStatus
  dataTimestamp: string
  exchanges: InstrumentExchange[]
}

export interface Dimension {
  key: string
  name: string
  score: number | null
  direction: string
  confidence: number | null
  summary: string
  recommendation: string
  category: 'EMPIRICAL' | 'CULTURAL_REFERENCE'
  dataStatus: 'FRESH' | 'CACHED' | 'UNAVAILABLE' | 'REFERENCE'
  includedInScore: boolean
  weight: number
  sourceName: string
  sourceUrl: string
  observedAt: string
  sampleSize: number
  keyMetrics: Record<string, unknown>
}

export interface Prediction {
  symbol: string
  displayName: string
  price: number
  change: number
  changePct: number
  compositeScore: number
  resonance: number
  confidence: number
  signal: string
  actionDirective: string
  recommendedPositionPct: number
  targetPrice: number
  stopLossPrice: number
  dataStatus: DataStatus
  dataTimestamp: string
  modelVersion: string
  traceId: string
  dimensions: Dimension[]
  culturalReferences: Dimension[]
  eventWindows: string[]
}

export interface Health {
  status: string
  components?: Record<string, { status?: string }>
}

export interface ProviderStatus {
  provider: string
  configured: boolean
  connected: boolean
  lastEventAt: string | null
  fallbackActive: boolean
  message: string
}

export interface KeyEvidence {
  name: string
  score: number | null
  direction: string
  summary: string
}

export interface LeadAnalysis {
  coreAnomaly: string
  marketContext: string
  newsDriver: string
  keyEvidence: KeyEvidence[]
}

export interface LeadExecution {
  actionDirective: string
  entryZone: string
  targetPrice: number
  stopLossPrice: number
  recommendedPositionPct: number
  riskRewardRatio: string
  invalidationCondition: string
}

export interface OpportunityLead {
  id: string
  symbol: string
  displayName: string
  exchange: string
  price: number
  change: number
  changePct: number
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  signal: string
  urgency: 'S' | 'A' | 'B'
  compositeScore: number
  confidence: number
  algorithmType: string
  algorithmName: string
  algorithmBadge: string
  analysis: LeadAnalysis
  execution: LeadExecution
  discoveredAt: string
  dataStatus: DataStatus
  dataTimestamp?: string
}

export interface LeadsResponse {
  source: string
  dataStatus: DataStatus
  scannedCount: number
  leadsCount: number
  dataTimestamp: string
  leads: OpportunityLead[]
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly traceId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface BacktestRequest {
  symbol: string
  strategy: string
  startDate?: string
  endDate?: string
  initialCapital?: number
  positionPct?: number
  feeRate?: number
  slippage?: number
  stopLossAtr?: number
  takeProfitAtr?: number
  leverage?: number
  marginRate?: number
  includeRollCost?: boolean
}

export interface DailyEquityPoint {
  date: string
  equity: number
  benchmarkEquity: number
  cash: number
  positionPct: number
  dailyReturnPct: number
  drawdownPct: number
}

export interface TradeLog {
  timestamp: string
  action: string
  price: number
  positionPct: number
  pnl: number
  returnPct: number
  reason: string
  holdBars: number
  contract?: string | null
  lots?: number
  fee?: number
  slippageCost?: number
  fromContract?: string | null
  toContract?: string | null
  oldPrice?: number | null
  newPrice?: number | null
  priceGap?: number | null
}

export interface BacktestResult {
  strategyName: string
  symbol: string
  dataSource: string
  dataTimestamp: string
  providerSymbol: string
  initialCapital: number
  finalEquity: number
  effectiveLeverage?: number
  rollTrades?: number
  totalRollYieldPct?: number
  rollCostTotal?: number
  rollPriceGapTotal?: number
  rollPriceGapPct?: number
  includeRollCost?: boolean
  executionModel?: string
  rollModelStatus?: string
  limitations?: string[]
  totalReturnPct: number
  annualizedReturnPct: number
  benchmarkReturnPct: number
  alphaPct: number
  maxDrawdownPct: number
  maxDrawdownDays: number
  sharpeRatio: number
  sortinoRatio: number
  calmarRatio: number
  totalTrades: number
  winningTrades: number
  losingTrades: number
  winRate: number
  profitLossRatio: number
  avgTradePnl: number
  avgHoldBars: number
  dailyEquity: DailyEquityPoint[]
  tradeLogs: TradeLog[]
}

export interface BacktestStrategyInfo {
  id: string
  name: string
  description: string
  bestFor?: string[]
  targetReturn?: string
  recommendedParams: {
    positionPct: number
    stopLossAtr: number
    takeProfitAtr: number
    leverage?: number
  }
}

export interface FuturesSymbolInfo {
  symbol: string
  name: string
  exchange: string
  sector: string
}

export interface BacktestPresets {
  strategies: BacktestStrategyInfo[]
  symbols: FuturesSymbolInfo[]
  defaultParams: {
    initialCapital: number
    positionPct: number
    feeRate: number
    slippage: number
    stopLossAtr: number
    takeProfitAtr: number
    marginRate?: number
    leverage?: number
  }
}

export interface HistorySymbolStatus {
  symbol: string
  displayName: string
  exchange: string
  sector: string
  totalBars: number
  startDate: string
  endDate: string
  updatedAt: string
  source?: string
  seriesType?: string
  rejectedBars?: number
}

export interface HistoryStatusResponse {
  totalSymbols: number
  totalBars: number
  cacheDir: string
  symbols: HistorySymbolStatus[]
}

export type PaperMode = 'LIVE' | 'HISTORICAL'
export type PaperSessionStatus = 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'ERROR'

export interface PaperPosition {
  contract: string
  direction: -1 | 0 | 1
  lots: number
  averagePrice: number
  marginOccupied: number
  unrealizedPnl: number
}

export interface PaperOrder {
  id: string
  clientOrderId: string
  side: 'BUY' | 'SELL'
  offset: 'OPEN' | 'CLOSE'
  orderType: 'MARKET' | 'LIMIT' | 'STOP'
  quantity: number
  remainingQuantity: number
  limitPrice?: number | null
  stopPrice?: number | null
  status: 'PENDING' | 'PARTIAL' | 'FILLED' | 'CANCELLED' | 'REJECTED'
  rejectionReason?: string | null
  createdAt: string
}

export interface PaperFill {
  id: string
  orderId?: string | null
  eventType: 'ORDER' | 'ROLL'
  contract: string
  side: 'BUY' | 'SELL'
  offset: 'OPEN' | 'CLOSE'
  quantity: number
  marketPrice: number
  fillPrice: number
  fee: number
  slippageCost: number
  realizedPnl: number
  reason: string
  marketTime: string
}

export interface PaperSession {
  id: string
  name: string
  mode: PaperMode
  symbol: string
  status: PaperSessionStatus
  dataSource: string
  dataTimestamp: string
  initialCash: number
  cashBalance: number
  equity: number
  realizedPnl: number
  commissionPaid: number
  slippagePaid: number
  marginRate: number
  feeRate: number
  slippageTicks: number
  autoRoll: boolean
  currentBarIndex: number
  totalBars: number
  currentMarketTime: string
  currentContract: string
  currentPrice: number
  volumeMultiple: number
  priceTick: number
  marginPerLot: number
  commissionPerLot: number
  version: number
  createdAt: string
  updatedAt: string
  position: PaperPosition
  orders: PaperOrder[]
  fills: PaperFill[]
}

export type PaperSessionSummary = Omit<PaperSession, 'position' | 'orders' | 'fills'>

export interface CreatePaperSessionRequest {
  name: string
  mode: PaperMode
  symbol: string
  startDate?: string
  endDate?: string
  initialCash: number
  marginRate: number
  feeRate: number
  slippageTicks: number
  maxParticipationRate: number
  autoRoll: boolean
}

export interface PlacePaperOrderRequest {
  clientOrderId: string
  side: 'BUY' | 'SELL'
  offset: 'OPEN' | 'CLOSE'
  orderType: 'MARKET' | 'LIMIT' | 'STOP'
  quantity: number
  limitPrice?: number
  stopPrice?: number
}

const REQUEST_TIMEOUT_MS = 15000

async function request<T>(path: string, options: RequestInit = {}, timeoutMs: number = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const traceId = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`

  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        'X-Trace-Id': traceId,
        ...(options.headers || {}),
      },
    })
    if (!response.ok) {
      let errorMsg = `服务返回 ${response.status}`
      try {
        const errorJson = await response.json()
        if (errorJson.detail || errorJson.message) errorMsg = errorJson.detail || errorJson.message
      } catch {
        // use default message
      }
      throw new ApiError(
        errorMsg,
        response.status,
        response.headers.get('X-Trace-Id') ?? traceId,
      )
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请稍后重试', 504, traceId)
    }
    throw new ApiError('无法连接到数据服务', undefined, traceId)
  } finally {
    window.clearTimeout(timer)
  }
}

export const api = {
  instruments: () => request<InstrumentCatalog>('/api/v1/market/instruments'),
  providerStatus: () => request<ProviderStatus>('/api/v1/market/provider'),
  quote: (symbol: string) => request<Quote>(`/api/v1/market/${encodeURIComponent(symbol)}/quote`),
  history: (symbol: string, limit = 5000) => request<History>(`/api/v1/market/${encodeURIComponent(symbol)}/history?limit=${limit}`),
  termStructure: (symbol: string) => request<TermStructure>(`/api/v1/market/${encodeURIComponent(symbol)}/term-structure`),
  microstructure: (symbol: string) => request<MarketMicrostructure>(`/api/v1/market/${encodeURIComponent(symbol)}/microstructure`),
  prediction: (symbol: string) => request<Prediction>(`/api/v1/predictions/${encodeURIComponent(symbol)}`),
  leads: () => request<LeadsResponse>('/api/v1/market/leads'),
  health: () => request<Health>('/actuator/health'),
  runBacktest: (req: BacktestRequest) => request<BacktestResult>('/api/v1/backtest/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }, 180000),
  backtestPresets: () => request<BacktestPresets>('/api/v1/backtest/presets'),
  historyStatus: () => request<HistoryStatusResponse>('/api/v1/data/history/status'),
  paperSessions: () => request<PaperSessionSummary[]>('/api/v1/paper/sessions'),
  paperSession: (id: string) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}`),
  createPaperSession: (body: CreatePaperSessionRequest) => request<PaperSession>('/api/v1/paper/sessions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }, 180000),
  placePaperOrder: (id: string, body: PlacePaperOrderRequest) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}/orders`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }, 30000),
  cancelPaperOrder: (id: string, orderId: string) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}/orders/${encodeURIComponent(orderId)}/cancel`, { method: 'POST' }),
  advancePaperSession: (id: string, steps: number) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}/advance`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ steps }),
  }, 30000),
  pausePaperSession: (id: string) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}/pause`, { method: 'POST' }),
  resumePaperSession: (id: string) => request<PaperSession>(`/api/v1/paper/sessions/${encodeURIComponent(id)}/resume`, { method: 'POST' }),
  deletePaperSession: (id: string) => request<void>(`/api/v1/paper/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
