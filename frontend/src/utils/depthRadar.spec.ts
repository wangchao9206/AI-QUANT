import {describe,it,expect} from 'vitest'
import {depthRadar} from './depthRadar'
import type {MarketMicrostructure} from '../services/api'
const now=Date.parse('2026-11-06T02:00:30Z')
const snapshot=():MarketMicrostructure=>({symbol:'RB2701',source:'test',dataStatus:'FRESH',dataTimestamp:new Date(now).toISOString(),lastPrice:100,bids:[{level:1,price:99,volume:80},{level:2,price:null,volume:999}],asks:[{level:1,price:100,volume:20}],trades:[{id:'1',timestamp:new Date(now-1000).toISOString(),price:100,volume:12,amount:0,openInterest:100,openInterestChange:0,side:'BUY'},{id:'2',timestamp:new Date(now-2000).toISOString(),price:99,volume:3,amount:0,openInterest:100,openInterestChange:0,side:'SELL'}]})
describe('observed depth radar',()=>{
 it('calculates visible depth imbalance and classifiable tick volumes',()=>{const r=depthRadar(snapshot(),now);expect(r.imbalance).toBe(.6);expect(r.spread).toBe(1);expect(r.bidLots).toBe(80);expect(r.bidCoverage).toBe(1);expect(r.buyRatio).toBe(.8);expect(r.maxTick).toBe(12);expect(r.fresh).toBe(true)})
 it('deduplicates ticks and excludes future and out-of-window observations',()=>{const s=snapshot();s.trades.push({...s.trades[0]!},{...s.trades[0]!,id:'future',timestamp:new Date(now+1000).toISOString()},{...s.trades[0]!,id:'old',timestamp:new Date(now-60001).toISOString()});expect(depthRadar(s,now).buy).toBe(12)})
 it('keeps absent or crossed depth and unknown direction distinct from zero',()=>{expect(depthRadar(null,now).imbalance).toBeNull();const s=snapshot();s.asks[0]!.price=98;s.trades.forEach(t=>t.side='NEUTRAL');const r=depthRadar(s,now);expect(r.spread).toBeNull();expect(r.imbalance).toBeNull();expect(r.buyRatio).toBeNull();expect(r.neutral).toBe(15)})
 it('treats cached, stale and future timestamps as inactive even if recently retrieved',()=>{const s=snapshot();expect(depthRadar(s,now+16000).fresh).toBe(false);expect(depthRadar(s,now-1000).fresh).toBe(false);s.dataStatus='CACHED';expect(depthRadar(s,now).fresh).toBe(false)})
})
