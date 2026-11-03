import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import ReplayView from './ReplayView.vue'
import {replayApi,type ReplaySession} from './replay'
import {chanlunApi} from './api'
vi.mock('./replay',()=>({replayApi:{create:vi.fn(),view:vi.fn(),recent:vi.fn(),decide:vi.fn(),advance:vi.fn()}}))
vi.mock('./api',()=>({chanlunApi:{engines:vi.fn(),datasets:vi.fn(),create:vi.fn()}}))
const dataset={id:'fu-daily-2026-10-30',sha256:'frozen',symbol:'FU0',displayName:'燃油',frequency:'DAY',bars:1894,start:'2019-01-02',end:'2026-10-27',priceBasis:'forward-observed-roll-ratio-v1'}
const sessionId='11111111-1111-4111-8111-111111111111'
function view(step=0,decided=false):ReplaySession{
  const count=50+step
  return {id:sessionId,title:'我的逐根练习',engineId:'native',startBars:50,observedBars:count,step,status:'ACTIVE',error:null,decisionSubmitted:decided,decisions:[],analysis:{runId:`run-${step}`,engineId:'native',engineVersion:'aiquant-chan-v1',profileHash:'fixed-profile',profile:{parameters:{}},dataset,datasetHash:'frozen',observedBars:count,observedAsOfDate:`2019-03-${step+1}`,priceBasis:dataset.priceBasis,recordedAt:'2026-10-31T00:00:00Z',layers:['BI','ZONE','BSP'],counts:{},structures:[],bars:Array.from({length:count},(_,index)=>({index,date:`day-${index}`,timestamp:'2019-01-02T00:00:00+08:00',contract:'FU1905',open:100,high:102,low:98,close:100+index/100,volume:100}))}}
}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();vi.mocked(chanlunApi.engines).mockResolvedValue([{id:'native',name:'自研引擎',status:'AVAILABLE',layers:['BI','ZONE','BSP']}]);vi.mocked(chanlunApi.datasets).mockResolvedValue([dataset]);vi.mocked(replayApi.recent).mockResolvedValue([]);vi.mocked(replayApi.create).mockResolvedValue(view());vi.mocked(replayApi.view).mockResolvedValue(view());vi.mocked(replayApi.decide).mockResolvedValue(view(0,true));vi.mocked(replayApi.advance).mockResolvedValue(view(1))})
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function setup(path='/chanlun/replay'){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/chanlun/replay',component:ReplayView},...['workbench','compare','academy','judgments','settings'].map(tab=>({path:`/chanlun/${tab}`,component:{template:'<div>其他页面</div>'}}))]})
  await router.push(path);await router.isReady();wrapper=mount(ReplayView,{global:{plugins:[router],stubs:{TongdaxinChart:{props:['points','overlays'],template:'<div data-testid="training-chart" :data-bar-count="points.length" />'},ChanlunReader:true}}});await flushPromises();return {router,wrapper}
}
const button=(text:string)=>wrapper!.findAll('button').find(b=>b.text()===text)!
describe('server-controlled replay',()=>{
  it('does not preload a full research run before starting a practice',async()=>{await setup();expect(chanlunApi.create).not.toHaveBeenCalled();expect(replayApi.create).not.toHaveBeenCalled();expect(wrapper!.find('[data-testid="training-chart"]').exists()).toBe(false)})
  it('requires a persisted decision before advancing and renders only the returned prefix',async()=>{
    await setup();await wrapper!.get('input[type=number]').setValue(50);await button('开始练习').trigger('click');await flushPromises()
    expect(button('展开下一根').attributes('disabled')).toBeDefined()
    expect(wrapper!.get('[data-testid="training-chart"]').attributes('data-bar-count')).toBe('50')
    await wrapper!.get('textarea').setValue('等待回踩，触及边界则放弃。');await button('提交当时判断').trigger('click');await flushPromises()
    expect(replayApi.decide).toHaveBeenCalledWith(sessionId,expect.objectContaining({expectedStep:0,content:'等待回踩，触及边界则放弃。'}))
    expect(button('展开下一根').attributes('disabled')).toBeUndefined()
    await button('展开下一根').trigger('click');await flushPromises()
    expect(replayApi.advance).toHaveBeenCalledWith(sessionId,expect.objectContaining({expectedStep:0}))
    expect(wrapper!.text()).toContain('已观察 51 根')
    expect(wrapper!.get('[data-testid="training-chart"]').attributes('data-bar-count')).toBe('51')
    expect(button('展开下一根').attributes('disabled')).toBeDefined()
    expect(chanlunApi.create).not.toHaveBeenCalled()
  })
  it('restores the server step through the session URL without creating a new practice',async()=>{vi.mocked(replayApi.view).mockResolvedValue(view(3,true));await setup(`/chanlun/replay?session=${sessionId}`);expect(replayApi.view).toHaveBeenCalledWith(sessionId);expect(wrapper!.text()).toContain('已观察 53 根');expect(replayApi.create).not.toHaveBeenCalled();expect(chanlunApi.create).not.toHaveBeenCalled()})
  it('keeps the same command after an uncertain network response and recovers before retrying',async()=>{
    await setup();await wrapper!.get('input[type=number]').setValue(50);await button('开始练习').trigger('click');await flushPromises();await wrapper!.get('textarea').setValue('依据已记录');await button('提交当时判断').trigger('click');await flushPromises()
    vi.mocked(replayApi.advance).mockRejectedValueOnce(new Error('网络中断'))
    vi.mocked(replayApi.view).mockResolvedValueOnce(view(1))
    await button('展开下一根').trigger('click');await flushPromises()
    expect(wrapper!.text()).toContain('已观察 51 根');expect(button('展开下一根').attributes('disabled')).toBeDefined();expect(replayApi.advance).toHaveBeenCalledTimes(1)
  })
})
