import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import MarketView from './MarketView.vue'
import {api} from '../services/api'
import {useExperience} from '../composables/useExperience'
vi.mock('../services/api',()=>({api:{radarMarket:vi.fn(),radarOverseas:vi.fn(),instruments:vi.fn(),prediction:vi.fn()}}))
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks();localStorage.clear();useExperience().setMode('SIMPLE')
  vi.mocked(api.radarMarket).mockResolvedValue({status:'READY',connected:true,dataTimestamp:'2026-10-16T15:00:00+08:00',catalogCount:3,observedCount:2,missingCount:1,breadth:{up:1,down:1,flat:0},sectors:[],items:[
    {symbol:'RBM',name:'螺纹钢',exchange:'SHFE',sector:'黑色金属',contract:'RB2701',price:3200,changePct:2,volume:100,openInterest:50,dataStatus:'CACHED',dataTimestamp:'2026-10-16T15:00:00+08:00'},
    {symbol:'MM',name:'豆粕',exchange:'DCE',sector:'农产品',contract:'M2701',price:2800,changePct:-3,volume:200,openInterest:80,dataStatus:'CACHED',dataTimestamp:'2026-10-16T15:00:00+08:00'}]})
  vi.mocked(api.radarOverseas).mockResolvedValue({status:'READY',dataTimestamp:'2026-10-16T15:00:00+08:00',items:[]})
  vi.mocked(api.instruments).mockResolvedValue({source:'test',dataStatus:'CACHED',dataTimestamp:'2026-10-16T15:00:00+08:00',exchanges:[{code:'SHFE',name:'上期所',instruments:[{exchange:'SHFE',exchangeName:'上期所',name:'黄金',node:'au',rootSymbol:'AU',mainSymbol:'AUM',contracts:['AU2612']}]}]})
})
afterEach(()=>{wrapper?.unmount();useExperience().setMode('SIMPLE')})
async function render(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/market',component:MarketView},{path:'/market/:symbol',component:{template:'<div />'}}]});await router.push('/market');wrapper=mount(MarketView,{global:{plugins:[router]}});await flushPromises()}
describe('market browser',()=>{
  it('shows multiple products and keeps uncovered catalog products without invented prices',async()=>{
    await render()
    expect(wrapper!.findAll('.instrument-card')).toHaveLength(3)
    expect(wrapper!.findAll('.instrument-card')[0]!.text()).toContain('豆粕')
    expect(wrapper!.get('a[href="/market/AUM"]').text()).toContain('暂无有效报价')
    expect(api.prediction).not.toHaveBeenCalled()
    await wrapper!.get('input[aria-label="搜索品种"]').setValue('黄金')
    expect(wrapper!.findAll('.instrument-card')).toHaveLength(1)
  })
  it('filters by industry and persists a personal watch list across remounts',async()=>{
    await render()
    await wrapper!.get('select[aria-label="所属行业"]').setValue('黑色金属')
    expect(wrapper!.findAll('.instrument-card')).toHaveLength(1)
    await wrapper!.get('button[aria-label="关注螺纹钢"]').trigger('click')
    expect(JSON.parse(localStorage.getItem('aiquant.market-watch.v1')!)).toEqual(['RBM'])
    wrapper!.unmount();await render()
    await wrapper!.get('.watch-filter').trigger('click')
    expect(wrapper!.findAll('.instrument-card')).toHaveLength(1)
    expect(wrapper!.get('.instrument-card').text()).toContain('螺纹钢')
  })
  it('switches from readable cards to the full table when professional mode is selected',async()=>{
    await render();expect(wrapper!.find('.market-table').exists()).toBe(false)
    useExperience().setMode('PRO');await flushPromises()
    expect(wrapper!.findAll('.market-table tbody tr')).toHaveLength(3)
    expect(wrapper!.text()).toContain('持仓量（手）')
  })
})
