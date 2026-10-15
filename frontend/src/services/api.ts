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
}

export interface History {
  symbol: string
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

const REQUEST_TIMEOUT_MS = 12000

async function request<T>(path: string): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const traceId = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`

  try {
    const response = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: 'application/json', 'X-Trace-Id': traceId },
    })
    if (!response.ok) {
      throw new ApiError(
        `服务返回 ${response.status}`,
        response.status,
        response.headers.get('X-Trace-Id') ?? traceId,
      )
    }
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
  quote: (symbol: string) => request<Quote>(`/api/v1/market/${encodeURIComponent(symbol)}/quote`),
  history: (symbol: string) => request<History>(`/api/v1/market/${encodeURIComponent(symbol)}/history`),
  termStructure: (symbol: string) => request<TermStructure>(`/api/v1/market/${encodeURIComponent(symbol)}/term-structure`),
  prediction: (symbol: string) => request<Prediction>(`/api/v1/predictions/${encodeURIComponent(symbol)}`),
  health: () => request<Health>('/actuator/health'),
}
