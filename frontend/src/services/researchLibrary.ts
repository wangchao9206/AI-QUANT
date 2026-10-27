import {request} from './api'

export type Metrics = {initialCash:number; finalEquity:number; returnPct:number; netPnl:number; maxDrawdownPct:number; closedTrades:number; [key:string]:unknown}
export type StudySummary = {id:string;title:string;badge:string;subtitle:string;scope:string;count:number;conclusion:string;defaultFamily:string}
export type ResearchCatalog = {revision:string;date:string;totalRuns:number;qualifiedCount:number;studies:StudySummary[]}
export type Run = {id:number;stage:string;family:string;symbol?:string;capital:number;cost:number;mode?:string;repair?:string;scale?:number;period?:number;stop?:number;direction?:string;delay?:boolean;metrics:Metrics}
export type Trade = {entryDate:string;exitDate:string;contract:string;direction:number;lots:number;entryPrice:number;exitPrice:number;netPnl:number;exitReason:string;[key:string]:unknown}
export type CurvePoint = {date:string;equity:number}
export type RunDetail = Run & {curve:CurvePoint[];trades:Trade[];decisions:unknown[]}
export type Study = StudySummary & {revision:string;assets:{name:string;size:number;sha256:string}[];filters:Record<string,(string|number)[]>;report:string;reportLinks:Record<string,string>;comparisons:Run[];results:Record<string,any>;journal:{family:string;name:string;hypothesis:string;failureReasons:string[];lesson:string;base:Metrics;repairs:unknown}[];observation:boolean}
export type Observation = {automaticUpdates:boolean;tradingEnabled:boolean;message:string;state:{asOf:string;revision:number;cash:number;equity:number;configHash:string;qualification:string;status:string;ordersSubmittedToBroker:number;position:Record<string,unknown>|null;trades:Trade[];curve:CurvePoint[];events:unknown[];nextSignal:{signal:string;reason:string;nodeTrace:unknown[];signalDate:string;maxPlannedEntryLots:number};config:Record<string,unknown>}}
const base='/api/v1/research/studies'
export const researchLibrary={
  catalog:()=>request<ResearchCatalog>(base),
  detail:(id:string,revision:string)=>request<Study>(`${base}/${encodeURIComponent(id)}?revision=${revision}`),
  runs:(id:string,revision:string,params:Record<string,string|number>)=>request<{total:number;items:Run[]}>(`${base}/${id}/runs?${new URLSearchParams({revision,...Object.fromEntries(Object.entries(params).map(([k,v])=>[k,String(v)]))})}`),
  run:(id:string,revision:string,run:number)=>request<RunDetail>(`${base}/${id}/runs/${run}?revision=${revision}`),
  observation:()=>request<Observation>(`${base}/fu-regime/observation`),
  asset:(id:string,revision:string,name:string,download=true)=>`${base}/${id}/assets/${encodeURIComponent(name)}?revision=${revision}&download=${download}`,
}
