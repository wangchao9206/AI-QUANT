import {mount,flushPromises,type VueWrapper} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import StrategyView from './StrategyView.vue'
import {api} from '../services/api'
vi.mock('../services/api',()=>({api:{instruments:vi.fn(),radarSignals:vi.fn(),validation:vi.fn(),prediction:vi.fn()}}))
let wrapper:VueWrapper|undefined
beforeEach(()=>{
  vi.clearAllMocks()
  vi.mocked(api.instruments).mockResolvedValue({source:'observed',dataTimestamp:'2026-10-16',dataStatus:'CACHED',exchanges:[{code:'SHFE',name:'上期所',instruments:[{name:'黄金',rootSymbol:'AU',mainSymbol:'AUM',node:'au',exchange:'SHFE',exchangeName:'上期所',contracts:[]},{name:'螺纹钢',rootSymbol:'RB',mainSymbol:'RBM',node:'rb',exchange:'SHFE',exchangeName:'上期所',contracts:[]}]}]})
  vi.mocked(api.radarSignals).mockResolvedValue({status:'READY',dataTimestamp:'2026-10-16',scannedCount:2,universeCount:2,missingCount:0,groups:[],items:[{id:'one',strategy:'DUAL_THRUST',signal:'BUY',name:'黄金',symbol:'AUM',sector:'贵金属',close:100,changePct:1,dataTimestamp:'2026-10-16',source:'observed',reason:'observed boundary',lower:99,upper:101}]})
  vi.mocked(api.validation).mockRejectedValue(new Error('temporarily unavailable'))
})
afterEach(()=>wrapper?.unmount())
async function render(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/strategy',component:StrategyView},{path:'/strategy/:symbol',component:{template:'<div />'}}]});await router.push('/strategy');wrapper=mount(StrategyView,{global:{plugins:[router]}});await flushPromises()}
describe('multi-product research entry',()=>{
  it('offers product choices and filters observed conditions without running single-product predictions',async()=>{
    await render()
    expect(wrapper!.findAll('.product-links a')).toHaveLength(2)
    expect(wrapper!.get('.condition-list a').attributes('href')).toBe('/strategy/AUM')
    expect(api.prediction).not.toHaveBeenCalled()
    await wrapper!.findAll('.method-grid button')[0]!.trigger('click')
    expect(wrapper!.findAll('.condition-list a')).toHaveLength(0)
    expect(wrapper!.text()).toContain('当前没有满足所选规则的品种')
    await wrapper!.get('input').setValue('螺纹')
    expect(wrapper!.get('.product-links a').attributes('href')).toBe('/strategy/RBM')
    expect(wrapper!.get('.validation-note').text()).toContain('没有与模型版本一致')
  })
  it('keeps product discovery and method explanations usable if the scan fails',async()=>{
    vi.mocked(api.radarSignals).mockRejectedValueOnce(new Error('scan offline'))
    await render()
    expect(wrapper!.text()).toContain('scan offline')
    expect(wrapper!.findAll('.product-links a')).toHaveLength(2)
    expect(wrapper!.findAll('.method-grid button')).toHaveLength(3)
  })
})
