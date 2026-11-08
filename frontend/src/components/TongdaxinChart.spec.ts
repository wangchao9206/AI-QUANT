import { mount,flushPromises } from '@vue/test-utils'
import { beforeEach,afterEach,describe, expect, it,vi } from 'vitest'
import TongdaxinChart from './TongdaxinChart.vue'
import type { ChartTrade } from '../utils/paperChartTrades'
import {drawingStorageKey} from '../utils/chartDrawings'
import {authState} from '../services/auth'
import {privateDocumentCacheKey} from '../composables/usePrivateDocument'
const workspace=vi.hoisted(()=>({read:vi.fn(),write:vi.fn()}))
vi.mock('../services/workspace',async original=>({...await original<typeof import('../services/workspace')>(),workspaceApi:workspace}))

beforeEach(()=>{localStorage.clear();authState.user=null;vi.clearAllMocks();workspace.read.mockImplementation(async target=>({ownerId:'owner-a',tenantId:'tenant-a',kind:target.kind,key:target.key,revision:0,content:null}))})
afterEach(()=>{authState.user=null})

describe('TongdaxinChart', () => {
  it('restores cloud layout, retains unavailable anchors and never writes on mount',async()=>{
    authState.user={id:'owner-a',tenantId:'tenant-a',username:'fixture',email:null,platformAdmin:false,mustChangePassword:false,role:'MEMBER',tenants:[],permissions:['market.read']}
    const content={schemaVersion:1,layout:{theme:'light',mainType:'line',subChart:'vol',maPeriods:[20],autoGroups:[]},items:[{id:'off-window',kind:'HORIZONTAL',anchors:[{timestamp:'2025-01-01T00:00:00Z',price:3000}]}]}
    workspace.read.mockImplementation(async target=>({ownerId:'owner-a',tenantId:'tenant-a',kind:target.kind,key:target.key,revision:2,content}))
    const w=mount(TongdaxinChart,{props:{drawingTools:true,drawingKey:'RB2701-900',points:[{timestamp:'2026-11-06T00:00:00Z',price:3010,changePct:0}]}});await flushPromises()
    expect(w.get('[aria-label="显示 MA20 均线"]').element).toHaveProperty('checked',true);expect(w.get('[aria-label="显示 MA5 均线"]').element).toHaveProperty('checked',false)
    expect(w.findAll('.manual-drawing line')).toHaveLength(0);expect(w.text()).toContain('1 条画线的锚点已超出当前加载历史，记录仍保留')
    expect(JSON.parse(localStorage.getItem(privateDocumentCacheKey('owner-a','tenant-a','CHART:RB2701-900'))!).draft.items).toEqual(content.items);expect(workspace.write).not.toHaveBeenCalled();w.unmount()
  })
  it('keeps every original drawing when the 100 drawing limit is reached',async()=>{
    authState.user={id:'owner-a',tenantId:'tenant-a',username:'fixture',email:null,platformAdmin:false,mustChangePassword:false,role:'MEMBER',tenants:[],permissions:['market.read']}
    const timestamp='2026-11-06T00:00:00Z',items=Array.from({length:100},(_,i)=>({id:'old-'+i,kind:'HORIZONTAL',anchors:[{timestamp,price:3000+i}]}))
    workspace.read.mockImplementation(async target=>({ownerId:'owner-a',tenantId:'tenant-a',kind:target.kind,key:target.key,revision:1,content:{schemaVersion:1,layout:{theme:'dark',mainType:'candle',subChart:'vol',maPeriods:[20],autoGroups:[]},items}}))
    const w=mount(TongdaxinChart,{props:{drawingTools:true,drawingKey:'RB2701-900',points:[{timestamp,price:3010,changePct:0}]}});await flushPromises();await w.findAll('button').find(b=>b.text()==='水平线')!.trigger('click');await w.get('.tdx-trading-chart').trigger('keydown',{key:'ArrowLeft'});await w.get('.tdx-trading-chart').trigger('keydown',{key:'Enter'})
    expect(w.text()).toContain('不会自动删除旧画线');expect(w.findAll('.manual-drawing')).toHaveLength(100);expect(w.find('[data-drawing-id="old-0"]').exists()).toBe(true);expect(workspace.write).not.toHaveBeenCalled();w.unmount()
  })
  it('reveals an initially selected archived structure outside the default latest window',()=>{
    const points=Array.from({length:200},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,i+1)).toISOString(),price:100+i,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points,selectedOverlayId:'archived',overlays:[{id:'archived',type:'BI',startIndex:2,endIndex:10,startPrice:102,endPrice:110,engineConfirmed:false}]}})
    expect(w.find('.structure-selected').exists()).toBe(true);w.unmount()
  })
  it('displays frozen automatic lines without enabling manual drawing or editing',async()=>{
    const points=Array.from({length:30},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,i+1)).toISOString(),price:100+i,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points,drawingTools:false,readonlyGeometry:true,geometry:{version:'frozen',status:'READY',lines:[{id:'old',kind:'REGRESSION_CENTER',label:'原事件中线',startIndex:0,endIndex:29,startPrice:101,endPrice:128}]}}})
    expect(w.findAll('.automatic-geometry')).toHaveLength(1);expect(w.find('.drawing-controls').exists()).toBe(false);expect(w.findAll('.manual-drawing')).toHaveLength(0)
    await w.setProps({readonlyGeometry:false});expect(w.findAll('.automatic-geometry')).toHaveLength(0);w.unmount()
  })
  it('renders independently selectable automatic channels and their known-time evidence',async()=>{
    const points=Array.from({length:80},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,i+1)).toISOString(),price:100+i*.1,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points,drawingTools:true,drawingKey:'RB2701-900',geometry:{version:'test',status:'READY',asOf:points[78]!.timestamp,lines:[{id:'regression',kind:'REGRESSION_UPPER',label:'60柱回归上轨',startIndex:20,endIndex:79,startPrice:104,endPrice:108,knownAt:points[78]!.timestamp},{id:'support',kind:'TREND_SUPPORT',label:'已确认低点支撑斜线',startIndex:30,endIndex:79,startPrice:103,endPrice:107}]}}})
    expect(w.findAll('.automatic-geometry')).toHaveLength(2);expect(w.text()).toContain('可知时点')
    await w.get('[aria-label="显示自动回归通道"]').setValue(false);expect(w.findAll('.automatic-geometry')).toHaveLength(1)
    expect(w.text()).toContain('手动画线');w.unmount()
  })
  it('draws a channel with three clicks, keeps it on reload, isolates periods and supports undo',async()=>{
    authState.user={id:'owner-a',tenantId:'tenant-a',username:'fixture',email:null,platformAdmin:false,mustChangePassword:false,role:'MEMBER',tenants:[],permissions:['market.read']}
    const points=Array.from({length:30},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,i+1)).toISOString(),price:100+i,changePct:0}))
    const props={points,drawingTools:true,drawingKey:'RB2701-900',initialVisibleBars:30}
    const w=mount(TongdaxinChart,{props})
    const svg=w.get('.tdx-svg').element as SVGSVGElement
    Object.defineProperty(svg,'getBoundingClientRect',{value:()=>({left:0,top:0,width:800,height:440})})
    await w.findAll('button').find(b=>b.text()==='平行通道')!.trigger('click')
    for(const [clientX,clientY] of [[100,150],[250,110],[400,80]])await w.get('.tdx-canvas-wrapper').trigger('mousedown',{button:0,clientX,clientY})
    expect(w.findAll('.manual-drawing line')).toHaveLength(3)
    expect(JSON.parse(localStorage.getItem(privateDocumentCacheKey('owner-a','tenant-a','CHART:RB2701-900'))!).draft.items[0].anchors).toHaveLength(3);expect(localStorage.getItem(drawingStorageKey('RB2701-900'))).toBeNull()
    expect(w.classes()).not.toContain('is-dragging');w.unmount()
    const restored=mount(TongdaxinChart,{props});expect(restored.findAll('.manual-drawing line')).toHaveLength(3)
    await restored.setProps({drawingKey:'RB2701-DAY'});expect(restored.findAll('.manual-drawing')).toHaveLength(0)
    await restored.setProps({drawingKey:'RB2701-900'});expect(restored.findAll('.manual-drawing line')).toHaveLength(3)
    await restored.findAll('button').find(b=>b.text()==='撤销画线')!.trigger('click');expect(restored.findAll('.manual-drawing')).toHaveLength(0);restored.unmount()
  })
  it('cancels partial drawings with Escape and leaves pan mode available',async()=>{
    const points=Array.from({length:30},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,i+1)).toISOString(),price:100+i,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points,drawingTools:true,drawingKey:'test'}})
    Object.defineProperty(w.get('.tdx-svg').element,'getBoundingClientRect',{value:()=>({left:0,top:0,width:800,height:440})})
    await w.findAll('button').find(b=>b.text()==='两点斜线')!.trigger('click')
    await w.get('.tdx-canvas-wrapper').trigger('mousedown',{button:0,clientX:100,clientY:150})
    expect(w.text()).toContain('第 2 / 2 个锚点')
    await w.get('[role="region"]').trigger('keydown',{key:'Escape'})
    expect(w.findAll('button').find(b=>b.text()==='平移')!.attributes('aria-pressed')).toBe('true')
    expect(w.findAll('.manual-drawing')).toHaveLength(0);w.unmount()
  })
  it('includes the year in calendar and monthly axis labels',()=>{
    const w=mount(TongdaxinChart,{props:{points:[{timestamp:'2024-01-31T16:00:00Z',price:100,changePct:0}],timeLabelMode:'month'}})
    expect(w.get('.hud-time').text()).toBe('2024-02-01');expect(w.text()).toContain('2024-02');w.unmount()
  })
  it('renders five full-window averages and can hide individual overlays',async()=>{
    const points=Array.from({length:200},(_,i)=>({timestamp:new Date(Date.UTC(2025,0,i+1)).toISOString(),price:i+1,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points}})
    expect(w.get('[data-ma="180"].hud-ma').text()).toBe('MA180: 110.50')
    expect(w.get('path[data-ma="180"]').attributes('d')).not.toContain('NaN')
    await w.get('[aria-label="显示 MA180 均线"]').setValue(false)
    expect(w.find('path[data-ma="180"]').exists()).toBe(false)
    await w.setProps({points:points.slice(0,59)});expect(w.get('[data-ma="60"].hud-ma').text()).toBe('MA60: —');w.unmount()
  })
  it('keeps the inspected timestamps when a fixed-size live window rolls forward',async()=>{
    const points=Array.from({length:61},(_,i)=>({timestamp:new Date(Date.UTC(2026,10,6,2,i)).toISOString(),price:100+i,changePct:0}))
    const w=mount(TongdaxinChart,{props:{points:points.slice(0,60),initialVisibleBars:20,preserveViewportOnAppend:true}})
    await w.findAll('.ctrl-btn').find(b=>b.text().includes('往前翻'))!.trigger('click')
    await w.setProps({points:points.slice(1)});expect(w.text()).toContain('第 25 ~ 44 周期');w.unmount()
  })
  it('distinguishes small-period candle timestamps to the second in Shanghai time',()=>{
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp:'2026-11-06T02:00:15Z',price:100,changePct:0}],timeLabelMode:'datetime-seconds'}})
    expect(wrapper.get('.hud-time').text()).toBe('2026-11-06 10:00:15');wrapper.unmount()
  })
  it('keeps an inspected historical window on append and follows the tail only when already at the tail',async()=>{
    const points=Array.from({length:61},(_,i)=>({timestamp:new Date(Date.UTC(2026,9,30,1,i*5)).toISOString(),price:100+i,changePct:0}))
    const wrapper=mount(TongdaxinChart,{props:{points:points.slice(0,60),initialVisibleBars:20,preserveViewportOnAppend:true}})
    await wrapper.findAll('.ctrl-btn').find(b=>b.text().includes('往前翻'))!.trigger('click')
    expect(wrapper.text()).toContain('第 26 ~ 45 周期')
    await wrapper.setProps({points});expect(wrapper.text()).toContain('第 26 ~ 45 周期')
    wrapper.unmount()
    const tail=mount(TongdaxinChart,{props:{points:points.slice(0,60),initialVisibleBars:20,preserveViewportOnAppend:true}})
    await tail.setProps({points});expect(tail.text()).toContain('第 42 ~ 61 周期');expect(tail.text()).toContain('展现 20 / 61 根');tail.unmount()
  })
  it('shows Shanghai minute labels and links external and keyboard cursors without emitting a viewport loop',async()=>{
    const points=Array.from({length:5},(_,i)=>({timestamp:`2026-10-30T01:${String(i*5).padStart(2,'0')}:00Z`,price:100+i,changePct:0}))
    const wrapper=mount(TongdaxinChart,{props:{points,timeLabelMode:'datetime',externalCursorTimestamp:points[1]!.timestamp}})
    expect(wrapper.get('.hud-time').text()).toBe('2026-10-30 09:05')
    expect(wrapper.find('.crosshair-layer').exists()).toBe(true)
    await wrapper.get('[role=region]').trigger('keydown',{key:'ArrowRight'})
    expect(wrapper.emitted('cursorTimestamp')?.at(-1)).toEqual([points[2]!.timestamp])
    await wrapper.setProps({linkedViewport:{start:points[0]!.timestamp,end:points[1]!.timestamp}})
    expect(wrapper.emitted('viewportChange')).toBeUndefined()
    wrapper.unmount()
  })
  it('renders no future candles or overlays when an external window is older than available input',()=>{
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp:'2026-10-30T09:00:00+08:00',price:100,changePct:0}],linkedViewport:{start:'2026-10-29T00:00:00Z',end:'2026-10-29T01:00:00Z'},overlays:[{id:'p',type:'BI',startIndex:0,endIndex:0,startPrice:99,endPrice:101,engineConfirmed:true}]}})
    expect(wrapper.text()).toContain('没有已封存行情')
    expect(wrapper.find('.structure-overlay').exists()).toBe(false)
    expect(wrapper.find('.hud-time').exists()).toBe(false)
    wrapper.unmount()
  })
  it('draws an invalidated candidate as a selectable point rather than an invisible zero-length line',async()=>{
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp:'2026-10-27T00:00:00+08:00',price:100,open:99,high:101,low:98,changePct:1}],overlays:[{id:'candidate',type:'BSP',startIndex:0,endIndex:0,startPrice:99,endPrice:99,engineConfirmed:false,signalType:'B3',signalState:'INVALIDATED'}]}})
    expect(wrapper.get('.structure-bsp circle').attributes('fill')).toBe('none')
    expect(wrapper.get('.structure-point-label').text()).toBe('× B3')
    await wrapper.get('.structure-bsp').trigger('keydown.enter')
    expect(wrapper.emitted('selectStructure')?.[0]).toEqual(['candidate'])
    wrapper.unmount()
  })
  it('selects a structural overlay with the keyboard and keeps unavailable change data distinct from zero',async()=>{
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp:'2026-10-27T00:00:00+08:00',price:100,open:99,high:101,low:98,changePct:0,changePctKnown:false}],overlays:[{id:'bi',type:'BI',startIndex:0,endIndex:0,startPrice:98,endPrice:101,engineConfirmed:false}]}})
    await wrapper.get('.structure-overlay').trigger('keydown.enter')
    expect(wrapper.emitted('selectStructure')?.[0]).toEqual(['bi'])
    expect(wrapper.get('.hud-chg').text()).toBe('—')
    expect(wrapper.find('.structure-line').attributes('stroke-dasharray')).toBe('6 4')
    wrapper.unmount()
  })
  it('groups actual fills on a candle, exposes their reasons and prices, and supports hiding markers',async()=>{
    const timestamp='2025-01-02T00:00:00+08:00'
    const trade:ChartTrade={id:'buy',timestamp,marketTime:'2025-01-02T07:00:00Z',contract:'JM2701',eventType:'ORDER',side:'BUY',offset:'OPEN',quantity:1,marketPrice:100,fillPrice:103.5,fee:3,slippageCost:30,realizedPnl:0,reason:'放量突破策略开多'}
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp,contract:'JM2701',price:100,open:100,high:101,low:99,changePct:0}],trades:[trade,{...trade,id:'second'},{...trade,id:'sell',side:'SELL',offset:'CLOSE',fillPrice:98.5,reason:'策略ATR保护止损'}]}})
    expect(wrapper.findAll('.trade-marker')).toHaveLength(2)
    expect(wrapper.findAll('.trade-markers circle')).toHaveLength(3)
    expect(wrapper.text()).toContain('买开多×2')
    const y=Number(wrapper.get('.trade-markers circle').attributes('cy'))
    expect(y).toBeGreaterThan(26);expect(y).toBeLessThan(210)
    await wrapper.get('.trade-marker').trigger('keydown',{key:'Enter'})
    expect(wrapper.get('[aria-label="买卖点成交详情"]').text()).toContain('103.50')
    expect(wrapper.get('[aria-label="买卖点成交详情"]').text()).toContain('放量突破策略开多')
    await wrapper.findAll('.trade-marker')[1]!.trigger('click')
    expect(wrapper.get('[aria-label="买卖点成交详情"]').text()).toContain('卖平多')
    expect(wrapper.get('[aria-label="买卖点成交详情"]').text()).toContain('策略ATR保护止损')
    await wrapper.get('[aria-label="显示买卖点"]').setValue(false)
    expect(wrapper.findAll('.trade-marker')).toHaveLength(0)
    expect(wrapper.find('.trade-details').exists()).toBe(false)
    wrapper.unmount()
  })
  it('uses the Shanghai daily label for UTC observations and shows the actual contract',()=>{
    const wrapper=mount(TongdaxinChart,{props:{points:[{timestamp:'2025-01-01T16:00:00Z',price:9220,changePct:.1,open:9230,high:9300,low:9160,volume:100,contract:'CJ505'}]}})
    expect(wrapper.get('.hud-time').text()).toBe('2025-01-02')
    expect(wrapper.text()).toContain('合约 红枣505合约（CJ505）')
    expect(wrapper.text()).toContain('开 9,230.00')
    expect(wrapper.get('.hud-chg').text()).toBe('+0.10%')
    wrapper.unmount()
  })
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

    const lineBtn = wrapper.findAll('.ctrl-btn').find((b) => b.text().includes('收盘线'))
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
