import {describe,it,expect} from 'vitest'
import {dkxIndicator} from './dkx'
import type {HistoryPoint} from '../services/api'
const bars=(n:number)=>Array.from({length:n},(_,i):HistoryPoint=>({timestamp:new Date(Date.UTC(2026,10,18,1,i)).toISOString(),contract:'FG701',price:i+1,open:i+1,high:i+1,low:i+1,changePct:0}))
describe('DKX causal OHLC calculation',()=>{
 it('requires full 20/29-bar windows and applies weights from 20 down to 1',()=>{
  const result=dkxIndicator(bars(30))
  expect(result.slice(0,19).every(v=>v.dkx===null)).toBe(true)
  expect(result[19]!.dkx).toBeCloseTo(2870/210,10)
  expect(result.slice(0,28).every(v=>v.madkx===null)).toBe(true)
  expect(result[28]!.madkx).toBeCloseTo(2870/210+4.5,10)
 })
 it('uses OHLC weighted MID rather than substituting a close-price moving average',()=>{
  const result=dkxIndicator(bars(29).map(p=>({...p,open:10,high:16,low:8,price:12})))
  expect(result[28]!.dkx).toBeCloseTo(70/6,10);expect(result[28]!.madkx).toBeCloseTo(70/6,10)
 })
 it('does not change the past when future bars are appended or the forming tail updates',()=>{
  const input=bars(50),before=dkxIndicator(input.slice(0,35))
  expect(dkxIndicator(input).slice(0,35)).toEqual(before)
  input[49]={...input[49]!,price:90000,high:90000}
  expect(dkxIndicator(input).slice(0,35)).toEqual(before)
 })
 it('leaves missing OHLC as gaps and warms up again after a contract change',()=>{
  const input=bars(75);input[22]={...input[22]!,open:undefined}
  for(let i=50;i<input.length;i++)input[i]={...input[i]!,contract:'FG705'}
  const result=dkxIndicator(input)
  expect(result[22]!.dkx).toBeNull();expect(result[41]!.dkx).toBeNull();expect(result[42]!.dkx).not.toBeNull()
  expect(result[50]!.dkx).toBeNull();expect(result[68]!.dkx).toBeNull();expect(result[69]!.dkx).not.toBeNull()
  expect(result[74]!.madkx).toBeNull()
 })
})
