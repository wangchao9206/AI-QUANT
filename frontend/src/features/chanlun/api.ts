import {request} from '../../services/api'

export type EngineId='native'|'chanpy'|'czsc'|'baseline'
export interface Engine {id:EngineId;name:string;status:'AVAILABLE'|'UNAVAILABLE';layers:string[]}
export interface Dataset {id:string;sha256:string;symbol:string;displayName:string;frequency:string;bars:number;start:string;end:string;priceBasis:string}
export interface Bar {index:number;date:string;timestamp:string;contract:string;open:number;high:number;low:number;close:number;volume:number}
export interface Structure {
  id:string;type:'FRACTAL'|'BI'|'SEGMENT'|'ZONE'|'BSP';startIndex:number;endIndex:number;direction:'UP'|'DOWN'|'RANGE';
  startPrice?:number;endPrice?:number;low?:number;high?:number;revision:number;engineConfirmed:boolean|null;
  rawFlag:string;firstObservedDate:string;engineConfirmedDate:string|null;eligibleAt:null;
  pivotStartDate:string;pivotEndDate:string;observedAsOfDate:string;state:string
  signalType?:string;signalState?:'CANDIDATE'|'INVALIDATED';invalidation?:number;evidence?:Record<string,unknown>
}
export interface StructureEvent extends Structure {eventType:'OBSERVED'|'REVISED'|'RETRACTED';observedDate:string;eventSeq:number}
export interface Analysis {
  runId:string;engineId:EngineId;engineVersion:string;profileHash:string;profile:{parameters:Record<string,unknown>};
  dataset:Dataset;datasetHash:string;observedBars:number;observedAsOfDate:string;priceBasis:string;
  bars:Bar[];structures:Structure[];counts:Partial<Record<Structure['type'],number>>;layers:string[];recordedAt:string
  derivedFrom?:{protocol:string;sourceRunId:string;observedIndex:number;sourceRecordedAt:string}
}
export interface Run {id:string;engineId:EngineId;observedBars:number;status:'QUEUED'|'RUNNING'|'SUCCEEDED'|'FAILED';error:string|null}
export interface Judgment {id:string;runId:string;structureId:string|null;outlook:'UP'|'DOWN'|'WAIT';content:string;createdAt:string;evidence:{engineId:EngineId;profileHash:string;datasetHash:string;observedAsOfDate:string;lessonNumber?:number;comparisonId?:string;sourceRunId?:string;observedIndex?:number}}
export interface JudgmentDraft {clientRequestId:string;runId:string;structureId:string|null;outlook:Judgment['outlook'];content:string;lessonNumber:number|null}
const base='/api/chanlun/v1'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const chanlunApi={
  engines:()=>request<Engine[]>(`${base}/engines`),
  datasets:()=>request<Dataset[]>(`${base}/datasets`),
  create:(body:{clientRequestId:string;engineId:EngineId;datasetId:string;observedBars:number})=>request<Run>(`${base}/runs`,post(body),120000),
  run:(id:string)=>request<Run>(`${base}/runs/${encodeURIComponent(id)}`),
  result:(id:string)=>request<Analysis>(`${base}/runs/${encodeURIComponent(id)}/structures`,{},120000),
  events:(id:string,structureId:string)=>request<StructureEvent[]>(`${base}/runs/${encodeURIComponent(id)}/events?structureId=${encodeURIComponent(structureId)}`),
  judge:(body:JudgmentDraft)=>request<{id:string;createdAt:string}>(`${base}/judgments`,post(body)),
  judgments:()=>request<Judgment[]>(`${base}/judgments`),
}
