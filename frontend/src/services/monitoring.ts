import {request} from './api'
export type MonitorAsset='FUTURE'|'OPTION'
export interface MonitorParameters {rules:string[];maPeriods:number[];lookback:number;volumeMultiple:number;jumpPct:number;bigLots:number;bollStd:number;atrMultiple:number;cooldownSeconds:number;pivotBars:number}
export interface MonitorCatalog {algorithmVersion:string;rules:{code:string;label:string}[];defaults:MonitorParameters;frequencies:number[];maxEnabledPerTenant:number;maxEnabledGlobal:number}
export interface MonitorJob {id:string;name:string;symbol:string;assetType:MonitorAsset;enabled:boolean;version:number;seconds:number;parameters:MonitorParameters;metadata:Record<string,unknown>;status:string;message:string;checkedAt:string|null;sourceTimestamp:string|null;createdBy:string;metrics:Record<string,unknown>}
export interface MonitorEvent {id:number;monitorId:string;rule:string;label:string;symbol:string;assetType:MonitorAsset;observedAt:string;createdAt:string;acknowledgedAt:string|null;evidence:Record<string,unknown>;algorithmVersion:string}
export interface MonitorPage<T>{items:T[];total:number;page:number;size:number}
export function monitorJson<T>(value:unknown):T{if(value&&typeof value==='object'&&'value' in value)return JSON.parse(String(value.value)) as T;return typeof value==='string'?JSON.parse(value) as T:value as T}
const base=(kind:MonitorAsset)=>kind==='OPTION'?'/api/v1/options/monitors':'/api/v1/market/monitors'
const query=(values:Record<string,string|number|boolean|undefined>)=>new URLSearchParams(Object.entries(values).filter(([,v])=>v!==undefined&&v!=='').map(([k,v])=>[k,String(v)])).toString()
const post=<T>(path:string,body:unknown)=>request<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},20000)
const normalize=(row:MonitorJob)=>({...row,parameters:monitorJson<MonitorParameters>(row.parameters),metadata:monitorJson<Record<string,unknown>>(row.metadata),metrics:monitorJson<Record<string,unknown>>(row.metrics)})
export const monitoringApi={
 catalog:(kind:MonitorAsset)=>request<MonitorCatalog>(base(kind)+'/catalog'),
 jobs:async(kind:MonitorAsset,q='',page=1)=>{const result=await request<MonitorPage<MonitorJob>>(base(kind)+'?'+query({q,page,size:20}));return {...result,items:result.items.map(normalize)}},
 save:async(kind:MonitorAsset,body:{name:string;symbol:string;seconds:number;enabled:boolean;version:number;parameters:MonitorParameters},id?:string)=>normalize(await post<MonitorJob>(base(kind)+(id?'/'+id:''),body)),
 enabled:(kind:MonitorAsset,job:MonitorJob,enabled:boolean)=>post<MonitorJob>(base(kind)+'/'+job.id+'/enabled',{enabled,version:job.version}),
 archive:(kind:MonitorAsset,job:MonitorJob)=>post(base(kind)+'/'+job.id+'/archive',{version:job.version}),
 events:async(kind:MonitorAsset,q='',page=1,monitorId='',unacknowledged=false)=>{const result=await request<MonitorPage<MonitorEvent>>(base(kind)+'/events?'+query({q,page,size:20,monitorId,unacknowledged}));return {...result,items:result.items.map(e=>({...e,evidence:monitorJson<Record<string,unknown>>(e.evidence)}))}},
 acknowledge:(kind:MonitorAsset,id:number)=>post(base(kind)+'/events/'+id+'/ack',{}),
}
