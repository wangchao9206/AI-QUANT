import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import CompareView from './CompareView.vue'
import {chanlunApi,type Analysis,type EngineId,type Structure} from './api'
import {comparisonApi,type ComparisonRun,type ComparisonDetail} from './comparison'
vi.mock('./api',()=>({chanlunApi:{engines:vi.fn(),datasets:vi.fn(),create:vi.fn(),result:vi.fn()}}))
vi.mock('./comparison',()=>({comparisonApi:{list:vi.fn(),get:vi.fn(),create:vi.fn(),at:vi.fn(),events:vi.fn(),judge:vi.fn()}}))
const dataset={id:'frozen',sha256:'hash',symbol:'FU0',displayName:'燃油',frequency:'DAY',bars:1894,start:'2019-01-02',end:'2026-10-27',priceBasis:'forward-observed-roll-ratio-v1'}
const structure:Structure={id:'a'.repeat(24),type:'BI',direction:'UP',startIndex:0,endIndex:1,revision:1,engineConfirmed:false,rawFlag:'dynamic',firstObservedDate:'2019-01-03',engineConfirmedDate:null,eligibleAt:null,pivotStartDate:'2019-01-02',pivotEndDate:'2019-01-03',observedAsOfDate:'2019-01-03',state:'CURRENT'}
function analysis(engineId:EngineId='native',total=2):Analysis{return {runId:`source-${engineId}`,engineId,engineVersion:'pinned',profileHash:'profile',profile:{parameters:{}},dataset,datasetHash:'hash',observedBars:total,observedAsOfDate:`2019-01-0${total+1}`,priceBasis:dataset.priceBasis,bars:Array.from({length:total},(_,i)=>({index:i,date:`2019-01-0${i+2}`,timestamp:`2019-01-0${i+2}T00:00:00+08:00`,contract:'FU1905',open:100,high:101,low:99,close:100,volume:1})),structures:[structure],counts:{BI:1},layers:['BI','ZONE'],recordedAt:'now'}}
function run(id='comparison'):ComparisonRun{return {id,status:'SUCCEEDED',error:null,createdAt:'now',request:{clientRequestId:'command',runIds:['source-native','source-chanpy'],layer:'BI',projection:'GEOMETRY',confirmedOnly:false},report:{version:'observed-geometry-comparison-v1',layer:'BI',projection:'GEOMETRY',confirmedOnly:false,priceTolerance:1e-8,sources:['native','chanpy'].map(engineId=>({runId:`source-${engineId}`,engineId:engineId as EngineId,profileHash:'profile',engineVersion:'pinned'})),observedBars:3,observedAsOfDate:'2019-01-04',datasetHash:'hash',priceBasis:dataset.priceBasis,firstDifference:{observedIndex:1,date:'2019-01-03',pairs:[]},firstGeometryDifference:{observedIndex:1,date:'2019-01-03',pairs:[]},firstConfirmationDifference:null,differentObservationCount:1,spans:[{startIndex:1,endIndex:1}],timeline:[0,1,2].map(observedIndex=>({observedIndex,date:`2019-01-0${observedIndex+2}`,different:observedIndex===1,geometryDifferent:observedIndex===1,confirmationDifferent:false,counts:{native:1,chanpy:1}})),limitations:['不同不能证明准确率']}}}
function detail(id='comparison',index=1):ComparisonDetail{return {comparisonId:id,observedIndex:index,date:`2019-01-0${index+2}`,frames:['native','chanpy'].map(id=>({sourceRunId:`source-${id}`,analysis:analysis(id as EngineId,index+1)})),pairs:[]}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.resetAllMocks()
  vi.mocked(chanlunApi.engines).mockResolvedValue(['native','chanpy','czsc','baseline'].map(id=>({id:id as EngineId,name:id,status:'AVAILABLE',layers:['BI','ZONE']})))
  vi.mocked(chanlunApi.datasets).mockResolvedValue([dataset]);vi.mocked(chanlunApi.create).mockImplementation(async b=>({id:`source-${b.engineId}`,engineId:b.engineId,observedBars:b.observedBars,status:'SUCCEEDED',error:null}))
  vi.mocked(chanlunApi.result).mockImplementation(async id=>analysis(id.replace('source-','') as EngineId,501))
  vi.mocked(comparisonApi.list).mockResolvedValue([]);vi.mocked(comparisonApi.get).mockImplementation(async id=>run(id));vi.mocked(comparisonApi.create).mockResolvedValue(run())
  vi.mocked(comparisonApi.at).mockImplementation(async (id,index)=>detail(id,index));vi.mocked(comparisonApi.events).mockResolvedValue([]);vi.mocked(comparisonApi.judge).mockResolvedValue({id:'note',createdAt:'now'})
})
afterEach(()=>wrapper?.unmount())
async function setup(path='/chanlun/compare?comparison=comparison'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/compare',component:CompareView},...['workbench','multiframe','radar','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div/>'}}))]});await router.push(path);await router.isReady()
  wrapper=mount(CompareView,{global:{plugins:[router],stubs:{TongdaxinChart:{name:'TongdaxinChart',props:['points','overlays','selectedOverlayId'],emits:['selectStructure'],template:'<div class="chart"/>'},ChanlunReader:true}}});await flushPromises();return {router,view:wrapper}
}
function button(text:string){return wrapper!.findAll('button').find(b=>b.text().startsWith(text))!}
describe('archived engine observation comparison',()=>{
  it('restores before catalog availability, uses first observation difference and sends only that prefix to charts',async()=>{
    vi.mocked(chanlunApi.engines).mockReturnValue(new Promise(()=>{}));vi.mocked(chanlunApi.datasets).mockReturnValue(new Promise(()=>{}))
    const {view}=await setup();expect(comparisonApi.at).toHaveBeenCalledWith('comparison',1);expect(chanlunApi.create).not.toHaveBeenCalled()
    expect(view.text()).toContain('当时取证 · 2019-01-03 · 2 根');expect(view.findAllComponents({name:'TongdaxinChart'})[0]!.props('points')).toHaveLength(2)
  })
  it('keeps slider selection separate from evidence until explicitly loaded, and archives that displayed index',async()=>{
    const {view}=await setup();await view.get('input[type=range]').setValue(2);expect(comparisonApi.at).toHaveBeenCalledTimes(1);expect(view.text()).toContain('当时取证 · 2019-01-03 · 2 根')
    await view.get('textarea').setValue('当时的依据');await button('保存此时点判断').trigger('click');await flushPromises();expect(comparisonApi.judge).toHaveBeenCalledWith('comparison',1,expect.objectContaining({sourceRunId:'source-native',structureId:null,content:'当时的依据'}))
    await button('载入所选时点').trigger('click');await flushPromises();expect(comparisonApi.at).toHaveBeenLastCalledWith('comparison',2)
  })
  it('ignores a slow older prefix response after a newer archive is opened',async()=>{
    const {router,view}=await setup();let finish!:(d:ComparisonDetail)=>void
    vi.mocked(comparisonApi.at).mockImplementation((id,index)=>id==='comparison'&&index===0?new Promise(resolve=>finish=resolve):Promise.resolve(detail(id,index)))
    await button('上一根').trigger('click');await router.push('/chanlun/compare?comparison=new&at=2');await flushPromises();finish(detail('comparison',0));await flushPromises()
    expect(view.text()).toContain('当时取证 · 2019-01-04 · 3 根');expect(view.findAllComponents({name:'TongdaxinChart'})[0]!.props('points')).toHaveLength(3)
  })
  it('selects a chart object from another source without losing selection and fetches bounded events',async()=>{
    const {view}=await setup();view.findAllComponents({name:'TongdaxinChart'})[1]!.vm.$emit('selectStructure',structure.id);await flushPromises()
    expect(comparisonApi.events).toHaveBeenLastCalledWith('comparison','source-chanpy',1,structure.id)
    await view.get('textarea').setValue('chan.py对应的结构');await button('保存此时点判断').trigger('click');await flushPromises();expect(comparisonApi.judge).toHaveBeenLastCalledWith('comparison',1,expect.objectContaining({sourceRunId:'source-chanpy',structureId:structure.id}))
  })
  it('reuses a judgment request after uncertain response and keeps drafts separate across evidence times',async()=>{
    const {view}=await setup();vi.mocked(comparisonApi.judge).mockRejectedValue(new Error('network'))
    await view.get('textarea').setValue('原判断');await button('保存此时点判断').trigger('click');await flushPromises();await button('保存此时点判断').trigger('click');await flushPromises()
    expect(vi.mocked(comparisonApi.judge).mock.calls[0]).toEqual(vi.mocked(comparisonApi.judge).mock.calls[1])
    await button('下一根').trigger('click');await flushPromises();expect((view.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    await button('上一根').trigger('click');await flushPromises();expect((view.get('textarea').element as HTMLTextAreaElement).value).toBe('原判断')
  })
  it('does not silently create a partial comparison when one chosen engine fails',async()=>{
    await setup('/chanlun/compare');vi.mocked(chanlunApi.create).mockImplementation(async b=>{if(b.engineId==='czsc')throw new Error('CZSC unavailable');return {id:`source-${b.engineId}`,engineId:b.engineId,observedBars:501,status:'SUCCEEDED',error:null}})
    await wrapper!.get('form').trigger('submit');await flushPromises();expect(comparisonApi.create).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('全部来源成功后才会创建对照')
  })
  it('rejects invalid archived indices without falling forward to latest evidence',async()=>{
    const {view}=await setup('/chanlun/compare?comparison=comparison&at=300');expect(comparisonApi.at).not.toHaveBeenCalled();expect(view.findAll('.chart')).toHaveLength(0);expect(view.text()).toContain('取证时点超出此对照范围')
  })
  it('rejects responses with more bars than the requested evidence bound',async()=>{
    vi.mocked(comparisonApi.at).mockResolvedValue(detail('comparison',2));const {view}=await setup();expect(view.text()).toContain('取证结果与请求时点不一致');expect(view.findAll('.chart')).toHaveLength(0)
  })
  it('carries the workbench input boundary into a new comparison without starting calculations',async()=>{
    vi.mocked(chanlunApi.result).mockResolvedValue(analysis('chanpy',501));const {view}=await setup('/chanlun/compare?run=source-chanpy')
    expect((view.get('input[type=number]').element as HTMLInputElement).value).toBe('501');expect(view.text()).toContain('已沿用工作台的501根输入界限');expect(comparisonApi.create).not.toHaveBeenCalled();expect(chanlunApi.create).not.toHaveBeenCalled()
  })
})
