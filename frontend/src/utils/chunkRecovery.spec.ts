import {beforeEach,describe,expect,it,vi} from 'vitest'
import {createMemoryHistory,createRouter} from 'vue-router'
import {createChunkRecovery} from './chunkRecovery'

const missing=()=>new TypeError('error loading dynamically imported module: http://192.168.100.247:8088/assets/TodayView-old.js')
describe('deployment chunk recovery',()=>{
 let clock:number,online:boolean
 const replace=vi.fn(),values=new Map<string,string>()
 const storage={getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value)}}
 const recover=()=>createChunkRecovery({storage:()=>storage,replace,now:()=>clock,online:()=>online})
 beforeEach(()=>{clock=1700000000000;online=true;values.clear();replace.mockClear()})
 it('reloads the pending destination including its query and anchor',async()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/today',component:()=>Promise.reject(missing())}]})
  const handle=recover();router.onError((e,to)=>{handle(e,to.fullPath)})
  await expect(router.push('/today?review=pending#plans')).rejects.toThrow('dynamically imported')
  expect(replace).toHaveBeenCalledWith('/today?review=pending#plans')
 })
 it('survives a new application instance without entering a reload loop',()=>{
  expect(recover()(missing(),'/today')).toBe(true)
  expect(recover()(missing(),'/today')).toBe(false)
  expect(recover()(missing(),'/paper')).toBe(false)
  expect(replace).toHaveBeenCalledTimes(1)
  clock+=5*60*1000;expect(recover()(missing(),'/today')).toBe(true)
 })
 it.each(['Failed to fetch dynamically imported module: /assets/missing.js','Importing a module script failed.','Unable to preload CSS for /assets/missing.css'])(
  'recognizes module and preload failure: %s',message=>{expect(recover()(new Error(message),'/today')).toBe(true)})
 it('does not refresh on business errors, offline failures or external destinations',()=>{
  expect(recover()(new Error('Origin not allowed'),'/today')).toBe(false)
  expect(recover()(new TypeError('Cannot read properties of undefined'),'/today')).toBe(false)
  for(const path of ['//outside.invalid','/\\outside.invalid','https://outside.invalid','/today\n'])expect(recover()(missing(),path)).toBe(false)
  online=false;expect(recover()(missing(),'/today')).toBe(false);expect(replace).not.toHaveBeenCalled()
 })
 it('avoids unbounded retries when browser storage cannot save the guard',()=>{
  const handle=createChunkRecovery({storage:()=>{throw new Error('storage blocked')},replace,now:()=>clock,online:()=>true})
  expect(handle(missing(),'/today')).toBe(false);expect(replace).not.toHaveBeenCalled()
 })
})
