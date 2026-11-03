import {request} from '../../services/api'
import type {Bar,Structure} from './api'
export type MonitorFrequency='DAY'|'MIN5'|'MIN30'
export interface MonitorDraft {clientRequestId:string;title:string;symbol:string;frequency:MonitorFrequency}
export interface MonitorAnalysis {bars:Bar[];structures:Structure[];profileHash:string;inputHash?:string;observedBars:number;observedAsOfDate:string;priceBasis:string;frequency:MonitorFrequency;symbol:string}
export interface MonitorEvent {eventSeq:number;payload:Structure&{eventType:string;observedIndex:number;eventSeq:number};inboxState:string;detectedAt:string}
export interface MonitorSummary {id:string;title:string;symbol:string;frequency:MonitorFrequency;enabled:boolean;status:string;observedBars:number;heartbeatAt:string|null;error:string|null;profileHash:string|null}
export interface MonitorView extends MonitorSummary {source:{receiptAt?:string;source?:string;closeProof?:string;message?:string;checkedAt?:string}|null;analysis:MonitorAnalysis|null;events:MonitorEvent[]}
export interface MonitorEvidence {event:MonitorEvent['payload'];analysis:MonitorAnalysis;detectedAt:string;viewScope:'EVENT_CANDIDATE_ONLY'}
export interface MonitorReview {id:string;monitorId:string;eventSeq:number;outlook:'UP'|'DOWN'|'WAIT';content:string;lessonNumber:number|null;evidence:MonitorEvidence;createdAt:string}
const base='/api/chanlun/v1/monitors'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const monitorApi={
  list:()=>request<MonitorSummary[]>(base),
  create:(body:MonitorDraft)=>request<MonitorView>(base,post(body)),
  get:(id:string)=>request<MonitorView>(`${base}/${encodeURIComponent(id)}`),
  control:(id:string,enabled:boolean)=>request<MonitorView>(`${base}/${encodeURIComponent(id)}/control`,post({enabled})),
  check:(id:string)=>request<MonitorView>(`${base}/${encodeURIComponent(id)}/check`,post({}),120000),
  evidence:(id:string,seq:number)=>request<MonitorEvidence>(`${base}/${encodeURIComponent(id)}/events/${seq}`),
  ack:(id:string,seq:number)=>request<MonitorView>(`${base}/${encodeURIComponent(id)}/events/${seq}/ack`,post({})),
  review:(id:string,seq:number,body:{clientRequestId:string;outlook:MonitorReview['outlook'];content:string;lessonNumber:number|null})=>request<{id:string}>(`${base}/${encodeURIComponent(id)}/events/${seq}/reviews`,post(body)),
  reviews:()=>request<MonitorReview[]>(`${base}/reviews`),
}
