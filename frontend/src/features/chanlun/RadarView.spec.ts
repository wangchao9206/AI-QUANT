import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import RadarView from './RadarView.vue'
import {monitorApi,type MonitorView,type MonitorEvidence} from './monitor'
import {api} from '../../services/api'
vi.mock('./monitor',()=>({monitorApi:{list:vi.fn(),get:vi.fn(),create:vi.fn(),check:vi.fn(),control:vi.fn(),evidence:vi.fn(),review:vi.fn(),ack:vi.fn()}}))
vi.mock('../../services/api',()=>({api:{instruments:vi.fn()}}))
const id='11111111-1111-4111-8111-111111111111'
const candidate={id:'a'.repeat(24),type:'BSP' as const,startIndex:40,endIndex:40,direction:'UP' as const,startPrice:100,endPrice:100,revision:1,engineConfirmed:true,rawFlag:'CANDIDATE',firstObservedDate:'2026-10-30T09:00:00+08:00',engineConfirmedDate:null,eligibleAt:null,pivotStartDate:'date',pivotEndDate:'date',observedAsOfDate:'date',state:'CURRENT',signalType:'B3',eventSeq:21,eventType:'OBSERVED',observedIndex:49,evidence:{referenceLessons:[20]}}
function analysis(count:number){return {symbol:'FU2701',frequency:'MIN5' as const,profileHash:'profile',priceBasis:'UNADJUSTED_DELIVERY',observedBars:count,observedAsOfDate:`bar-${count}`,bars:Array.from({length:count},(_,index)=>({index,date:`day-${index}`,timestamp:'2026-10-30T09:00:00+08:00',contract:'FU2701',open:100,high:102,low:99,close:101,volume:10})),structures:[candidate]}}
function monitor():MonitorView{return {id,title:'测试监控',symbol:'FU2701',frequency:'MIN5',enabled:true,status:'CLOSED',observedBars:60,heartbeatAt:'2026-10-31',error:null,profileHash:'profile',source:{source:'TQSDK_PRIMARY_SERIAL',closeProof:'SUCCESSOR_OBSERVED'},analysis:analysis(60),events:[{eventSeq:21,payload:candidate,inboxState:'SUPPRESSED_BOOTSTRAP',detectedAt:'2026-10-31'}]}}
function evidence():MonitorEvidence{return {event:candidate,analysis:analysis(50),detectedAt:'2026-10-31',viewScope:'EVENT_CANDIDATE_ONLY'}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.resetAllMocks();vi.mocked(api.instruments).mockResolvedValue({source:'天勤',dataStatus:'FRESH',dataTimestamp:'now',exchanges:[{code:'SHFE',name:'上期所',instruments:[{exchange:'SHFE',exchangeName:'上期所',name:'燃油',node:'fu',rootSymbol:'FU',mainSymbol:'FUM',contracts:['FU2701']}]}]});vi.mocked(monitorApi.list).mockResolvedValue([monitor()]);vi.mocked(monitorApi.get).mockResolvedValue(monitor());vi.mocked(monitorApi.create).mockResolvedValue(monitor());vi.mocked(monitorApi.evidence).mockResolvedValue(evidence());vi.mocked(monitorApi.review).mockResolvedValue({id:'review'})})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function setup(path='/chanlun/radar'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/radar',component:RadarView},...['workbench','compare','replay','lab','academy','judgments','reviews','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div/>'}}))]})
  await router.push(path);await router.isReady();wrapper=mount(RadarView,{global:{plugins:[router],stubs:{TongdaxinChart:{props:['points','overlays'],template:'<div data-testid="chart" :data-count="points.length" />'},ChanlunReader:true}}});await flushPromises();return router
}
describe('persistent radar',()=>{
  it('does not auto-subscribe or run a calculation when the page opens',async()=>{await setup();expect(monitorApi.create).not.toHaveBeenCalled();expect(monitorApi.check).not.toHaveBeenCalled();expect(wrapper!.text()).toContain('关闭页面后仍运行')})
  it('creates an explicit primary contract and keeps the server task after page unmount',async()=>{await setup();await wrapper!.get('form.create').trigger('submit');await flushPromises();expect(monitorApi.create).toHaveBeenCalledWith(expect.objectContaining({symbol:'FU2701',frequency:'MIN5'}));wrapper!.unmount();wrapper=undefined;expect(monitorApi.control).not.toHaveBeenCalled()})
  it('uses the frozen event prefix for the chart and binds review to that event',async()=>{
    await setup(`/chanlun/radar?monitor=${id}&event=21`);expect(wrapper!.get('[data-testid=chart]').attributes('data-count')).toBe('50');expect(wrapper!.text()).toContain('历史初始化');await wrapper!.get('textarea').setValue('当时证据与失效条件');await wrapper!.get('form:not(.create)').trigger('submit');await flushPromises();expect(monitorApi.review).toHaveBeenCalledWith(id,21,expect.objectContaining({content:'当时证据与失效条件',lessonNumber:20}));expect(wrapper!.text()).toContain('复盘已保存')
  })
  it('does not reload immutable event evidence on a quiet heartbeat refresh',async()=>{
    await setup(`/chanlun/radar?monitor=${id}&event=21`);expect(monitorApi.evidence).toHaveBeenCalledTimes(1)
    await wrapper!.findAll('button').find(b=>b.text()==='刷新状态')!.trigger('click');await flushPromises()
    expect(monitorApi.get).toHaveBeenCalledTimes(2);expect(monitorApi.evidence).toHaveBeenCalledTimes(1)
  })
})
