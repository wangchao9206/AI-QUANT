import {describe,it,expect} from 'vitest'
import {frozenDecisionGeometry} from './decisionGeometry'
const points=[{timestamp:'2026-11-06T07:00:00Z'},{timestamp:'2026-11-06T07:15:00Z'},{timestamp:'2026-11-06T07:30:00Z'}]
const line={id:'frozen',kind:'REGRESSION_CENTER',label:'原线',startIndex:560,endIndex:599,startPrice:100,endPrice:110,startTimestamp:points[0]!.timestamp,endTimestamp:points[2]!.timestamp,knownAt:points[1]!.timestamp}
describe('frozen decision geometry',()=>{
 it('matches timestamp anchors after the historical data window moved',()=>{
  const g=frozenDecisionGeometry({version:'v1',status:'READY',lines:[line]},points,'2026-11-06T07:45:00Z')
  expect(g?.lines[0]).toMatchObject({startIndex:0,endIndex:2,startPrice:100,endPrice:110})
 })
 it('does not snap missing anchors or future confirmations to present candles',()=>{
  expect(frozenDecisionGeometry({lines:[line]},points.slice(1),'2026-11-06T07:45:00Z')?.lines).toEqual([])
  expect(frozenDecisionGeometry({lines:[line]},points,'2026-11-06T07:00:00Z')?.lines).toEqual([])
  expect(frozenDecisionGeometry({lines:[{...line,startTimestamp:undefined}]},points,'2026-11-06T07:45:00Z')?.lines).toEqual([])
 })
})
