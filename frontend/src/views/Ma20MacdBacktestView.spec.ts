import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { request } from '../services/api'
import Ma20MacdBacktestView from './Ma20MacdBacktestView.vue'

vi.mock('../services/api', () => ({ request: vi.fn(), ApiError: Error }))

describe('MA20 MACD minute replay', () => {
  it('uses the verified contract and displays the engine’s result for the selected cost', async () => {
    vi.mocked(request).mockResolvedValue({
      symbol: 'FG701', scope: { first: '2026-10-19', last: '2026-11-16', scoreDays: 21 },
      metrics: { netPnl: 14, returnPct: .0014, maxDrawdownPct: .01, closedTrades: 0 }, trades: [],
    })
    const wrapper = mount(Ma20MacdBacktestView, { global: { stubs: { RouterLink: true } } })
    expect(request).not.toHaveBeenCalled()
    await wrapper.get('select').setValue(2)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(request).toHaveBeenCalledWith('/api/v1/research/ma20-macd/backtest', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ symbol: 'FG701', startDate: '2026-10-19', endDate: '2026-11-16', costMultiplier: 2 }),
    }), 60000)
    expect(wrapper.get('[aria-label="回测结果"]').text()).toContain('14.00 元')
    wrapper.unmount()
  })
})
