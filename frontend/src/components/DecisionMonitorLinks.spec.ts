import {mount,flushPromises} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {describe,it,expect,vi} from 'vitest'
import DecisionMonitorLinks from './DecisionMonitorLinks.vue'
const mocks=vi.hoisted(()=>({jobs:vi.fn(),get:vi.fn(),bindMonitor:vi.fn()}))
vi.mock('../services/monitoring',()=>({monitoringApi:mocks}))
vi.mock('../services/decisions',()=>({decisionsApi:mocks}))
describe('private plan rule links',()=>{
 it('only offers same-contract tasks and sends explicit plan/version identity',async()=>{mocks.jobs.mockResolvedValue({items:[{id:'m1',name:'task',symbol:'JM2701',version:3,enabled:false},{id:'m2',symbol:'JM2705'}],total:2});mocks.bindMonitor.mockResolvedValue({});const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div/>'}}]});await router.push('/');const w=mount(DecisionMonitorLinks,{props:{caseId:'c1',planId:'p1',symbol:'JM2701',links:[],editable:true},global:{plugins:[router]}});await w.findAll('button')[0]!.trigger('click');await flushPromises();expect(w.findAll('article')).toHaveLength(1);await w.findAll('button').find(b=>b.text()==='关联到本计划版本')!.trigger('click');await flushPromises();expect(mocks.bindMonitor).toHaveBeenCalledWith('c1','p1','m1');expect(w.emitted('saved')).toHaveLength(1);w.unmount()})
 it('retains old snapshot and warns when a shared task changes',async()=>{mocks.get.mockResolvedValue({symbol:'JM2701',version:4});const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div/>'}},{path:'/live',component:{template:'<div/>'}}]});await router.push('/');const w=mount(DecisionMonitorLinks,{props:{caseId:'c1',planId:'p1',symbol:'JM2701',editable:false,links:[{planId:'p1',monitorId:'m1',createdAt:'2026-11-07T00:00:00Z',snapshot:{id:'m1',name:'original',symbol:'JM2701',version:3,seconds:900,enabled:false,parameters:{}}}]},global:{plugins:[router]}});await w.find('button').trigger('click');await flushPromises();expect(w.text()).toContain('任务已修改或启停');expect(w.text()).toContain('规则 v3');expect(w.find('a').attributes('href')).toContain('plan=p1');w.unmount()})
})
