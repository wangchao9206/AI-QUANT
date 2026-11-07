import {describe,it,expect} from 'vitest'
import type {LocationQuery} from 'vue-router'
import type {OptionChain} from '../types/options'
import {optionFuture,optionQuery,optionSelection,optionReference} from './optionContext'
import {tradeSelection} from './tradingContext'
const chain:OptionChain={id:'DCE:DCE.m2701:2026-12-05T15:00:00+08:00',exchange:'DCE',underlyingSymbol:'DCE.m2701',underlyingType:'FUTURE',expiry:'2026-12-05T15:00:00+08:00',product:'m',contractCount:2}
const cid='10000000-0000-4000-8000-000000000001',pid='10000000-0000-4000-8000-000000000002'
describe('professional option identity',()=>{
 it('accepts qualified provider chain identifiers and exact option symbols',()=>{expect(optionQuery({symbol:'M2701',chain:chain.id,option:'DCE.m2701-P-3000',side:'SELL',lots:'3',rate:'.035',dividend:'1e-7',period:'900'})).toMatchObject({symbol:'M2701',chain:chain.id,option:'DCE.m2701-P-3000',side:'SELL',lots:3,rate:.035,dividend:1e-7,frequency:900,errors:[]})})
 const invalid:LocationQuery[]=[{chain:['first','second']},{option:'DCE.m2701-P-3000'},{symbol:'MM'},{symbol:'M0'},{mode:'REPLAY'},{asOf:'2025-01-01'},{side:'SHORT'},{lots:'1.5'},{lots:'10001'},{rate:'NaN'},{rate:' '},{dividend:'-0.1'},{period:'900',seconds:'60'},{plan:pid}]
 it.each(invalid)('rejects ambiguous or unsupported context %j',q=>expect(optionQuery(q).errors.length).toBeGreaterThan(0))
 it('never treats an index or a different exchange as an actual futures month',()=>{expect(optionFuture({...chain,underlyingType:'INDEX',underlyingSymbol:'CFFEX.000300'})).toBe('');expect(optionFuture({...chain,underlyingSymbol:'SHFE.m2701'})).toBe('')})
 it('keeps same-month private references but removes every foreign-month binding',()=>{
   const q={symbol:'M2701',period:'900',case:cid,plan:pid,session:cid,monitor:pid,mode:'LIVE'}
   const same=optionSelection(q,chain,'DCE.m2701-P-3000','SELL',2,.03,.01)
   expect(same).toMatchObject({symbol:'M2701',case:cid,plan:pid,period:'900',side:'SELL',lots:'2',rate:'0.03',dividend:'0.01'})
   expect(same.session).toBeUndefined();expect(same.monitor).toBeUndefined();expect(same.mode).toBeUndefined()
   const changed=optionSelection(q,{...chain,underlyingSymbol:'DCE.m2705'})
   expect(changed.symbol).toBe('M2705');expect(changed.case).toBeUndefined();expect(changed.plan).toBeUndefined()
   expect(optionSelection(q,{...chain,underlyingType:'INDEX'}).symbol).toBeUndefined()
 })
 it('restores the professional selection through a same-futures chart visit and detaches it on month change',()=>{
   const q={symbol:'M2701',period:'900',chain:chain.id,option:'DCE.m2701-P-3000',side:'SELL',lots:'3',rate:'.035',dividend:'0'}
   expect(optionReference(q,'M2701')).toMatchObject({chain:chain.id,option:q.option,side:'SELL',lots:'3',rate:'0.035'})
   expect(optionReference(q,'M2705')).toEqual({})
   const changed=tradeSelection(q,'M2705',900)
   for(const key of ['chain','option','side','lots','rate','dividend'])expect(changed[key]).toBeUndefined()
 })
})
