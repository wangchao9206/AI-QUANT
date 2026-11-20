import type {Router} from 'vue-router'

const KEY='aiquant:chunk-reload-at'
const COOLDOWN=5*60*1000
interface RecoveryPort {
 storage:()=>Pick<Storage,'getItem'|'setItem'>
 replace:(target:string)=>void
 now:()=>number
 online:()=>boolean
}

/** A broken release must never trap a browser in a reload loop. */
export function createChunkRecovery(port:RecoveryPort){
 return (error:unknown,target:string)=>{
  const message=error instanceof Error?error.message:String(error)
  if(!/Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(message)
   ||!/^\/(?!\/)/.test(target)||/[\\\r\n]/.test(target)||!port.online())return false
  try{
   const storage=port.storage(),previous=storage.getItem(KEY),now=port.now()
   if(previous!==null&&Number.isFinite(Number(previous))&&now-Number(previous)<COOLDOWN)return false
   storage.setItem(KEY,String(now))
  }catch{return false}
  port.replace(target)
  return true
 }
}

export function installChunkRecovery(router:Router){
 const recover=createChunkRecovery({storage:()=>window.sessionStorage,replace:target=>{
  const next=new URL(target,window.location.href)
  // Replacing an identical URL containing a hash may only scroll the document.
  if(next.pathname===window.location.pathname&&next.search===window.location.search){
   if(next.hash!==window.location.hash)window.history.replaceState(window.history.state,'',target)
   window.location.reload()
  }else window.location.replace(target)
 },now:Date.now,online:()=>navigator.onLine})
 return router.onError((error,to)=>{recover(error,to.fullPath)})
}
