import { describe, expect, it } from 'vitest'
import type { HistoryPoint, PaperFill } from '../services/api'
import { paperChartTrades, tradeLabel } from './paperChartTrades'

const bar=(day:string,contract='JM2701'):HistoryPoint=>({timestamp:day+'T00:00:00+08:00',contract,price:100,changePct:0,open:100,high:102,low:98})
const fill=(time:string,overrides:Partial<PaperFill>={}):PaperFill=>({id:time,marketTime:time,contract:'JM2701',side:'BUY',offset:'OPEN',eventType:'ORDER',quantity:1,marketPrice:100,fillPrice:100.5,fee:3,slippageCost:30,realizedPnl:0,reason:'策略开仓',...overrides})

describe('paper chart execution matching',()=>{
  it('uses Shanghai dates, keeps actual slipped fill prices, deduplicates, and excludes future fills',()=>{
    const f=fill('2025-01-01T16:00:00Z')
    const result=paperChartTrades([bar('2025-01-02')],[f,f,fill('2025-01-03T00:00:00Z')],'2025-01-02T07:00:00Z','HISTORICAL')
    expect(result.trades).toHaveLength(1)
    expect(result.trades[0]).toEqual({...f,timestamp:'2025-01-02T00:00:00+08:00'})
    expect(result.unplaced).toEqual([])
  })
  it('maps Friday night and Saturday early morning only to an observed Monday trading day',()=>{
    const result=paperChartTrades([bar('2025-01-03'),bar('2025-01-06')],[fill('2025-01-03T21:00:00+08:00'),fill('2025-01-04T01:00:00+08:00')],'2025-01-06T16:30:00+08:00','LIVE')
    expect(result.trades.map(t=>t.timestamp)).toEqual(['2025-01-06T00:00:00+08:00','2025-01-06T00:00:00+08:00'])
  })
  it('does not put an unfinished trading day or old-contract roll leg on the preceding/new-contract candle',()=>{
    const old=fill('2025-01-03T15:00:00+08:00',{id:'roll',contract:'JM2501',eventType:'ROLL',offset:'CLOSE',side:'SELL'})
    const night=fill('2025-01-03T21:00:00+08:00')
    const result=paperChartTrades([bar('2025-01-03')],[old,night],'2025-01-03T21:01:00+08:00','LIVE')
    expect(result.trades).toEqual([])
    expect(result.unplaced).toEqual([old,night])
  })
  it('does not truncate to the session snapshot or record page',()=>{
    const fills=Array.from({length:250},(_,i)=>fill('2025-01-02T07:00:00Z',{id:String(i)}))
    expect(paperChartTrades([bar('2025-01-02')],fills,'2025-01-02T07:00:00Z','HISTORICAL').trades).toHaveLength(250)
  })
  it('excludes records outside the selected window and labels all four directions',()=>{
    expect(paperChartTrades([bar('2025-01-03')],[fill('2025-01-02T07:00:00Z')],'2025-01-03T07:00:00Z','HISTORICAL')).toEqual({trades:[],unplaced:[]})
    expect(['BUY','SELL'].flatMap(side=>['OPEN','CLOSE'].map(offset=>tradeLabel({side,offset} as PaperFill)))).toEqual(['买开多','买平空','卖开空','卖平多'])
  })
})
