import {reactive} from 'vue'
import type {Router} from 'vue-router'
import {request,ApiError} from './api'
import {setStorageScope} from '../utils/storageScope'

export type TenantRole='OWNER'|'ADMIN'|'MEMBER'|'VIEWER'
export interface Identity {id:string;username:string;email:string|null;platformAdmin:boolean;mustChangePassword:boolean;tenantId:string;role:TenantRole;tenants:{id:string;name:string;role:TenantRole}[];permissions?:string[];menus?:{id:string;parentId:string|null;label:string;path:string|null;permission:string;sortOrder:number}[]}
export const authState=reactive<{user:Identity|null;loaded:boolean}>({user:null,loaded:false})
const base='/api/v1/auth'
export async function authCall<T=Record<string,unknown>>(path:string,body?:unknown):Promise<T>{return request<T>(base+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},20000)}
export async function loadIdentity(){
  try{authState.user=await authCall<Identity>('/me');setStorageScope(`${authState.user.id}:${authState.user.tenantId}`)}
  catch(e){if(e instanceof ApiError&&e.status===401){forgetIdentity()}else throw e}
  finally{authState.loaded=true}
  return authState.user
}
export function forgetIdentity(){authState.user=null;authState.loaded=true;setStorageScope(null)}
export function safeNext(value:unknown){return typeof value==='string'&&/^\/(?!\/)/.test(value)&&!value.startsWith('/auth/')?value:'/today'}
export function installAuthGuard(router:Router){router.beforeEach(async to=>{
  if(to.meta.public)return true
  try{if(!authState.loaded||authState.user)await loadIdentity()}catch{return {path:'/auth/login',query:{error:'账号服务暂不可用，请稍后重试。'}}}
  if(!authState.user)return {path:'/auth/login',query:{next:to.fullPath}}
  if(authState.user.mustChangePassword&&to.path!=='/auth/change-password')return '/auth/change-password'
  if(to.path==='/access-denied'||to.path.startsWith('/auth/')||to.path==='/account')return true
  if(to.path.startsWith('/admin'))return canManage()?true:'/access-denied'
  const resource=routeResource(to.path)
  if(resource&&!hasPermission(resource+'.read'))return '/access-denied'
  return true
})}
export function canManage(){return Boolean(authState.user&&(authState.user.platformAdmin||['OWNER','ADMIN'].includes(authState.user.role)))}
export function hasPermission(code:string){return authState.user?.permissions===undefined||authState.user.permissions.includes(code)}
export function routeResource(path:string){if(/^\/strategy\/[^/]+/.test(path)&&!path.startsWith('/strategy/workflows'))return 'research';const modules:Record<string,string>={live:'market',overview:'overview',news:'news',leads:'leads',market:'market',options:'options',chanlun:'chanlun',strategy:'workflows',research:'research',learn:'learn',mentors:'mentors',personal:'personal',books:'books',backtest:'backtest',paper:'paper',system:'system'};return modules[path.split('/')[1]??'']}
