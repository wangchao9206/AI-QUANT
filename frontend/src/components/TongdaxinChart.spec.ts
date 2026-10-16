import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TongdaxinChart from './TongdaxinChart.vue'

describe('TongdaxinChart', () => {
  const mockPoints = Array.from({ length: 60 }, (_, i) => ({
    timestamp: `2026-08-${String((i % 28) + 1).padStart(2, '0')}T00:00:00Z`,
    price: 100 + (i % 10) * 2 - (i % 5) * 3,
    changePct: (i % 2 === 0 ? 1 : -1) * (1 + (i % 4)),
    open: 99 + (i % 10) * 2 - (i % 5) * 3,
    high: 103 + (i % 10) * 2 - (i % 5) * 3,
    low: 97 + (i % 10) * 2 - (i % 5) * 3,
    volume: 1000 + i,
  }))

  it('renders with accessibility, sub-chart and slider mini-map', () => {
    const wrapper = mount(TongdaxinChart, {
      props: {
        points: mockPoints,
        symbol: 'CJM',
        displayName: '红枣主力',
      },
    })

    expect(wrapper.get('.tdx-trading-chart').attributes('aria-label')).toBe('通达信交互式行情图表')
    expect(wrapper.text()).toContain('CJM')
    expect(wrapper.text()).toContain('红枣主力')
    expect(wrapper.text()).toContain('MACD')
    // 检查时间轴小地图
    expect(wrapper.find('.slider-map-layer').exists()).toBe(true)
    expect(wrapper.find('.slider-window').exists()).toBe(true)
  })

  it('switches sub-chart types to VOL and change% correctly', async () => {
    const wrapper = mount(TongdaxinChart, {
      props: {
        points: mockPoints,
        symbol: 'CJM',
        defaultSubChart: 'macd',
      },
    })

    // Click VOL button
    const volBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('VOL'))
    expect(volBtn).toBeDefined()
    await volBtn!.trigger('click')
    expect(wrapper.text()).toContain('VOL(5, 10)')

    // Click 涨跌柱 button
    const chgBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('涨跌柱'))
    expect(chgBtn).toBeDefined()
    await chgBtn!.trigger('click')
    expect(wrapper.text()).toContain('CHG%')
  })

  it('supports candle and line modes', async () => {
    const wrapper = mount(TongdaxinChart, {
      props: {
        points: mockPoints,
        defaultMainType: 'candle',
      },
    })

    expect(wrapper.findAll('.candle-item').length).toBeGreaterThan(0)

    const lineBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('分时线'))
    await lineBtn!.trigger('click')
    expect(wrapper.find('.trend-line').exists()).toBe(true)
  })

  it('does not fabricate candles or volume when OHLCV is missing', async () => {
    const closeOnlyPoints = mockPoints.map(({ open: _open, high: _high, low: _low, volume: _volume, ...point }) => point)
    const wrapper = mount(TongdaxinChart, {
      props: {
        points: closeOnlyPoints,
        defaultMainType: 'candle',
        defaultSubChart: 'vol',
      },
    })

    expect(wrapper.findAll('.candle-item')).toHaveLength(0)
    expect(wrapper.findAll('.sub-chart-layer rect')).toHaveLength(0)
    expect(wrapper.text()).toContain('VOL: —')
  })

  it('supports interactive operations: zoom in, zoom out, pan, and range presets', async () => {
    const wrapper = mount(TongdaxinChart, {
      props: {
        points: mockPoints,
      },
    })

    // 默认展示部分周期 (45根)
    expect(wrapper.text()).toContain('展现 45 / 60 根')

    // 点击放大按钮
    const zoomInBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('放大'))
    expect(zoomInBtn).toBeDefined()
    await zoomInBtn!.trigger('click')
    // 放大后展现根数应减少
    expect(wrapper.text()).not.toContain('展现 45 / 60 根')

    // 点击预设 "全部 (60)"
    const allBtn = wrapper.findAll('.preset-btn').find((b) => b.text().includes('全部'))
    expect(allBtn).toBeDefined()
    await allBtn!.trigger('click')
    expect(wrapper.text()).toContain('展现 60 / 60 根')

    // 点击预设 "近1月" (20日)
    const m1Btn = wrapper.findAll('.preset-btn').find((b) => b.text().includes('近1月'))
    expect(m1Btn).toBeDefined()
    await m1Btn!.trigger('click')
    expect(wrapper.text()).toContain('展现 20 / 60 根')

    // 点击往前翻 (看以前的行情)
    const prevBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('往前翻'))
    expect(prevBtn).toBeDefined()
    await prevBtn!.trigger('click')
    expect(wrapper.text()).toContain('展现 20 / 60 根')
    // 起始点应该往前移
    expect(wrapper.text()).toContain('第 26 ~ 45 周期')
  })
})
