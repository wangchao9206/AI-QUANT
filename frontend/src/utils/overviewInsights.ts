import type { MarketRadar, NewsRadar, SignalRadar, OverseasRadar, MarketRadarItem } from '../types/radar'
import type { LeadsResponse } from '../services/api'
import { formatNumber, formatPct } from './format'

export interface DailySummaryStance {
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  title: string
  desc: string
  up: number
  down: number
  flat: number
  upRatio: number
  averageChange: number
}

export interface SectorHighlight {
  name: string
  averageChange: number
  count: number
  up: number
  down: number
}

export interface TurnoverLead {
  symbol: string
  name: string
  exchange: string
  sector: string
  price: number
  changePct: number
  volume: number
  openInterest?: number
}

export interface MacroDigest {
  id: string
  title: string
  summary: string
  url: string
  publisher: string
  publishedAt: string
  relatedSymbols: string[]
  sourceTier?: string
}

export interface VolatilityRiskAlert {
  symbol: string
  name: string
  changePct: number
  reason: string
}

export interface DailySummaryData {
  stance: DailySummaryStance
  topSector: SectorHighlight | null
  bottomSector: SectorHighlight | null
  turnoverFocus: TurnoverLead[]
  macroHighlights: MacroDigest[]
  riskAlerts: VolatilityRiskAlert[]
}

export interface OverseasTransmission {
  symbol: string
  name: string
  price: number
  changePct: number
  unit: string
  relatedSymbols: string[]
  gapExpectation: 'GAP_UP' | 'GAP_DOWN' | 'NEUTRAL'
  expectationText: string
  cautionNote: string
}

export interface ActionableOpportunity {
  id: string
  symbol: string
  name: string
  exchange?: string
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  urgency: 'S' | 'A' | 'B'
  badgeText: string
  badgeType: 'resonance' | 'signal' | 'lead' | 'overseas'
  catalyst: string
  entryZone: string
  stopLoss: string
  targetPrice?: number
  currentPrice?: number
}

export interface PreMarketData {
  transmissions: OverseasTransmission[]
  opportunities: ActionableOpportunity[]
  actionChecklist: string[]
}

export function computeDailySummary(
  market: MarketRadar | null | undefined,
  news: NewsRadar | null | undefined,
  _signals?: SignalRadar | null | undefined,
): DailySummaryData {
  const up = market?.breadth?.up ?? 0
  const down = market?.breadth?.down ?? 0
  const flat = market?.breadth?.flat ?? 0
  const total = up + down + flat

  let upRatio = 50
  if (total > 0) {
    upRatio = Math.round((up / total) * 100)
  }

  let avgChange = 0
  if (market?.sectors && market.sectors.length > 0) {
    const sum = market.sectors.reduce((acc, s) => acc + s.averageChange, 0)
    avgChange = Number((sum / market.sectors.length).toFixed(2))
  } else if (market?.items && market.items.length > 0) {
    const sum = market.items.reduce((acc, it) => acc + it.changePct, 0)
    avgChange = Number((sum / market.items.length).toFixed(2))
  }

  let sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = 'NEUTRAL'
  let title = '结构分化 · 震荡博弈'
  let desc = `上涨 ${up} 家 / 下跌 ${down} 家，多空处于均衡博弈阶段，重点把握独立板块与品种结构性行情。`

  if (total > 0) {
    if (upRatio >= 60) {
      sentiment = 'BULLISH'
      title = '多头主导 · 偏强共振'
      desc = `上涨 ${up} 家 (${upRatio}%)，多头动能明显占优，全市场均涨 ${formatPct(avgChange)}，顺应主线顺势观察。`
    } else if (upRatio <= 40 && down > up) {
      sentiment = 'BEARISH'
      title = '空头主导 · 避险防御'
      desc = `下跌 ${down} 家 (${Math.round((down / total) * 100)}%)，空头承压显著，全市场均跌 ${formatPct(avgChange)}，注意仓位防守与止损防线。`
    }
  }

  const stance: DailySummaryStance = {
    sentiment,
    title,
    desc,
    up,
    down,
    flat,
    upRatio,
    averageChange: avgChange,
  }

  let topSector: SectorHighlight | null = null
  let bottomSector: SectorHighlight | null = null
  if (market?.sectors && market.sectors.length > 0) {
    const sorted = [...market.sectors].sort((a, b) => b.averageChange - a.averageChange)
    if (sorted[0]) {
      topSector = { ...sorted[0] }
    }
    if (sorted.length > 1 && sorted[sorted.length - 1].averageChange < (sorted[0]?.averageChange ?? 0)) {
      bottomSector = { ...sorted[sorted.length - 1] }
    }
  }

  const turnoverFocus: TurnoverLead[] = (market?.items ?? [])
    .slice()
    .sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0))
    .slice(0, 3)
    .map(i => ({
      symbol: i.symbol,
      name: i.name,
      exchange: i.exchange,
      sector: i.sector,
      price: i.price,
      changePct: i.changePct,
      volume: i.volume,
      openInterest: i.openInterest,
    }))

  const macroHighlights: MacroDigest[] = (news?.items ?? [])
    .slice()
    .sort((a, b) => Number(b.sourceTier === 'PRIMARY') - Number(a.sourceTier === 'PRIMARY'))
    .slice(0, 3)
    .map(n => ({
      id: n.id,
      title: n.title,
      summary: n.summary,
      url: n.url,
      publisher: n.publisher,
      publishedAt: n.publishedAt,
      relatedSymbols: n.relatedSymbols ?? [],
      sourceTier: n.sourceTier,
    }))

  const riskAlerts: VolatilityRiskAlert[] = (market?.items ?? [])
    .filter(i => Math.abs(i.changePct) >= 2.5)
    .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
    .slice(0, 3)
    .map(i => ({
      symbol: i.symbol,
      name: i.name,
      changePct: i.changePct,
      reason: `日内振幅达 ${formatPct(i.changePct)}，波动显著放大，警惕隔夜单边跳空与追涨杀跌风险。`,
    }))

  return {
    stance,
    topSector,
    bottomSector,
    turnoverFocus,
    macroHighlights,
    riskAlerts,
  }
}

export function computePreMarketOpportunities(
  overseas: OverseasRadar | null | undefined,
  signals: SignalRadar | null | undefined,
  leads: LeadsResponse | null | undefined,
  market: MarketRadar | null | undefined,
): PreMarketData {
  const overseasItems = overseas?.items ?? []
  const transmissions: OverseasTransmission[] = overseasItems
    .slice()
    .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
    .slice(0, 4)
    .map(it => {
      let gapExpectation: 'GAP_UP' | 'GAP_DOWN' | 'NEUTRAL' = 'NEUTRAL'
      let expectationText = '平开震荡'
      let cautionNote = '外盘隔夜波动温和，预计境内开盘走势平稳，重在跟踪日内独立形态与资金动向。'

      if (it.changePct >= 0.5) {
        gapExpectation = 'GAP_UP'
        expectationText = '偏高开预警'
        cautionNote = `外盘${it.name}隔夜强劲（${formatPct(it.changePct)}），境内关联品种开盘存在高开冲动，注意防范开盘5分钟诱多与冲高回落。`
      } else if (it.changePct <= -0.5) {
        gapExpectation = 'GAP_DOWN'
        expectationText = '偏低开预警'
        cautionNote = `外盘${it.name}隔夜承压下挫（${formatPct(it.changePct)}），境内关联品种开盘承压，关注关键支撑防线与早盘回补力度。`
      }

      return {
        symbol: it.symbol,
        name: it.name,
        price: it.price,
        changePct: it.changePct,
        unit: it.unit,
        relatedSymbols: it.relatedSymbols ?? [],
        gapExpectation,
        expectationText,
        cautionNote,
      }
    })

  const marketMap = new Map<string, MarketRadarItem>()
  for (const m of market?.items ?? []) {
    marketMap.set(m.symbol, m)
  }

  const signalList = signals?.items ?? []
  const leadList = (leads?.leads ?? []).filter(l => l.algorithmType !== 'CYCLE_PIVOT')

  const opportunities: ActionableOpportunity[] = []
  const seenSymbols = new Set<string>()

  // A) Resonance Check: Symbol in both signals and leads with compatible direction
  for (const sig of signalList) {
    const matchedLead = leadList.find(l => l.symbol === sig.symbol)
    if (matchedLead) {
      const dir: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = sig.signal === 'BUY' ? 'BULLISH' : 'BEARISH'
      const mItem = marketMap.get(sig.symbol)

      opportunities.push({
        id: `res-${sig.symbol}`,
        symbol: sig.symbol,
        name: sig.name || matchedLead.displayName,
        exchange: mItem?.exchange || matchedLead.exchange,
        direction: dir,
        urgency: matchedLead.urgency || 'S',
        badgeText: '🔥 策略与线索强共振',
        badgeType: 'resonance',
        catalyst: `${sig.reason || '日线策略条件达成'}；${matchedLead.analysis?.coreAnomaly || '多维量价异动'}`,
        entryZone: matchedLead.execution?.entryZone || (dir === 'BULLISH' ? `突破 ${formatNumber(sig.upper, 2)}` : `跌破 ${formatNumber(sig.lower, 2)}`),
        stopLoss: matchedLead.execution?.stopLossPrice
          ? `${formatNumber(matchedLead.execution.stopLossPrice, 2)} (失效防线)`
          : (dir === 'BULLISH' ? `下破 ${formatNumber(sig.lower, 2)} 止损` : `上破 ${formatNumber(sig.upper, 2)} 止损`),
        targetPrice: matchedLead.execution?.targetPrice,
        currentPrice: mItem?.price ?? sig.close,
      })
      seenSymbols.add(sig.symbol)
    }
  }

  // B) High Urgency Leads (S or A urgency)
  for (const l of leadList) {
    if (seenSymbols.has(l.symbol)) continue
    if (l.urgency === 'S' || l.urgency === 'A') {
      const mItem = marketMap.get(l.symbol)
      opportunities.push({
        id: `lead-${l.id || l.symbol}`,
        symbol: l.symbol,
        name: l.displayName,
        exchange: l.exchange,
        direction: l.direction,
        urgency: l.urgency,
        badgeText: `${l.algorithmBadge || '量价异动'} · 优先级 ${l.urgency}`,
        badgeType: 'lead',
        catalyst: l.analysis?.coreAnomaly || `${l.algorithmName || '量价模型'} 发出显著异动信号`,
        entryZone: l.execution?.entryZone || (l.direction === 'BULLISH' ? '回踩企稳确认区间' : '反弹承压受阻区间'),
        stopLoss: l.execution?.stopLossPrice ? `${formatNumber(l.execution.stopLossPrice, 2)} (严格止损)` : '以破位支撑为硬止损',
        targetPrice: l.execution?.targetPrice,
        currentPrice: mItem?.price ?? l.price,
      })
      seenSymbols.add(l.symbol)
    }
    if (opportunities.length >= 6) break
  }

  // C) Strategy Breakthrough Signals (if not enough)
  if (opportunities.length < 6) {
    for (const sig of signalList) {
      if (seenSymbols.has(sig.symbol)) continue
      const dir: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = sig.signal === 'BUY' ? 'BULLISH' : 'BEARISH'
      const mItem = marketMap.get(sig.symbol)
      opportunities.push({
        id: `sig-${sig.id || sig.symbol}`,
        symbol: sig.symbol,
        name: sig.name,
        exchange: mItem?.exchange,
        direction: dir,
        urgency: 'A',
        badgeText: `${sig.strategy} 触发`,
        badgeType: 'signal',
        catalyst: sig.reason || `日线触发 ${sig.signal === 'BUY' ? '多头突破' : '空头破位'} 条件`,
        entryZone: dir === 'BULLISH' ? `突破上轨 ${formatNumber(sig.upper, 2)} 确认` : `下破下轨 ${formatNumber(sig.lower, 2)} 确认`,
        stopLoss: dir === 'BULLISH' ? `回跌破 ${formatNumber(sig.lower, 2)} 止损` : `反弹突破 ${formatNumber(sig.upper, 2)} 止损`,
        currentPrice: mItem?.price ?? sig.close,
      })
      seenSymbols.add(sig.symbol)
      if (opportunities.length >= 6) break
    }
  }

  // D) Overseas Catalyst transmission to domestic (if still < 4)
  if (opportunities.length < 4) {
    for (const tr of transmissions) {
      if (Math.abs(tr.changePct) >= 0.5) {
        for (const rel of tr.relatedSymbols) {
          if (seenSymbols.has(rel)) continue
          const mItem = marketMap.get(rel)
          const dir = tr.changePct > 0 ? 'BULLISH' : 'BEARISH'
          opportunities.push({
            id: `ovs-${rel}`,
            symbol: rel,
            name: mItem?.name || rel,
            exchange: mItem?.exchange,
            direction: dir,
            urgency: 'B',
            badgeText: `外盘联动催化 (${tr.name})`,
            badgeType: 'overseas',
            catalyst: `外盘 ${tr.name} 隔夜变动 ${formatPct(tr.changePct)}，催化境内 ${rel} 开盘跳空预期`,
            entryZone: dir === 'BULLISH' ? '待集合竞价完成，回踩支撑企稳' : '待反弹衰竭，破位顺势',
            stopLoss: '开盘价反向 1.5% 为防御警戒线',
            currentPrice: mItem?.price,
          })
          seenSymbols.add(rel)
          if (opportunities.length >= 4) break
        }
      }
    }
  }

  const actionChecklist = [
    '08:45-08:55：核对隔夜外盘大宗收盘价差与人民币汇率传导预期。',
    '08:55-09:00：盯紧集合竞价撮合价量，严防假单虚挂与极端跳空缺口。',
    '09:00-09:05：等待开盘前5分钟脉冲消化，严格在突破确认或支撑回踩后按计划入场。',
    '全天纪律：单品种风险敞口严控在净资产 2% 以内，破位坚决止损，绝不逆势扛单。',
  ]

  return {
    transmissions,
    opportunities: opportunities.slice(0, 6),
    actionChecklist,
  }
}
