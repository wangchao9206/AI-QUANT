import {request,type PaperSession,type RecordPage} from './api'
export interface PersonalRules {riskPct:number;maxMarginPct:number;volumeRatio:number;maxStopAtr:number;cooldownBars:number}
export interface PersonalVersion {id:string;parentId:string|null;title:string;hypothesis:string;validationPlan:string;rules:PersonalRules;engineVersion:string;createdAt:string}
export interface PersonalPlan {state:string;action:'ENTER'|'WAIT'|'HOLD'|'EXIT';direction:number;entryPrice:number;stopPrice:number|null;maxLots:number;riskBudget:number;plannedRisk:number;atr:number|null;ma20:number|null;ma60:number|null;weeklyMa10:number|null;boxLevel:number|null;volumeRatio:number|null;reasons:string[]}
export interface PersonalRunSummary {id:string;name:string;symbol:string;status:string;equity:number;initialCash:number;currentMarketTime:string;versionId:string;versionTitle:string;trainingMode:'GUIDED'|'RULE_REPLAY';riskHalted:boolean}
export interface PersonalRun {session:PaperSession;plan:PersonalPlan;versionId:string;trainingMode:'GUIDED'|'RULE_REPLAY';rules:PersonalRules;trainingStart:string;peakEquity:number;riskHalted:boolean;activeStop:number|null;metrics:{decisions:number;compliant:number;humanAdherencePct:number|null;closedFillFragments:number;closedTradeCount:number;closedNetPnl:number;maxDrawdownPct:number;lossBeyondBudgetCount:number;validationStatus:string;sampleWarning:string}}
export interface PersonalEvent {id:string;barIndex:number;marketTime:string;action:string;compliant:boolean;emotion:number;notes:string;plan:PersonalPlan;outcome:{beforeEquity:number;afterEquity:number;afterMarketTime:string;afterBarIndex:number;positionLots:number;openedFillFragments:number;closedFillFragments:number;notes:string[];riskHalted:boolean;automated:boolean;orders:{side:string;offset_type:string;order_type:string;status:string;rejection_reason:string|null}[]}}
export interface PersonalReflection {id:string;sessionId:string|null;eventId:string|null;category:string;content:string;createdAt:string}
export interface PersonalCreate {versionId:string;name:string;symbol:string;startDate:string;endDate:string;initialCash:number;trainingMode:'GUIDED'|'RULE_REPLAY'}
export interface PersonalStep {commandId:string;expectedBarIndex:number;action:'FOLLOW'|'WAIT'|'EXIT';emotion:number;riskAccepted:boolean;stopAccepted:boolean;noRevenge:boolean;notes:string}
const base='/api/v1/paper/personal'
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const personalApi={
  versions:()=>request<PersonalVersion[]>(base+'/versions'),
  createVersion:(body:{parentId:string;title:string;hypothesis:string;validationPlan:string;rules:PersonalRules})=>request<PersonalVersion[]>(base+'/versions',post(body)),
  runs:(page=1)=>request<RecordPage<PersonalRunSummary>>(`${base}/runs?page=${page}&pageSize=6`),
  create:(body:PersonalCreate)=>request<PersonalRun>(base+'/runs',post(body),180000),
  run:(id:string)=>request<PersonalRun>(`${base}/runs/${encodeURIComponent(id)}`),
  step:(id:string,body:PersonalStep)=>request<PersonalRun>(`${base}/runs/${encodeURIComponent(id)}/step`,post(body),180000),
  events:(id:string,page=1,pageSize=10)=>request<RecordPage<PersonalEvent>>(`${base}/runs/${encodeURIComponent(id)}/events?page=${page}&pageSize=${pageSize}`),
  reflections:(sessionId?:string,page=1,pageSize=10)=>request<RecordPage<PersonalReflection>>(`${base}/reflections?page=${page}&pageSize=${pageSize}${sessionId?'&sessionId='+encodeURIComponent(sessionId):''}`),
  reflect:(body:{sessionId?:string;eventId?:string;category:string;content:string})=>request<void>(base+'/reflections',post(body)),
}
