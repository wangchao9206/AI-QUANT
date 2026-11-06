import {describe,it,expect} from 'vitest'
import {RefreshSchedule} from './refreshSchedule'
describe('adaptive snapshot refresh',()=>{
  it('bounds cached polling and restores live cadence on recovery or explicit refresh',()=>{
    const schedule=new RefreshSchedule(2000)
    let now=0,reads=0
    for(;now<=60000;now+=1000)if(schedule.due(now)){reads++;schedule.received('CACHED',now)}
    expect(reads).toBeLessThanOrEqual(7)
    expect(reads).toBeGreaterThan(2)
    schedule.received('FRESH',now)
    expect(schedule.due(now+1999)).toBe(false)
    expect(schedule.due(now+2000)).toBe(true)
    schedule.failed(now)
    schedule.reset()
    expect(schedule.due(now)).toBe(true)
  })
})
