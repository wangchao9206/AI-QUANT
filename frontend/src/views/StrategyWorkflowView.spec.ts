import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {describe,it,expect,vi,beforeEach} from 'vitest'
import {createRouter,createMemoryHistory} from 'vue-router'
import {customTemplate} from '../utils/workflowGraph'
import StrategyWorkflowView from './StrategyWorkflowView.vue'
const mock=vi.hoisted(()=>({list:vi.fn(),create:vi.fn(),save:vi.fn(),validate:vi.fn(),publish:vi.fn(),draft:vi.fn(),debug:vi.fn(),replayStatus:vi.fn(),chanProfile:vi.fn(),observe:vi.fn(),shadows:vi.fn(),shadow:vi.fn(),version:vi.fn(),evidence:vi.fn()}))
vi.mock('../services/workflows',()=>({workflowsApi:mock}))
vi.mock('../services/api',()=>({api:{replayStatus:mock.replayStatus}}))
async function setup(query:Record<string,string>={}){
 const placeholder={template:'<div />'}
 const router=createRouter({history:createMemoryHistory(),routes:[
  {path:'/',component:StrategyWorkflowView},
  ...['/strategy','/strategy/self-developed-trinity','/backtest','/paper'].map(path=>({path,component:placeholder})),
 ]})
 await router.push({path:'/',query})
 const wrapper=mount(StrategyWorkflowView,{global:{plugins:[router]}})
 await flushPromises()
 return wrapper
}
const button=(wrapper:VueWrapper,name:string)=>wrapper.findAll('button').find(item=>item.text()===name)!
const move=async(wrapper:VueWrapper,name:string)=>{
 await wrapper.get('nav[aria-label="工作流步骤"]').findAll('button').find(item=>item.text().endsWith(name))!.trigger('click')
}
beforeEach(()=>{vi.resetAllMocks();mock.list.mockResolvedValue([]);mock.shadows.mockResolvedValue([]);mock.replayStatus.mockResolvedValue({symbols:[{symbol:'JM0',startDate:'2025-01-01',endDate:'2025-03-01'}]});mock.validate.mockImplementation(async(definition)=>({definition,engineVersion:'workflow-daily-v1',requiredBars:20,nodeCount:definition.nodes.length,risk:{lots:1,stopLossAtr:2,takeProfitAtr:3}}))})
describe('workflow editor',()=>{
 it('opens the fourth step with a required profit target for an MA trend version',async()=>{
  const wrapper=await setup({template:'ma-trend-15m'})
  expect(wrapper.get('[aria-label="工作流名称"]').element).toHaveProperty('value','MA5／10／20 趋势与 15 分钟确认')
  expect(wrapper.text()).toContain('触发止盈后平掉当时持仓的一半')
  await button(wrapper,'去看信号').trigger('click')
  expect(wrapper.find('[aria-label="均线与分钟信号试算"]').exists()).toBe(true)
  await button(wrapper,'前往发布').trigger('click')
  expect(wrapper.get('[aria-current="step"]').text()).toContain('发布与模拟')
  expect(wrapper.get('[aria-label="策略发布状态"]').text()).toContain('盈利目标')
  expect(wrapper.get('[aria-label="策略发布状态"] input').attributes()).toHaveProperty('required')
  wrapper.unmount()
 })
 it('offers the multi-timeframe research template beside the daily workflow tools',async()=>{
  const wrapper=await setup()
  const entry=wrapper.get('a[href="/strategy/self-developed-trinity"]')
  expect(entry.text()).toBe('编辑「自研道氏-威科夫-缠论三位一体」模板')
  expect(wrapper.find('[aria-label="工作流模板"]').exists()).toBe(true)
  expect(wrapper.get('[aria-current="step"]').text()).toContain('选策略')
  expect(wrapper.find('[aria-label="策略编排画布"]').exists()).toBe(false)
  wrapper.unmount()
 })
 it('pins a Chan draft, publishes it and requires an explicit archived observation before simulation',async()=>{
  const pins={engineId:'native',engineVersion:'aiquant-chan-v1',implementationHash:'frozen-source',rulesHash:'frozen-rules',priceQuantization:'DECIMAL_HALF_UP_6',qualification:'HISTORICAL_NEXT_OPEN_ONLY_V1',inputBasis:'OBSERVED_CONTINUOUS_DAILY',exitRule:'ANY_SAME_DIRECTION_INVALIDATED'}
  mock.chanProfile.mockResolvedValue(pins)
  mock.create.mockImplementation(async value=>({...value,id:'chan-draft',revision:1,versions:[]}))
  mock.publish.mockImplementation(async()=>({id:'chan-version',workflowId:'chan-draft',name:'Chan',version:1,engineVersion:'workflow-daily-v2',definition:mock.create.mock.calls[0]![0].definition,lots:1}))
  mock.shadows.mockResolvedValue([])
  const w=await setup()
  await button(w,'新建缠论草稿').trigger('click');await flushPromises()
  const saved=mock.create.mock.calls[0]![0].definition
  expect(saved.schemaVersion).toBe(2);expect(saved.nodes.find((n:{type:string})=>n.type==='CHAN_SIGNAL').params).toEqual({...pins,group:'THIRD'})
  await move(w,'发布与模拟')
  await button(w,'发布版本').trigger('click');await flushPromises()
  expect(w.find('a[href^="/paper?"]').exists()).toBe(false)
  expect(w.get('[aria-label="缠论冻结观察"]').text()).toContain('至少 50 根日线')
  mock.observe.mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue({id:'shadow-1',workflowVersionId:'chan-version',symbol:'JM0',direction:0,historyCount:80,signalTime:'2025-03-01T00:00:00Z',signal:'HOLD',reason:'没有首次候选',recordedAt:'2026-11-06',nodeTrace:[],inputSnapshot:{signalBars:[]}})
  const form=w.get('[aria-label="缠论冻结观察"] form')
  await form.trigger('submit');await flushPromises()
  const command=mock.observe.mock.calls[0]![1]
  await form.trigger('submit');await flushPromises()
  expect(mock.observe.mock.calls[1]![1]).toEqual(command)
  expect(w.find('a[href^="/paper?"]').attributes('href')).toContain('shadow=shadow-1')
  w.unmount()
 })
 it('edits a custom graph, saves then publishes a frozen version and exposes both runners',async()=>{
  const w=await setup();await w.get('[aria-label="工作流模板"]').setValue('CUSTOM')
  await button(w,'使用模板').trigger('click');await flushPromises()
  expect(w.get('[aria-current="step"]').text()).toContain('改规则')
  expect(w.find('[aria-label="策略编排画布"]').exists()).toBe(false)
  await button(w,'打开高级画布').trigger('click');await flushPromises()
  expect(w.findAll('[data-node]')).toHaveLength(customTemplate().nodes.length)
  const definition=customTemplate();const draft={id:'draft-1',name:'收盘价高于均线',description:'',definition,revision:1,versions:[]}
  mock.create.mockImplementation(async(v)=>({...draft,definition:v.definition}))
  mock.publish.mockImplementation(async()=>({id:'version-1',workflowId:'draft-1',name:draft.name,version:1,lots:1,definition,stopLossAtr:2,takeProfitAtr:3}))
  await move(w,'发布与模拟')
  await button(w,'发布版本').trigger('click');await flushPromises()
  expect(mock.validate).toHaveBeenCalledOnce();expect(mock.create).toHaveBeenCalledOnce();expect(mock.publish).toHaveBeenCalledWith('draft-1',1,expect.any(String))
  expect(w.find('a[href^="/backtest?"]').attributes('href')).toContain('workflowVersion=version-1')
  expect(w.find('a[href^="/paper?"]').attributes('href')).toContain('workflowVersion=version-1')
  w.unmount()
 })
 it('leaves the graph editable after a rejected publish and never calls the runner',async()=>{
  const w=await setup();mock.validate.mockRejectedValue(new Error('存在未连接的节点'))
  await button(w,'使用模板').trigger('click')
  await move(w,'发布与模拟')
  await button(w,'发布版本').trigger('click');await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('未连接');expect(mock.create).not.toHaveBeenCalled();expect(mock.publish).not.toHaveBeenCalled()
  await move(w,'改规则')
  expect(w.find('[aria-label="工作流名称"]').exists()).toBe(true)
  w.unmount()
 })
 it('shows actual node trace from signal-only historical debug',async()=>{
  const w=await setup();mock.debug.mockResolvedValue({signal:'HOLD',reason:'条件不成立',historyCount:61,requiredBars:61,source:'OBSERVED',nodeTrace:[{nodeId:'preset',label:'突破条件',status:'BLOCKED',value:false,reason:'价格未突破'}]})
  await button(w,'使用模板').trigger('click')
  await button(w,'去看信号').trigger('click')
  await w.get('form').trigger('submit');await flushPromises()
  expect(mock.debug).toHaveBeenCalledWith(expect.objectContaining({schemaVersion:1}),'JM0',expect.any(String),0)
  expect(w.get('[aria-label="信号结果"]').text()).toContain('价格未突破')
  await w.get('[aria-label="在画布定位 突破条件"]').trigger('click')
  expect(w.find('[aria-label="策略编排画布"]').exists()).toBe(true)
  expect(mock.create).not.toHaveBeenCalled();w.unmount()
 })
 it('opens saved decision evidence from the paper route without starting a draft',async()=>{
  mock.evidence.mockResolvedValue({symbol:'JM0',signal:'BUY',reason:'已归档入场依据',signalTime:'2025-03-01T00:00:00Z',observationKind:'FROZEN_PAPER_DECISION',inputSnapshot:{signalBars:[]},nodeTrace:[]})
  const w=await setup({session:'paper-1',decision:'2025-03-01T00:00:00Z'})
  expect(mock.evidence).toHaveBeenCalledWith('paper-1','2025-03-01T00:00:00Z')
  expect(w.get('#workflow-stage-title').text()).toBe('查看模拟决策')
  expect(w.get('[aria-label="缠论冻结观察"]').text()).toContain('已归档入场依据')
  expect(mock.create).not.toHaveBeenCalled()
  w.unmount()
 })
})
