import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMarketStore } from '../stores/market'
import InstrumentPicker from './InstrumentPicker.vue'

describe('InstrumentPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
  })

  it('searches the observed catalog and selects through the route and store', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/market', component: { template: '<div />' } }],
    })
    await router.push('/market?symbol=IFM')
    await router.isReady()
    const store = useMarketStore()
    store.symbol = 'IFM'
    store.catalog = {
      source: 'provider', dataStatus: 'FRESH', dataTimestamp: '2026-10-15T00:00:00Z',
      exchanges: [
        { code: 'CFFEX', name: '中国金融期货交易所', instruments: [{ exchange: 'CFFEX', exchangeName: '中国金融期货交易所', name: '沪深300股指', node: 'if', rootSymbol: 'IF', mainSymbol: 'IFM', contracts: ['IF2610'] }] },
        { code: 'SHFE', name: '上海期货交易所', instruments: [{ exchange: 'SHFE', exchangeName: '上海期货交易所', name: '螺纹钢', node: 'rb', rootSymbol: 'RB', mainSymbol: 'RBM', contracts: ['RB2701'] }] },
      ],
    }
    const load = vi.spyOn(store, 'load').mockResolvedValue()
    const wrapper = mount(InstrumentPicker, { global: { plugins: [router] } })

    await wrapper.get('.instrument-trigger').trigger('click')
    await wrapper.get('#global-instrument-search').setValue('螺纹')

    expect(wrapper.findAll('.picker-option')).toHaveLength(2)
    expect(wrapper.text()).toContain('RBM')
    expect(wrapper.text()).toContain('RB2701')

    await wrapper.findAll('.picker-option')[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.symbol).toBe('RB2701')
    expect(load).toHaveBeenCalledWith('RB2701')
    expect(wrapper.find('.picker-panel').exists()).toBe(false)
  })
})
