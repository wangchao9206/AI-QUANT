import {MA_PERIODS,type MaPeriod} from './movingAverages'
import {DRAWING_POINTS,type ChartDrawing} from './chartDrawings'
export interface PersonalPreferences {schemaVersion:1;experience:'SIMPLE'|'PRO'}
export interface ChartLayout {theme:'light'|'dark';mainType:'candle'|'line';subChart:'vol'|'macd'|'change';maPeriods:MaPeriod[];autoGroups:string[]}
export interface PrivateChart {schemaVersion:1;layout:ChartLayout;items:ChartDrawing[]}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
function fields(v:unknown,keys:string[]):v is Record<string,unknown>{return object(v)&&Object.keys(v).length===keys.length&&Object.keys(v).every(k=>keys.includes(k))}
function unique(v:unknown,values:readonly unknown[]){return Array.isArray(v)&&v.length<=values.length&&new Set(v).size===v.length&&v.every(k=>values.includes(k))}
const bad=():never=>{throw new Error('私人偏好或画线格式不兼容，原草稿保留。')}
export function validatePreferences(v:unknown):PersonalPreferences {if(!fields(v,['schemaVersion','experience'])||v.schemaVersion!==1||!['SIMPLE','PRO'].includes(String(v.experience)))return bad();return v as unknown as PersonalPreferences}
export function validatePrivateChart(v:unknown):PrivateChart {
 if(!fields(v,['schemaVersion','layout','items'])||v.schemaVersion!==1||!fields(v.layout,['theme','mainType','subChart','maPeriods','autoGroups'])||!Array.isArray(v.items)||v.items.length>100)return bad()
 const l=v.layout;if(!['light','dark'].includes(String(l.theme))||!['candle','line'].includes(String(l.mainType))||!['vol','macd','change'].includes(String(l.subChart))||!unique(l.maPeriods,MA_PERIODS)||!unique(l.autoGroups,['REGRESSION','TREND','HORIZONTAL']))return bad()
 const ids=new Set<string>()
 for(const d of v.items){
  if(!fields(d,['id','kind','anchors'])||typeof d.id!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(d.id)||ids.has(d.id)||typeof d.kind!=='string'||!Object.hasOwn(DRAWING_POINTS,d.kind)||!Array.isArray(d.anchors)||d.anchors.length!==DRAWING_POINTS[d.kind as keyof typeof DRAWING_POINTS])return bad()
  ids.add(d.id)
  for(const a of d.anchors)if(!fields(a,['timestamp','price'])||typeof a.timestamp!=='string'||a.timestamp.length>40||!/T.*(?:Z|[+-]\d\d:\d\d)$/.test(a.timestamp)||!Number.isFinite(Date.parse(a.timestamp))||typeof a.price!=='number'||!Number.isFinite(a.price)||a.price<=0||a.price>1e12)return bad()
  if(d.anchors.length>1&&Date.parse(d.anchors[0].timestamp)===Date.parse(d.anchors[1].timestamp))return bad()
 }
 return v as unknown as PrivateChart
}
