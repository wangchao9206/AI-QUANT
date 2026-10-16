import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import IndicatorBarChart from './IndicatorBarChart.vue'
import type { Dimension } from '../services/api'

const mockDimensions: Dimension[] = [
  {
    key: 'momentum',
    name: '量价动能',
    score: 65,
    direction: 'BULLISH',
    confidence: 0.85,
    summary: '动量指标上扬',
    recommendation: '持有多头仓位',
    category: 'EMPIRICAL',
    dataStatus: 'FRESH',
    includedInScore: true,
    weight: 0.13,
    sourceName: '东方财富',
    sourceUrl: 'https://eastmoney.com',
    observedAt: '2026-10-15T08:00:00Z',
    sampleSize: 60,
    keyMetrics: { '5日动量': '+3.2%' },
  },
  {
    key: 'sentiment',
    name: '新闻舆情',
    score: -45,
    direction: 'BEARISH',
    confidence: 0.72,
    summary: '利空消息较多',
    recommendation: '防范短线回调',
    category: 'EMPIRICAL',
    dataStatus: 'FRESH',
    includedInScore: true,
    weight: 0.07,
    sourceName: '新浪新闻',
    sourceUrl: 'https://sina.com',
    observedAt: '2026-10-15T08:00:00Z',
    sampleSize: 30,
    keyMetrics: { '利空词频': '15' },
  },
]

const mockCultural: Dimension[] = [
  {
    key: 'liuyao',
    name: '六爻时历参考',
    score: 35,
    direction: 'BULLISH',
    confidence: 0.45,
    summary: '时间卦象偏吉',
    recommendation: '作氛围辅助参考',
    category: 'CULTURAL_REFERENCE',
    dataStatus: 'REFERENCE',
    includedInScore: true,
    weight: 0.03,
    sourceName: '中国传统历法',
    sourceUrl: '',
    observedAt: '2026-10-15T08:00:00Z',
    sampleSize: 1,
    keyMetrics: { '时间卦': '水天需' },
  },
]

describe('IndicatorBarChart', () => {
  it('renders multi-dimension bar chart with Chinese bullish/bearish summary', () => {
    const wrapper = mount(IndicatorBarChart, {
      props: {
        dimensions: mockDimensions,
        culturalDimensions: mockCultural,
      },
    })

    // Check Chinese sentiment camps
    expect(wrapper.text()).toContain('看多')
    expect(wrapper.text()).toContain('看空')
    expect(wrapper.text()).toContain('中性')

    // Check indicator labels
    expect(wrapper.text()).toContain('量价动能')
    expect(wrapper.text()).toContain('新闻舆情')
    expect(wrapper.text()).toContain('六爻时历')

    // Check scores rendered
    expect(wrapper.text()).toContain('+65')
    expect(wrapper.text()).toContain('-45')
  })

  it('supports filtering by empirical and cultural tabs', async () => {
    const wrapper = mount(IndicatorBarChart, {
      props: {
        dimensions: mockDimensions,
        culturalDimensions: mockCultural,
      },
    })

    const buttons = wrapper.findAll('.tab-btn')
    // Click cultural tab
    const culturalBtn = buttons.find((b) => b.text().includes('文化'))
    expect(culturalBtn).toBeDefined()
    await culturalBtn!.trigger('click')

    // Now only cultural is visible in list
    expect(wrapper.findAll('.bar-column')).toHaveLength(1)
    expect(wrapper.text()).toContain('六爻时历')
  })
})
