import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import ResearchWorkbench from './ResearchWorkbench.vue'
import {api} from '../services/api'
import type {ResearchContext,ResearchPlan} from '../types/research'
vi.mock('../services/api',()=>({api:{researchContext:vi.fn(),researchPlan:vi.fn()}}))
const context:ResearchContext={symbol:'CJM',modelVersion:'test',signalTimestamp:'2026-10-16T15:00:00+08:00',traceId:'test',
  execution:{contract:'CJ701',quote:{symbol:'CJ701',price:6400,dataTimestamp:'2026-10-16T15:00:00+08:00',volumeMultiple:5,priceTick:5,marginPerLot:3000,commissionPerLot:3,upperLimit:6800,lowerLimit:5900,expiryTimestamp:null},marketState:'CLOSED_CACHE',phase:'CLOSED',checkedAt:'2026-10-17T12:00:00+08:00'},
  atr:100,atrBasis:'主连日线',events:[],dimensionNote:'共享输入不等于独立证据',modes:{
    EMPIRICAL:{score:10,signal:'HOLD',resonance:.6,empiricalCoverage:.8,availableDimensions:8,totalDimensions:11,culturalEffectiveWeight:0,missing:['天气'],confidenceMeaning:'非胜率',calibratedWinRate:null},
    CULTURAL_COMPARE:{score:15,signal:'HOLD',resonance:.6,empiricalCoverage:.8,availableDimensions:8,totalDimensions:11,culturalEffectiveWeight:.12,missing:['天气'],confidenceMeaning:'非胜率',calibratedWinRate:null}}}
const plan={planId:'plan-1',createdAt:'2026-10-17T12:00:00+08:00',symbol:'CJM',contract:'CJ701',mode:'EMPIRICAL',modeEvidence:context.modes.EMPIRICAL,
  modelVersion:'test',dataTimestamp:context.execution.quote!.dataTimestamp,marketState:'CLOSED_CACHE',action:'WAIT',actionMessage:'空仓等待，不新增仓位',gates:[],entryPrice:6400,stopPrice:null,targetPrice:null,scenarioDirection:'NONE',maxLots:0,newLots:0,reduceLots:0,limits:{risk:0,margin:0,leverage:0},riskPerLot:null,frictionPerLot:10,riskBudget:10000,plannedLoss:0,existingPositionRisk:0,marginRequired:0,marginPct:0,notionalLeverage:0,lossPct:0,holdingHorizon:'日线',validity:'参数变化后重算',trigger:'等待方向',invalidation:'行情异常暂停',assumptions:[],inputs:{symbol:'CJM',mode:'EMPIRICAL',equity:1_000_000,riskPct:1,marginBudgetPct:30,maxLeverage:2,dailyLossLimitPct:2,dailyLoss:0,totalRiskLimitPct:3,otherRisk:0,otherMargin:0,otherNotional:0,positionSide:'FLAT',existingLots:0,feeRate:.0001,slippageTicks:1,marginRate:.12}} as ResearchPlan
let wrapper:VueWrapper|undefined
beforeEach(()=>{localStorage.clear();vi.clearAllMocks();vi.mocked(api.researchContext).mockResolvedValue(structuredClone(context));vi.mocked(api.researchPlan).mockResolvedValue(structuredClone(plan))})
afterEach(()=>wrapper?.unmount())
describe('ResearchWorkbench',()=>{
  it('accepts default and fractional account inputs under native HTML constraints',async()=>{
    wrapper=mount(ResearchWorkbench,{props:{symbol:'CJM'}});await flushPromises()
    expect((wrapper.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
    await wrapper.get('input[name="equity"]').setValue('123456.78')
    await wrapper.get('input[name="riskPct"]').setValue('0.35')
    await wrapper.get('input[name="dailyLoss"]').setValue('123.45')
    expect((wrapper.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
    await wrapper.get('input[name="riskPct"]').setValue('0')
    expect((wrapper.get('form').element as HTMLFormElement).checkValidity()).toBe(false)
  })
  it('defaults to empirical research, keeps HOLD flat, saves frozen plans and reopens them for review',async()=>{
    wrapper=mount(ResearchWorkbench,{props:{symbol:'CJM'}});await flushPromises()
    expect(wrapper.text()).toContain('休市缓存')
    expect(wrapper.find('.mode-switch').exists()).toBe(false)
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(api.researchPlan).toHaveBeenCalledWith(expect.objectContaining({mode:'EMPIRICAL',positionSide:'FLAT',existingLots:0,expectedContract:'CJ701'}))
    expect(wrapper.text()).toContain('空仓等待')
    await wrapper.get('.save-plan').trigger('click')
    expect(JSON.parse(localStorage.getItem('aiquant.plan-journal.v1')!)).toHaveLength(1)
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    await wrapper.get('textarea').setValue('记录执行偏差')
    await wrapper.get('.journal-entry .quiet-button').trigger('click')
    await wrapper.findAll('[role="tab"]')[0]!.trigger('click')
    await wrapper.get('.save-plan').trigger('click')
    expect(JSON.parse(localStorage.getItem('aiquant.plan-journal.v1')!)[0].notes).toBe('记录执行偏差')
    await wrapper.get('input[name="equity"]').setValue('900000')
    expect(wrapper.get('.save-plan').attributes('disabled')).toBeDefined()
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    expect(wrapper.find('.journal-entry').exists()).toBe(true)
    expect(JSON.parse(localStorage.getItem('aiquant.plan-journal.v1')!)[0].plan.inputs.equity).toBe(1_000_000)
  })
  it('does not apply a late calculation after switching instruments',async()=>{
    let resolve:(value:ResearchPlan)=>void=()=>{}
    vi.mocked(api.researchPlan).mockImplementationOnce(()=>new Promise(r=>resolve=r))
    wrapper=mount(ResearchWorkbench,{props:{symbol:'CJM'}});await flushPromises()
    await wrapper.get('form').trigger('submit');await wrapper.setProps({symbol:'RBM'});await flushPromises()
    resolve(structuredClone(plan));await flushPromises()
    expect(wrapper.find('.save-plan').exists()).toBe(false)
  })
  it('keeps the previous plan explicitly stale when risk inputs change during a request',async()=>{
    let resolve:(value:ResearchPlan)=>void=()=>{}
    vi.mocked(api.researchPlan).mockImplementationOnce(()=>new Promise(r=>resolve=r))
    wrapper=mount(ResearchWorkbench,{props:{symbol:'CJM'}});await flushPromises()
    await wrapper.get('form').trigger('submit');await wrapper.get('input[name="riskPct"]').setValue('0.5')
    resolve(structuredClone(plan));await flushPromises()
    expect(wrapper.find('.save-plan').exists()).toBe(false)
  })
})
