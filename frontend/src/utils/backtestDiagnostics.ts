import type { BacktestResult } from '../services/api'

export function backtestDiagnostics(result: BacktestResult) {
  const exits=result.tradeLogs.filter(t=>t.action.includes('FLATTEN'))
  let streak=0,maxLosingStreak=0,peak=result.initialCapital,below=0,longestRecovery=0
  let previous=result.initialCapital
  const years=new Map<string,{year:string;start:number;end:number;days:number}>()
  for(const trade of exits){streak=trade.pnl<0?streak+1:0;maxLosingStreak=Math.max(maxLosingStreak,streak)}
  for(const point of result.dailyEquity){
    const year=point.date.slice(0,4);let row=years.get(year)
    if(!row){row={year,start:previous,end:point.equity,days:0};years.set(year,row)}
    row.end=point.equity;row.days++
    if(point.equity>=peak){peak=point.equity;below=0}else{below++;longestRecovery=Math.max(longestRecovery,below)}
    previous=point.equity
  }
  return {closedTrades:exits.length,maxLosingStreak,longestRecovery,currentUnderwater:below,
    years:[...years.values()].map(row=>({...row,returnPct:row.start>0?(row.end/row.start-1)*100:0}))}
}
