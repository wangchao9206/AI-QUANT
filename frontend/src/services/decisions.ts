import {request} from './api'
import type {MonitorEvent} from './monitoring'
export interface PlanFields {side:'LONG'|'SHORT';entry:number;stop:number;target:number;lots:number;equity:number;budget:number;hypothesis:string;invalidation:string;validUntil:string}
export interface DecisionPlan {id:string;version:number;fields:PlanFields;createdAt:string}
export interface DecisionCase {id:string;symbol:string;version:number;origin:MonitorEvent;createdAt:string;updatedAt:string;plans:DecisionPlan[];reviews:{id:string;planId:string;version:number;outcome:string;notes:string;createdAt:string}[];paper:{planId:string;version:number;sessionId:string;createdAt:string}[]}
export interface Readiness {planId:string;version:number;checkedAt:string;ready:boolean;qualifiedForProfit:false;reasons:string[];scenarioLoss?:number;marginRequired?:number;meaning:string;assumptions?:string}
const base='/api/v1/paper/decisions'
const post=<T>(path:string,body:unknown={})=>request<T>(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},30000)
export const decisionsApi={
 list:(page=1)=>request<{items:DecisionCase[];total:number;page:number;size:number}>(base+'?page='+page+'&size=20'),
 forSession:(id:string)=>request<{caseId?:string;planId?:string;version?:number}>(base+'/for-session/'+id),
 fromEvent:(eventId:number)=>post<DecisionCase>('/from-event',{eventId}),
 detail:(id:string)=>request<DecisionCase>(base+'/'+id),
 save:(id:string,expectedVersion:number,fields:PlanFields,commandId:string)=>post<DecisionCase>(`/${id}/plans`,{expectedVersion,fields,commandId}),
 check:(id:string,planId:string)=>post<Readiness>(`/${id}/plans/${planId}/check`),
 paper:(id:string,planId:string,commandId:string)=>post<{sessionId:string;created:boolean}>(`/${id}/plans/${planId}/paper`,{commandId}),
 review:(id:string,planId:string,outcome:string,notes:string,commandId:string)=>post<DecisionCase>(`/${id}/plans/${planId}/reviews`,{outcome,notes,commandId}),
}
