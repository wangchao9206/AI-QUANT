<script setup lang="ts">
import {instrumentLabel} from '../utils/instrumentNames'
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'
import {
  CandlestickChart,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  LineChart as LineChartIcon,
  Maximize2,
  Minimize2,
  Moon,
  RotateCcw,
  Sun,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'
import type { HistoryPoint } from '../services/api'
import {MA_PERIODS,MA_COLORS,movingAverages,type MaPeriod} from '../utils/movingAverages'
import { tradeLabel, type ChartTrade } from '../utils/paperChartTrades'
import type {ChartStructureOverlay} from '../utils/chartStructureOverlays'
import { formatNumber, formatPct, formatTradingDate,formatTradingDateTime } from '../utils/format'
import {lastTimeAtOrBefore,timeWindowIndices,type TimeWindow} from '../utils/chartTimeLink'
import {DRAWING_LABELS,DRAWING_POINTS,drawingSegments,drawingStorageKey,readDrawings,type ChartGeometry,type ChartDrawing,type DrawingAnchor,type DrawingKind} from '../utils/chartDrawings'

interface Props {
  points: HistoryPoint[]
  overlays?: ChartStructureOverlay[]
  selectedOverlayId?: string
  initialVisibleBars?: number
  timeLabelMode?:'date'|'datetime'|'datetime-seconds'|'calendar'|'month'
  externalCursorTimestamp?:string|null
  linkedViewport?:TimeWindow|null
  preserveViewportOnAppend?:boolean
  drawingTools?:boolean
  drawingKey?:string
  geometry?:ChartGeometry
  trades?: ChartTrade[]
  symbol?: string
  displayName?: string
  height?: number
  defaultSubChart?: 'vol' | 'macd' | 'change'
  defaultTheme?: 'dark' | 'light'
  defaultMainType?: 'candle' | 'line'
}

const props = withDefaults(defineProps<Props>(), {
  symbol: '',
  displayName: '行情走势',
  height: 440,
  defaultSubChart: 'macd',
  defaultTheme: 'dark',
  defaultMainType: 'candle',
  trades: () => [],
  overlays: () => [],
  initialVisibleBars:45,
  timeLabelMode:'date',
  drawingTools:false,
  drawingKey:'',
})
const emit=defineEmits<{selectStructure:[id:string];cursorTimestamp:[timestamp:string|null];viewportChange:[window:TimeWindow]}>()
const canvasContainer=ref<HTMLElement|null>(null)
const measuredWidth=ref(800)
const overlayClipId=`structure-${useId().replace(/:/g,'')}`
let resizeObserver:ResizeObserver|undefined
onMounted(()=>{
  if(typeof ResizeObserver==='undefined'||!canvasContainer.value)return
  resizeObserver=new ResizeObserver(entries=>{const next=entries[0]?.contentRect.width;if(next&&next>=240)measuredWidth.value=next})
  resizeObserver.observe(canvasContainer.value)
})
onUnmounted(()=>{resizeObserver?.disconnect();window.removeEventListener('mousemove',handleWindowMouseMove);window.removeEventListener('mouseup',handleWindowMouseUp)})

const showTrades = ref(true)
const enabledMa=ref<MaPeriod[]>([...MA_PERIODS])
const drawingMode=ref<'PAN'|DrawingKind>('PAN'),manualDrawings=ref<ChartDrawing[]>([]),drawingDraft=ref<DrawingAnchor[]>([]),drawingHover=ref<DrawingAnchor|null>(null),drawingNotice=ref('')
const autoGroups=ref(['REGRESSION','TREND','HORIZONTAL'])
const autoGroupLabels:Record<string,string>={REGRESSION:'回归通道',TREND:'趋势斜线',HORIZONTAL:'支撑阻力'}
const storedDrawingKey=computed(()=>props.drawingKey||props.symbol)
watch(storedDrawingKey,()=>{
  drawingDraft.value=[];drawingHover.value=null;drawingMode.value='PAN';drawingNotice.value=''
  if(!props.drawingTools||!storedDrawingKey.value){manualDrawings.value=[];return}
  try{manualDrawings.value=readDrawings(localStorage.getItem(drawingStorageKey(storedDrawingKey.value)))}catch{manualDrawings.value=[];drawingNotice.value='浏览器未允许读取画线记录。'}
},{immediate:true})
watch(manualDrawings,items=>{
  if(!props.drawingTools||!storedDrawingKey.value)return
  try{localStorage.setItem(drawingStorageKey(storedDrawingKey.value),JSON.stringify({version:1,items}))}catch{drawingNotice.value='画线已保留在当前页面，浏览器未允许本地保存。'}
},{deep:true})
function chooseDrawing(kind:'PAN'|DrawingKind){drawingMode.value=kind;drawingDraft.value=[];drawingHover.value=null;drawingNotice.value=''}
function cancelDrawing(){chooseDrawing('PAN');handleMouseLeave()}
function undoDrawing(){if(drawingDraft.value.length){drawingDraft.value=[];drawingHover.value=null}else manualDrawings.value=manualDrawings.value.slice(0,-1)}
function clearDrawings(){manualDrawings.value=[];drawingDraft.value=[];drawingHover.value=null}
const visibleMaPeriods=computed(()=>MA_PERIODS.filter(p=>enabledMa.value.includes(p)))
const selectedTradeKey = ref<string | null>(null)

// 看盘配置状态
const subChartType = ref<'vol' | 'macd' | 'change'>(props.defaultSubChart)
const mainChartType = ref<'candle' | 'line'>(props.defaultMainType)
const chartTheme = ref<'dark' | 'light'>(props.defaultTheme)
const isExpanded = ref(false)

// 视窗缩放与平移 (DataZoom / Viewport Window)
const rangeStart = ref(0)
const rangeEnd = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartRange = ref({ start: 0, end: 0 })
const hoverIndex = ref<number | null>(null) // 在当前可见序列中的索引

// 画布尺寸基准
const width = computed(()=>measuredWidth.value)
const chartLeft = 12
const chartRight = computed(()=>width.value-74)
const chartWidth = computed(()=>chartRight.value-chartLeft)
const mainTop = 26
const mainBottom = 210
const mainHeight = mainBottom - mainTop
const subTop = 236
const subBottom = 338
const subHeight = subBottom - subTop
const dateY = 354
// 底部 DataZoom 小地图导航条
const sliderTop = 368
const sliderBottom = 396
const sliderHeight = sliderBottom - sliderTop

// 基础数据点模型
interface BarItem {
  contract?: string
  index: number
  timestamp: string
  dateLabel: string
  fullDate: string
  price: number
  open: number
  high: number
  low: number
  close: number
  change: number
  changePct: number
  hasChangePct: boolean
  isUp: boolean
  hasOhlc: boolean
  hasVolume: boolean
  averages: Record<MaPeriod,number|null>
  vol: number
  volMa5: number
  volMa10: number
  dif: number
  dea: number
  macd: number
}

// 1. 在全量历史数据上计算所有技术指标 (确保均线和 MACD 在缩放平移时不发生断层失真)
const allComputedBars = computed<BarItem[]>(() => {
  const list = props.points
  if (!list || list.length === 0) return []

  const n = list.length
  // MACD 连续计算
  const k12 = 2 / (12 + 1)
  const k26 = 2 / (26 + 1)
  const k9 = 2 / (9 + 1)
  let prevEma12 = list[0].price
  let prevEma26 = list[0].price
  let prevDea = 0

  const difArr: number[] = []
  const deaArr: number[] = []
  const macdArr: number[] = []

  for (let i = 0; i < n; i++) {
    const p = list[i].price
    const ema12 = i === 0 ? p : p * k12 + prevEma12 * (1 - k12)
    const ema26 = i === 0 ? p : p * k26 + prevEma26 * (1 - k26)
    prevEma12 = ema12
    prevEma26 = ema26
    const d = ema12 - ema26
    difArr.push(d)

    const de = i === 0 ? d : d * k9 + prevDea * (1 - k9)
    prevDea = de
    deaArr.push(de)
    macdArr.push((d - de) * 2)
  }

  const rawBars: BarItem[] = []
  const averages=movingAverages(list.map(p=>p.price))
  for (let i = 0; i < n; i++) {
    const cur = list[i]
    const p = cur.price
    const chg = cur.changePct || 0
    const close = p
    const hasOhlc = [cur.open, cur.high, cur.low].every((value) => typeof value === 'number' && Number.isFinite(value))
    const open = hasOhlc ? Number(cur.open) : close
    const high = hasOhlc ? Number(cur.high) : close
    const low = hasOhlc ? Number(cur.low) : close
    const change = close - open
    const isUp = hasOhlc ? close >= open : chg >= 0

    const hasVolume = typeof cur.volume === 'number' && Number.isFinite(cur.volume) && cur.volume >= 0
    const vol = hasVolume ? Number(cur.volume) : 0
    const intraday=props.timeLabelMode==='datetime'||props.timeLabelMode==='datetime-seconds'
    const fullDate = intraday?formatTradingDateTime(cur.timestamp,props.timeLabelMode==='datetime-seconds'):formatTradingDate(cur.timestamp)
    const dateStr = intraday?fullDate.slice(11):props.timeLabelMode==='month'?fullDate.slice(0,7):props.timeLabelMode==='calendar'?fullDate:fullDate.slice(5, 10).replace('-', '/')

    rawBars.push({
      index: i,
      timestamp: cur.timestamp,
      contract: cur.contract,
      dateLabel: dateStr,
      fullDate,
      price: p,
      open,
      high,
      low,
      close,
      change,
      changePct: chg,
      hasChangePct: cur.changePctKnown!==false,
      isUp,
      hasOhlc,
      hasVolume,
      averages:Object.fromEntries(MA_PERIODS.map(period=>[period,averages[period][i]??null])) as Record<MaPeriod,number|null>,
      vol,
      volMa5: vol,
      volMa10: vol,
      dif: difArr[i],
      dea: deaArr[i],
      macd: macdArr[i],
    })
  }

  // 计算量均线
  for (let i = 0; i < n; i++) {
    const s5 = rawBars.slice(Math.max(0, i - 4), i + 1).filter((item) => item.hasVolume)
    rawBars[i].volMa5 = s5.length ? s5.reduce((sum, item) => sum + item.vol, 0) / s5.length : 0

    const s10 = rawBars.slice(Math.max(0, i - 9), i + 1).filter((item) => item.hasVolume)
    rawBars[i].volMa10 = s10.length ? s10.reduce((sum, item) => sum + item.vol, 0) / s10.length : 0
  }

  return rawBars
})

// 初始化视窗范围：默认显示近 45 根 K 线，保证每根柱子足够粗、清晰、易辨识
function initRange() {
  const total = allComputedBars.value.length
  if (total === 0) {
    rangeStart.value = 0
    rangeEnd.value = 0
    return
  }
  const defaultSpan = Math.min(total, props.initialVisibleBars)
  rangeStart.value = Math.max(0, total - defaultSpan)
  rangeEnd.value = total
}

watch(
  () => props.points,
  (next,prior) => {
    if(props.preserveViewportOnAppend&&prior?.length&&next.length&&next.some(p=>p.timestamp===prior.at(-1)?.timestamp)){
      const span=Math.max(1,rangeEnd.value-rangeStart.value)
      if(rangeEnd.value===prior.length){rangeEnd.value=next.length;rangeStart.value=Math.max(0,next.length-span)}
      else {
        const startTime=prior[rangeStart.value]?.timestamp
        const index=next.findIndex(p=>startTime!=null&&p.timestamp>=startTime)
        rangeStart.value=Math.max(0,Math.min(index<0?0:index,next.length-1))
        rangeEnd.value=Math.min(next.length,rangeStart.value+span)
      }
      return
    }
    initRange()
  },
  { immediate: true },
)
watch(()=>props.symbol,initRange)

onMounted(() => {
  if (rangeEnd.value === 0 && allComputedBars.value.length > 0) {
    initRange()
  }
})

// 2. 当前视窗内可见的数据点 (Visible Bars) 及其屏幕坐标映射
interface VisibleBar extends BarItem {
  x: number
}

const visibleBars = computed<VisibleBar[]>(() => {
  const all = allComputedBars.value
  if (!all.length) return []
  if(props.linkedViewport&&!timeWindowIndices(all,props.linkedViewport,b=>b.timestamp))return []
  const start = Math.max(0, Math.min(rangeStart.value, all.length - 1))
  const end = Math.max(start + 1, Math.min(rangeEnd.value, all.length))
  const slice = all.slice(start, end)
  const n = slice.length
  const dx = chartWidth.value / n

  return slice.map((item, idx) => ({
    ...item,
    x: chartLeft + (idx + 0.5) * dx,
  }))
})

let applyingExternalWindow=false
function setExternalRange(start:number,end:number){
  applyingExternalWindow=true;rangeStart.value=start;rangeEnd.value=end
  void nextTick(()=>{applyingExternalWindow=false})
}
watch([rangeStart,rangeEnd],()=>{
  if(applyingExternalWindow)return
  const bars=visibleBars.value
  if(bars.length)emit('viewportChange',{start:bars[0]!.timestamp,end:bars.at(-1)!.timestamp})
},{flush:'post'})
watch(()=>props.linkedViewport,value=>{
  if(!value)return
  const range=timeWindowIndices(allComputedBars.value,value,b=>b.timestamp)
  if(range)setExternalRange(range.start,range.end)
},{immediate:true})
watch(()=>props.externalCursorTimestamp,value=>{
  if(!value)return
  const index=lastTimeAtOrBefore(allComputedBars.value,value,b=>b.timestamp)
  if(index===null||index>=rangeStart.value&&index<rangeEnd.value)return
  const span=Math.max(1,rangeEnd.value-rangeStart.value),end=Math.min(allComputedBars.value.length,Math.max(span,index+Math.ceil(span/2)))
  setExternalRange(Math.max(0,end-span),end)
},{immediate:true})
const effectiveCursorIndex=computed(()=>{
  if(hoverIndex.value!==null)return hoverIndex.value
  return props.externalCursorTimestamp?lastTimeAtOrBefore(visibleBars.value,props.externalCursorTimestamp,b=>b.timestamp):null
})

// 当前可见柱体宽度
const barWidth = computed(() => {
  const n = visibleBars.value.length
  if (!n) return 6
  const dx = chartWidth.value / n
  return Math.max(2.5, Math.min(22, dx * 0.72))
})

// 3. 当前视窗的动态纵坐标自适应 (Auto-fit Price Scale)
// 随着用户缩放和平移，价格轴自动适应当前可见区域的最大值与最小值，确保波动细节清晰放大
const visiblePriceRange = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return { min: 0, max: 100, span: 100 }
  let minP = Math.min(...bars.map((b) => b.low))
  let maxP = Math.max(...bars.map((b) => b.high))
  for(const bar of bars)for(const period of visibleMaPeriods.value){const ma=bar.averages[period];if(ma!=null){minP=Math.min(minP,ma);maxP=Math.max(maxP,ma)}}
  if (showTrades.value) for (const trade of visibleTrades.value) {
    minP = Math.min(minP, trade.fillPrice)
    maxP = Math.max(maxP, trade.fillPrice)
  }
  const pad = (maxP - minP) * (showTrades.value && visibleTrades.value.length ? 0.25 : 0.06) || 1
  minP -= pad
  maxP += pad
  return { min: minP, max: maxP, span: maxP - minP }
})

const visibleTrades = computed(() => {
  const timestamps = new Set(visibleBars.value.map(b => b.timestamp))
  return props.trades.filter(t => timestamps.has(t.timestamp) && Number.isFinite(t.fillPrice) && t.fillPrice > 0)
})

const tradeGroups = computed(() => {
  const groups = new Map<string, {key:string;bar:VisibleBar;side:'BUY'|'SELL';fills:ChartTrade[]}>()
  const bars = new Map(visibleBars.value.map(b => [b.timestamp, b]))
  for (const trade of visibleTrades.value) {
    const key = `${trade.timestamp}:${trade.side}`, bar = bars.get(trade.timestamp)!
    const group = groups.get(key) ?? { key, bar, side:trade.side, fills:[] }
    group.fills.push(trade); groups.set(key, group)
  }
  return [...groups.values()].map(group => {
    const buy = group.side === 'BUY'
    const prices = group.fills.map(f => f.fillPrice)
    const anchor = buy ? Math.min(group.bar.low, ...prices) : Math.max(group.bar.high, ...prices)
    const y = Math.max(mainTop + 10, Math.min(mainBottom - 10, getY(anchor) + (buy ? 14 : -14)))
    const labels = new Set(group.fills.map(tradeLabel))
    const label = labels.size === 1 ? [...labels][0] : buy ? '买入' : '卖出'
    return {...group, y, label:label + (group.fills.length > 1 ? `×${group.fills.length}` : '')}
  })
})
const selectedTrade = computed(() => showTrades.value ? tradeGroups.value.find(g => g.key === selectedTradeKey.value) : undefined)
watch(() => props.trades, () => { selectedTradeKey.value = null })

function getY(price: number): number {
  const { min, span } = visiblePriceRange.value
  return mainBottom - ((price - min) / span) * mainHeight
}
const automaticLines=computed(()=>props.drawingTools?(props.geometry?.lines??[]).filter(line=>autoGroups.value.some(group=>line.kind.startsWith(group))&&[line.startIndex,line.endIndex,line.startPrice,line.endPrice].every(Number.isFinite)):[])
const automaticChannels=computed(()=>automaticLines.value.filter(line=>line.kind==='REGRESSION_UPPER').flatMap(upper=>{
  const lower=automaticLines.value.find(line=>line.kind==='REGRESSION_LOWER'&&line.startIndex===upper.startIndex&&line.endIndex===upper.endIndex)
  return lower?[{id:upper.id,upper,lower}]:[]
}))
const drawnLines=computed(()=>manualDrawings.value.map(item=>({item,segments:drawingSegments(item,props.points,props.points.length-1)})))
const hiddenDrawingCount=computed(()=>drawnLines.value.filter(d=>!d.segments.length).length)
const previewSegments=computed(()=>{
  if(drawingMode.value==='PAN'||!drawingDraft.value.length||!drawingHover.value)return []
  const anchors=[...drawingDraft.value,drawingHover.value]
  const kind=drawingMode.value==='CHANNEL'&&anchors.length<3?'LINE':drawingMode.value
  return drawingSegments({id:'preview',kind,anchors:anchors.slice(0,DRAWING_POINTS[kind])},props.points,props.points.length-1)
})
const drawingInstruction=computed(()=>drawingMode.value==='PAN'?'选择画线工具后，在主图点击锚点。':`${DRAWING_LABELS[drawingMode.value]}：请点击第 ${drawingDraft.value.length+1} / ${DRAWING_POINTS[drawingMode.value]} 个锚点，Esc 取消。`)
function eventAnchor(e:MouseEvent):DrawingAnchor|null{
  const svg=canvasContainer.value?.querySelector('svg');if(!svg)return null
  const rect=svg.getBoundingClientRect();if(!rect.width||!rect.height)return null
  const x=(e.clientX-rect.left)/rect.width*width.value,y=(e.clientY-rect.top)/rect.height*props.height
  if(x<chartLeft||x>chartRight.value||y<mainTop||y>mainBottom)return null
  const index=rangeStart.value+Math.floor((x-chartLeft)/chartWidth.value*Math.max(1,rangeEnd.value-rangeStart.value))
  const bar=props.points[Math.min(rangeEnd.value-1,index)];if(!bar)return null
  const price=visiblePriceRange.value.min+(mainBottom-y)/mainHeight*visiblePriceRange.value.span
  return Number.isFinite(price)&&price>0?{timestamp:bar.timestamp,price}:null
}
function addDrawingAnchor(anchor:DrawingAnchor){
  const kind=drawingMode.value;if(kind==='PAN')return
  if(drawingDraft.value.length===1&&kind!=='HORIZONTAL'&&drawingDraft.value[0]!.timestamp===anchor.timestamp){drawingNotice.value='第二个锚点请选择另一根 K 线。';return}
  drawingNotice.value='';drawingDraft.value=[...drawingDraft.value,anchor]
  if(drawingDraft.value.length===DRAWING_POINTS[kind]){
    manualDrawings.value=[...manualDrawings.value,{id:`drawing-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,kind,anchors:drawingDraft.value}].slice(-100)
    drawingDraft.value=[];drawingHover.value=null
  }
}
const visibleOverlays=computed(()=>visibleBars.value.length?props.overlays.filter(item=>item.endIndex>=rangeStart.value&&item.startIndex<rangeEnd.value):[])
function overlayX(index:number){return chartLeft+(index-rangeStart.value+.5)*chartWidth.value/Math.max(1,rangeEnd.value-rangeStart.value)}
watch(()=>props.selectedOverlayId,id=>{
  const item=props.overlays.find(s=>s.id===id)
  if(!item||item.startIndex>=rangeStart.value&&item.endIndex<rangeEnd.value)return
  const total=props.points.length,span=Math.min(total,Math.max(props.initialVisibleBars,item.endIndex-item.startIndex+9))
  rangeEnd.value=Math.min(total,item.endIndex+5);rangeStart.value=Math.max(0,rangeEnd.value-span)
})

// 可见区域最高点与最低点标注
const extremePoints = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return null
  let maxBar = bars[0]
  let minBar = bars[0]
  for (const b of bars) {
    if (b.high > maxBar.high) maxBar = b
    if (b.low < minBar.low) minBar = b
  }
  return {
    high: { x: maxBar.x, y: getY(maxBar.high), val: maxBar.high },
    low: { x: minBar.x, y: getY(minBar.low), val: minBar.low },
  }
})

// 主图线条 Points
const pricePolyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getY(b.price).toFixed(1)}`).join(' ')
})

const priceAreaPath = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return ''
  const first = bars[0]
  const last = bars[bars.length - 1]
  const linePoints = bars.map((b) => `L ${b.x.toFixed(1)} ${getY(b.price).toFixed(1)}`).join(' ')
  return `M ${first.x.toFixed(1)} ${mainBottom} ${linePoints} L ${last.x.toFixed(1)} ${mainBottom} Z`
})

const maPaths=computed(()=>visibleMaPeriods.value.map(period=>{
  let pen=false
  const path=visibleBars.value.map(bar=>{const value=bar.averages[period];if(value==null){pen=false;return ''}const command=pen?'L':'M';pen=true;return `${command}${bar.x.toFixed(1)},${getY(value).toFixed(1)}`}).join(' ')
  return {period,path}
}))

// 4. 副图指标在当前视窗内的自适应标尺
// (1) MACD
const macdMaxAbs = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return 1
  let max = 0.01
  for (const b of bars) {
    max = Math.max(max, Math.abs(b.dif), Math.abs(b.dea), Math.abs(b.macd))
  }
  return max * 1.15
})

const macdZeroY = subTop + subHeight / 2 // 287px

function getMacdY(val: number): number {
  const half = subHeight * 0.44
  return macdZeroY - (val / macdMaxAbs.value) * half
}

const difPolyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getMacdY(b.dif).toFixed(1)}`).join(' ')
})

const deaPolyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getMacdY(b.dea).toFixed(1)}`).join(' ')
})

// (2) VOL 成交量
const volMax = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return 1000
  let max = 1
  for (const b of bars) {
    max = Math.max(max, b.vol, b.volMa5, b.volMa10)
  }
  return max * 1.15
})

function getVolY(v: number): number {
  return subBottom - (v / volMax.value) * (subHeight * 0.92)
}

const volMa5Polyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getVolY(b.volMa5).toFixed(1)}`).join(' ')
})

const volMa10Polyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getVolY(b.volMa10).toFixed(1)}`).join(' ')
})

// (3) 涨跌幅柱状图
const chgMaxAbs = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return 2
  let max = 0.5
  for (const b of bars) {
    if(b.hasChangePct)max = Math.max(max, Math.abs(b.changePct))
  }
  return max * 1.2
})

function getChgY(c: number): number {
  const half = subHeight * 0.44
  return macdZeroY - (c / chgMaxAbs.value) * half
}

// 5. 底部 DataZoom 迷你时间轴全览小地图 (Mini-map)
const totalBarsCount = computed(() => allComputedBars.value.length)

const miniPricePolyline = computed(() => {
  const all = allComputedBars.value
  if (!all.length) return ''
  const minP = Math.min(...all.map((b) => b.price))
  const maxP = Math.max(...all.map((b) => b.price))
  const spanP = maxP - minP || 1
  const n = all.length
  return all
    .map((b, i) => {
      const x = chartLeft + (i / Math.max(n - 1, 1)) * chartWidth.value
      const y = sliderBottom - 4 - ((b.price - minP) / spanP) * (sliderHeight - 8)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

// 视窗在小地图滑块中的高亮框位置
const sliderWindowRect = computed(() => {
  const total = totalBarsCount.value
  if (!total) return { x: chartLeft, width: chartWidth.value }
  const x = chartLeft + (rangeStart.value / total) * chartWidth.value
  const w = ((rangeEnd.value - rangeStart.value) / total) * chartWidth.value
  return { x: Math.max(chartLeft, x), width: Math.max(8, w) }
})

// 6. 交互操作函数：缩放、平移、预设范围
function zoom(factor: number, focalRatio = 0.5) {
  const total = totalBarsCount.value
  if (total <= 10) return

  const curSpan = rangeEnd.value - rangeStart.value
  const newSpan = Math.round(curSpan * factor)
  const clampedSpan = Math.max(10, Math.min(total, newSpan))
  const deltaSpan = clampedSpan - curSpan

  let newStart = Math.round(rangeStart.value - deltaSpan * focalRatio)
  let newEnd = newStart + clampedSpan

  if (newStart < 0) {
    newStart = 0
    newEnd = clampedSpan
  } else if (newEnd > total) {
    newEnd = total
    newStart = Math.max(0, total - clampedSpan)
  }

  rangeStart.value = newStart
  rangeEnd.value = newEnd
}

function pan(deltaBars: number) {
  const total = totalBarsCount.value
  if (!total) return

  const span = rangeEnd.value - rangeStart.value
  let newStart = rangeStart.value + deltaBars
  let newEnd = rangeEnd.value + deltaBars

  if (newStart < 0) {
    newStart = 0
    newEnd = span
  } else if (newEnd > total) {
    newEnd = total
    newStart = total - span
  }

  rangeStart.value = Math.max(0, newStart)
  rangeEnd.value = Math.min(total, newEnd)
}

// 快速周期预设
function setPreset(days: number | 'all') {
  const total = totalBarsCount.value
  if (!total) return
  if (days === 'all') {
    rangeStart.value = 0
    rangeEnd.value = total
  } else {
    rangeStart.value = Math.max(0, total - days)
    rangeEnd.value = total
  }
}

function jumpToEarliest() {
  const span = rangeEnd.value - rangeStart.value
  rangeStart.value = 0
  rangeEnd.value = Math.min(totalBarsCount.value, span)
}

function jumpToLatest() {
  const total = totalBarsCount.value
  const span = rangeEnd.value - rangeStart.value
  rangeEnd.value = total
  rangeStart.value = Math.max(0, total - span)
}

// 7. 鼠标交互事件：拖拽平移、滚轮缩放、十字光标
function handleWheel(e: WheelEvent) {
  const svg = (e.currentTarget as HTMLElement).querySelector('.tdx-svg') || (e.currentTarget as HTMLElement)
  const rect = svg.getBoundingClientRect()
  const mouseX = ((e.clientX - rect.left) / rect.width) * width.value
  const focal = Math.max(0, Math.min(1, (mouseX - chartLeft) / chartWidth.value))

  if (e.deltaY < 0) {
    // 滚轮向上：放大 (看清细节)
    zoom(0.82, focal)
  } else {
    // 滚轮向下：缩小 (看更多周期)
    zoom(1.22, focal)
  }
}

function handleMouseDown(e: MouseEvent) {
  if(e.button!==0)return
  if(props.drawingTools&&drawingMode.value!=='PAN'){
    e.preventDefault();const anchor=eventAnchor(e);if(anchor)addDrawingAnchor(anchor);return
  }
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartRange.value = { start: rangeStart.value, end: rangeEnd.value }
  window.addEventListener('mousemove', handleWindowMouseMove)
  window.addEventListener('mouseup', handleWindowMouseUp)
}

function handleWindowMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  const deltaX = e.clientX - dragStartX.value
  const visibleN = visibleBars.value.length || 1
  const barStep = chartWidth.value / visibleN
  const deltaBars = Math.round(deltaX / barStep)

  const total = totalBarsCount.value
  const span = dragStartRange.value.end - dragStartRange.value.start
  let newStart = dragStartRange.value.start - deltaBars
  let newEnd = dragStartRange.value.end - deltaBars

  if (newStart < 0) {
    newStart = 0
    newEnd = span
  } else if (newEnd > total) {
    newEnd = total
    newStart = Math.max(0, total - span)
  }

  rangeStart.value = Math.max(0, newStart)
  rangeEnd.value = Math.min(total, newEnd)
}

function handleWindowMouseUp() {
  isDragging.value = false
  window.removeEventListener('mousemove', handleWindowMouseMove)
  window.removeEventListener('mouseup', handleWindowMouseUp)
}

function handleMouseMove(e: MouseEvent) {
  if (isDragging.value) return
  if(props.drawingTools&&drawingMode.value!=='PAN')drawingHover.value=eventAnchor(e)
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const mouseX = ((e.clientX - rect.left) / rect.width) * width.value

  const bars = visibleBars.value
  if (!bars.length) return

  const n = bars.length
  const dx = chartWidth.value / n
  const idx = Math.floor((mouseX - chartLeft) / dx)
  if (idx >= 0 && idx < n) {
    if(hoverIndex.value!==idx)emit('cursorTimestamp',bars[idx]!.timestamp)
    hoverIndex.value = idx
  }
}

function handleMouseLeave() {
  drawingHover.value=null
  hoverIndex.value = null
  emit('cursorTimestamp',null)
}

function keyboardCursor(direction:number){
  const bars=visibleBars.value;if(!bars.length)return
  const index=Math.max(0,Math.min(bars.length-1,(effectiveCursorIndex.value??bars.length-1)+direction))
  hoverIndex.value=index;emit('cursorTimestamp',bars[index]!.timestamp)
}

// 小地图滑块点击跳转
function handleSliderClick(e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const clickX = ((e.clientX - rect.left) / rect.width) * width.value
  const total = totalBarsCount.value
  if (!total) return

  const targetRatio = Math.max(0, Math.min(1, (clickX - chartLeft) / chartWidth.value))
  const targetCenterBar = Math.round(targetRatio * total)
  const span = rangeEnd.value - rangeStart.value
  const half = Math.round(span / 2)

  let newStart = targetCenterBar - half
  let newEnd = targetCenterBar + (span - half)

  if (newStart < 0) {
    newStart = 0
    newEnd = span
  } else if (newEnd > total) {
    newEnd = total
    newStart = Math.max(0, total - span)
  }

  rangeStart.value = Math.max(0, newStart)
  rangeEnd.value = Math.min(total, newEnd)
}

// 聚焦读取的数据点
const activeBar = computed<VisibleBar | null>(() => {
  const bars = visibleBars.value
  if (!bars.length) return null
  if (effectiveCursorIndex.value !== null && bars[effectiveCursorIndex.value]) {
    return bars[effectiveCursorIndex.value]
  }
  return bars[bars.length - 1]
})
</script>

<template>
  <div
    class="tdx-trading-chart"
    :class="[
      `theme--${chartTheme}`,
      { 'is-fullscreen': isExpanded, 'is-dragging': isDragging },
    ]"
    role="region"
    tabindex="0"
    aria-label="通达信交互式行情图表"
    @keydown.left.self.prevent="keyboardCursor(-1)"
    @keydown.right.self.prevent="keyboardCursor(1)"
    @keydown.esc="cancelDrawing"
    @keydown.enter.self.prevent="drawingTools&&drawingMode!=='PAN'&&activeBar?addDrawingAnchor({timestamp:activeBar.timestamp,price:activeBar.close}):undefined"
    @wheel.prevent="handleWheel"
  >
    <!-- 1. 顶部通达信 HUD 动态读数栏 -->
    <header class="tdx-hud-bar">
      <div class="hud-main-info">
        <strong class="symbol-badge">{{instrumentLabel(symbol,displayName)}}</strong>
        <span class="display-name">{{ displayName }}</span>

        <template v-if="activeBar">
          <span class="hud-item hud-time">{{ activeBar.fullDate }}</span>
          <span v-if="activeBar.contract" class="hud-item">合约 {{instrumentLabel(activeBar.contract)}}</span>
          <span v-if="activeBar.hasOhlc" class="hud-item">开 {{formatNumber(activeBar.open)}} / 高 {{formatNumber(activeBar.high)}} / 低 {{formatNumber(activeBar.low)}}</span>
          <span
            class="hud-item hud-price"
            :class="activeBar.isUp ? 'txt-bullish' : 'txt-bearish'"
          >
            收盘: {{ formatNumber(activeBar.price) }}
          </span>
          <span
            class="hud-item hud-chg"
            :class="activeBar.changePct >= 0 ? 'txt-bullish' : 'txt-bearish'"
          >
            {{ formatPct(activeBar.hasChangePct?activeBar.changePct:null) }}
          </span>
          <span v-for="ma in visibleMaPeriods" :key="ma" class="hud-item hud-ma" :data-ma="ma" :style="{color:MA_COLORS[ma]}">MA{{ma}}: {{ formatNumber(activeBar.averages[ma]) }}</span>
        </template>
      </div>

      <!-- 右侧控制区 -->
      <div class="hud-controls">
        <!-- 周期视窗快速预设 -->
        <div class="preset-group" title="快速切换观察周期">
          <button
            type="button"
            class="preset-btn"
            :class="{ active: rangeEnd - rangeStart <= 22 && rangeEnd === totalBarsCount }"
            @click="setPreset(20)"
          >
            近1月
          </button>
          <button
            type="button"
            class="preset-btn"
            :class="{ active: rangeEnd - rangeStart > 22 && rangeEnd - rangeStart <= 130 && rangeEnd === totalBarsCount }"
            @click="setPreset(120)"
          >
            近半年
          </button>
          <button
            type="button"
            class="preset-btn"
            :class="{ active: rangeEnd - rangeStart > 130 && rangeEnd - rangeStart <= 260 && rangeEnd === totalBarsCount }"
            @click="setPreset(250)"
          >
            近1年
          </button>
          <button
            type="button"
            class="preset-btn"
            :class="{ active: rangeEnd - rangeStart > 260 && rangeEnd - rangeStart <= 800 && rangeEnd === totalBarsCount }"
            @click="setPreset(750)"
          >
            近3年
          </button>
          <button
            type="button"
            class="preset-btn"
            :class="{ active: rangeStart === 0 && rangeEnd === totalBarsCount }"
            @click="setPreset('all')"
          >
            全部 ({{ totalBarsCount }})
          </button>
        </div>

        <!-- 主图切换 -->
        <div class="btn-group" title="主图样式切换">
          <button
            type="button"
            class="ctrl-btn"
            :class="{ active: mainChartType === 'candle' }"
            @click="mainChartType = 'candle'"
          >
            <CandlestickChart :size="13" />
            <span>K线柱</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            :class="{ active: mainChartType === 'line' }"
            @click="mainChartType = 'line'"
          >
            <LineChartIcon :size="13" />
            <span>收盘线</span>
          </button>
        </div>

        <!-- 副图柱状图切换 (MACD/VOL/涨跌柱) -->
        <div class="btn-group" title="通达信副图柱状图切换">
          <button
            type="button"
            class="ctrl-btn"
            :class="{ active: subChartType === 'macd' }"
            @click="subChartType = 'macd'"
          >
            <span>MACD</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            :class="{ active: subChartType === 'vol' }"
            @click="subChartType = 'vol'"
          >
            <span>VOL</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            :class="{ active: subChartType === 'change' }"
            @click="subChartType = 'change'"
          >
            <span>涨跌柱</span>
          </button>
        </div>

        <!-- 缩放与历史导航按钮组 (操作核心) -->
        <div class="btn-group zoom-group">
          <button
            type="button"
            class="ctrl-btn"
            title="放大当前区域 (看清K线细节与影线)"
            @click="zoom(0.75)"
          >
            <ZoomIn :size="13" />
            <span>放大</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            title="缩小当前区域 (看更多历史周期与宏观趋势)"
            @click="zoom(1.3)"
          >
            <ZoomOut :size="13" />
            <span>缩小</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            title="查看更早以前的历史行情 (向左平移)"
            @click="pan(-15)"
          >
            <ChevronLeft :size="13" />
            <span>往前翻</span>
          </button>
          <button
            type="button"
            class="ctrl-btn"
            title="查看更新的行情 (向右平移)"
            @click="pan(15)"
          >
            <span>往后翻</span>
            <ChevronRight :size="13" />
          </button>
          <button
            type="button"
            class="ctrl-btn"
            title="回到当前数据末端"
            @click="jumpToLatest"
          >
            <RotateCcw :size="12" />
            <span>最新</span>
          </button>
        </div>

        <!-- 黑白主题切换 -->
        <button
          type="button"
          class="icon-btn"
          :title="chartTheme === 'dark' ? '切换浅色模式' : '切换通达信经典黑底模式'"
          @click="chartTheme = chartTheme === 'dark' ? 'light' : 'dark'"
        >
          <Moon v-if="chartTheme === 'dark'" :size="13" />
          <Sun v-else :size="13" />
        </button>

        <!-- 全屏展开 -->
        <button
          type="button"
          class="icon-btn"
          :title="isExpanded ? '还原窗口' : '全屏展开'"
          @click="isExpanded = !isExpanded"
        >
          <Minimize2 v-if="isExpanded" :size="13" />
          <Maximize2 v-else :size="13" />
        </button>
      </div>
    </header>
    <div class="ma-controls" aria-label="价格均线设置"><label v-for="ma in MA_PERIODS" :key="ma" :style="{color:MA_COLORS[ma]}"><input v-model="enabledMa" type="checkbox" :value="ma" :aria-label="`显示 MA${ma} 均线`"/>MA{{ma}}</label><small>按当前周期收盘价计算 · 不足 N 根显示 —</small></div>
    <div v-if="drawingTools" class="drawing-controls" aria-label="画线工具">
      <div class="drawing-buttons"><button type="button" :aria-pressed="drawingMode==='PAN'" @click="chooseDrawing('PAN')">平移</button><button v-for="(label,kind) in DRAWING_LABELS" :key="kind" type="button" :aria-pressed="drawingMode===kind" @click="chooseDrawing(kind)">{{label}}</button><button type="button" :disabled="!manualDrawings.length&&!drawingDraft.length" @click="undoDrawing">撤销画线</button><button type="button" :disabled="!manualDrawings.length&&!drawingDraft.length" @click="clearDrawings">清空手动画线</button></div>
      <div class="drawing-auto"><span>自动参考：</span><label v-for="(label,group) in autoGroupLabels" :key="group"><input v-model="autoGroups" type="checkbox" :value="group" :aria-label="`显示自动${label}`"/>{{label}}</label><span v-if="geometry?.asOf">截至 {{formatTradingDateTime(geometry.asOf)}}</span></div>
      <p class="drawing-guidance">{{drawingInstruction}} 手动画线仅在本浏览器按合约／周期保存，不参与自动预警。可用左右键选择 K 线、Enter 按收盘价落点。</p>
      <p v-if="drawingNotice" role="status" class="drawing-guidance">{{drawingNotice}}</p><p v-if="hiddenDrawingCount" class="drawing-guidance">{{hiddenDrawingCount}} 条画线的锚点已超出当前加载历史，记录仍保留。</p>
      <details v-if="automaticLines.length" class="drawing-evidence"><summary>自动线依据与价位</summary><ul><li v-for="line in automaticLines" :key="line.id">{{line.label}} · 末端 {{formatNumber(line.endPrice)}}<span v-if="line.knownAt"> · 可知时点 {{formatTradingDateTime(line.knownAt)}}</span></li></ul><p>按已完成柱生成的当前参考，不代表历史上更早时点已经知道这条线。</p></details>
      <p v-else class="drawing-guidance">{{geometry?.status==='READY'?'当前未选中自动参考线。':'自动参考线等待完整 K 线窗口。'}}</p>
    </div>
    <p v-if="points.length&&!visibleBars.length" class="linked-window-empty" role="status">该周期在联动时窗内没有已封存行情。</p>

    <!-- 2. 副图参数与交互操作提示条 -->
    <div class="tdx-sub-hud">
      <div class="sub-hud-left">
        <template v-if="subChartType === 'macd' && activeBar">
          <span class="sub-name">MACD(12, 26, 9)</span>
          <span class="dif-label">DIF: {{ activeBar.dif.toFixed(2) }}</span>
          <span class="dea-label">DEA: {{ activeBar.dea.toFixed(2) }}</span>
          <span
            class="macd-label"
            :class="activeBar.macd >= 0 ? 'txt-bullish' : 'txt-bearish'"
          >
            MACD: {{ activeBar.macd >= 0 ? '+' : '' }}{{ activeBar.macd.toFixed(2) }}
          </span>
        </template>

        <template v-else-if="subChartType === 'vol' && activeBar">
          <span class="sub-name">VOL(5, 10)</span>
          <span
            class="vol-label"
            :class="activeBar.isUp ? 'txt-bullish' : 'txt-bearish'"
          >
            VOL: {{ activeBar.hasVolume ? activeBar.vol.toLocaleString() : '—' }}
          </span>
          <span class="dif-label">MA5: {{ Math.round(activeBar.volMa5).toLocaleString() }}</span>
          <span class="dea-label">MA10: {{ Math.round(activeBar.volMa10).toLocaleString() }}</span>
        </template>

        <template v-else-if="subChartType === 'change' && activeBar">
          <span class="sub-name">CHG% (零轴多空能量柱)</span>
          <span
            class="chg-label"
            :class="activeBar.isUp ? 'txt-bullish' : 'txt-bearish'"
          >
            幅度: {{ formatPct(activeBar.hasChangePct?activeBar.changePct:null) }}
          </span>
        </template>
      </div>

      <!-- 视窗交互说明徽章 -->
      <div class="interactive-hint">
        <span class="hint-pill">
          💡 鼠标滚轮缩放 · 按住左键横向拖拽平移 · 下方滑块可自由拖动
        </span>
        <span class="range-info">
          显示第 {{ rangeStart + 1 }} ~ {{ rangeEnd }} 周期 (当前展现 {{ rangeEnd - rangeStart }} / {{ totalBarsCount }} 根)
        </span>
      </div>
    </div>

    <div v-if="trades.length" class="trade-legend" aria-label="成交买卖点图例">
      <label><input v-model="showTrades" type="checkbox" aria-label="显示买卖点"/>显示买卖点</label>
      <span class="trade-buy">▲ 买开多 / 买平空</span><span class="trade-sell">▼ 卖开空 / 卖平多</span>
      <small>当前视窗 {{visibleTrades.length}} / {{trades.length}} 笔 · 点击标记查看成交</small>
    </div>
    <!-- 3. 通达信主舞台 SVG (主图 K线/折线 + 副图 柱状图 + 十字光标 + 时间轴小地图) -->
    <div
      class="tdx-canvas-wrapper"
      ref="canvasContainer"
      @mousedown="handleMouseDown"
    >
      <svg
        class="tdx-svg"
        :viewBox="`0 0 ${width} ${height}`"
        preserveAspectRatio="none"
        @mousemove="handleMouseMove"
        @mouseleave="handleMouseLeave"
      >
        <defs>
          <clipPath :id="overlayClipId"><rect :x="chartLeft" :y="mainTop" :width="chartWidth" :height="mainHeight"/></clipPath>
          <linearGradient id="tdxLineGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0" />
          </linearGradient>
        </defs>

        <!-- 1. 背景参考网格线 -->
        <g class="grid-lines">
          <!-- 主图网格 -->
          <line
            v-for="n in 3"
            :key="`m-grid-${n}`"
            :x1="chartLeft"
            :y1="mainTop + (n * mainHeight) / 4"
            :x2="chartRight"
            :y2="mainTop + (n * mainHeight) / 4"
            class="ref-grid"
          />
          <!-- 主副图分割线 -->
          <line
            :x1="chartLeft"
            :y1="mainBottom + 12"
            :x2="chartRight"
            :y2="mainBottom + 12"
            class="ref-split"
          />
          <!-- 副图零轴基准线 -->
          <line
            v-if="subChartType === 'macd' || subChartType === 'change'"
            :x1="chartLeft"
            :y1="macdZeroY"
            :x2="chartRight"
            :y2="macdZeroY"
            class="ref-zero-axis"
          />
          <line
            v-else
            :x1="chartLeft"
            :y1="subTop + subHeight / 2"
            :x2="chartRight"
            :y2="subTop + subHeight / 2"
            class="ref-grid"
          />
          <line
            :x1="chartLeft"
            :y1="subBottom"
            :x2="chartRight"
            :y2="subBottom"
            class="ref-grid"
          />
        </g>

        <!-- 2. 主图绘制区 (当前视窗内可见数据) -->
        <g class="main-chart-layer">
          <!-- 折线图模式 -->
          <template v-if="mainChartType === 'line'">
            <path :d="priceAreaPath" fill="url(#tdxLineGrad)" />
            <polyline :points="pricePolyline" class="trend-line" />
          </template>

          <!-- K线柱状图模式：红阳绿阴柱体 -->
          <template v-else>
            <template v-for="bar in visibleBars" :key="`candle-${bar.index}`">
            <g v-if="bar.hasOhlc" class="candle-item">
              <!-- 上下影线 -->
              <line
                :x1="bar.x"
                :y1="getY(bar.high)"
                :x2="bar.x"
                :y2="getY(bar.low)"
                :stroke="bar.isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'"
                stroke-width="1.3"
              />
              <!-- 实体柱 (阳线实心红柱，阴线实心绿柱) -->
              <rect
                :x="bar.x - barWidth / 2"
                :y="getY(Math.max(bar.open, bar.close))"
                :width="barWidth"
                :height="Math.max(2, Math.abs(getY(bar.open) - getY(bar.close)))"
                :fill="bar.isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'"
                :stroke="bar.isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'"
                stroke-width="1"
              />
            </g>
            </template>
          </template>

          <path v-for="ma in maPaths" :key="ma.period" :d="ma.path" class="ma-line" :data-ma="ma.period" :stroke="MA_COLORS[ma.period]"/>

          <!-- 当前视窗极值标注 -->
          <g v-if="extremePoints" class="extreme-labels">
            <text
              :x="extremePoints.high.x"
              :y="extremePoints.high.y - 6"
              class="extreme-txt"
              text-anchor="middle"
            >
              ↑ 高 {{ formatNumber(extremePoints.high.val) }}
            </text>
            <text
              :x="extremePoints.low.x"
              :y="extremePoints.low.y + 14"
              class="extreme-txt"
              text-anchor="middle"
            >
              ↓ 低 {{ formatNumber(extremePoints.low.val) }}
            </text>
          </g>
        </g>

        <g v-if="drawingTools" class="drawing-overlays" :clip-path="`url(#${overlayClipId})`">
          <polygon v-for="channel in automaticChannels" :key="`band-${channel.id}`" class="automatic-channel-band" :points="`${overlayX(channel.upper.startIndex)},${getY(channel.upper.startPrice)} ${overlayX(channel.upper.endIndex)},${getY(channel.upper.endPrice)} ${overlayX(channel.lower.endIndex)},${getY(channel.lower.endPrice)} ${overlayX(channel.lower.startIndex)},${getY(channel.lower.startPrice)}`"/>
          <g v-for="line in automaticLines" :key="line.id" class="automatic-geometry" :class="`geometry-${line.kind.split('_')[0]!.toLowerCase()}`" role="img" :aria-label="line.label">
            <title>{{line.label}} · {{line.knownAt?'可知时点 '+formatTradingDateTime(line.knownAt):'只用已完成柱'}}</title>
            <line :x1="overlayX(line.startIndex)" :y1="getY(line.startPrice)" :x2="overlayX(line.endIndex)" :y2="getY(line.endPrice)" :stroke-dasharray="line.kind==='REGRESSION_CENTER'?'3 3':undefined"/>
          </g>
          <g v-for="drawing in drawnLines" :key="drawing.item.id" class="manual-drawing" :data-drawing-id="drawing.item.id" role="img" :aria-label="`手动${DRAWING_LABELS[drawing.item.kind]}`">
            <title>手动{{DRAWING_LABELS[drawing.item.kind]}} · 仅供个人判断，不参与预警</title>
            <polygon v-if="drawing.item.kind==='CHANNEL'&&drawing.segments.length>=2" :points="`${overlayX(drawing.segments[0]!.startIndex)},${getY(drawing.segments[0]!.startPrice)} ${overlayX(drawing.segments[0]!.endIndex)},${getY(drawing.segments[0]!.endPrice)} ${overlayX(drawing.segments[1]!.endIndex)},${getY(drawing.segments[1]!.endPrice)} ${overlayX(drawing.segments[1]!.startIndex)},${getY(drawing.segments[1]!.startPrice)}`"/>
            <line v-for="(line,index) in drawing.segments" :key="index" :x1="overlayX(line.startIndex)" :y1="getY(line.startPrice)" :x2="overlayX(line.endIndex)" :y2="getY(line.endPrice)" :stroke-dasharray="line.role==='center'?'4 4':undefined"/>
          </g>
          <line v-for="(line,index) in previewSegments" :key="`draft-${index}`" class="drawing-preview" :x1="overlayX(line.startIndex)" :y1="getY(line.startPrice)" :x2="overlayX(line.endIndex)" :y2="getY(line.endPrice)"/>
        </g>
        <g class="structure-overlays" :clip-path="`url(#${overlayClipId})`">
          <g v-for="item in visibleOverlays" :key="item.id" class="structure-overlay" :class="[`structure-${item.type.toLowerCase()}`,{'structure-selected':item.id===selectedOverlayId}]"
            role="button" tabindex="0" :aria-label="`${item.type} 第${item.startIndex+1}至${item.endIndex+1}根，${item.engineConfirmed?'引擎确定':'动态结构'}`"
            @mousedown.stop @click.stop="emit('selectStructure',item.id)" @keydown.enter.prevent="emit('selectStructure',item.id)" @keydown.space.prevent="emit('selectStructure',item.id)">
            <template v-if="(item.type==='FRACTAL'||item.type==='BSP') && item.startPrice!==undefined">
              <title>{{item.signalType??'分型'}} · {{item.signalState==='INVALIDATED'?'已失效':item.type==='BSP'?'研究候选，交易资格未评估':'已观察'}}</title>
              <circle :cx="overlayX(item.endIndex)" :cy="getY(item.startPrice)" :r="item.type==='BSP'?5:3" :fill="item.signalState==='INVALIDATED'?'none':'currentColor'" stroke="currentColor"/>
              <text v-if="item.type==='BSP'" :x="overlayX(item.endIndex)" :y="getY(item.startPrice)-10" class="structure-point-label">{{item.signalState==='INVALIDATED'?'× ':''}}{{item.signalType}}</text>
              <rect :x="overlayX(item.endIndex)-16" :y="getY(item.startPrice)-16" width="32" height="32" fill="transparent"/>
            </template>
            <template v-else-if="item.type==='ZONE' && item.high!==undefined && item.low!==undefined">
              <rect :x="overlayX(item.startIndex)" :y="getY(item.high)" :width="Math.max(1,overlayX(item.endIndex)-overlayX(item.startIndex))" :height="Math.max(1,getY(item.low)-getY(item.high))" class="structure-zone-area"/>
            </template>
            <template v-else-if="item.startPrice!==undefined && item.endPrice!==undefined">
              <line :x1="overlayX(item.startIndex)" :y1="getY(item.startPrice)" :x2="overlayX(item.endIndex)" :y2="getY(item.endPrice)" :stroke-dasharray="item.engineConfirmed?undefined:'6 4'" class="structure-line"/>
              <line :x1="overlayX(item.startIndex)" :y1="getY(item.startPrice)" :x2="overlayX(item.endIndex)" :y2="getY(item.endPrice)" class="structure-hit"/>
            </template>
          </g>
        </g>

        <!-- 3. 副图柱状图绘制区 -->
        <g class="sub-chart-layer">
          <!-- MACD 红绿柱 -->
          <template v-if="subChartType === 'macd'">
            <g v-for="bar in visibleBars" :key="`macd-bar-${bar.index}`">
              <rect
                v-if="bar.macd >= 0"
                :x="bar.x - barWidth / 2"
                :y="getMacdY(bar.macd)"
                :width="barWidth"
                :height="Math.max(1.5, macdZeroY - getMacdY(bar.macd))"
                fill="var(--color-bullish)"
              />
              <rect
                v-else
                :x="bar.x - barWidth / 2"
                :y="macdZeroY"
                :width="barWidth"
                :height="Math.max(1.5, getMacdY(bar.macd) - macdZeroY)"
                fill="var(--color-bearish)"
              />
            </g>
            <polyline :points="difPolyline" class="dif-curve" />
            <polyline :points="deaPolyline" class="dea-curve" />
          </template>

          <!-- VOL 成交量红绿柱 -->
          <template v-else-if="subChartType === 'vol'">
            <g v-for="bar in visibleBars" :key="`vol-bar-${bar.index}`">
              <rect
                v-if="bar.hasVolume"
                :x="bar.x - barWidth / 2"
                :y="getVolY(bar.vol)"
                :width="barWidth"
                :height="Math.max(2, subBottom - getVolY(bar.vol))"
                :fill="bar.isUp ? 'var(--color-bullish)' : 'var(--color-bearish)'"
              />
            </g>
            <polyline :points="volMa5Polyline" class="dif-curve" />
            <polyline :points="volMa10Polyline" class="dea-curve" />
          </template>

          <!-- 涨跌幅能量柱 (零轴对称) -->
          <template v-else-if="subChartType === 'change'">
            <g v-for="bar in visibleBars" :key="`chg-bar-${bar.index}`">
              <rect
                v-if="bar.hasChangePct && bar.changePct >= 0"
                :x="bar.x - barWidth / 2"
                :y="getChgY(bar.changePct)"
                :width="barWidth"
                :height="Math.max(2, macdZeroY - getChgY(bar.changePct))"
                fill="var(--color-bullish)"
              />
              <rect
                v-else-if="bar.hasChangePct"
                :x="bar.x - barWidth / 2"
                :y="macdZeroY"
                :width="barWidth"
                :height="Math.max(2, getChgY(bar.changePct) - macdZeroY)"
                fill="var(--color-bearish)"
              />
            </g>
          </template>
        </g>

        <!-- 4. 右侧 Y 轴标尺刻度 -->
        <g class="y-axis-labels">
          <text :x="chartRight + 8" :y="mainTop + 4" class="axis-txt">
            {{ formatNumber(visiblePriceRange.max) }}
          </text>
          <text :x="chartRight + 8" :y="mainTop + mainHeight / 2 + 3" class="axis-txt">
            {{ formatNumber(visiblePriceRange.min + visiblePriceRange.span / 2) }}
          </text>
          <text :x="chartRight + 8" :y="mainBottom" class="axis-txt">
            {{ formatNumber(visiblePriceRange.min) }}
          </text>

          <!-- 副图标尺 -->
          <template v-if="subChartType === 'macd'">
            <text :x="chartRight + 8" :y="subTop + 6" class="axis-txt">
              +{{ macdMaxAbs.toFixed(1) }}
            </text>
            <text :x="chartRight + 8" :y="macdZeroY + 3" class="axis-txt zero-txt">0.0</text>
            <text :x="chartRight + 8" :y="subBottom" class="axis-txt">
              -{{ macdMaxAbs.toFixed(1) }}
            </text>
          </template>
          <template v-else-if="subChartType === 'vol'">
            <text :x="chartRight + 8" :y="subTop + 6" class="axis-txt">
              {{ Math.round(volMax / 1000) }}k
            </text>
            <text :x="chartRight + 8" :y="subBottom" class="axis-txt zero-txt">0</text>
          </template>
          <template v-else>
            <text :x="chartRight + 8" :y="subTop + 6" class="axis-txt">
              +{{ chgMaxAbs.toFixed(1) }}%
            </text>
            <text :x="chartRight + 8" :y="macdZeroY + 3" class="axis-txt zero-txt">0%</text>
            <text :x="chartRight + 8" :y="subBottom" class="axis-txt">
              -{{ chgMaxAbs.toFixed(1) }}%
            </text>
          </template>
        </g>

        <!-- 5. X 轴时间刻度 -->
        <g class="x-axis-labels">
          <template v-for="(b, idx) in visibleBars" :key="`date-${b.index}`">
            <text
              v-if="idx % Math.ceil(visibleBars.length / (width<500?3:6)) === 0"
              :x="b.x"
              :y="dateY"
              class="axis-txt date-txt"
              :text-anchor="idx===0?'start':'middle'"
            >
              {{ b.dateLabel }}
            </text>
          </template>
        </g>

        <!-- 6. 底部 DataZoom 迷你时间轴全览小地图 (Mini-map Slider) -->
        <g class="slider-map-layer" @click="handleSliderClick">
          <!-- 小地图底栏背景 -->
          <rect
            :x="chartLeft"
            :y="sliderTop"
            :width="chartWidth"
            :height="sliderHeight"
            class="slider-bg"
            rx="3"
          />
          <!-- 全量走势折线预览 -->
          <polyline :points="miniPricePolyline" class="mini-line" />

          <!-- 左侧未选阴影区 -->
          <rect
            :x="chartLeft"
            :y="sliderTop"
            :width="sliderWindowRect.x - chartLeft"
            :height="sliderHeight"
            class="slider-mask"
          />
          <!-- 右侧未选阴影区 -->
          <rect
            :x="sliderWindowRect.x + sliderWindowRect.width"
            :y="sliderTop"
            :width="chartRight - (sliderWindowRect.x + sliderWindowRect.width)"
            :height="sliderHeight"
            class="slider-mask"
          />

          <!-- 当前高亮视窗窗口 (可拖拽滑块) -->
          <rect
            :x="sliderWindowRect.x"
            :y="sliderTop"
            :width="sliderWindowRect.width"
            :height="sliderHeight"
            class="slider-window"
            rx="2"
          />
          <!-- 左右拖拽把手指示条 -->
          <line
            :x1="sliderWindowRect.x + 2"
            :y1="sliderTop + 6"
            :x2="sliderWindowRect.x + 2"
            :y2="sliderBottom - 6"
            class="slider-handle"
          />
          <line
            :x1="sliderWindowRect.x + sliderWindowRect.width - 2"
            :y1="sliderTop + 6"
            :x2="sliderWindowRect.x + sliderWindowRect.width - 2"
            :y2="sliderBottom - 6"
            class="slider-handle"
          />

          <!-- 导航提示文字 -->
          <text
            :x="chartLeft + 6"
            :y="sliderBottom - 8"
            class="slider-tip-txt"
          >
            历史全景轨迹 ({{ totalBarsCount }} 周期) · 左右拖拽或滚轮可快速平移浏览以前行情
          </text>
        </g>

        <!-- 7. 十字光标联动 (Crosshair) -->
        <g v-if="activeBar && effectiveCursorIndex !== null && !isDragging" class="crosshair-layer">
          <!-- 垂直虚线 -->
          <line
            :x1="activeBar.x"
            :y1="mainTop"
            :x2="activeBar.x"
            :y2="subBottom"
            class="crosshair-line"
          />
          <!-- 水平价格虚线 -->
          <line
            :x1="chartLeft"
            :y1="getY(activeBar.price)"
            :x2="chartRight"
            :y2="getY(activeBar.price)"
            class="crosshair-line"
          />
          <!-- 悬停价格标签 -->
          <rect
            :x="chartRight + 2"
            :y="getY(activeBar.price) - 8"
            width="64"
            height="16"
            class="crosshair-badge-rect"
          />
          <text
            :x="chartRight + 34"
            :y="getY(activeBar.price) + 4"
            class="crosshair-badge-txt"
            text-anchor="middle"
          >
            {{ formatNumber(activeBar.price) }}
          </text>

          <!-- 悬停时间标签 -->
          <rect
            :x="activeBar.x - 26"
            :y="dateY - 14"
            width="52"
            height="16"
            class="crosshair-badge-rect"
          />
          <text
            :x="activeBar.x"
            :y="dateY - 2"
            class="crosshair-badge-txt"
            text-anchor="middle"
          >
            {{ activeBar.dateLabel }}
          </text>
        </g>
        <g v-if="showTrades" class="trade-markers">
          <g v-for="group in tradeGroups" :key="group.key" class="trade-marker"
            :class="group.side==='BUY'?'trade-buy':'trade-sell'" role="button" tabindex="0"
            :aria-label="`${group.bar.fullDate} ${group.label}，${group.fills.length} 笔成交，查看详情`"
            :aria-pressed="selectedTradeKey===group.key"
            @mousedown.stop @mouseenter="selectedTradeKey=group.key" @focus="selectedTradeKey=group.key"
            @click.stop="selectedTradeKey=group.key" @keydown.enter.prevent="selectedTradeKey=group.key"
            @keydown.space.prevent="selectedTradeKey=group.key" @keydown.esc="selectedTradeKey=null">
            <title>{{group.bar.fullDate}} {{group.label}} · {{group.fills.map(f=>`${f.quantity}手 @ ${formatNumber(f.fillPrice)}`).join('；')}}</title>
            <line :x1="group.bar.x" :x2="group.bar.x" :y1="group.y" :y2="getY(group.fills[0].fillPrice)" stroke="currentColor" stroke-width="1" stroke-dasharray="2 2" />
            <circle v-for="fill in group.fills" :key="fill.id" :cx="group.bar.x" :cy="getY(fill.fillPrice)" r="3" fill="currentColor" stroke="white" stroke-width="1" />
            <path :d="group.side==='BUY'?`M ${group.bar.x} ${group.y-6} l -5 8 h 10 Z`:`M ${group.bar.x} ${group.y+6} l -5 -8 h 10 Z`" fill="currentColor" />
            <text :x="group.bar.x" :y="group.y+(group.side==='BUY'?14:-9)" text-anchor="middle" class="trade-marker-label">{{group.label}}</text>
            <rect :x="group.bar.x-18" :y="group.y-16" width="36" height="36" fill="transparent" />
          </g>
        </g>
      </svg>
    </div>
    <section v-if="selectedTrade" class="trade-details" aria-label="买卖点成交详情" aria-live="polite">
      <header><strong :class="selectedTrade.side==='BUY'?'trade-buy':'trade-sell'">{{selectedTrade.bar.fullDate}} · {{selectedTrade.label}}</strong><button type="button" aria-label="关闭成交详情" @click="selectedTradeKey=null">关闭</button></header>
      <div class="trade-details-scroll"><article v-for="fill in selectedTrade.fills" :key="fill.id">
        <div><b :class="fill.side==='BUY'?'trade-buy':'trade-sell'">{{tradeLabel(fill)}}{{fill.eventType==='ROLL'?' · 换月':''}}</b><strong>{{instrumentLabel(fill.contract)}} · {{fill.quantity}} 手 @ {{formatNumber(fill.fillPrice)}}</strong></div>
        <time>{{new Date(fill.marketTime).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}}</time>
        <p>行情价 {{formatNumber(fill.marketPrice)}} · 手续费 {{formatNumber(fill.fee)}} · 滑点成本 {{formatNumber(fill.slippageCost)}}<span v-if="fill.offset==='CLOSE'"> · 已实现盈亏 {{formatNumber(fill.realizedPnl)}}</span></p>
        <p>{{fill.reason||'模拟撮合成交'}}</p>
      </article></div>
    </section>
  </div>
</template>

<style scoped>
.drawing-controls{border-top:1px solid var(--tdx-grid,#64748b55);padding:8px 12px;font-size:11px;color:inherit}.drawing-buttons,.drawing-auto{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-bottom:6px}.drawing-buttons button{border:1px solid #64748b88;background:transparent;color:inherit;border-radius:4px;padding:4px 8px;cursor:pointer}.drawing-buttons button[aria-pressed=true]{border-color:#e0a849;background:#e0a84924}.drawing-buttons button:disabled{opacity:.4;cursor:default}.drawing-auto label{display:inline-flex;gap:3px;align-items:center}.drawing-guidance{margin:4px 0;opacity:.8;font-size:10px;line-height:1.6}.drawing-evidence summary{cursor:pointer}.drawing-evidence ul{margin:6px 0;padding-left:18px;line-height:1.8}.drawing-evidence p{opacity:.75;margin:5px 0}.drawing-overlays{pointer-events:none}.automatic-channel-band{fill:#3da6c8;fill-opacity:.065;stroke:none}.automatic-geometry line{stroke:currentColor;stroke-width:1.4;fill:none}.automatic-geometry{pointer-events:stroke;color:#3da6c8}.geometry-trend{color:#b58de2}.geometry-horizontal{color:#86a879}.manual-drawing line{stroke:#e8ac47;stroke-width:1.7}.manual-drawing polygon{fill:#e8ac47;fill-opacity:.09;stroke:none}.drawing-preview{stroke:#e8ac47;stroke-width:1.5;stroke-dasharray:5 4}.theme--light .geometry-regression{color:#167b9a}.theme--light .geometry-trend{color:#8851ac}.theme--light .geometry-horizontal{color:#4e8346}.theme--light .manual-drawing line,.theme--light .drawing-preview{stroke:#a86a08}
.structure-fractal{color:#9a65ae}.structure-bsp{color:#a35f23}.structure-point-label{fill:currentColor;font-size:11px;font-weight:600;paint-order:stroke;stroke:var(--trade-label-bg,#fff);stroke-width:2px}
.structure-overlay{color:#386da9;cursor:pointer}.structure-segment{color:#ba7736}.structure-zone{color:#6d8967}.structure-line{stroke:currentColor;stroke-width:2;fill:none}.structure-hit{stroke:transparent;stroke-width:32;pointer-events:stroke}.structure-zone-area{fill:currentColor;fill-opacity:.14;stroke:currentColor;stroke-width:1}.structure-selected .structure-line{stroke-width:3}.structure-selected .structure-zone-area{fill-opacity:.25}.structure-overlay:focus-visible{outline:2px solid currentColor}
.trade-buy{color:var(--color-bullish,#c74444)}
.trade-sell{color:var(--color-bearish,#178369)}
.trade-legend{display:flex;flex-wrap:wrap;align-items:center;gap:.45rem 1rem;padding:.65rem 1rem;border-bottom:1px solid var(--color-line);font-size:.68rem}
.trade-legend label{display:flex;align-items:center;gap:.3rem;cursor:pointer}.trade-legend small{opacity:.7}
.trade-marker{cursor:pointer;outline:none}.trade-marker:focus rect{stroke:currentColor;stroke-width:1;rx:4}
.trade-marker-label{fill:currentColor;font-size:9px;font-weight:700;paint-order:stroke;stroke:var(--trade-label-bg,#fff);stroke-width:2.5px;stroke-linejoin:round}
.theme--dark{--trade-label-bg:#121a29}
.trade-details{padding:.8rem 1rem;border-top:1px solid var(--color-line);font-size:.72rem}
.trade-details header,.trade-details article>div{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.4rem}
.trade-details button{color:inherit;border:1px solid var(--color-line);border-radius:.3rem;background:transparent;padding:.2rem .5rem;cursor:pointer}
.trade-details-scroll{max-height:15rem;overflow:auto}.trade-details article{padding:.7rem 0;border-bottom:1px solid var(--color-line)}
.trade-details time,.trade-details p{opacity:.8;font-size:.67rem;line-height:1.65;overflow-wrap:anywhere}.trade-details p{margin:.2rem 0 0}
.tdx-trading-chart {
  display: flex;
  flex-direction: column;
  width: 100%;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-line);
  overflow: hidden;
  user-select: none;
  transition: all var(--duration-fast) ease;
}

/* 通达信经典黑底风格 */
.theme--dark {
  background: #11141a;
  color: #d1d5db;
  border-color: #262b36;
}

.theme--dark .tdx-hud-bar {
  background: #161b24;
  border-bottom: 1px solid #242a35;
}

.theme--dark .ref-grid {
  stroke: #1e2430;
  stroke-dasharray: 2, 3;
}

.theme--dark .ref-split {
  stroke: #2a313f;
  stroke-width: 1.5;
}

.theme--dark .ref-zero-axis {
  stroke: #333d4e;
  stroke-dasharray: 3, 3;
}

.theme--dark .axis-txt {
  fill: #6b7280;
}

.theme--dark .trend-line {
  stroke: #38bdf8;
}

.theme--dark .crosshair-line {
  stroke: #94a3b8;
  stroke-dasharray: 3, 3;
}

.theme--dark .crosshair-badge-rect {
  fill: #2563eb;
}

.theme--dark .slider-bg {
  fill: #161a22;
  stroke: #262c38;
}

.theme--dark .slider-mask {
  fill: rgba(0, 0, 0, 0.45);
}

.theme--dark .slider-window {
  fill: rgba(56, 189, 248, 0.12);
  stroke: #38bdf8;
  stroke-width: 1.2;
}

.theme--dark .slider-handle {
  stroke: #38bdf8;
  stroke-width: 2;
}

.theme--dark .mini-line {
  fill: none;
  stroke: #475569;
  stroke-width: 1;
}

.theme--dark .slider-tip-txt {
  fill: #64748b;
  font-size: 8.5px;
  font-family: var(--font-sans);
}

/* 现代浅色风格 */
.theme--light {
  background: #ffffff;
  color: #1f2937;
  border-color: var(--color-line);
}

.theme--light .tdx-hud-bar {
  background: #f8fafc;
  border-bottom: 1px solid var(--color-line);
}

.theme--light .ref-grid {
  stroke: #f1f5f9;
  stroke-dasharray: 2, 3;
}

.theme--light .ref-split {
  stroke: #e2e8f0;
  stroke-width: 1.5;
}

.theme--light .ref-zero-axis {
  stroke: #cbd5e1;
  stroke-dasharray: 3, 3;
}

.theme--light .axis-txt {
  fill: #94a3b8;
}

.theme--light .trend-line {
  stroke: #0284c7;
}

.theme--light .crosshair-line {
  stroke: #64748b;
  stroke-dasharray: 3, 3;
}

.theme--light .crosshair-badge-rect {
  fill: #1e293b;
}

.theme--light .slider-bg {
  fill: #f1f5f9;
  stroke: #cbd5e1;
}

.theme--light .slider-mask {
  fill: rgba(255, 255, 255, 0.6);
}

.theme--light .slider-window {
  fill: rgba(2, 132, 199, 0.12);
  stroke: #0284c7;
  stroke-width: 1.2;
}

.theme--light .slider-handle {
  stroke: #0284c7;
  stroke-width: 2;
}

.theme--light .mini-line {
  fill: none;
  stroke: #cbd5e1;
  stroke-width: 1;
}

.theme--light .slider-tip-txt {
  fill: #94a3b8;
  font-size: 8.5px;
  font-family: var(--font-sans);
}

/* 顶部 HUD 看盘条 */
.tdx-hud-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  padding: 0.5rem 0.85rem;
  font-size: 0.73rem;
}

.hud-main-info {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.55rem;
}

.symbol-badge {
  font-family: var(--font-numeric);
  font-weight: 700;
  font-size: 0.85rem;
  color: #f59e0b;
}

.display-name {
  font-weight: 600;
  color: #cbd5e1;
}

.theme--light .display-name {
  color: #334155;
}

.hud-item {
  font-family: var(--font-numeric);
  font-size: 0.7rem;
}

.hud-time {
  opacity: 0.75;
}

.hud-price {
  font-weight: 700;
  font-size: 0.76rem;
}

.hud-chg {
  font-weight: 600;
}

.hud-ma {
  font-size: 0.65rem;
  font-weight: 600;
}
.ma-controls{display:flex;align-items:center;flex-wrap:wrap;gap:.5rem .9rem;padding:.55rem .8rem;border-bottom:1px solid #64748b33;font-size:.65rem}
.ma-controls label{display:flex;align-items:center;gap:.3rem;cursor:pointer;white-space:nowrap}
.ma-controls input{accent-color:currentColor;margin:0}
.ma-controls small{opacity:.65;font-size:.58rem;margin-left:auto}

.ma5 {
  color: #facc15;
}

.ma10 {
  color: #38bdf8;
}

.ma20 {
  color: #f43f5e;
}

.txt-bullish {
  color: var(--color-bullish) !important;
}

.txt-bearish {
  color: var(--color-bearish) !important;
}

/* 控制按钮组 */
.hud-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.preset-group {
  display: inline-flex;
  padding: 2px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.2);
}

.theme--light .preset-group {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}

.preset-btn {
  padding: 0.2rem 0.42rem;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: inherit;
  font-size: 0.63rem;
  font-weight: 600;
  cursor: pointer;
  opacity: 0.7;
  transition: all 0.15s ease;
}

.preset-btn.active {
  background: #3b82f6;
  color: white;
  opacity: 1;
}

.btn-group {
  display: inline-flex;
  padding: 2px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.2);
}

.theme--light .btn-group {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}

.ctrl-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.42rem;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: inherit;
  font-size: 0.64rem;
  font-weight: 600;
  cursor: pointer;
  opacity: 0.75;
  transition: all 0.15s ease;
}

.ctrl-btn.active {
  background: rgba(255, 255, 255, 0.2);
  opacity: 1;
}

.theme--light .ctrl-btn.active {
  background: #ffffff;
  color: #0284c7;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.ctrl-btn:hover {
  opacity: 1;
}

.zoom-group .ctrl-btn {
  color: #60a5fa;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.2);
  color: inherit;
  cursor: pointer;
  opacity: 0.8;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  opacity: 1;
}

.theme--light .icon-btn {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}

/* 副图参数提示条与交互说明 */
.tdx-sub-hud {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.22rem 0.85rem;
  font-size: 0.65rem;
  font-family: var(--font-numeric);
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
}

.theme--light .tdx-sub-hud {
  border-top-color: #f1f5f9;
}

.sub-hud-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.sub-name {
  font-weight: 700;
  color: #94a3b8;
}

.dif-label {
  color: #facc15;
}

.dea-label {
  color: #38bdf8;
}

.interactive-hint {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.62rem;
  color: #94a3b8;
}

.hint-pill {
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
}

.theme--light .hint-pill {
  background: #f1f5f9;
}

.range-info {
  font-family: var(--font-numeric);
  color: #38bdf8;
  font-weight: 600;
}

/* 画布主舞台 */
.tdx-canvas-wrapper {
  position: relative;
  width: 100%;
  flex: 1;
  cursor: grab;
}

.is-dragging .tdx-canvas-wrapper {
  cursor: grabbing;
}

.tdx-svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 24rem;
}

.trend-line {
  fill: none;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.ma-line {
  fill: none;
  stroke-width: 1.2;
  opacity: 0.85;
}

.ma5-line {
  stroke: #facc15;
}

.ma10-line {
  stroke: #38bdf8;
}

.ma20-line {
  stroke: #f43f5e;
}

.extreme-txt {
  font-family: var(--font-numeric);
  font-size: 9px;
  font-weight: 700;
  fill: #facc15;
}

.dif-curve {
  fill: none;
  stroke: #facc15;
  stroke-width: 1.2;
}

.dea-curve {
  fill: none;
  stroke: #38bdf8;
  stroke-width: 1.2;
}

.axis-txt {
  font-family: var(--font-numeric);
  font-size: 11px;
}

.zero-txt {
  fill: #eab308 !important;
}

.date-txt {
  font-size: 11px;
}

.crosshair-line {
  pointer-events: none;
}

.crosshair-badge-txt {
  fill: #ffffff;
  font-family: var(--font-numeric);
  font-size: 9px;
  font-weight: 700;
}

.slider-map-layer {
  cursor: pointer;
}

/* 全屏状态 */
.is-fullscreen {
  position: fixed;
  inset: 1.5rem;
  z-index: 9999;
  height: auto;
  box-shadow: 0 25px 60px rgba(0, 0, 0, 0.55);
}
</style>
