export interface GeometryLine {id:string;kind:string;label:string;startIndex:number;endIndex:number;startPrice:number;endPrice:number;knownAt?:string}
export interface ChartGeometry {version:string;status:string;asOf?:string;lines:GeometryLine[];features?:Record<string,number>}
export type DrawingKind='LINE'|'RAY'|'HORIZONTAL'|'CHANNEL'
export interface DrawingAnchor {timestamp:string;price:number}
export interface ChartDrawing {id:string;kind:DrawingKind;anchors:DrawingAnchor[]}
export interface DrawingSegment {startIndex:number;endIndex:number;startPrice:number;endPrice:number;role:'edge'|'center'}
export const DRAWING_POINTS:Record<DrawingKind,number>={LINE:2,RAY:2,HORIZONTAL:1,CHANNEL:3}
export const DRAWING_LABELS:Record<DrawingKind,string>={LINE:'两点斜线',RAY:'趋势射线',HORIZONTAL:'水平线',CHANNEL:'平行通道'}
export function drawingStorageKey(key:string){return 'aiquant.chart-drawings.v1.'+encodeURIComponent(key)}
export function readDrawings(raw:string|null):ChartDrawing[]{
  if(!raw)return []
  try{
    const parsed=JSON.parse(raw) as {version?:unknown;items?:unknown}
    if(parsed.version!==1||!Array.isArray(parsed.items))return []
    return parsed.items.slice(-100).filter((item):item is ChartDrawing=>{
      if(!item||typeof item!=='object'||typeof item.id!=='string'||item.id.length>100||!Object.hasOwn(DRAWING_POINTS,item.kind)||!Array.isArray(item.anchors)||item.anchors.length!==DRAWING_POINTS[item.kind as DrawingKind])return false
      return item.anchors.every((a:DrawingAnchor)=>a&&typeof a.timestamp==='string'&&Number.isFinite(Date.parse(a.timestamp))&&typeof a.price==='number'&&Number.isFinite(a.price)&&a.price>0)
    })
  }catch{return []}
}
export function drawingSegments(drawing:ChartDrawing,points:{timestamp:string}[],rightIndex:number):DrawingSegment[]{
  const anchors=drawing.anchors.map(a=>({...a,index:points.findIndex(p=>p.timestamp===a.timestamp)}))
  // Retain saved anchors, but never snap missing old timestamps onto a new candle.
  if(anchors.some(a=>a.index<0)||anchors.length<DRAWING_POINTS[drawing.kind])return []
  let a=anchors[0]!
  if(drawing.kind==='HORIZONTAL')return [{startIndex:0,endIndex:rightIndex,startPrice:a.price,endPrice:a.price,role:'edge'}]
  let b=anchors[1]!
  if(a.index===b.index)return []
  if(drawing.kind!=='LINE'&&a.index>b.index)[a,b]=[b,a]
  const slope=(b.price-a.price)/(b.index-a.index)
  if(drawing.kind==='LINE')return [{startIndex:a.index,endIndex:b.index,startPrice:a.price,endPrice:b.price,role:'edge'}]
  const end=Math.max(a.index,b.index,rightIndex)
  const edge:DrawingSegment={startIndex:a.index,endIndex:end,startPrice:a.price,endPrice:a.price+slope*(end-a.index),role:'edge'}
  if(drawing.kind==='RAY')return [edge]
  const c=anchors[2]!,offset=c.price-(a.price+slope*(c.index-a.index))
  return [edge,{...edge,startPrice:edge.startPrice+offset,endPrice:edge.endPrice+offset},
    {...edge,startPrice:edge.startPrice+offset/2,endPrice:edge.endPrice+offset/2,role:'center'}]
}
