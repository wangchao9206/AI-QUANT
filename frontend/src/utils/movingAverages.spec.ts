import {describe,it,expect} from 'vitest'
import {MA_PERIODS,movingAverages} from './movingAverages'
describe('full-window price moving averages',()=>{
 it('requires exactly N closes and computes all five periods without shortened windows',()=>{const prices=Array.from({length:200},(_,i)=>i+1),result=movingAverages(prices);for(const n of MA_PERIODS){expect(result[n][n-2]).toBeNull();expect(result[n][n-1]).toBe((n+1)/2);expect(result[n][199]).toBe((201+200-n)/2)}})
 it('does not use later candles and recovers only after invalid closes leave the full window',()=>{const prices=Array.from({length:190},(_,i)=>i+1);const before=movingAverages(prices.slice(0,180));prices[189]=1e9;const after=movingAverages(prices);expect(after[180][179]).toBe(before[180][179]);const missing=movingAverages([1,2,NaN,4,5,6,7,8]);expect(missing[5][6]).toBeNull();expect(missing[5][7]).toBe(6)})
})
