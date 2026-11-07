import type {ChartGeometry,GeometryLine} from './chartDrawings'

/** Stored indices belong to the old source window. Match timestamps, never reuse those indices. */
export function frozenDecisionGeometry(value:unknown,points:{timestamp:string}[],availableAt:string):ChartGeometry|undefined {
 if(!value||typeof value!=='object')return
 const g=value as ChartGeometry
 if(!Array.isArray(g.lines)||!Number.isFinite(Date.parse(availableAt)))return
 const index=new Map(points.map((p,i)=>[Date.parse(p.timestamp),i]))
 const lines=g.lines.flatMap(raw=>{
  const line=raw as GeometryLine&{startTimestamp?:string;endTimestamp?:string}
  const start=index.get(Date.parse(line.startTimestamp??'')),end=index.get(Date.parse(line.endTimestamp??''))
  if(start===undefined||end===undefined||start>=end||!Number.isFinite(line.startPrice)||!Number.isFinite(line.endPrice)||line.startPrice<=0||line.endPrice<=0||!line.knownAt||!Number.isFinite(Date.parse(line.knownAt))||Date.parse(line.knownAt)>Date.parse(availableAt))return []
  return [{...line,startIndex:start,endIndex:end}]
 })
 return {...g,lines}
}
