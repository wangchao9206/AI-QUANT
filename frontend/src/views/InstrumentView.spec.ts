import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MarketView from './InstrumentView.vue'
import { useMarketStore } from '../stores/market'
import { api, type History, type Quote, type TermStructure } from '../services/api'

describe('InstrumentView', () => {
  let router: any

  beforeEach(async () => {
    vi.restoreAllMocks()
    const pinia = createPinia()
    setActivePinia(pinia)
    router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/market/:symbol', component: MarketView }],
    })
    await router.push('/market/CJ701')
    await router.isReady()
  })

  it('keeps the coking-coal ladder after navigating from main to delivery and another delivery', async () => {
    const store = useMarketStore()
    store.catalog = {exchanges: []} as any
    vi.spyOn(api, 'quote').mockImplementation(async symbol => ({symbol, displayName: '焦煤', price: 100,
      change: 0, changePct: 0, source: 'observed', dataStatus: 'CACHED', dataTimestamp: '2026-10-16T07:00:00Z'}) as Quote)
    vi.spyOn(api, 'history').mockImplementation(async symbol => ({symbol, points: [], dataStatus: 'CACHED', dataTimestamp: '2026-10-16T07:00:00Z'}) as unknown as History)
    const curve = vi.spyOn(api, 'termStructure').mockImplementation(async root => ({rootSymbol: root, dataStatus: 'CACHED', dataTimestamp: '2026-10-16T07:00:00Z',
      contracts: ['2701', '2705'].map(month => ({contract: root + month, price: 100, maturityDate: '2027-01-01'})),
    }) as TermStructure)
    await router.push('/market/JMM')
    const wrapper = mount(MarketView, {global: {plugins: [router]}})
    await flushPromises()
    await wrapper.findAll('.ladder-row')[0]!.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/market/JM2701')
    expect(curve).toHaveBeenLastCalledWith('JM')
    expect(wrapper.findAll('.contract-name').map(row => row.text())).toEqual(['JM2701', 'JM2705'])
    await wrapper.findAll('.ladder-row')[1]!.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/market/JM2705')
    expect(store.quote?.symbol).toBe('JM2705')
    wrapper.unmount()
  })

  it('renders contract ladder and allows clicking on contracts to switch display', async () => {
    const store = useMarketStore()
    store.symbol = 'CJ701'
    store.state = 'ready'
    store.quote = {
      symbol: 'CJ701',
      displayName: '红枣2701',
      price: 6470.0,
      change: 120.0,
      changePct: 1.89,
      source: 'TqSdk',
      dataStatus: 'FRESH',
      dataTimestamp: '2026-10-15T10:00:00Z',
    }
    store.history = {
      symbol: 'CJ701',
      seriesSymbol: 'CJ701',
      seriesType: 'CONTRACT',
      source: 'TQSDK',
      dataStatus: 'FRESH',
      dataTimestamp: '2026-10-15T10:00:00Z',
      points: [
        { timestamp: '2026-10-14T00:00:00Z', price: 6350, changePct: 0 },
        { timestamp: '2026-10-15T00:00:00Z', price: 6470, changePct: 1.89 },
      ],
    }
    store.termStructure = {
      rootSymbol: 'CJ',
      dataStatus: 'FRESH',
      dataTimestamp: '2026-10-15T10:00:00Z',
      contracts: [
        { contract: 'CJ612', maturityDate: '2026-12-01', price: 6290.0 },
        { contract: 'CJ701', maturityDate: '2027-01-01', price: 6470.0 },
        { contract: 'CJ703', maturityDate: '2027-03-01', price: 6510.0 },
      ],
    }

    const loadSpy = vi.spyOn(store, 'loadMarket').mockResolvedValue()

    const wrapper = mount(MarketView, {
      global: {
        plugins: [router],
      },
    })

    // 验证合约梯度表格渲染
    const rows = wrapper.findAll('.ladder-row')
    expect(rows).toHaveLength(3)

    // 验证当前选中合约高亮状态 (CJ701 为当前展示中)
    const activeRow = wrapper.find('.ladder-row.is-active')
    expect(activeRow.exists()).toBe(true)
    expect(activeRow.text()).toContain('CJ701')
    expect(activeRow.text()).toContain('展示中')

    // 点击未选中的 CJ703 合约行
    const cj703Row = rows.find((r) => r.text().includes('CJ703'))
    expect(cj703Row).toBeDefined()
    await cj703Row!.trigger('click')
    await flushPromises()

    // 验证触发了 store.load('CJ703')
    expect(loadSpy).toHaveBeenCalledWith('CJ703')
  })
})
