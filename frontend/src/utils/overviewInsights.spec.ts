import { describe, expect, it } from 'vitest'
import { computeDailySummary, computePreMarketOpportunities } from './overviewInsights'
import type { MarketRadar, NewsRadar, SignalRadar, OverseasRadar } from '../types/radar'
import type { LeadsResponse } from '../services/api'

describe('overviewInsights', () => {
  const mockMarket: MarketRadar = {
    status: 'READY',
    dataTimestamp: '2026-10-19T15:00:00+08:00',
    catalogCount: 3,
    observedCount: 3,
    missingCount: 0,
    connected: true,
    breadth: { up: 2, down: 1, flat: 0 },
    sectors: [
      { name: '有色金属', count: 1, up: 1, down: 0, averageChange: 2.8 },
      { name: '黑色建材', count: 1, up: 1, down: 0, averageChange: 0.5 },
      { name: '农产品', count: 1, up: 0, down: 1, averageChange: -1.2 },
    ],
    items: [
      {
        symbol: 'CUM',
        name: '沪铜',
        exchange: 'SHFE',
        sector: '有色金属',
        contract: 'CU2701',
        price: 78000,
        changePct: 2.8,
        volume: 50000,
        openInterest: 20000,
        dataTimestamp: '2026-10-19T15:00:00+08:00',
        dataStatus: 'CACHED',
      },
      {
        symbol: 'RBM',
        name: '螺纹钢',
        exchange: 'SHFE',
        sector: '黑色建材',
        contract: 'RB2701',
        price: 3300,
        changePct: 0.5,
        volume: 120000,
        openInterest: 50000,
        dataTimestamp: '2026-10-19T15:00:00+08:00',
        dataStatus: 'CACHED',
      },
      {
        symbol: 'MM',
        name: '豆粕',
        exchange: 'DCE',
        sector: '农产品',
        contract: 'M2701',
        price: 2950,
        changePct: -1.2,
        volume: 80000,
        openInterest: 30000,
        dataTimestamp: '2026-10-19T15:00:00+08:00',
        dataStatus: 'CACHED',
      },
    ],
  }

  const mockNews: NewsRadar = {
    status: 'READY',
    dataTimestamp: '2026-10-19T15:00:00+08:00',
    items: [
      {
        id: 'n1',
        title: '央行降息释放长期流动性',
        summary: '加大宏观政策逆周期调节力度',
        url: 'https://example.com/macro',
        publisher: '官方通告',
        publishedAt: '2026-10-19T14:30:00+08:00',
        relatedSymbols: ['CUM', 'RBM'],
        topic: '宏观政策',
        sourceTier: 'PRIMARY',
      },
      {
        id: 'n2',
        title: '大豆进口通关提速',
        summary: '主要港口大豆到港增加',
        url: 'https://example.com/agri',
        publisher: '产业快讯',
        publishedAt: '2026-10-19T13:00:00+08:00',
        relatedSymbols: ['MM'],
        topic: '产业资讯',
        sourceTier: 'SECONDARY',
      },
    ],
  }

  describe('computeDailySummary', () => {
    it('handles empty or null data gracefully', () => {
      const summary = computeDailySummary(null, null, null)
      expect(summary.stance.sentiment).toBe('NEUTRAL')
      expect(summary.topSector).toBeNull()
      expect(summary.bottomSector).toBeNull()
      expect(summary.turnoverFocus).toHaveLength(0)
      expect(summary.macroHighlights).toHaveLength(0)
      expect(summary.riskAlerts).toHaveLength(0)
    })

    it('computes bullish stance when up ratio >= 60%', () => {
      const summary = computeDailySummary(mockMarket, mockNews, null)
      expect(summary.stance.sentiment).toBe('BULLISH')
      expect(summary.stance.up).toBe(2)
      expect(summary.stance.down).toBe(1)
      expect(summary.stance.upRatio).toBe(67)
      expect(summary.topSector?.name).toBe('有色金属')
      expect(summary.bottomSector?.name).toBe('农产品')
      expect(summary.turnoverFocus).toHaveLength(3)
      expect(summary.turnoverFocus[0].symbol).toBe('RBM') // 120000 volume
      expect(summary.macroHighlights).toHaveLength(2)
      expect(summary.macroHighlights[0].title).toBe('央行降息释放长期流动性')
      expect(summary.riskAlerts).toHaveLength(1) // CUM is 2.8% >= 2.5%
      expect(summary.riskAlerts[0].symbol).toBe('CUM')
    })
  })

  describe('computePreMarketOpportunities', () => {
    const mockOverseas: OverseasRadar = {
      status: 'READY',
      dataTimestamp: '2026-10-19T15:00:00+08:00',
      items: [
        {
          symbol: 'GC',
          name: '纽约黄金 CFD',
          price: 2750,
          changePct: 1.2,
          unit: '美元/盎司',
          sector: '贵金属',
          dataTimestamp: '2026-10-19T15:00:00+08:00',
          dataStatus: 'CACHED',
          relatedSymbols: ['AUM'],
          sourceUrl: 'https://finance.sina.com.cn/futures/quotes/GC.shtml',
        },
        {
          symbol: 'CL',
          name: 'NYMEX原油',
          price: 72.5,
          changePct: -0.8,
          unit: '美元/桶',
          sector: '能源化工',
          dataTimestamp: '2026-10-19T15:00:00+08:00',
          dataStatus: 'CACHED',
          relatedSymbols: ['SCM'],
          sourceUrl: 'https://finance.sina.com.cn/futures/quotes/CL.shtml',
        },
      ],
    }

    const mockSignals: SignalRadar = {
      status: 'READY',
      dataTimestamp: '2026-10-19T15:00:00+08:00',
      scannedCount: 3,
      universeCount: 3,
      missingCount: 0,
      groups: [],
      items: [
        {
          id: 'sig-1',
          strategy: 'DUAL_THRUST',
          signal: 'BUY',
          symbol: 'CUM',
          name: '沪铜',
          sector: '有色金属',
          close: 78000,
          changePct: 2.8,
          dataTimestamp: '2026-10-19T15:00:00+08:00',
          source: 'tqsdk',
          reason: '突破日线上轨 77,500',
          lower: 76000,
          upper: 77500,
        },
      ],
    }

    const mockLeads: LeadsResponse = {
      source: 'test',
      dataStatus: 'CACHED',
      scannedCount: 3,
      leadsCount: 1,
      dataTimestamp: '2026-10-19T15:00:00+08:00',
      leads: [
        {
          id: 'lead-1',
          symbol: 'CUM',
          displayName: '沪铜主力',
          exchange: 'SHFE',
          price: 78000,
          change: 2100,
          changePct: 2.8,
          direction: 'BULLISH',
          signal: 'BUY',
          urgency: 'S',
          compositeScore: 88,
          confidence: 0.9,
          algorithmType: 'ORDER_FLOW_IMBALANCE',
          algorithmName: '订单流失衡',
          algorithmBadge: '资金主动扫盘',
          analysis: {
            coreAnomaly: '多头主动大单吃单，买一量持续放大',
            marketContext: '外盘铜大幅走高共振',
            newsDriver: '宏观流动性宽松',
            keyEvidence: [],
          },
          execution: {
            actionDirective: '回踩77,600做多',
            entryZone: '77,600 - 77,800',
            targetPrice: 79500,
            stopLossPrice: 76800,
            recommendedPositionPct: 15,
            riskRewardRatio: '2.5:1',
            invalidationCondition: '跌破76,800支撑失效',
          },
          discoveredAt: '2026-10-19T15:00:00+08:00',
          dataStatus: 'CACHED',
        },
      ],
    }

    it('computes overseas gap expectations correctly', () => {
      const res = computePreMarketOpportunities(mockOverseas, null, null, mockMarket)
      expect(res.transmissions).toHaveLength(2)
      expect(res.transmissions[0].symbol).toBe('GC')
      expect(res.transmissions[0].gapExpectation).toBe('GAP_UP')
      expect(res.transmissions[0].expectationText).toBe('偏高开预警')
      expect(res.transmissions[1].symbol).toBe('CL')
      expect(res.transmissions[1].gapExpectation).toBe('GAP_DOWN')
      expect(res.transmissions[1].expectationText).toBe('偏低开预警')
    })

    it('identifies strategy and lead resonance for pre-market opportunities', () => {
      const res = computePreMarketOpportunities(mockOverseas, mockSignals, mockLeads, mockMarket)
      expect(res.opportunities.length).toBeGreaterThan(0)
      const resonance = res.opportunities.find(o => o.symbol === 'CUM')
      expect(resonance).toBeDefined()
      expect(resonance?.badgeType).toBe('resonance')
      expect(resonance?.badgeText).toContain('共振')
      expect(resonance?.direction).toBe('BULLISH')
      expect(resonance?.catalyst).toContain('突破日线上轨')
      expect(resonance?.entryZone).toBe('77,600 - 77,800')
      expect(resonance?.stopLoss).toContain('76,800.00')
      expect(res.actionChecklist.length).toBe(4)
    })
  })
})
