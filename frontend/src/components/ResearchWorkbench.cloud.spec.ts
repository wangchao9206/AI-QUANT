import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import ResearchWorkbench from './ResearchWorkbench.vue'
import {authState,type Identity} from '../services/auth'
import {setStorageScope} from '../utils/storageScope'
import {writeJournal,JOURNAL_KEY,journalEntry} from '../utils/planJournal'
import type {ResearchContext,ResearchPlan} from '../types/research'
const mocks=vi.hoisted(()=>({researchContext:vi.fn(),researchPlan:vi.fn(),calculateResearch:vi.fn(),archiveResearch:vi.fn(),previewImport:vi.fn()}))
vi.mock('../services/api',()=>({api:mocks,request:vi.fn(),ApiError:class extends Error{status=500}}))
vi.mock('../services/decisions',()=>({decisionsApi:mocks}))
const user:Identity={id:'10000000-0000-4000-8000-000000000001',tenantId:'20000000-0000-4000-8000-000000000001',username:'isolated-qa',email:null,platformAdmin:false,mustChangePassword:false,role:'OWNER',tenants:[],permissions:['paper.read','paper.write','market.read','research.read','research.write']}
const scope=user.id+':'+user.tenantId
const evidence={score:10,signal:'HOLD',resonance:.6,empiricalCoverage:.8,availableDimensions:8,totalDimensions:11,culturalEffectiveWeight:0,missing:[],confidenceMeaning:'非胜率',calibratedWinRate:null}
const context:ResearchContext={symbol:'CJM',modelVersion:'isolated-model',signalTimestamp:'2026-11-06T07:00:00Z',traceId:'fixture',execution:{contract:'CJ701',quote:{symbol:'CJ701',price:6400,dataTimestamp:'2026-11-06T07:00:00Z',volumeMultiple:5,priceTick:5,marginPerLot:3000,commissionPerLot:3,upperLimit:null,lowerLimit:null,expiryTimestamp:null},marketState:'CLOSED_CACHE',phase:'CLOSED',checkedAt:'2026-11-07T00:00:00Z'},atr:100,atrBasis:'日线',modes:{EMPIRICAL:evidence,CULTURAL_COMPARE:evidence},events:[],dimensionNote:'非独立证据'}
const plan={planId:'30000000-0000-4000-8000-000000000001',createdAt:'2026-11-07T00:00:00Z',symbol:'CJM',contract:'CJ701',mode:'EMPIRICAL',modeEvidence:evidence,modelVersion:'isolated-model',dataTimestamp:context.execution.quote!.dataTimestamp,marketState:'CLOSED_CACHE',action:'WAIT',actionMessage:'空仓等待',gates:[],entryPrice:6400,stopPrice:null,targetPrice:null,scenarioDirection:'NONE',maxLots:0,newLots:0,reduceLots:0,riskBudget:10000,plannedLoss:0,existingPositionRisk:0,marginRequired:0,marginPct:0,notionalLeverage:0,lossPct:0,frictionPerLot:10,riskPerLot:null,limits:{risk:0,margin:0,leverage:0},trigger:'等待方向',invalidation:'条件变化后重算',validity:'条件变化后重算',holdingHorizon:'日线',assumptions:[],inputs:{symbol:'CJM',mode:'EMPIRICAL',equity:1000000,riskPct:1,marginBudgetPct:30,maxLeverage:2,dailyLossLimitPct:2,dailyLoss:0,totalRiskLimitPct:3,otherRisk:0,otherMargin:0,otherNotional:0,positionSide:'FLAT',existingLots:0,feeRate:.0001,slippageTicks:1,marginRate:.12}} as ResearchPlan
let wrapper:VueWrapper|undefined
beforeEach(()=>{
 localStorage.clear();sessionStorage.clear();vi.clearAllMocks();authState.user=structuredClone(user);setStorageScope(scope)
 mocks.researchContext.mockResolvedValue(structuredClone(context));mocks.researchPlan.mockResolvedValue(structuredClone(plan));mocks.calculateResearch.mockResolvedValue({sourceId:'source-one',sourceHash:'a'.repeat(64),plan:structuredClone(plan)});mocks.archiveResearch.mockResolvedValue({id:'saved-case'})
 mocks.previewImport.mockImplementation(async raw=>({id:'import-one',kind:'LOCAL_IMPORT',sourceHash:'b'.repeat(64),snapshot:JSON.parse(raw),request:{},createdAt:'2026-11-07T00:00:00Z',archivedCaseId:null}))
})
afterEach(()=>{wrapper?.unmount();authState.user=null;setStorageScope(null)})
async function render(props:Record<string,unknown>={}){wrapper=mount(ResearchWorkbench,{props:{symbol:'CJM',...props},global:{stubs:{RouterLink:{props:['to'],template:'<a :href="to"><slot/></a>'}}}});await flushPromises();return wrapper}
function button(text:string){return wrapper!.findAll('button').find(b=>b.text()===text)!}
describe('research decision bridge',()=>{
 it('archives the authoritative receipt and preserves WAIT without a local recalculation',async()=>{
  await render();await wrapper!.get('form').trigger('submit');await flushPromises();expect(mocks.calculateResearch).toHaveBeenCalledWith(expect.objectContaining({symbol:'CJM',mode:'EMPIRICAL'}),expect.any(String));expect(mocks.researchPlan).not.toHaveBeenCalled()
  await button('保存到服务端决策档案').trigger('click');await flushPromises();expect(mocks.archiveResearch).toHaveBeenCalledWith('source-one',false,undefined);expect(wrapper!.text()).toContain('未改写为入场指令');expect(wrapper!.get('.cloud-save a').attributes('href')).toBe('/paper/decisions/saved-case');expect(plan.action).toBe('WAIT')
 })
 it('appends a fresh calculation to the explicitly selected case',async()=>{
  await render({decisionCaseId:'existing-case'});await wrapper!.get('form').trigger('submit');await flushPromises();await button('归档到原决策档案').trigger('click');await flushPromises();expect(mocks.archiveResearch).toHaveBeenCalledWith('source-one',false,'existing-case')
 })
 it('previews and confirms local imports, detects edits, and preserves the original local bytes',async()=>{
  const entry=journalEntry(plan);entry.notes='original private note';writeJournal([entry]);const before=localStorage.getItem(JOURNAL_KEY+':'+scope)
  await render({initialTab:'JOURNAL'});await button('预览导入服务端').trigger('click');await flushPromises();expect(mocks.previewImport).toHaveBeenCalledWith(expect.any(String),scope,scope,false,expect.any(String));expect(mocks.archiveResearch).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('未经服务端核验')
  await wrapper!.get('.import-preview input[type="checkbox"]').setValue(true);await wrapper!.get('.journal-entry textarea').setValue('edited after preview');await button('确认归属并导入').trigger('click');await flushPromises();expect(mocks.archiveResearch).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('内容已变化')
  await button('预览导入服务端').trigger('click');await flushPromises();await wrapper!.get('.import-preview input[type="checkbox"]').setValue(true);await button('确认归属并导入').trigger('click');await flushPromises();expect(mocks.archiveResearch).toHaveBeenCalledWith('import-one',true);expect(localStorage.getItem(JOURNAL_KEY+':'+scope)).toBe(before)
 })
 it('does not silently claim unscoped records or read them as the active journal',async()=>{
  localStorage.setItem(JOURNAL_KEY,JSON.stringify([journalEntry(plan)]));await render({initialTab:'JOURNAL'});expect(wrapper!.find('.journal-entry').exists()).toBe(false);expect(mocks.previewImport).not.toHaveBeenCalled()
  await button('查看未归属旧日志（1条）').trigger('click');expect(button('预览这条旧记录').attributes('disabled')).toBeDefined();await wrapper!.get('.import-panel .check-row input').setValue(true);await button('预览这条旧记录').trigger('click');await flushPromises();expect(mocks.previewImport).toHaveBeenCalledWith(expect.any(String),scope,'UNSCOPED',true,expect.any(String));expect(localStorage.getItem(JOURNAL_KEY)).not.toBeNull()
 })
 it('drops a late preview after the account or workspace changes',async()=>{
  writeJournal([journalEntry(plan)]);let resolve:(v:unknown)=>void=()=>{};mocks.previewImport.mockImplementationOnce(()=>new Promise(r=>resolve=r));await render({initialTab:'JOURNAL'});await button('预览导入服务端').trigger('click')
  const nextTenant='20000000-0000-4000-8000-000000000002';setStorageScope(user.id+':'+nextTenant);authState.user={...structuredClone(user),tenantId:nextTenant};await flushPromises();resolve({id:'old-private-preview',kind:'LOCAL_IMPORT',sourceHash:'old-owner',snapshot:journalEntry(plan)});await flushPromises();expect(wrapper!.find('.import-preview').exists()).toBe(false);expect(mocks.archiveResearch).not.toHaveBeenCalled()
 })
 it('retains the local-only workflow when server persistence permissions are absent',async()=>{
  authState.user={...structuredClone(user),permissions:['research.read','research.write']};await render();await wrapper!.get('form').trigger('submit');await flushPromises();expect(mocks.researchPlan).toHaveBeenCalled();expect(mocks.calculateResearch).not.toHaveBeenCalled();await wrapper!.get('.save-plan').trigger('click');expect(localStorage.getItem(JOURNAL_KEY+':'+scope)).not.toBeNull()
 })
})
