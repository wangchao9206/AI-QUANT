import {describe,it,expect} from 'vitest'
import type {LocationQuery} from 'vue-router'
import {multiframeQuery,multiframeResult,frozenSelection,chanMarketReference} from './chanlunContext'
import {observationFixture,observationFixtureId as id,structureFixtureId as sid} from '../features/chanlun/contextFixtures'
import {tradeSelection} from './tradingContext'
describe('chanlun source identity',()=>{
 it('keeps market period separate from the stored observation frequency and structure',()=>{expect(multiframeQuery({symbol:'rb2701',period:'900',observation:id,frame:'MIN5',structure:sid})).toMatchObject({symbol:'RB2701',frequency:900,frame:'MIN5',structure:sid,errors:[]})})
 const invalid:LocationQuery[]=[{symbol:'RBM'},{observation:['a','b']},{frame:'MIN5'},{observation:id,structure:sid},{observation:id,frame:'MIN15'},{observation:id,frame:'MIN5',structure:['a','b']},{frames:'DAY'},{mode:'REPLAY'},{asOf:'2025-01-01'}]
 it.each(invalid)('rejects unsupported or ambiguous references: %j',q=>expect(multiframeQuery(q).errors.length).toBeGreaterThan(0))
 it('uses the exact frame even if two frames contain the same structure id',()=>{const value=observationFixture();expect(frozenSelection(value,'MIN5',sid)?.frame.frequency).toBe('MIN5');expect(()=>frozenSelection(value,'DAY',sid)).toThrow('指定周期');expect(()=>frozenSelection(value,'MIN5','missing')).toThrow('指定结构')})
 it('rejects a different observation, contract or renderable frame identity',()=>{
  expect(()=>multiframeResult(observationFixture(),'20000000-0000-4000-8000-000000000002')).toThrow('不一致')
  const value=observationFixture();value.report!.frames[1]!.analysis.symbol='RB2705';expect(()=>multiframeResult(value,id)).toThrow('不一致')
 })
 it('never carries an old observation across a futures month change',()=>{
  const q={symbol:'RB2701',period:'900',chanObservation:id,chanFrame:'MIN5',chanStructure:sid}
  expect(chanMarketReference(q,'RB2701')).toMatchObject({chanObservation:id,chanFrame:'MIN5',chanStructure:sid});expect(chanMarketReference(q,'RB2705')).toEqual({})
  expect(tradeSelection(q,'RB2705',900).chanObservation).toBeUndefined()
 })
})
