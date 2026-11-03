import {request} from '../../services/api'
import type {Analysis,EngineId,Judgment,Structure,StructureEvent} from './api'
export type ComparisonLayer='BI'|'SEGMENT'|'ZONE'
export interface ComparisonDraft {clientRequestId:string;runIds:string[];layer:ComparisonLayer;projection:'GEOMETRY'|'WITH_CONFIRMATION';confirmedOnly:boolean}
export interface PairEvidence {
  summary:{left:EngineId;right:EngineId;leftOnly:number;rightOnly:number;matched:number;confirmationDifferences:number}
  leftObjects:Structure[];rightObjects:Structure[];confirmationObjects:{left:Structure;right:Structure;leftFlag:string;rightFlag:string}[]
}
export interface ComparisonWitness {observedIndex:number;date:string;pairs:PairEvidence[]}
export interface ComparisonReport {
  version:string;layer:ComparisonLayer;projection:ComparisonDraft['projection'];confirmedOnly:boolean;priceTolerance:number
  sources:{runId:string;engineId:EngineId;profileHash:string;engineVersion:string}[]
  observedBars:number;observedAsOfDate:string;datasetHash:string;priceBasis:string
  firstDifference:ComparisonWitness|null;firstGeometryDifference:ComparisonWitness|null;firstConfirmationDifference:ComparisonWitness|null
  differentObservationCount:number;spans:{startIndex:number;endIndex:number}[]
  timeline:{observedIndex:number;date:string;different:boolean;geometryDifferent:boolean;confirmationDifferent:boolean;counts:Partial<Record<EngineId,number>>}[]
  limitations:string[]
}
export interface ComparisonRun {id:string;status:'RUNNING'|'SUCCEEDED'|'FAILED';error:string|null;request:ComparisonDraft;report:ComparisonReport|null;createdAt:string}
export interface ComparisonSummary {id:string;status:ComparisonRun['status'];layer:ComparisonLayer;projection:ComparisonDraft['projection'];observedBars:number|null;createdAt:string}
export interface ComparisonDetail {comparisonId:string;observedIndex:number;date:string;frames:{sourceRunId:string;analysis:Analysis}[];pairs:PairEvidence[]}
export interface ComparisonJudgment {clientRequestId:string;sourceRunId:string;structureId:string|null;outlook:Judgment['outlook'];content:string;lessonNumber:number|null}
const base='/api/chanlun/v1/comparisons'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const comparisonApi={
  list:()=>request<ComparisonSummary[]>(base),
  get:(id:string)=>request<ComparisonRun>(`${base}/${encodeURIComponent(id)}`),
  create:(body:ComparisonDraft)=>request<ComparisonRun>(base,post(body),120000),
  at:(id:string,index:number)=>request<ComparisonDetail>(`${base}/${encodeURIComponent(id)}/at/${index}`),
  events:(id:string,sourceRunId:string,index:number,structureId:string)=>request<StructureEvent[]>(`${base}/${encodeURIComponent(id)}/events?${new URLSearchParams({sourceRunId,observedIndex:String(index),structureId})}`),
  judge:(id:string,index:number,body:ComparisonJudgment)=>request<{id:string;createdAt:string}>(`${base}/${encodeURIComponent(id)}/at/${index}/judgments`,post(body)),
}
