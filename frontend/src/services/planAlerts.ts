import {request} from './api'
export type EntryMode='BREAKOUT'|'PULLBACK'
export interface PlanAlertEvent {id:string;caseId:string;planId:string;version:number;symbol:string;kind:'ENTRY'|'STOP'|'TARGET'|'EXPIRED';observedAt:string;createdAt:string;acknowledgedAt:string|null;evidence:Record<string,unknown>}
export interface PlanAlertSubscription {revision:number;enabled:boolean;entryMode:EntryMode;status:string;message:string;checkedAt:string|null}
export interface PlanAlertState {subscription:PlanAlertSubscription|null;events:PlanAlertEvent[]}
export interface PlanAlertPage {items:PlanAlertEvent[];total:number;page:number;size:number}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
const date=(v:unknown)=>typeof v==='string'&&Number.isFinite(Date.parse(v))
const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0
const events=(v:unknown):v is PlanAlertEvent[]=>Array.isArray(v)&&v.every(e=>object(e)&&['id','caseId','planId','symbol'].every(k=>typeof e[k]==='string'&&!!e[k])&&count(e.version)&&['ENTRY','STOP','TARGET','EXPIRED'].includes(String(e.kind))&&date(e.observedAt)&&date(e.createdAt)&&(e.acknowledgedAt===null||date(e.acknowledgedAt))&&object(e.evidence))
function state(v:unknown):PlanAlertState{if(!object(v)||!events(v.events)||v.subscription!==null&&(!object(v.subscription)||!count(v.subscription.revision)||typeof v.subscription.enabled!=='boolean'||!['BREAKOUT','PULLBACK'].includes(String(v.subscription.entryMode))||typeof v.subscription.status!=='string'||typeof v.subscription.message!=='string'||v.subscription.checkedAt!==null&&!date(v.subscription.checkedAt)))throw new Error('计划提醒响应结构异常，请刷新重试。');return v as unknown as PlanAlertState}
const base='/api/v1/paper/decisions',path=(c:string,p:string)=>`${base}/${c}/plans/${p}/alerts`
export const planAlertsApi={
 read:async(c:string,p:string)=>state(await request<unknown>(path(c,p))),
 edit:async(c:string,p:string,enabled:boolean,entryMode:EntryMode,revision:number)=>state(await request<unknown>(path(c,p),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,entryMode,revision})})),
 events:async(unread=true,page=1):Promise<PlanAlertPage>=>{const v=await request<unknown>(`${base}/alerts/events?unread=${unread}&page=${page}`);if(!object(v)||!events(v.items)||!count(v.total)||v.page!==page||v.size!==20)throw new Error('提醒列表响应结构异常，请刷新重试。');return v as unknown as PlanAlertPage},
 ack:(id:string)=>request(`${base}/alerts/events/${id}/ack`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}),
}
