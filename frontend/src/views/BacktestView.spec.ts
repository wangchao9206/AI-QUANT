import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import BacktestView from './BacktestView.vue'
import { api } from '../services/api'

vi.mock('../services/api', () => ({
  api: {
    backtestPresets: vi.fn(),
    replayStatus: vi.fn(),
    runBacktest: vi.fn(),
    validation: vi.fn(),
  },
}))

describe('BacktestView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.validation).mockResolvedValue({status:'NOT_RUN',profitabilityValidated:false,strategies:[]})
    vi.mocked(api.backtestPresets).mockResolvedValue({
      strategies: [
        {
          id: 'BOLLINGER_REVERSAL',
          name: '布林带自适应均值回归',
          description: '测试布林策略',
          bestFor: ['CJ0'],
          recommendedParams: { positionPct: 25, stopLossAtr: 2.0, takeProfitAtr: 2.5, leverage: 1.8 },
        },
        {
          id: 'MOMENTUM_BREAKOUT',
          name: '唐奇安通道放量突破',
          description: '测试动量策略',
          bestFor: ['RB0'],
          recommendedParams: { positionPct: 30, stopLossAtr: 2.0, takeProfitAtr: 4.0, leverage: 2.0 },
        },
      ],
      symbols: [
        { symbol: 'CJ0', name: '红枣主连', exchange: 'CZCE', sector: '农产品' },
        { symbol: 'RB0', name: '螺纹钢主连', exchange: 'SHFE', sector: '黑色建材' },
      ],
      defaultParams: {
        initialCapital: 1000000,
        positionPct: 25,
        feeRate: 0.0001,
        slippage: 1.0,
        stopLossAtr: 2.0,
        takeProfitAtr: 2.5,
        marginRate: 0.12,
        leverage: 1.8,
      },
    })

    vi.mocked(api.replayStatus).mockResolvedValue({
      totalSymbols: 1,
      source: 'OBSERVED_DELIVERY_CONTRACT',
      message: '真实合约历史',
      symbols: [
        {
          symbol: 'CJ0',
          displayName: '红枣主连',
          source: 'TQSDK_REAL_DOMINANT_DAILY',
          totalBars: 1806,
          startDate: '2019-05-06',
          endDate: '2026-10-15',
          generatedAt: '2026-10-15T00:00:00Z',
        },
      ],
    })

    vi.mocked(api.runBacktest).mockResolvedValue({
      strategyName: '布林带自适应均值回归',
      symbol: 'CJ0',
      dataSource: 'TQSDK_REAL_DOMINANT_DAILY',
      dataTimestamp: '2026-10-15T16:00:00+08:00',
      providerSymbol: 'KQ.m@CZCE.CJ',
      initialCapital: 1000000,
      finalEquity: 2663300,
      effectiveLeverage: 1.8,
      totalReturnPct: 166.33,
      annualizedReturnPct: 14.7,
      benchmarkReturnPct: -35.94,
      alphaPct: 202.27,
      maxDrawdownPct: 39.41,
      maxDrawdownDays: 85,
      sharpeRatio: 1.25,
      sortinoRatio: 1.82,
      calmarRatio: 0.37,
      totalTrades: 74,
      winningTrades: 50,
      losingTrades: 24,
      winRate: 67.6,
      profitLossRatio: 2.31,
      avgTradePnl: 22477.0,
      avgHoldBars: 11.2,
      dailyEquity: [
        { date: '2019-05-06', equity: 1000000, benchmarkEquity: 1000000, cash: 1000000, positionPct: 0, dailyReturnPct: 0, drawdownPct: 0 },
        { date: '2019-05-07', equity: 1020000, benchmarkEquity: 995000, cash: 750000, positionPct: 25, dailyReturnPct: 2.0, drawdownPct: 0 },
      ],
      tradeLogs: [
        { timestamp: '2019-06-05', action: 'OPEN_BUY', price: 8900, positionPct: 25, pnl: 0, returnPct: 0, reason: '触及布林下轨', holdBars: 0 },
        { timestamp: '2019-06-15', action: 'FLATTEN_LONG', price: 9400, positionPct: 0, pnl: 85000, returnPct: 9.4, reason: '回归布林中轨', holdBars: 8 },
      ],
    })
  })

  it('does not auto-run and labels results as historical simulation', async () => {
    const wrapper = mount(BacktestView)
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(wrapper.text()).toContain('量化回测与模拟交易引擎')
    expect(wrapper.text()).toContain('策略适配提示')
    expect(wrapper.text()).toContain('结果不代表实盘收益')
    expect(wrapper.text()).not.toContain('实盘最优策略推荐')
    expect(api.runBacktest).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('真实合约历史已就绪：1 品种')

    await wrapper.get('.btn-run').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(wrapper.text()).toContain('+166.33%')
    expect(wrapper.text()).toContain('67.6%')
    expect(wrapper.text()).toContain('1.8x')
  })

  it('keeps the executed parameters frozen for doubled costs after editing the form',async()=>{
    const wrapper=mount(BacktestView)
    await new Promise(resolve=>setTimeout(resolve,30))
    await wrapper.get('.btn-run').trigger('click')
    await new Promise(resolve=>setTimeout(resolve,20))
    await wrapper.findAll('.form-select')[0]!.setValue('RB0')
    expect((wrapper.findAll('.form-select')[1]!.element as HTMLSelectElement).value).toBe('BOLLINGER_REVERSAL')
    await wrapper.get('.robustness-panel button').trigger('click')
    await new Promise(resolve=>setTimeout(resolve,20))
    expect(api.runBacktest).toHaveBeenLastCalledWith(expect.objectContaining({symbol:'CJ0',strategy:'BOLLINGER_REVERSAL',costMultiplier:2}))
    expect(wrapper.text()).toContain('双倍成本区间收益')
  })
})
