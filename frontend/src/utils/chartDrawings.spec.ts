import {describe,it,expect} from 'vitest'
import {drawingSegments,readDrawings,type ChartDrawing} from './chartDrawings'
const points=Array.from({length:8},(_,i)=>({timestamp:new Date(Date.UTC(2026,10,7,0,i)).toISOString()}))
const anchor=(i:number,price:number)=>({timestamp:points[i]!.timestamp,price})
describe('manual chart drawing anchors',()=>{
 it('retains time anchors across a rolling window without snapping an absent anchor',()=>{
  const drawing:ChartDrawing={id:'line',kind:'LINE',anchors:[anchor(2,100),anchor(5,106)]}
  expect(drawingSegments(drawing,points.slice(1),6)[0]).toMatchObject({startIndex:1,endIndex:4,startPrice:100,endPrice:106})
  expect(drawingSegments(drawing,points.slice(3),4)).toEqual([])
 })
 it('constructs a three-point parallel channel with equal slopes and a midpoint',()=>{
  const segments=drawingSegments({id:'channel',kind:'CHANNEL',anchors:[anchor(1,100),anchor(3,104),anchor(4,110)]},points,7)
  expect(segments).toEqual([{startIndex:1,endIndex:7,startPrice:100,endPrice:112,role:'edge'},
   {startIndex:1,endIndex:7,startPrice:104,endPrice:116,role:'edge'},
   {startIndex:1,endIndex:7,startPrice:102,endPrice:114,role:'center'}])
 })
 it('rejects broken local records and preserves valid horizontal anchors',()=>{
  const drawing:ChartDrawing={id:'h',kind:'HORIZONTAL',anchors:[anchor(1,100)]}
  expect(readDrawings(JSON.stringify({version:1,items:[drawing,{...drawing,anchors:[anchor(1,-1)]},{...drawing,kind:'SCRIPT'}]}))).toEqual([drawing])
  expect(readDrawings('{broken')).toEqual([])
  expect(drawingSegments(drawing,points,7)).toEqual([{startIndex:0,endIndex:7,startPrice:100,endPrice:100,role:'edge'}])
 })
})
