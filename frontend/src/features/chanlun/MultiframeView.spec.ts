import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import MultiframeView from './MultiframeView.vue'
import {multiframeApi,type MultiframeRun,type MultiframeFrame} from './multiframe'
import {api} from '../../services/api'
import {monitorApi} from './monitor'
import {decisionsApi} from '../../services/decisions'
import {observationFixture,structureFixtureId as sid} from './contextFixtures'
import {authState} from '../../services/auth'
vi.mock('./multiframe',()=>({multiframeApi:{list:vi.fn(),get:vi.fn(),create:vi.fn()}}))
vi.mock('./monitor',()=>({monitorApi:{list:vi.fn()}}))
vi.mock('../../services/api',()=>({api:{instruments:vi.fn()}}))
vi.mock('../../services/decisions',()=>({decisionsApi:{detail:vi.fn()}}))
const id='11111111-1111-4111-8111-111111111111'
function frame(frequency:'MIN5'|'MIN30'):MultiframeFrame{
  const stamps=frequency==='MIN30'?[['09:00','09:30'],['09:30','10:00']]:[['09:30','09:35'],['09:35','09:40']]
  const bars=stamps.map(([start,seal],i)=>({index:i,providerIndex:i,timestamp:`2026-10-30T${start}:00+08:00`,sealedByTimestamp:`2026-10-30T${seal}:00+08:00`,date:'2026-10-30',contract:'FU2701',open:100,high:102,low:99,close:101,volume:10}))
  return {frequency,source:{receiptAt:'2026-10-31T12:00:00+08:00',source:'PRIMARY',status:'CLOSED'},analysis:{bars,structures:[],profileHash:'profile',inputHash:'input',observedBars:2,observedAsOfDate:bars[1]!.timestamp,symbol:'FU2701',frequency,priceBasis:'UNADJUSTED_DELIVERY'},lastSealedBy:bars[1]!.sealedByTimestamp,firstProviderIndex:0,lastProviderIndex:1,sourceWindowBars:3,sourceWindowStart:bars[0]!.timestamp}
}
function run():MultiframeRun{return {id,status:'SUCCEEDED',error:null,createdAt:'now',request:{clientRequestId:id,symbol:'FU2701',frames:'PAIR',asOf:null},report:{configHash:'config',capturedAt:'2026-10-31T12:00:00+08:00',asOf:'2026-10-30T11:00:00+08:00',frames:[frame('MIN30'),frame('MIN5')],config:{symbol:'FU2701',mode:'HISTORICAL',priceBasis:'UNADJUSTED_DELIVERY'},limitations:['历史重建不是当时已收到的行情'],executable:false}}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.resetAllMocks();authState.user=null;vi.mocked(api.instruments).mockResolvedValue({source:'primary',dataStatus:'FRESH',dataTimestamp:'now',exchanges:[]});vi.mocked(monitorApi.list).mockResolvedValue([{enabled:true,symbol:'FU2701'} as never]);vi.mocked(multiframeApi.list).mockResolvedValue([]);vi.mocked(multiframeApi.get).mockResolvedValue(run());vi.mocked(multiframeApi.create).mockImplementation(async body=>({...observationFixture(body.symbol,id),request:body}))})
afterEach(()=>{wrapper?.unmount();authState.user=null;vi.useRealTimers()})
async function setup(path='/chanlun/multiframe'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/multiframe',component:MultiframeView},...['workbench','radar','compare','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div/>'}}))]});await router.push(path);await router.isReady();wrapper=mount(MultiframeView,{global:{plugins:[router],stubs:{TongdaxinChart:{name:'TongdaxinChart',props:['points','overlays','externalCursorTimestamp','linkedViewport'],emits:['cursorTimestamp','viewportChange'],template:'<div class="chart-stub" />'},ChanlunReader:true}}});await flushPromises();return router
}
describe('independent multi-timeframe observations',()=>{
  it('clears a restored observation when the current identity loses read permission',async()=>{
    await setup(`/chanlun/multiframe?observation=${id}`);authState.user={id,tenantId:id,username:'new',email:null,role:'MEMBER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:[]};await flushPromises();expect(wrapper!.findAll('.chart-stub')).toHaveLength(0);expect(wrapper!.text()).toContain('当前身份不能读取缠论观察');expect(multiframeApi.get).toHaveBeenCalledTimes(1)
  })
  it('opens an actual-month draft without creating an observation and never maps 15 minutes to a different source frame',async()=>{
    const router=await setup('/chanlun/multiframe?symbol=RB2701&period=900');expect(wrapper!.get('input[list]').element).toHaveProperty('value','RB2701');expect(multiframeApi.get).not.toHaveBeenCalled();expect(multiframeApi.create).not.toHaveBeenCalled();expect(router.currentRoute.value.query.period).toBe('900');expect(wrapper!.text()).toContain('30分/5分观察组合分开')
  })
  it('restores a frame-scoped structure and gives a current-market link back to the frozen record',async()=>{
    vi.mocked(multiframeApi.get).mockResolvedValue(observationFixture('RB2701',id));await setup(`/chanlun/multiframe?observation=${id}&symbol=RB2701&period=900&frame=MIN5&structure=${sid}`)
    expect(wrapper!.find('.evidence').text()).toContain('5 分钟');const href=wrapper!.findAll('a').find(a=>a.text().includes('查看当前行情并保留'))!.attributes('href')!
    expect(href).toContain('chanObservation='+id);expect(href).toContain('chanFrame=MIN5');expect(href).toContain('chanStructure='+sid);expect(href).toContain('period=900');expect(multiframeApi.create).not.toHaveBeenCalled()
  })
  it('refuses an absent requested structure instead of selecting the last structure',async()=>{
    vi.mocked(multiframeApi.get).mockResolvedValue(observationFixture('RB2701',id));await setup(`/chanlun/multiframe?observation=${id}&frame=MIN5&structure=missing`);expect(wrapper!.text()).toContain('指定结构不在此周期');expect(wrapper!.findAll('.chart-stub')).toHaveLength(0);expect(multiframeApi.create).not.toHaveBeenCalled()
  })
  it('rejects a stored observation from another requested month',async()=>{await setup(`/chanlun/multiframe?observation=${id}&symbol=RB2701`);expect(wrapper!.text()).toContain('冻结观察与请求的合约不一致');expect(wrapper!.findAll('.chart-stub')).toHaveLength(0)})
  it('clears the frozen chart when the URL returns to a draft without an observation id',async()=>{const router=await setup(`/chanlun/multiframe?observation=${id}`);await router.push('/chanlun/multiframe?symbol=RB2701');await flushPromises();expect(wrapper!.findAll('.chart-stub')).toHaveLength(0);expect(wrapper!.text()).toContain('观察草稿');expect(multiframeApi.create).not.toHaveBeenCalled()})
  it('pins a private original plan before an explicit observation is created',async()=>{
    const cid='30000000-0000-4000-8000-000000000001',pid='30000000-0000-4000-8000-000000000002'
    vi.mocked(decisionsApi.detail).mockResolvedValue({id:cid,symbol:'RB2701',version:2,origin:{id:42,label:'synthetic',evidence:{triggerSeconds:900}},plans:[{id:pid,version:1,fields:{}}],paper:[],reviews:[]} as never)
    const router=await setup(`/chanlun/multiframe?case=${cid}&plan=${pid}`);expect(multiframeApi.create).not.toHaveBeenCalled();await wrapper!.get('form').trigger('submit');await flushPromises();expect(router.currentRoute.value.query.plan).toBe(pid);expect(router.currentRoute.value.query.case).toBe(cid);expect(router.currentRoute.value.query.period).toBe('900');expect(wrapper!.findAll('.chart-stub')).toHaveLength(2)
  })
  it('does not create or read an observation after a private source is denied and offers an explicit independent draft',async()=>{vi.mocked(decisionsApi.detail).mockRejectedValue(new Error('private source denied'));const router=await setup('/chanlun/multiframe?case=30000000-0000-4000-8000-000000000001');expect(wrapper!.text()).toContain('private source denied');expect(multiframeApi.get).not.toHaveBeenCalled();expect(multiframeApi.create).not.toHaveBeenCalled();await wrapper!.findAll('button').find(b=>b.text()==='解除引用，进入独立观察草稿')!.trigger('click');await flushPromises();expect(router.currentRoute.value.query.case).toBeUndefined();expect(wrapper!.text()).toContain('观察草稿');expect(multiframeApi.create).not.toHaveBeenCalled()})
  it('drops a late stored observation response after the URL changes',async()=>{
    let resolve!:(v:MultiframeRun)=>void;vi.mocked(multiframeApi.get).mockReturnValueOnce(new Promise(r=>resolve=r));const router=await setup(`/chanlun/multiframe?observation=${id}`);await router.push('/chanlun/multiframe?symbol=RB2701');await flushPromises();resolve(run());await flushPromises();expect(wrapper!.findAll('.chart-stub')).toHaveLength(0);expect(router.currentRoute.value.query.symbol).toBe('RB2701')
  })
  it('does not subscribe on entry and restores the frozen record without recomputing',async()=>{
    await setup(`/chanlun/multiframe?observation=${id}`);expect(multiframeApi.get).toHaveBeenCalledWith(id);expect(multiframeApi.create).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('共同重建界限');expect(wrapper!.text()).toContain('历史重建不是当时已收到的行情')
  })
  it('links by successor proof and keeps chart point references stable during cursor movement',async()=>{
    await setup(`/chanlun/multiframe?observation=${id}`);const charts=wrapper!.findAllComponents({name:'TongdaxinChart'}),original=charts[0]!.props('points')
    charts[1]!.vm.$emit('cursorTimestamp','2026-10-30T09:35:00+08:00');await flushPromises()
    expect(charts[0]!.props('externalCursorTimestamp')).toBe('2026-10-30T09:00:00+08:00');expect(charts[0]!.props('points')).toBe(original)
    await wrapper!.findAll('button').find(b=>b.text()==='按光标界限重新构建')!.trigger('click');await flushPromises()
    expect(multiframeApi.create).toHaveBeenCalledWith(expect.objectContaining({asOf:'2026-10-30T09:40:00+08:00',symbol:'FU2701',frames:'PAIR'}))
  })
  it('retains the same request after an uncertain network response',async()=>{
    vi.mocked(multiframeApi.create).mockRejectedValueOnce(new Error('连接中断'));await setup();await wrapper!.get('form').trigger('submit');await flushPromises();const first=vi.mocked(multiframeApi.create).mock.calls[0]![0];await wrapper!.get('form').trigger('submit');await flushPromises();expect(vi.mocked(multiframeApi.create).mock.calls[1]![0]).toEqual(first)
  })
  it('interprets the typed observation clock as Shanghai time',async()=>{
    await setup();await wrapper!.get('input[type=datetime-local]').setValue('2026-10-30T09:40');await wrapper!.get('form').trigger('submit');await flushPromises();expect(multiframeApi.create).toHaveBeenCalledWith(expect.objectContaining({asOf:'2026-10-30T01:40:00.000Z'}))
  })
  it('continues the exact stored request after restoring a pending observation',async()=>{
    const waiting=run();waiting.status='WAITING_INPUT';waiting.report=null;waiting.error='等待原始数据';vi.mocked(multiframeApi.get).mockResolvedValue(waiting)
    await setup(`/chanlun/multiframe?observation=${id}`);expect(multiframeApi.create).not.toHaveBeenCalled();await wrapper!.findAll('button').find(b=>b.text()==='继续原请求')!.trigger('click');await flushPromises();expect(multiframeApi.create).toHaveBeenCalledWith(waiting.request)
  })
})
