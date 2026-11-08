import {request} from './api'
export interface WorkspaceTarget {kind:'PREFERENCES'|'CHART';key:string;path?:string;localKey:string}
export interface WorkspaceDocument<T> {ownerId:string;tenantId:string;kind:WorkspaceTarget['kind'];key:string;revision:number;content:T|null;updatedAt?:string}
export const workspaceApi={
 read:<T>(target:WorkspaceTarget)=>request<WorkspaceDocument<T>>(target.path!),
 write:<T>(target:WorkspaceTarget,body:{commandId:string;expectedRevision:number;content:T})=>request<WorkspaceDocument<T>>(target.path!,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
}
export const preferencesTarget:WorkspaceTarget={kind:'PREFERENCES',key:'WORKSPACE',localKey:'PREFERENCES',path:'/api/v1/auth/workspace/preferences'}
export function chartWorkspaceTarget(key:string):WorkspaceTarget {
 const match=/^([A-Z]{1,4}\d{3,4})-(15|30|60|180|300|900|DAY|WEEK|MONTH)$/.exec(key)
 return match?{kind:'CHART',key:`LIVE_FUTURES_UNADJUSTED:${match[1]}:${match[2]}`,localKey:`CHART:${key}`,path:`/api/v1/auth/workspace/charts/${match[1]}/${match[2]}`}:{kind:'CHART',key:'LOCAL:'+key,localKey:'LOCAL:'+key}
}
