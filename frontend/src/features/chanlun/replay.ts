import {request} from '../../services/api'
import type {Analysis,EngineId,Judgment,Structure} from './api'

export interface ReplayDecision {
  id:string;step:number;observedBars:number;runId:string;judgmentId:string;structureId:string|null;
  outlook:Judgment['outlook'];content:string;createdAt:string;
  evidence:Judgment['evidence']&{replaySessionId:string;replayStep:number;structureSnapshot?:Structure}
}
export interface ReplaySession {
  id:string;title:string;engineId:EngineId;startBars:number;observedBars:number;step:number;
  status:'ACTIVE'|'ADVANCING'|'COMPLETE';error:string|null;analysis:Analysis;decisions:ReplayDecision[];decisionSubmitted:boolean
}
export interface ReplaySummary {id:string;title:string;engineId:EngineId;observedBars:number;step:number;state:'ACTIVE'|'COMPLETE';createdAt:string}
export interface CreateReplay {clientRequestId:string;title:string;engineId:EngineId;datasetId:string;startBars:number}
export interface ReplayDecisionDraft {clientRequestId:string;expectedStep:number;structureId:string|null;outlook:Judgment['outlook'];content:string;lessonNumber:number|null}
const base='/api/chanlun/v1/replays'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const replayApi={
  create:(body:CreateReplay)=>request<ReplaySession>(base,post(body),120000),
  recent:()=>request<ReplaySummary[]>(base),
  view:(id:string)=>request<ReplaySession>(`${base}/${encodeURIComponent(id)}`),
  decide:(id:string,body:ReplayDecisionDraft)=>request<ReplaySession>(`${base}/${encodeURIComponent(id)}/decisions`,post(body)),
  advance:(id:string,body:{clientRequestId:string;expectedStep:number})=>request<ReplaySession>(`${base}/${encodeURIComponent(id)}/advance`,post(body),120000),
}
