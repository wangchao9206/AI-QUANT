import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LeadsView from './LeadsView.vue'
import { api, type LeadsResponse } from '../services/api'

const mockLeadsData: LeadsResponse = {
  source: 'AI-QUANT 智能线索雷达扫描引擎',
  dataStatus: 'FRESH',
  scannedCount: 6,
  leadsCount: 2,
  dataTimestamp: '2026-10-15T16:30:00Z',
  leads: [
    {
      id: 'lead-cjm-resonance',
      symbol: 'CJM',
      displayName: '红枣主力',
      exchange: 'CZCE',
      price: 6470.0,
      change: 120.0,
      changePct: 1.89,
      direction: 'BULLISH',
      signal: '十四维高确信度同向共振 · 强烈看多',
      urgency: 'S',
      compositeScore: 78.5,
      confidence: 0.88,
      algorithmType: 'DIMENSION_RESONANCE',
      algorithmName: '十四维全息多空共振算法',
      algorithmBadge: '十四维大共振',
      analysis: {
        coreAnomaly: '实证量价、基差与时历指标在林果板块形成强烈同向共振',
        marketContext: '主力合约放量冲破颈线位',
        newsDriver: '红枣主产区受极端霜冻预期影响，现货惜售挺价',
        keyEvidence: [
          {
            name: '量价动量',
            score: 85.0,
            direction: 'BULLISH',
            summary: '突破20日布林上轨',
          },
        ],
      },
      execution: {
        actionDirective: '顺势建多仓，等待回踩支撑确认',
        entryZone: '6,450.0 ~ 6,490.0',
        targetPrice: 6850.0,
        stopLossPrice: 6320.0,
        recommendedPositionPct: 25.0,
        riskRewardRatio: '3.6:1',
        invalidationCondition: '收盘跌破6320硬止损撤单',
      },
      discoveredAt: '2026-10-15T16:30:00Z',
      dataStatus: 'FRESH',
    },
    {
      id: 'lead-rbm-breakout',
      symbol: 'RBM',
      displayName: '螺纹钢主力',
      exchange: 'SHFE',
      price: 3320.0,
      change: -45.0,
      changePct: -1.34,
      direction: 'BEARISH',
      signal: '破位下行动能加剧 · 空头突破',
      urgency: 'A',
      compositeScore: -55.0,
      confidence: 0.79,
      algorithmType: 'MOMENTUM_BREAKOUT',
      algorithmName: '量价动能突破算法',
      algorithmBadge: '量价动能突破',
      analysis: {
        coreAnomaly: '放量跌破前期重要震荡平台下沿',
        marketContext: '持仓量激增伴随价格杀跌，空头主力增仓主动施压',
        newsDriver: '下游地产施工开工率不及预期，钢厂累库压力显现',
        keyEvidence: [],
      },
      execution: {
        actionDirective: '逢反弹轻仓试空',
        entryZone: '3,330.0 ~ 3,345.0',
        targetPrice: 3200.0,
        stopLossPrice: 3380.0,
        recommendedPositionPct: 15.0,
        riskRewardRatio: '2.5:1',
        invalidationCondition: '站回3380平台上方止损',
      },
      discoveredAt: '2026-10-15T16:30:00Z',
      dataStatus: 'FRESH',
    },
  ],
}

describe('LeadsView', () => {
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/leads', component: LeadsView },
        { path: '/market', component: { template: '<div>Market</div>' } },
        { path: '/strategy', component: { template: '<div>Strategy</div>' } },
      ],
    })
    await router.push('/leads')
    await router.isReady()
  })


  it('renders opportunity leads with detailed analysis and operations', async () => {
    vi.spyOn(api, 'leads').mockResolvedValue(mockLeadsData)

    const wrapper = mount(LeadsView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('智能线索池 · 品种机会推荐')
    expect(wrapper.text()).toContain('6 个品种')
    expect(wrapper.text()).toContain('2 条有效')

    const cards = wrapper.findAll('.lead-card')
    expect(cards).toHaveLength(2)

    // Check CJM card
    const firstCard = cards[0]
    expect(firstCard.text()).toContain('CJM')
    expect(firstCard.text()).toContain('红枣主力')
    expect(firstCard.text()).toContain('S 级机会')
    expect(firstCard.text()).toContain('十四维大共振')
    expect(firstCard.text()).toContain('6,450.0 ~ 6,490.0')
    expect(firstCard.text()).toContain('顺势建多仓')
    expect(firstCard.text()).toContain('3.6:1')
    expect(firstCard.text()).toContain('极端霜冻预期')

    // Check RBM card
    const secondCard = cards[1]
    expect(secondCard.text()).toContain('RBM')
    expect(secondCard.text()).toContain('螺纹钢主力')
    expect(secondCard.text()).toContain('A 级机会')
  })

  it('filters leads by direction and urgency', async () => {
    vi.spyOn(api, 'leads').mockResolvedValue(mockLeadsData)

    const wrapper = mount(LeadsView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    // Click bullish filter
    const bullButton = wrapper.find('.mini-tab.bull')
    await bullButton.trigger('click')

    const cardsAfterDirection = wrapper.findAll('.lead-card')
    expect(cardsAfterDirection).toHaveLength(1)
    expect(cardsAfterDirection[0].text()).toContain('CJM')

    // Click S-grade filter
    const sButton = wrapper.find('.mini-tab.s-tag')
    await sButton.trigger('click')

    const cardsAfterUrgency = wrapper.findAll('.lead-card')
    expect(cardsAfterUrgency).toHaveLength(1)
  })

  it('filters leads by algorithm type', async () => {
    vi.spyOn(api, 'leads').mockResolvedValue(mockLeadsData)

    const wrapper = mount(LeadsView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    // Select MOMENTUM_BREAKOUT
    const breakoutBtn = wrapper.findAll('.pill-tab').find((b) => b.text().includes('量价动能突破'))
    expect(breakoutBtn).toBeDefined()
    await breakoutBtn?.trigger('click')

    const cards = wrapper.findAll('.lead-card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('RBM')
  })
})
