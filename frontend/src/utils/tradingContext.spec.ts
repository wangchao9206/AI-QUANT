import {describe,it,expect} from 'vitest'
import type {LocationQuery} from 'vue-router'
import {tradingQuery,tradeSelection,instrumentContextPath} from './tradingContext'
const cid='10000000-0000-4000-8000-000000000001',pid='10000000-0000-4000-8000-000000000002'
describe('trading URL identity',()=>{
 it('keeps actual delivery month, period and chosen tab',()=>{expect(tradingQuery({symbol:'rb2701',period:'900',case:cid,plan:pid,tab:'options'})).toMatchObject({symbol:'RB2701',frequency:900,tab:'options',errors:[]})})
 const invalid:LocationQuery[]=[{period:'30MIN'},{period:'900',seconds:'60'},{symbol:['RB2701','RB2705']},{mode:'REPLAY'},{asOf:'2020-01-01'},{plan:pid},{case:'bad'},{tab:['futures','options']}]
 it.each(invalid)('rejects ambiguous context %j',q=>expect(tradingQuery(q).errors.length).toBeGreaterThan(0))
 it('recognizes a case id carried by the route instead of a duplicated query',()=>expect(tradingQuery({plan:pid},true).errors).toEqual([]))
 it('detaches all prior bindings when choosing another delivery month',()=>{const q=tradeSelection({symbol:'RB2701',period:'900',case:cid,plan:pid,monitor:cid,session:cid,decision:cid},'RB2705','DAY');expect(q.symbol).toBe('RB2705');expect(q.period).toBe('DAY');for(const k of ['case','plan','monitor','session','decision'])expect(q[k]).toBeUndefined()})
 it('retains a verified same-instrument context and period across detail pages',()=>{expect(instrumentContextPath('/strategy/RB2701',{case:cid,plan:pid,period:'900'},'RB2701','RB2701').query).toEqual({case:cid,plan:pid,period:'900'});expect(instrumentContextPath('/strategy/RB2705',{case:cid,plan:pid,period:'900'},'RB2705','RB2701').query).toEqual({period:'900'})})
})
