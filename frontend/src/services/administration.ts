import {authCall} from './auth'
export type AdminRow=Record<string,any>
export interface AdminPage {items:AdminRow[];total:number;page:number;size:number}
export interface AdminCatalog {platformAdmin:boolean;permissions:{module:string;label:string;read:string;write:string}[];routes:string[]}
export const administration={
  get:<T>(path:string,params:Record<string,string|number|undefined>={})=>authCall<T>('/manage'+path+query(params)),
  post:<T=AdminRow>(path:string,body:unknown,tenantId?:string)=>authCall<T>('/manage'+path+query({tenantId}),body),
}
export function query(params:Record<string,string|number|undefined>){const values=Object.entries(params).filter(([,v])=>v!==undefined&&v!=='').map(([k,v])=>[k,String(v)]);return values.length?'?'+new URLSearchParams(values).toString():''}
export function jsonValue<T=unknown>(value:unknown):T {try{if(value&&typeof value==='object'&&'value' in value)return JSON.parse(String(value.value)) as T;return typeof value==='string'?JSON.parse(value) as T:value as T}catch{return value as T}}
export function exportAdminPage(rows:AdminRow[],name:string){if(!rows.length)return;const columns=Object.keys(rows[0]!).filter(k=>!['beforeState','afterState'].includes(k));const cell=(v:unknown)=>{let value=v==null?'':typeof v==='object'?JSON.stringify(v):String(v);if(/^[=+@\-\t\r]/.test(value))value="'"+value;return '"'+value.replaceAll('"','""')+'"'};const text='\uFEFF'+[columns.map(cell).join(','),...rows.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=name+'.csv';link.click();URL.revokeObjectURL(url)}
