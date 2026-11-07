import {mount} from '@vue/test-utils'
import {describe,it,expect} from 'vitest'
import DecisionResearchSources from './DecisionResearchSources.vue'
import type {ResearchSource} from '../services/decisions'
const plan={planId:'fixture',symbol:'CJM',contract:'CJ701',mode:'CULTURAL_COMPARE',modelVersion:'original',action:'WAIT',actionMessage:'继续等待',dataTimestamp:'2026-11-06T07:00:00Z',createdAt:'2026-11-07T00:00:00Z',newLots:0,reduceLots:0,modeEvidence:{score:42},gates:['证据不足']}
describe('decision research sources',()=>{
 it('preserves comparison mode and self reports without inventing execution or probability',()=>{
  const source={id:'source',kind:'LOCAL_IMPORT',sourceHash:'hash',createdAt:'2026-11-07T00:00:00Z',request:{},snapshot:{id:'entry',savedAt:'2026-11-06T00:00:00Z',plan,status:'EXECUTED',actualPnl:123,notes:'private original note'}} as ResearchSource
  const w=mount(DecisionResearchSources,{props:{sources:[source],caseId:'case-one'},global:{stubs:{RouterLink:{name:'RouterLink',props:['to'],template:'<a><slot/></a>'}}}})
  expect(w.text()).toContain('本机自报 · 未经服务端核验');expect(w.text()).toContain('文化参考对照');expect(w.text()).toContain('原动作：空仓等待');expect(w.text()).toContain('非胜率');expect(w.text()).toContain('不构成模拟账本');expect(w.get('button').text()).toBe('下载本次导入原文')
  expect(w.findComponent({name:'RouterLink'}).props('to')).toMatchObject({path:'/strategy/CJM',query:{case:'case-one'},hash:'#trade-plan'});w.unmount()
 })
})
