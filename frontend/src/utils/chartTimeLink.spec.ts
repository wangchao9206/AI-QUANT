import {describe,it,expect} from 'vitest'
import {lastTimeAtOrBefore,timeWindowIndices} from './chartTimeLink'
describe('time-bound chart links',()=>{
  const bars=[{start:'2026-10-30T09:00:00+08:00',sealed:'2026-10-30T09:30:00+08:00'},{start:'2026-10-30T09:30:00+08:00',sealed:'2026-10-30T10:00:00+08:00'}]
  it('maps to the last proven-sealed bar rather than a later candle with an earlier start',()=>{
    expect(lastTimeAtOrBefore(bars,'2026-10-30T01:40:00Z',b=>b.sealed)).toBe(0)
    expect(lastTimeAtOrBefore(bars,'2026-10-30T09:20:00+08:00',b=>b.sealed)).toBeNull()
    expect(lastTimeAtOrBefore(bars,'unknown',b=>b.sealed)).toBeNull()
  })
  it('does not select future data if the other timeframe has no candle before the window',()=>{
    expect(timeWindowIndices(bars,{start:'2026-10-29T00:00:00Z',end:'2026-10-29T20:00:00Z'},b=>b.start)).toBeNull()
    expect(timeWindowIndices(bars,{start:'2026-10-30T09:10:00+08:00',end:'2026-10-30T09:40:00+08:00'},b=>b.start)).toEqual({start:0,end:2})
  })
})
