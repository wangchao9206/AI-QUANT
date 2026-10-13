import type { History, Prediction, Quote, TermStructure } from './api'

const now = new Date().toISOString()
const prices = [742.6, 744.2, 743.1, 746.8, 748.4, 747.2, 750.6, 753.1, 751.9, 755.8, 758.4, 757.2, 760.8, 762.6]

export const demoQuote: Quote = {
  symbol: 'RB2505', displayName: '螺纹钢 2505', price: 3768, change: 31, changePct: 0.83,
  source: '演示快照（非实时）', dataStatus: 'DEGRADED', dataTimestamp: now,
}

export const demoHistory: History = {
  symbol: 'RB2505', dataStatus: 'DEGRADED', dataTimestamp: now,
  points: prices.map((price, index) => ({
    timestamp: new Date(Date.now() - (prices.length - index) * 3600_000).toISOString(),
    price: Math.round(price * 5), changePct: index ? (price / prices[index - 1] - 1) * 100 : 0,
  })),
}

export const demoTermStructure: TermStructure = {
  rootSymbol: 'RB', dataStatus: 'DEGRADED', dataTimestamp: now,
  contracts: [
    { contract: 'RB2505', maturityDate: '2026-05-15', price: 3768 },
    { contract: 'RB2510', maturityDate: '2026-10-15', price: 3792 },
    { contract: 'RB2601', maturityDate: '2027-01-15', price: 3815 },
    { contract: 'RB2605', maturityDate: '2027-05-15', price: 3831 },
  ],
}

const dimensionNames = ['趋势动量', '量价结构', '期限结构', '波动状态', '资金流向', '持仓变化', '基差强弱', '宏观因子', '产业供需', '情绪温度', '事件风险']

export const demoPrediction: Prediction = {
  symbol: 'RB2505', displayName: '螺纹钢 2505', price: 3768, change: 31, changePct: 0.83,
  compositeScore: 67.4, resonance: 0.73, confidence: 0.81, signal: '谨慎偏多',
  actionDirective: '等待回踩确认，分两次建立观察仓位', recommendedPositionPct: 18,
  targetPrice: 3896, stopLossPrice: 3698, dataStatus: 'DEGRADED', dataTimestamp: now,
  modelVersion: 'demo-2.0', traceId: 'demo-local-snapshot',
  dimensions: dimensionNames.map((name, index) => ({
    key: `dimension_${index + 1}`, name,
    score: [78, 71, 64, 42, 69, 58, 73, 61, 55, 66, 47][index],
    direction: index === 3 || index === 10 ? 'NEUTRAL' : 'BULLISH',
    confidence: [0.88, 0.82, 0.76, 0.67, 0.79, 0.72, 0.84, 0.7, 0.68, 0.75, 0.63][index],
    summary: `${name}处于可观察区间，证据强度已纳入综合评分。`,
    recommendation: index === 3 ? '控制追价节奏' : '保持条件式偏多观察', keyMetrics: {},
  })),
  eventWindows: ['10:00 产业库存数据', '14:30 主力合约移仓观察', '周五 宏观数据窗口'],
}

export const demoBundle = {
  quote: demoQuote,
  history: demoHistory,
  termStructure: demoTermStructure,
  prediction: demoPrediction,
}
