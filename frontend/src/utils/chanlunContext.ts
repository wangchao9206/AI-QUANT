import type {LocationQuery,LocationQueryRaw} from 'vue-router'
import type {MultiframeRun,MultiframeDraft} from '../features/chanlun/multiframe'
import type {Analysis} from '../features/chanlun/api'
import {contextUuid,tradingQuery,contextPeriod} from './tradingContext'
export const deliverySymbol=(v:unknown)=>typeof v==='string'&&/^[A-Z]{1,4}\d{3,4}$/.test(v.toUpperCase())?v.toUpperCase():''
export const chanObject=(v:unknown)=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(v)?v:''
const frameName=(v:unknown)=>typeof v==='string'&&['DAY','MIN30','MIN5'].includes(v)?v:''
export function multiframeQuery(q:LocationQuery){
 const parsed=tradingQuery(q),errors=[...parsed.errors]
 if(q.symbol!==undefined&&!deliverySymbol(q.symbol))errors.push('缠论多周期入口需要实际交割月，不能以主连代替。')
 const observation=contextUuid(q.observation),frame=frameName(q.frame),structure=chanObject(q.structure)
 if(q.observation!==undefined&&!observation)errors.push('冻结观察标识无效。')
 if(q.frames!==undefined&&q.frames!=='PAIR'&&q.frames!=='TRIPLE')errors.push('多周期组合参数无效。')
 if(q.frame!==undefined&&!frame||q.structure!==undefined&&!structure)errors.push('观察周期或结构标识无效。')
 if((frame||structure)&&!observation||structure&&!frame)errors.push('结构定位需要冻结观察与明确周期。')
 return {...parsed,observation,frame,structure,frames:q.frames==='TRIPLE'?'TRIPLE' as const:'PAIR' as const,errors}
}
const date=(v:unknown)=>typeof v==='string'&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v))
const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v)
/** This checks identity and renderable bounds; the server remains authoritative for reconstruction rules. */
export function multiframeResult(value:unknown,id?:string,requested?:MultiframeDraft):MultiframeRun {
 const fail=()=>{throw new Error('观察响应的身份、合约或冻结来源不一致，已停止展示。')}
 if(!object(value)||!contextUuid(value.id)||id&&value.id!==id||!['QUEUED','RUNNING','WAITING_INPUT','SUCCEEDED','FAILED'].includes(value.status)||!object(value.request))return fail()
 const r=value.request
 if(!contextUuid(r.clientRequestId)||!deliverySymbol(r.symbol)||!['PAIR','TRIPLE'].includes(r.frames)||r.asOf!==null&&!date(r.asOf))return fail()
 if(requested&&(r.clientRequestId!==requested.clientRequestId||r.symbol!==requested.symbol||r.frames!==requested.frames||r.asOf!==requested.asOf&&(r.asOf===null||requested.asOf===null||Date.parse(r.asOf)!==Date.parse(requested.asOf))))return fail()
 const report=value.report
 if(report!==null){
  if(!object(report)||value.status!=='SUCCEEDED'||!object(report.config)||report.config.symbol!==r.symbol||!['HISTORICAL','HISTORICAL_SUCCESSOR_BOUND_RECONSTRUCTION'].includes(report.config.mode)||report.config.priceBasis!=='UNADJUSTED_DELIVERY'||report.executable!==false||!date(report.asOf)||!date(report.capturedAt)||!Array.isArray(report.frames)||!Array.isArray(report.limitations)||typeof report.configHash!=='string')return fail()
  const expected=r.frames==='TRIPLE'?['DAY','MIN30','MIN5']:['MIN30','MIN5']
  if(Date.parse(report.asOf)>Date.parse(report.capturedAt)||report.frames.length!==expected.length||new Set(report.frames.map((f:any)=>f?.frequency)).size!==expected.length)return fail()
  for(const f of report.frames){
   const a=f?.analysis
   if(!object(f)||!expected.includes(f.frequency)||!object(a)||a.symbol!==r.symbol||a.frequency!==f.frequency||a.priceBasis!=='UNADJUSTED_DELIVERY'||!Array.isArray(a.bars)||!a.bars.length||a.observedBars!==a.bars.length||!Array.isArray(a.structures)||!object(f.source)||!date(f.source.receiptAt)||!date(f.lastSealedBy)||!a.bars.every((b:any)=>object(b)&&b.contract===r.symbol&&date(b.timestamp)&&date(b.sealedByTimestamp)&&Date.parse(b.sealedByTimestamp)>Date.parse(b.timestamp)&&Date.parse(b.sealedByTimestamp)<=Date.parse(report.asOf)))return fail()
  }
 }else if(value.status==='SUCCEEDED')return fail()
 return value as unknown as MultiframeRun
}
export function frozenSelection(run:MultiframeRun,frame:string,structure:string){
 if(!frame&&!structure)return null
 const selected=run.report?.frames.find(f=>f.frequency===frame)
 if(!selected)throw new Error('指定周期不在此冻结观察中，不替换其他周期。')
 const item=structure?selected.analysis.structures.find(s=>s.id===structure):undefined
 if(structure&&!item)throw new Error('指定结构不在此周期的冻结结果中，不替换其他结构。')
 return item?{frame:selected,structure:item}:null
}
/** Browser association only, never an immutable evidence binding or an execution qualification. */
export function chanMarketReference(q:LocationQuery,symbol:string):LocationQueryRaw {
 if(!deliverySymbol(symbol)||deliverySymbol(q.symbol)!==symbol||!contextUuid(q.chanObservation))return {}
 if(q.chanFrame!==undefined&&!frameName(q.chanFrame)||q.chanStructure!==undefined&&!chanObject(q.chanStructure)||q.chanStructure!==undefined&&!q.chanFrame)return {}
 return {chanObservation:contextUuid(q.chanObservation),...q.chanFrame?{chanFrame:String(q.chanFrame)}:{},...q.chanStructure?{chanStructure:String(q.chanStructure)}:{}}
}
export function marketOrigin(q:LocationQuery,symbol:string):LocationQueryRaw {
 const next:LocationQueryRaw={symbol,period:String(contextPeriod(q.period??q.seconds)??60)}
 if(deliverySymbol(q.symbol)===symbol&&contextUuid(q.case)){next.case=contextUuid(q.case);if(contextUuid(q.plan))next.plan=contextUuid(q.plan)}
 return next
}
export function historicalResult(value:Analysis,id?:string):Analysis {
 if(!value||id&&value.runId!==id||!chanObject(value.runId)||!value.dataset||typeof value.dataset.symbol!=='string'||value.datasetHash!==value.dataset.sha256||!Number.isInteger(value.observedBars)||value.observedBars<1||value.observedBars>value.dataset.bars||!Array.isArray(value.bars)||!Array.isArray(value.structures)||!Array.isArray(value.layers))throw new Error('历史分析来源与请求不一致，已停止展示。')
 return value
}
