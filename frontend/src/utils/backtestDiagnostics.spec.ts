import {describe,it,expect} from 'vitest'
import type {BacktestResult} from '../services/api'
import {backtestDiagnostics} from './backtestDiagnostics'
describe('backtest diagnostics',()=>{
  it('counts losing closed trades and distinguishes unresolved drawdown from recovered drawdown',()=>{
    const result={initialCapital:100,tradeLogs:[{action:'OPEN_BUY',pnl:-1},{action:'FLATTEN_LONG',pnl:-2},{action:'ROLL_LONG',pnl:-1},{action:'FLATTEN_SHORT',pnl:-3},{action:'FINAL_FLATTEN',pnl:1}],
      dailyEquity:[{date:'2025-12-29',equity:110},{date:'2025-12-30',equity:100},{date:'2025-12-31',equity:90},{date:'2026-01-02',equity:111},{date:'2026-01-05',equity:105}]} as BacktestResult
    const summary=backtestDiagnostics(result)
    expect(summary.closedTrades).toBe(3)
    expect(summary.maxLosingStreak).toBe(2)
    expect(summary.longestRecovery).toBe(2)
    expect(summary.currentUnderwater).toBe(1)
    expect(summary.years[0]?.returnPct).toBeCloseTo(-10)
    expect(summary.years[1]?.returnPct).toBeCloseTo(16.6666667)
  })
})
