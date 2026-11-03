import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import MultiframeView from './MultiframeView.vue'
import {multiframeApi,type MultiframeRun,type MultiframeFrame} from './multiframe'
import {api} from '../../services/api'
import {monitorApi} from './monitor'
vi.mock('./multiframe',()=>({multiframeApi:{list:vi.fn(),get:vi.fn(),create:vi.fn()}}))
vi.mock('./monitor',()=>({monitorApi:{list:vi.fn()}}))
vi.mock('../../services/api',()=>({api:{instruments:vi.fn()}}))
const id='11111111-1111-4111-8111-111111111111'
function frame(frequency:'MIN5'|'MIN30'):MultiframeFrame{
  const stamps=frequency==='MIN30'?[['09:00','09:30'],['09:30','10:00']]:[['09:30','09:35'],['09:35','09:40']]
  const bars=stamps.map(([start,seal],i)=>({index:i,providerIndex:i,timestamp:`2026-10-30T${start}:00+08:00`,sealedByTimestamp:`2026-10-30T${seal}:00+08:00`,date:'2026-10-30',contract:'FU2701',open:100,high:102,low:99,close:101,volume:10}))
  return {frequency,source:{receiptAt:'2026-10-31T12:00:00+08:00',source:'PRIMARY',status:'CLOSED'},analysis:{bars,structures:[],profileHash:'profile',inputHash:'input',observedBars:2,observedAsOfDate:bars[1]!.timestamp,symbol:'FU2701',frequency,priceBasis:'UNADJUSTED_DELIVERY'},lastSealedBy:bars[1]!.sealedByTimestamp,firstProviderIndex:0,lastProviderIndex:1,sourceWindowBars:3,sourceWindowStart:bars[0]!.timestamp}
}
function run():MultiframeRun{return {id,status:'SUCCEEDED',error:null,createdAt:'now',request:{clientRequestId:id,symbol:'FU2701',frames:'PAIR',asOf:null},report:{configHash:'config',capturedAt:'2026-10-31T12:00:00+08:00',asOf:'2026-10-30T11:00:00+08:00',frames:[frame('MIN30'),frame('MIN5')],config:{symbol:'FU2701',mode:'HISTORICAL',priceBasis:'UNADJUSTED_DELIVERY'},limitations:['历史重建不是当时已收到的行情'],executable:false}}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.resetAllMocks();vi.mocked(api.instruments).mockResolvedValue({source:'primary',dataStatus:'FRESH',dataTimestamp:'now',exchanges:[]});vi.mocked(monitorApi.list).mockResolvedValue([{enabled:true,symbol:'FU2701'} as never]);vi.mocked(multiframeApi.list).mockResolvedValue([]);vi.mocked(multiframeApi.get).mockResolvedValue(run());vi.mocked(multiframeApi.create).mockResolvedValue(run())})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function setup(path='/chanlun/multiframe'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/multiframe',component:MultiframeView},...['workbench','radar','compare','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div/>'}}))]});await router.push(path);await router.isReady();wrapper=mount(MultiframeView,{global:{plugins:[router],stubs:{TongdaxinChart:{name:'TongdaxinChart',props:['points','overlays','externalCursorTimestamp','linkedViewport'],emits:['cursorTimestamp','viewportChange'],template:'<div class="chart-stub" />'},ChanlunReader:true}}});await flushPromises();return router
}
describe('independent multi-timeframe observations',()=>{
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
