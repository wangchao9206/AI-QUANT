import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import MonitorPanel from './MonitorPanel.vue'
const mocks=vi.hoisted(()=>({catalog:vi.fn(),jobs:vi.fn(),events:vi.fn(),save:vi.fn(),enabled:vi.fn(),archive:vi.fn(),acknowledge:vi.fn(),write:true}))
vi.mock('../services/monitoring',()=>({monitoringApi:mocks}))
vi.mock('../services/auth',()=>({hasPermission:(code:string)=>!code.endsWith('.write')||mocks.write}))
const parameters={rules:['PRICE_UP_60S','MACD_GOLDEN'],maPeriods:[5,10,20,60,180],lookback:20,volumeMultiple:2,jumpPct:10,bigLots:100,bollStd:2,atrMultiple:2,cooldownSeconds:60,pivotBars:2}
const job={id:'job-one',name:'测试后台任务',symbol:'RB2701',assetType:'FUTURE',enabled:true,version:3,seconds:60,parameters,metadata:{},status:'READY',message:'监控运行中',checkedAt:'2026-11-06T02:00:00Z',sourceTimestamp:'2026-11-06T02:00:00Z',metrics:{}}
const event={id:1,monitorId:'job-one',rule:'BIG_BUY',label:'大额买向成交增量',symbol:'RB2701',observedAt:'2026-11-06T02:00:00Z',createdAt:'2026-11-06T02:00:01Z',acknowledgedAt:null,evidence:{lots:120},algorithmVersion:'depth-monitor-v1'}
const wrappers:ReturnType<typeof mount>[]=[]
async function setup(assetType:'FUTURE'|'OPTION'='FUTURE',paused=false){const w=mount(MonitorPanel,{props:{assetType,symbol:assetType==='OPTION'?'DCE.m2701-C-3000':'RBM',paused}});wrappers.push(w);await flushPromises();return w}
beforeEach(()=>{vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-06T02:00:03Z'));Object.defineProperty(document,'hidden',{configurable:true,value:false});vi.clearAllMocks();mocks.write=true;mocks.catalog.mockResolvedValue({algorithmVersion:'depth-monitor-v1',rules:[{code:'PRICE_UP_60S',label:'60 秒涨幅超阈值'},{code:'MACD_GOLDEN',label:'MACD 金叉'}],defaults:parameters,frequencies:[60,180,300,900],maxEnabledPerTenant:20,maxEnabledGlobal:32});mocks.jobs.mockResolvedValue({items:[job],total:1,page:1,size:20});mocks.events.mockResolvedValue({items:[event],total:1,page:1,size:20});mocks.save.mockResolvedValue(job);mocks.enabled.mockResolvedValue(job);mocks.archive.mockResolvedValue({});mocks.acknowledge.mockResolvedValue({})})
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.useRealTimers()})
describe('server monitor management',()=>{
 it('explains background persistence and shows saved triggers with evidence',async()=>{const w=await setup();expect(w.text()).toContain('关闭页面仍运行');expect(mocks.jobs).toHaveBeenCalledWith('FUTURE','',1);await w.findAll('button').find(b=>b.text()==='触发依据')!.trigger('click');expect(w.get('[aria-label="监控触发依据"]').text()).toContain('120')})
 it('saves independently configurable option thresholds and retains failed forms',async()=>{const w=await setup('OPTION');await w.findAll('button').find(b=>b.text().includes('监控当前期权'))!.trigger('click');expect((w.get('[aria-label="大额成交手数"]').element as HTMLInputElement).value).toBe('20');await w.get('[aria-label="大额成交手数"]').setValue('50');await w.get('[aria-label="60 秒涨跌阈值"]').setValue('12');mocks.save.mockRejectedValueOnce(new Error('版本冲突'));await w.get('[aria-label="监控规则配置"]').trigger('submit');await flushPromises();expect(w.find('[aria-label="监控规则配置"]').exists()).toBe(true);expect(w.text()).toContain('版本冲突');expect(mocks.save).toHaveBeenCalledWith('OPTION',expect.objectContaining({symbol:'DCE.m2701-C-3000',parameters:expect.objectContaining({bigLots:50,jumpPct:12})}),undefined)})
 it('requires explicit confirmation before stopping a running monitor',async()=>{const w=await setup();await w.findAll('button').find(b=>b.text()==='暂停')!.trigger('click');expect(mocks.enabled).not.toHaveBeenCalled();expect(w.get('[role="alertdialog"]').text()).toContain('暂停后不再产生新触发记录');await w.get('[role="alertdialog"]').findAll('button').find(b=>b.text()==='确认操作')!.trigger('click');await flushPromises();expect(mocks.enabled).toHaveBeenCalledWith('FUTURE',expect.objectContaining({id:'job-one',version:3}),false)})
 it('does not equate pausing UI refresh with disabling the backend task',async()=>{const w=await setup('FUTURE',true);const count=mocks.jobs.mock.calls.length;await vi.advanceTimersByTimeAsync(10000);expect(mocks.jobs).toHaveBeenCalledTimes(count);expect(mocks.enabled).not.toHaveBeenCalled();expect(w.text()).toContain('服务器监控仍继续');await w.setProps({paused:false});await flushPromises();expect(mocks.jobs.mock.calls.length).toBeGreaterThan(count);w.unmount();const last=mocks.jobs.mock.calls.length;await vi.advanceTimersByTimeAsync(10000);expect(mocks.jobs).toHaveBeenCalledTimes(last)})
 it('hides mutation controls for read-only users while preserving trigger history',async()=>{mocks.write=false;const w=await setup();expect(w.findAll('button').some(b=>b.text().includes('监控当前'))).toBe(false);expect(w.findAll('button').some(b=>b.text()==='暂停'||b.text()==='标记已读'||b.text()==='归档')).toBe(false);expect(w.text()).toContain('大额买向成交增量')})
 it('searches and paginates durable events rather than generating local examples',async()=>{mocks.events.mockResolvedValue({items:[event],total:45,page:1,size:20});const w=await setup();await w.get('[aria-label="搜索监控触发"]').setValue('MACD');await w.findAll('form').find(f=>f.find('[aria-label="搜索监控触发"]').exists())!.trigger('submit');await flushPromises();expect(mocks.events).toHaveBeenLastCalledWith('FUTURE','MACD',1,'',false);await w.findAll('.monitor-pagination button').find(b=>b.text()==='下一页')!.trigger('click');await flushPromises();expect(mocks.events).toHaveBeenLastCalledWith('FUTURE','MACD',2,'',false)})
 it('acknowledges a stored trigger using the asset-specific endpoint',async()=>{const w=await setup('OPTION');await w.findAll('button').find(b=>b.text()==='标记已读')!.trigger('click');await flushPromises();expect(mocks.acknowledge).toHaveBeenCalledWith('OPTION',1)})
 it('configures entry and exit templates with daily references rather than volume-gated same-period averages',async()=>{
  const w=await setup();await w.findAll('button').find(b=>b.text()==='15分钟突破／跌破日线MA20')!.trigger('click')
  await w.get('[aria-label="监控规则配置"]').trigger('submit');await flushPromises()
  expect(mocks.save).toHaveBeenLastCalledWith('FUTURE',expect.objectContaining({seconds:900,parameters:expect.objectContaining({dailyMaPeriod:20,rules:['DAILY_MA_BREAKOUT_UP','DAILY_MA_BREAKOUT_DOWN']})}),undefined)
  await w.findAll('button').find(b=>b.text()==='日线回踩MA5')!.trigger('click')
  await w.get('[aria-label="监控规则配置"]').trigger('submit');await flushPromises()
  expect(mocks.save).toHaveBeenLastCalledWith('FUTURE',expect.objectContaining({parameters:expect.objectContaining({dailyMaPeriod:5,pullbackTolerancePct:.2,rules:['DAILY_MA_PULLBACK','DAILY_MA_BREAKOUT_DOWN']})}),undefined)
 })

 it('uses failed statistical results as research context instead of labeling them a verified entry edge',async()=>{
  mocks.catalog.mockResolvedValueOnce({rules:[],defaults:parameters,frequencies:[60,900],research:{auditedSymbols:81,dataEnd:'2026-10-30',conditions:{UP_TREND:{label:'上升排列',developmentSelectedHorizon:10,selected:{VALIDATION:{samples:466,meanNetPct:.026},RETROSPECTIVE_2025_2026:{samples:497,meanNetPct:-.032,doubleCostMeanPct:-.106}}}}}})
  const w=await setup();expect(w.text()).toContain('没有条件通过跨时段稳健性门槛');expect(w.text()).toContain('-0.032')
  await w.findAll('button').find(b=>b.text()==='日线趋势／拐点研究预警')!.trigger('click')
  await w.get('[aria-label="监控规则配置"]').trigger('submit');await flushPromises()
  expect(mocks.save).toHaveBeenLastCalledWith('FUTURE',expect.objectContaining({parameters:expect.objectContaining({rules:['DAILY_RESEARCH_CONTEXT']})}),undefined)
 })

 it('offers outcome-first probability alerts with user-selectable target and evidence scope',async()=>{
  const w=await setup();await w.findAll('button').find(b=>b.text()==='结果反推 · 概率预警')!.trigger('click')
  expect(w.text()).toContain('概率预警目标');expect(w.text()).toContain('证据范围')
  await w.get('[aria-label="监控规则配置"]').trigger('submit');await flushPromises()
  expect(mocks.save).toHaveBeenLastCalledWith('FUTURE',expect.objectContaining({seconds:900,parameters:expect.objectContaining({rules:['OUTCOME_PATTERN'],outcomeTarget:'ALL',outcomeEvidence:'IMPROVED'})}),undefined)
 })

})
