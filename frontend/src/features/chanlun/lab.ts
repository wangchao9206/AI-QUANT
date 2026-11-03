import {request} from '../../services/api'
export type LabGroup='THIRD'|'ALL'
export interface LabDraft {clientRequestId:string;group:LabGroup;initialCash:number}
export interface LabMetric {initialCash:number;finalEquity:number;netPnl:number;returnPct:number;maxDrawdownPct:number;closedTrades:number;winRatePct:number;fees:number;slippageCost:number;overBudgetExits:number;denials:Record<string,number>}
export interface LabCandidate {structureId:string;source:string;confirmedIndex:number;pivotIndex:number;invalidation:number;direction:number;evidence:Record<string,unknown>;firstObservationDate?:string;pivotDate?:string}
export interface LabTrade extends LabCandidate {entryDate:string;exitDate:string;contract:string;lots:number;entryPrice:number;exitPrice:number;netPnl:number;exitReason:string;plannedRisk:number}
export interface LabDecision extends LabCandidate {executionDate?:string;outcome:string}
export interface LabVariant {id:string;metrics:LabMetric;trades:LabTrade[];decisions:LabDecision[];excluded:LabDecision[];curve:Array<{date:string;equity:number}>}
export interface LabReport {engineVersion:string;configHash:string;config:{group:LabGroup;initialCash:number;profileHash:string;datasetHash:string;implementationHash:string;window:string[]};candidateTape:LabCandidate[];invalidationObservations:Record<string,number>;variants:LabVariant[];assumptions:string[];executable:false}
export interface LabExperiment {id:string;status:'RUNNING'|'SUCCEEDED'|'FAILED';error:string|null;createdAt:string;request:LabDraft;report:LabReport|null}
export interface LabSummary {id:string;status:LabExperiment['status'];group:LabGroup;initialCash:number;createdAt:string}
const base='/api/chanlun/v1/lab'
export const labApi={
  recent:()=>request<LabSummary[]>(base),
  get:(id:string)=>request<LabExperiment>(`${base}/${encodeURIComponent(id)}`),
  create:(body:LabDraft)=>request<LabExperiment>(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},120000),
}
