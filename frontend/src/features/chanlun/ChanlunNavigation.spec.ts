import {mount} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {describe,it,expect} from 'vitest'
import ChanlunNavigation from './ChanlunNavigation.vue'
describe('typed chanlun navigation',()=>{
 it('passes a historical run only to views that can read that run',async()=>{
  const router=createRouter({history:createMemoryHistory(),routes:['workbench','radar','multiframe','compare','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:'/chanlun/'+tab,component:{template:'<div/>'}}))});await router.push('/chanlun/workbench?run=archived&structure=old')
  const w=mount(ChanlunNavigation,{props:{active:'workbench',context:{run:'archived',structure:'old'}},global:{plugins:[router]}})
  const link=(name:string)=>w.findAll('a').find(a=>a.text()===name)!.attributes('href')
  expect(link('引擎对照')).toBe('/chanlun/compare?run=archived');expect(link('原典课堂')).toContain('structure=old');expect(link('多周期观察')).toBe('/chanlun/multiframe');expect(link('逐根训练')).toBe('/chanlun/replay');w.unmount()
 })
})
