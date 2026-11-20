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
async function render(){
  const placeholder={template:'<div />'}
  const router=createRouter({history:createMemoryHistory(),routes:[
    {path:'/strategy',component:StrategyView},
    {path:'/strategy/self-developed-trinity',name:'personal-trinity',component:placeholder},
    {path:'/strategy/:symbol',component:placeholder},
    ...['/paper','/backtest','/backtest/ma20-macd','/research','/learn','/market'].map(path=>({path,component:placeholder})),
  ]})
  await router.push('/strategy')
  wrapper=mount(StrategyView,{global:{plugins:[router]}})
  await flushPromises()
  return router
}
describe('multi-product research entry',()=>{
  it('opens the editable personal strategy template from the catalog',async()=>{
    const router=await render()
    const card=wrapper!.get('.strategy-template-card')
    expect(card.get('h3').text()).toBe('自研道氏-威科夫-缠论三位一体')
    const editor=card.get('a')
    expect(editor.text()).toBe('编辑策略模板')
    await editor.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('personal-trinity')
  })
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
  it('links a minute strategy and a daily strategy to their corresponding backtest and simulation setup',async()=>{
    await render()
    const cards=wrapper!.findAll('.execution-catalog li')
    const minute=cards.find(card=>card.text().includes('1分钟MA20＋日线MACD'))!
    const daily=cards.find(card=>card.text().includes('Dual Thrust'))!
    expect(minute.findAll('a').map(a=>a.attributes('href'))).toEqual([
      '/backtest/ma20-macd','/paper?automation=MA20_MACD#paper-automation',
    ])
    expect(daily.findAll('a').map(a=>a.attributes('href'))).toEqual([
      '/backtest?strategy=DUAL_THRUST','/paper?automation=DUAL_THRUST#paper-automation',
    ])
  })
  it('keeps product discovery and method explanations usable if the scan fails',async()=>{
    vi.mocked(api.radarSignals).mockRejectedValueOnce(new Error('scan offline'))
    await render()
    expect(wrapper!.text()).toContain('scan offline')
    expect(wrapper!.findAll('.product-links a')).toHaveLength(2)
    expect(wrapper!.findAll('.method-grid button')).toHaveLength(3)
  })
})
