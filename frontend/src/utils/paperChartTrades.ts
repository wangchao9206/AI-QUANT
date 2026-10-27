import type { HistoryPoint, PaperFill, PaperMode } from '../services/api'
import { formatTradingDate } from './format'

/** timestamp is the observed candle label; marketTime remains the fill time. */
export interface ChartTrade extends PaperFill { timestamp: string }

export function tradeLabel(fill: Pick<PaperFill, 'side' | 'offset'>): string {
  if (fill.side === 'BUY') return fill.offset === 'OPEN' ? '买开多' : '买平空'
  return fill.offset === 'OPEN' ? '卖开空' : '卖平多'
}

export function paperChartTrades(points: HistoryPoint[], fills: PaperFill[], asOf: string, mode: PaperMode) {
  const trades: ChartTrade[] = [], unplaced: PaperFill[] = []
  const dates = [...new Set(points.map(p => formatTradingDate(p.timestamp)))].sort()
  const first = dates[0], cutoff = Date.parse(asOf)
  const seen = new Set<string>()
  const byDate = new Map(points.map(p => [formatTradingDate(p.timestamp), p]))
  for (const fill of fills) {
    const time = Date.parse(fill.marketTime)
    if (seen.has(fill.id) || !Number.isFinite(time) || !Number.isFinite(cutoff) || time > cutoff
      || !Number.isFinite(fill.fillPrice) || fill.fillPrice <= 0) continue
    seen.add(fill.id)
    let day = formatTradingDate(fill.marketTime)
    if (mode === 'LIVE') {
      const hour = Number(new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Shanghai', hour: '2-digit', hourCycle: 'h23',
      }).format(new Date(time)))
      if (hour >= 18 || hour < 6) {
        // Use observed trading-day labels for nights/weekends/holidays.
        const earliest = hour >= 18 ? new Date(Date.parse(day + 'T00:00:00Z') + 86400000).toISOString().slice(0, 10) : day
        const observed = dates.find(d => d >= earliest && Date.parse(d) - Date.parse(earliest) <= 14 * 86400000)
        if (!observed) { unplaced.push(fill); continue }
        day = observed
      }
    }
    if (first && day < first) continue
    const bar = byDate.get(day)
    // A roll close on the old contract is not a price on the new-contract bar.
    if (!bar || !bar.contract || bar.contract.toUpperCase() !== fill.contract.toUpperCase()) {
      unplaced.push(fill); continue
    }
    trades.push({ ...fill, timestamp: bar.timestamp })
  }
  return { trades, unplaced }
}
