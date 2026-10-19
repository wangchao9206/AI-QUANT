import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createPinia} from 'pinia'
import {createMemoryHistory,createRouter} from 'vue-router'
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest'
import OverviewView from './OverviewView.vue'
import {api} from '../services/api'
import {useMarketStore} from '../stores/market'

vi.mock('../services/api',()=>({api:{radarMarket:vi.fn(),radarNews:vi.fn(),radarSignals:vi.fn(),radarOverseas:vi.fn(),leads:vi.fn(),instruments:vi.fn()}}))
const time='2026-10-16T15:00:00+08:00'
const heat={status:'READY' as const,dataTimestamp:time,source:'observed',catalogCount:2,observedCount:2,missingCount:0,connected:true,breadth:{up:1,down:1,flat:0},sectors:[{name:'黑色金属',count:1,up:1,down:0,averageChange:2},{name:'农产品',count:1,up:0,down:1,averageChange:-3}],items:[
  {symbol:'RBM',name:'螺纹钢',exchange:'SHFE',sector:'黑色金属',contract:'RB2701',price:3200,changePct:2,volume:1000,openInterest:100,dataTimestamp:time,dataStatus:'CACHED' as const},
  {symbol:'MM',name:'豆粕',exchange:'DCE',sector:'农产品',contract:'M2701',price:2800,changePct:-3,volume:2000,openInterest:100,dataTimestamp:time,dataStatus:'CACHED' as const}]}
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
  vi.mocked(api.radarMarket).mockResolvedValue(structuredClone(heat))
  vi.mocked(api.radarNews).mockResolvedValue({status:'READY',dataTimestamp:time,items:[{id:'n1',title:'全市场新闻事件',summary:'原文摘要',url:'https://example.com/news',publisher:'source',publishedAt:time,relatedSymbols:['MM'],topic:'产业资讯'}]})
  vi.mocked(api.radarSignals).mockResolvedValue({status:'READY',dataTimestamp:time,scannedCount:2,universeCount:2,missingCount:0,items:[],groups:[{id:'DUAL_THRUST',name:'Dual Thrust',rule:'真实条件',matched:0,long:0,short:0}]})
  vi.mocked(api.radarOverseas).mockResolvedValue({status:'READY',dataTimestamp:time,items:[{symbol:'GC',name:'纽约黄金 CFD',price:4000,changePct:1,unit:'美元/盎司',sector:'贵金属',dataTimestamp:time,dataStatus:'CACHED',relatedSymbols:['AUM'],sourceUrl:'https://finance.sina.com.cn/futures/quotes/GC.shtml'}]})
  vi.mocked(api.leads).mockResolvedValue({source:'test',dataStatus:'CACHED',scannedCount:9,leadsCount:0,dataTimestamp:time,leads:[]})
  vi.mocked(api.instruments).mockResolvedValue({source:'test',dataStatus:'CACHED',dataTimestamp:time,exchanges:[]})
})
afterEach(()=>wrapper?.unmount())
async function render(){
  const pinia=createPinia()
  const store=useMarketStore(pinia)
  const singleLoad=vi.spyOn(store,'load')
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/overview',component:OverviewView},{path:'/market',component:{template:'<div>行情详情</div>'}},{path:'/strategy',component:{template:'<div>计划</div>'}},{path:'/leads',component:{template:'<div>线索池</div>'}},{path:'/backtest',component:{template:'<div>回测</div>'}}]})
  await router.push('/overview?symbol=CJM');await router.isReady()
  wrapper=mount(OverviewView,{global:{plugins:[pinia,router]}});await flushPromises()
  return {singleLoad,router}
}
describe('cross-market overview',()=>{
  it('loads five independent radars without a selected-product dashboard',async()=>{
    const {singleLoad}=await render()
    for(const title of ['热门品种','新闻雷达','线索雷达','策略雷达','外盘雷达'])expect(wrapper!.findAll('h2').some(h=>h.text()===title)).toBe(true)
    expect(singleLoad).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('纽约黄金 CFD')
    expect(wrapper!.text()).toContain('全市场新闻事件')
    expect(wrapper!.findAll('.heat-card')).toHaveLength(2)
    expect(wrapper!.findAll('.heat-card')[0]!.text()).toContain('豆粕')
    expect(wrapper!.findAll('.heat-card')[0]!.attributes('href')).toBe('/market/MM')
  })
  it('keeps other radars usable when news fails and retries only news',async()=>{
    vi.mocked(api.radarNews).mockRejectedValueOnce(new Error('新闻源暂不可用'))
    await render()
    expect(wrapper!.get('#news').text()).toContain('新闻源暂不可用')
    expect(wrapper!.findAll('.heat-card')).toHaveLength(2)
    expect(wrapper!.get('#overseas').text()).toContain('纽约黄金 CFD')
    const attempts=vi.mocked(api.radarMarket).mock.calls.length
    await wrapper!.get('#news .module-error button').trigger('click');await flushPromises()
    expect(wrapper!.get('#news').text()).toContain('全市场新闻事件')
    expect(api.radarMarket).toHaveBeenCalledTimes(attempts)
  })
  it('sorts movers and filters the heat board without changing other radars',async()=>{
    await render()
    const gain=wrapper!.findAll('.segmented button').find(b=>b.text()==='涨幅榜')!
    await gain.trigger('click')
    expect(wrapper!.findAll('.heat-card')[0]!.text()).toContain('螺纹钢')
    await wrapper!.get('select[aria-label="品种榜板块"]').setValue('农产品')
    expect(wrapper!.findAll('.heat-card')).toHaveLength(1)
    expect(wrapper!.get('#overseas').text()).toContain('纽约黄金 CFD')
    expect(api.radarSignals).toHaveBeenCalledTimes(1)
  })
  it('renders daily summary and premarket opportunities panels and navigation jumps',async()=>{
    await render()
    expect(wrapper!.find('#summary').exists()).toBe(true)
    expect(wrapper!.find('#premarket').exists()).toBe(true)
    expect(wrapper!.get('#summary').text()).toContain('每日总结')
    expect(wrapper!.get('#premarket').text()).toContain('盘前机会')
    expect(wrapper!.get('#summary').text()).toContain('结构分化 · 震荡博弈')
    expect(wrapper!.get('#summary').text()).toContain('最强领涨板块')
    expect(wrapper!.get('#summary').text()).toContain('全市场成交前三')
    expect(wrapper!.get('#premarket').text()).toContain('外盘隔夜催化与境内跳空预警')
    expect(wrapper!.get('#premarket').text()).toContain('盘前交易三步法操作纪律')
    const jumps=wrapper!.findAll('.radar-jumps a')
    expect(jumps.some(a=>a.attributes('href')==='#summary'&&a.text().includes('每日总结'))).toBe(true)
    expect(jumps.some(a=>a.attributes('href')==='#premarket'&&a.text().includes('盘前机会'))).toBe(true)
  })
})
