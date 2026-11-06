import {mount,flushPromises} from '@vue/test-utils'
import {describe,it,expect,vi,beforeEach} from 'vitest'
import {createRouter,createMemoryHistory} from 'vue-router'
import {customTemplate,template} from '../utils/workflowGraph'
import StrategyWorkflowView from './StrategyWorkflowView.vue'
const mock=vi.hoisted(()=>({list:vi.fn(),create:vi.fn(),save:vi.fn(),validate:vi.fn(),publish:vi.fn(),draft:vi.fn(),debug:vi.fn(),replayStatus:vi.fn(),chanProfile:vi.fn(),observe:vi.fn(),shadows:vi.fn(),shadow:vi.fn(),version:vi.fn()}))
vi.mock('../services/workflows',()=>({workflowsApi:mock}))
vi.mock('../services/api',()=>({api:{replayStatus:mock.replayStatus}}))
async function setup(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:StrategyWorkflowView},{path:'/backtest',component:{template:'<div />'}},{path:'/paper',component:{template:'<div />'}}]});await router.push('/');await router.isReady();const wrapper=mount(StrategyWorkflowView,{global:{plugins:[router]}});await flushPromises();return wrapper}
beforeEach(()=>{vi.resetAllMocks();mock.list.mockResolvedValue([]);mock.replayStatus.mockResolvedValue({symbols:[{symbol:'JM0',startDate:'2025-01-01',endDate:'2025-03-01'}]});mock.validate.mockImplementation(async(definition)=>({definition,engineVersion:'workflow-daily-v1',requiredBars:20,nodeCount:definition.nodes.length,risk:{lots:1,stopLossAtr:2,takeProfitAtr:3}}))})
describe('workflow editor',()=>{
 it('pins a Chan draft, publishes it and requires an explicit archived observation before simulation',async()=>{
  const pins={engineId:'native',engineVersion:'aiquant-chan-v1',implementationHash:'frozen-source',rulesHash:'frozen-rules',priceQuantization:'DECIMAL_HALF_UP_6',qualification:'HISTORICAL_NEXT_OPEN_ONLY_V1',inputBasis:'OBSERVED_CONTINUOUS_DAILY',exitRule:'ANY_SAME_DIRECTION_INVALIDATED'}
  mock.chanProfile.mockResolvedValue(pins)
  mock.create.mockImplementation(async value=>({...value,id:'chan-draft',revision:1,versions:[]}))
  mock.publish.mockImplementation(async()=>({id:'chan-version',workflowId:'chan-draft',name:'Chan',version:1,engineVersion:'workflow-daily-v2',definition:mock.create.mock.calls[0]![0].definition,lots:1}))
  mock.shadows.mockResolvedValue([])
  const w=await setup()
  await w.findAll('button').find(b=>b.text()==='新建缠论草稿')!.trigger('click');await flushPromises()
  const saved=mock.create.mock.calls[0]![0].definition
  expect(saved.schemaVersion).toBe(2);expect(saved.nodes.find((n:{type:string})=>n.type==='CHAN_SIGNAL').params).toEqual({...pins,group:'THIRD'})
  await w.findAll('button').find(b=>b.text()==='发布版本')!.trigger('click');await flushPromises()
  expect(w.find('a[href^="/paper?"]').exists()).toBe(false)
  mock.observe.mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue({id:'shadow-1',workflowVersionId:'chan-version',symbol:'JM0',direction:0,historyCount:80,signalTime:'2025-03-01T00:00:00Z',signal:'HOLD',reason:'没有首次候选',recordedAt:'2026-11-06',nodeTrace:[],inputSnapshot:{signalBars:[]}})
  const button=w.findAll('button').find(b=>b.text()==='归档当前日期的观察')!
  await button.trigger('click');await flushPromises()
  const command=mock.observe.mock.calls[0]![1]
  await button.trigger('click');await flushPromises()
  expect(mock.observe.mock.calls[1]![1]).toEqual(command)
  expect(w.find('a[href^="/paper?"]').attributes('href')).toContain('shadow=shadow-1')
  w.unmount()
 })
 it('edits a custom graph, saves then publishes a frozen version and exposes both runners',async()=>{
  const w=await setup();await w.get('[aria-label="工作流模板"]').setValue('CUSTOM')
  await w.findAll('button').find(b=>b.text()==='新建')!.trigger('click');await flushPromises()
  expect(w.findAll('[data-node]')).toHaveLength(customTemplate().nodes.length)
  const definition=customTemplate();const draft={id:'draft-1',name:'收盘价高于均线',description:'',definition,revision:1,versions:[]}
  mock.create.mockImplementation(async(v)=>({...draft,definition:v.definition}))
  mock.publish.mockImplementation(async()=>({id:'version-1',workflowId:'draft-1',name:draft.name,version:1,lots:1,definition,stopLossAtr:2,takeProfitAtr:3}))
  await w.findAll('button').find(b=>b.text()==='发布版本')!.trigger('click');await flushPromises()
  expect(mock.validate).toHaveBeenCalledOnce();expect(mock.create).toHaveBeenCalledOnce();expect(mock.publish).toHaveBeenCalledWith('draft-1',1,expect.any(String))
  expect(w.find('a[href^="/backtest?"]').attributes('href')).toContain('workflowVersion=version-1')
  expect(w.find('a[href^="/paper?"]').attributes('href')).toContain('workflowVersion=version-1')
  w.unmount()
 })
 it('leaves the graph editable after a rejected publish and never calls the runner',async()=>{
  const w=await setup();mock.validate.mockRejectedValue(new Error('存在未连接的节点'))
  await w.findAll('button').find(b=>b.text()==='发布版本')!.trigger('click');await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('未连接');expect(mock.create).not.toHaveBeenCalled();expect(mock.publish).not.toHaveBeenCalled()
  w.unmount()
 })
 it('shows actual node trace from signal-only historical debug',async()=>{
  const w=await setup();mock.debug.mockResolvedValue({signal:'HOLD',reason:'条件不成立',historyCount:61,requiredBars:61,source:'OBSERVED',nodeTrace:[{nodeId:'preset',label:'突破条件',status:'BLOCKED',value:false,reason:'价格未突破'}]})
  await w.findAll('button').find(b=>b.text()==='试算节点')!.trigger('click');await flushPromises()
  expect(mock.debug).toHaveBeenCalledWith(expect.objectContaining({schemaVersion:1}),'JM0',expect.any(String),0)
  expect(w.text()).toContain('价格未突破');expect(mock.create).not.toHaveBeenCalled();w.unmount()
 })
})
