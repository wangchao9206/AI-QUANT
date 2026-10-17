export type ResearchMode = 'EMPIRICAL' | 'CULTURAL_COMPARE'
export interface ModeEvidence {
  score: number; signal: string; resonance: number; empiricalCoverage: number
  availableDimensions: number; totalDimensions: number; culturalEffectiveWeight: number
  missing: string[]; confidenceMeaning: string; calibratedWinRate: null
}
export interface ExecutionQuote {
  priceBasis?: 'COMPLETED_DAILY_CLOSE'
  symbol: string; price: number; dataTimestamp: string; volumeMultiple: number | null
  priceTick: number | null; marginPerLot: number | null; commissionPerLot: number | null
  upperLimit: number | null; lowerLimit: number | null; expiryTimestamp: number | null
}
export interface ResearchContext {
  symbol: string; modelVersion: string; signalTimestamp: string; traceId: string
  execution: { contract: string | null; quote: ExecutionQuote | null; marketState: string; phase: string; checkedAt: string }
  atr: number | null; atrBasis: string; modes: Record<ResearchMode, ModeEvidence>
  events: { type: string; label: string; urgent: boolean }[]; dimensionNote: string
}
export interface PlanRequest {
  symbol: string; mode: ResearchMode; expectedContract?: string
  equity: number; riskPct: number; marginBudgetPct: number; maxLeverage: number
  dailyLossLimitPct: number; dailyLoss: number; totalRiskLimitPct: number
  otherRisk: number; otherMargin: number; otherNotional: number
  positionSide: 'FLAT' | 'LONG' | 'SHORT'; existingLots: number
  entryPrice?: number; stopPrice?: number; targetPrice?: number
  feeRate: number; slippageTicks: number; marginRate: number
}
export interface ResearchPlan {
  researchContext?: ResearchContext
  planId: string; createdAt: string; symbol: string; contract: string; mode: ResearchMode
  modeEvidence: ModeEvidence; modelVersion: string; dataTimestamp: string; marketState: string
  action: string; actionMessage: string; gates: string[]; entryPrice: number
  stopPrice: number | null; targetPrice: number | null; scenarioDirection: string
  maxLots: number; newLots: number; reduceLots: number; limits: {risk: number; margin: number; leverage: number}
  riskPerLot: number | null; frictionPerLot: number; riskBudget: number; plannedLoss: number
  existingPositionRisk: number; marginRequired: number; marginPct: number; notionalLeverage: number; lossPct: number
  holdingHorizon: string; validity: string; trigger: string; invalidation: string; assumptions: string[]; inputs: PlanRequest
}
export interface ValidationStrategy {
  symbol: string; strategy: string; baseReturn: number; stressedReturn: number | null
  maxDrawdown: number; trades: number; source: string
}
export interface ValidationSnapshot {
  status: string; message?: string; modelVersion?: string; currentModelVersion?: string; generatedAt?: string
  period?: {start: string; end: string}; assets?: number; cases?: number
  executionChecks?: {missedStops: number; offTickFills: number; cashDifference: number}
  strategies: ValidationStrategy[]; profitabilityValidated: false; outOfSampleValidated?: false
  limits?: string[]
}
