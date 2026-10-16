import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MarketView from './MarketView.vue'
import { useMarketStore } from '../stores/market'

describe('MarketView', () => {
  let router: any

  beforeEach(async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/market', component: MarketView }],
    })
    await router.push('/market?symbol=CJ701')
    await router.isReady()
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

    const loadSpy = vi.spyOn(store, 'load').mockResolvedValue()

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
