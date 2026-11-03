import {request} from '../../services/api'
import type {Bar} from './api'
import type {MonitorAnalysis,MonitorFrequency} from './monitor'
export interface MultiframeDraft {clientRequestId:string;symbol:string;frames:'PAIR'|'TRIPLE';asOf:string|null}
export interface SealedBar extends Bar {sealedByTimestamp:string;providerIndex:number}
export interface MultiframeFrame {frequency:MonitorFrequency;source:{receiptAt:string;source:string;status:string};analysis:Omit<MonitorAnalysis,'bars'>&{bars:SealedBar[];inputHash:string};lastSealedBy:string;firstProviderIndex:number;lastProviderIndex:number;sourceWindowBars:number;sourceWindowStart:string}
export interface MultiframeReport {configHash:string;capturedAt:string;asOf:string;frames:MultiframeFrame[];config:{symbol:string;mode:string;priceBasis:string};limitations:string[];executable:false}
export interface MultiframeRun {id:string;status:'QUEUED'|'RUNNING'|'WAITING_INPUT'|'SUCCEEDED'|'FAILED';error:string|null;request:MultiframeDraft;report:MultiframeReport|null;createdAt:string}
export interface MultiframeSummary {id:string;status:MultiframeRun['status'];symbol:string;frames:'PAIR'|'TRIPLE';createdAt:string}
const base='/api/chanlun/v1/multiframe'
export const multiframeApi={
  list:()=>request<MultiframeSummary[]>(base),
  get:(id:string)=>request<MultiframeRun>(`${base}/${encodeURIComponent(id)}`),
  create:(body:MultiframeDraft)=>request<MultiframeRun>(base,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},120000),
}
