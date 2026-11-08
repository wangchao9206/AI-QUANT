import {computed,nextTick,onScopeDispose,ref,watch,type Ref} from 'vue'
import {authState} from '../services/auth'
import {workspaceApi,type WorkspaceDocument,type WorkspaceTarget} from '../services/workspace'
import {ApiError} from '../services/api'
import {requestUuid} from '../utils/requestId'
export interface PrivateSyncControls {
 revision:Ref<number>;loading:Ref<boolean>;saving:Ref<boolean>;ready:Ref<boolean>;conflict:Ref<boolean>;message:Ref<string>;backupAvailable:Ref<boolean>;dirty:Ref<boolean>;cloud:Ref<boolean>;localPreview:Ref<string>;remotePreview:Ref<string>
 refresh:()=>Promise<void>;save:()=>Promise<void>;useRemote:()=>void;overwriteRemote:()=>Promise<void>;restoreBackup:()=>void
}

const clone=<T>(value:T):T=>JSON.parse(JSON.stringify(value)) as T
function canonical(value:unknown):string {if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}';return JSON.stringify(value)}
export const privateDocumentCacheKey=(owner:string,tenant:string,key:string)=>`aiquant.private-workspace.v1.${owner}:${tenant}:${encodeURIComponent(key)}`

/** Explicit saves, optimistic revisions and identity-bound responses. Edits during loads/saves remain drafts. */
export function usePrivateDocument<T>(target:Ref<WorkspaceTarget|null>,defaults:()=>T,validate:(value:unknown)=>T,authorized:Ref<boolean>){
 const draft=ref<T>(clone(defaults())) as Ref<T>,base=ref<T>(clone(defaults())) as Ref<T>,revision=ref(0),remote=ref<WorkspaceDocument<T>|null>(null) as Ref<WorkspaceDocument<T>|null>
 const loading=ref(false),saving=ref(false),ready=ref(false),conflict=ref(false),message=ref(''),backupAvailable=ref(false)
 const cacheWriteBlocked=ref(false),statusMessage=computed(()=>message.value+(cacheWriteBlocked.value?' 本机原始草稿未能读取，已保留原文并暂停覆盖该缓存；新编辑请明确保存到账号。':''))
 const dirty=computed(()=>canonical(draft.value)!==canonical(base.value)),cloud=computed(()=>!!target.value?.path&&!!authState.user&&authorized.value)
 const localPreview=computed(()=>JSON.stringify(draft.value,null,2)),remotePreview=computed(()=>remote.value?JSON.stringify(remote.value.content,null,2):'尚未读取云端')
 let empty=clone(defaults()),generation=0,alive=true,loadingLocal=false,cacheKey='',boundScope='',attempt:{commandId:string;expectedRevision:number;content:T}|null=null
 const scope=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,authorized.value,target.value]))
 function persist(){if(loadingLocal||cacheWriteBlocked.value||!cacheKey||boundScope!==scope.value)return;try{localStorage.setItem(cacheKey,JSON.stringify({version:1,baseRevision:revision.value,base:base.value,draft:draft.value}))}catch{message.value='当前草稿仍在页面中，本机存储不可用；尚未保存的修改请及时保存到账号。'}}
 function backup(){if(!cacheKey)return;try{localStorage.setItem(cacheKey+'.backup',JSON.stringify({version:1,content:draft.value}));backupAvailable.value=true}catch{throw new Error('无法备份本机草稿，已停止替换；请先恢复浏览器存储。')}}
 function checked(value:WorkspaceDocument<T>,current:WorkspaceTarget,owner:string,tenant:string):WorkspaceDocument<T>{
  if(!value||value.ownerId!==owner||value.tenantId!==tenant||value.kind!==current.kind||value.key!==current.key||!Number.isSafeInteger(value.revision)||value.revision<0||value.revision>1_000_000_000||value.revision===0&&value.content!==null||value.revision>0&&value.content===null)throw new Error('私人记录的账号、工作空间或图表身份不匹配，已停止恢复。')
  return {...value,content:value.revision===0?clone(empty):validate(value.content)}
 }
 function adopt(value:WorkspaceDocument<T>){loadingLocal=true;draft.value=clone(value.content!);base.value=clone(value.content!);revision.value=value.revision;loadingLocal=false;conflict.value=false;ready.value=true;attempt=null;persist()}
 async function refresh(){
  const current=target.value,user=authState.user,ticket=generation;if(!current?.path||!user||!authorized.value)return
  const owner=user.id,tenant=user.tenantId;loading.value=true;message.value='正在读取本人记录…'
  try{
   // loadIdentity updates the storage scope just after assigning authState.user.
   await nextTick();if(!alive||ticket!==generation)return
   const value=checked(await workspaceApi.read<T>(current),current,owner,tenant);if(!alive||ticket!==generation)return
   remote.value=value
   if(value.revision<revision.value){conflict.value=true;ready.value=true;message.value='云端版本低于本机基线；草稿保留，请比较后选择。';return}
   if(dirty.value&&canonical(draft.value)!==canonical(value.content)&&canonical(base.value)!==canonical(value.content)){conflict.value=true;ready.value=true;message.value='云端与本机草稿不同；两份均保留，请比较后选择。';return}
   if(dirty.value&&canonical(draft.value)!==canonical(value.content)){loadingLocal=true;revision.value=value.revision;base.value=clone(value.content!);loadingLocal=false;conflict.value=false;ready.value=true;persist();message.value='已核对云端版本，本机未保存的修改仍保留。';return}
   adopt(value);message.value=value.revision?'已恢复本人记录 v'+value.revision:'尚无账号记录；修改后可明确保存。'
  }catch(e){if(alive&&ticket===generation)message.value=e instanceof Error?e.message:'私人记录读取失败；本机草稿保留。'}finally{if(alive&&ticket===generation)loading.value=false}
 }
 async function save(){
  const current=target.value,user=authState.user,ticket=generation;if(!current?.path||!user||!authorized.value||!ready.value||loading.value||saving.value||conflict.value)return
  let content:T;try{content=validate(clone(draft.value))}catch(e){message.value=e instanceof Error?e.message:'草稿格式无效。';return}
  if(!attempt||attempt.expectedRevision!==revision.value||canonical(attempt.content)!==canonical(content))attempt={commandId:requestUuid(),expectedRevision:revision.value,content}
  const command=clone(attempt),owner=user.id,tenant=user.tenantId;saving.value=true;message.value='正在保存到本人账号…'
  try{
   const value=checked(await workspaceApi.write(current,command),current,owner,tenant);if(!alive||ticket!==generation)return
   if(canonical(value.content)!==canonical(command.content)||value.revision!==command.expectedRevision+1)throw new Error('保存响应与本次草稿或版本不一致，请读取云端核对；本机草稿保留。')
   loadingLocal=true;base.value=clone(value.content!);revision.value=value.revision;remote.value=value;loadingLocal=false;attempt=null;conflict.value=false;persist()
   message.value='已保存到本人账号 v'+value.revision+(dirty.value?'；保存期间的新编辑仍在本机草稿。':'')
  }catch(e){if(alive&&ticket===generation){message.value=e instanceof Error?e.message:'保存响应不确定；重试沿用原请求编号。';if(e instanceof ApiError&&e.status===409){await refresh();if(ticket===generation){conflict.value=true;message.value='云端版本已变化；本机草稿保留，请比较后选择。'}}}}finally{if(alive&&ticket===generation)saving.value=false}
 }
 function useRemote(){if(!remote.value||loading.value||saving.value)return;try{backup();adopt(remote.value);message.value='已采用云端版本，替换前的本机草稿已备份。'}catch(e){message.value=(e as Error).message}}
 async function overwriteRemote(){if(!remote.value||loading.value||saving.value)return;loadingLocal=true;base.value=clone(remote.value.content!);revision.value=remote.value.revision;loadingLocal=false;conflict.value=false;attempt=null;await save()}
 function replaceDraft(content:T){if(boundScope===scope.value)draft.value=validate(clone(content))}
 function restoreBackup(){if(!cacheKey)return;try{const saved=JSON.parse(localStorage.getItem(cacheKey+'.backup')??'null');if(saved?.version!==1)throw new Error('本机备份不可读取。');const value=validate(saved.content);backup();replaceDraft(value);message.value='已恢复本机备份，尚未保存到账号。'}catch(e){message.value=(e as Error).message}}
 function replaceWithBackup(content:T){try{const value=validate(content);backup();replaceDraft(value);message.value='已放入本机草稿，原草稿已备份；尚未保存到账号。'}catch(e){message.value=(e as Error).message}}
 watch(draft,()=>persist(),{deep:true,flush:'sync'})
 watch(scope,()=>{
  boundScope=scope.value
  ++generation;loadingLocal=true;empty=clone(defaults());draft.value=clone(empty);base.value=clone(empty);revision.value=0;remote.value=null;loading.value=false;saving.value=false;ready.value=false;conflict.value=false;message.value='';attempt=null;backupAvailable.value=false;cacheKey='';cacheWriteBlocked.value=false
  const user=authState.user,current=target.value
  if(user&&current&&authorized.value){cacheKey=privateDocumentCacheKey(user.id,user.tenantId,current.localKey);try{
    const raw=localStorage.getItem(cacheKey),cached=raw===null?null:JSON.parse(raw);if(raw!==null){if(cached?.version!==1||!Number.isSafeInteger(cached.baseRevision)||cached.baseRevision<0||cached.baseRevision>1_000_000_000)throw new Error('Invalid cache');const cachedDraft=validate(cached.draft),cachedBase=validate(cached.base);draft.value=cachedDraft;base.value=cachedBase;revision.value=cached.baseRevision}
    backupAvailable.value=!!localStorage.getItem(cacheKey+'.backup')
   }catch{cacheWriteBlocked.value=true}
  }
  loadingLocal=false
  if(user&&current?.path&&authorized.value)void refresh();else message.value=current&&!current.path?'此图仅保留本人本机草稿；跨设备请选实际交割月。':'未登录时画线仅保留在当前页面。'
 },{immediate:true,flush:'sync'})
 onScopeDispose(()=>{alive=false;++generation})
 return {draft,revision,remote,loading,saving,ready,conflict,message:statusMessage,backupAvailable,dirty,cloud,localPreview,remotePreview,refresh,save,useRemote,overwriteRemote,replaceDraft,replaceWithBackup,restoreBackup}
}
