<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
import { formatNumber, formatPct } from '../utils/format'

interface Props {
  points: HistoryPoint[]
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
})

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
const width = 800
const chartLeft = 12
const chartRight = 726
const chartWidth = chartRight - chartLeft
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
  isUp: boolean
  hasOhlc: boolean
  hasVolume: boolean
  ma5: number
  ma10: number
  ma20: number
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

    // 均线
    const s5 = list.slice(Math.max(0, i - 4), i + 1)
    const ma5 = s5.reduce((sum, b) => sum + b.price, 0) / s5.length

    const s10 = list.slice(Math.max(0, i - 9), i + 1)
    const ma10 = s10.reduce((sum, b) => sum + b.price, 0) / s10.length

    const s20 = list.slice(Math.max(0, i - 19), i + 1)
    const ma20 = s20.reduce((sum, b) => sum + b.price, 0) / s20.length

    const hasVolume = typeof cur.volume === 'number' && Number.isFinite(cur.volume) && cur.volume >= 0
    const vol = hasVolume ? Number(cur.volume) : 0
    const dateStr = cur.timestamp ? cur.timestamp.slice(5, 10).replace('-', '/') : ''
    const fullDate = cur.timestamp ? cur.timestamp.slice(0, 10) : ''

    rawBars.push({
      index: i,
      timestamp: cur.timestamp,
      dateLabel: dateStr,
      fullDate,
      price: p,
      open,
      high,
      low,
      close,
      change,
      changePct: chg,
      isUp,
      hasOhlc,
      hasVolume,
      ma5,
      ma10,
      ma20,
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
  const defaultSpan = Math.min(total, 45)
  rangeStart.value = Math.max(0, total - defaultSpan)
  rangeEnd.value = total
}

watch(
  () => props.points,
  () => {
    initRange()
  },
  { immediate: true },
)

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
  const start = Math.max(0, Math.min(rangeStart.value, all.length - 1))
  const end = Math.max(start + 1, Math.min(rangeEnd.value, all.length))
  const slice = all.slice(start, end)
  const n = slice.length
  const dx = chartWidth / n

  return slice.map((item, idx) => ({
    ...item,
    x: chartLeft + (idx + 0.5) * dx,
  }))
})

// 当前可见柱体宽度
const barWidth = computed(() => {
  const n = visibleBars.value.length
  if (!n) return 6
  const dx = chartWidth / n
  return Math.max(2.5, Math.min(22, dx * 0.72))
})

// 3. 当前视窗的动态纵坐标自适应 (Auto-fit Price Scale)
// 随着用户缩放和平移，价格轴自动适应当前可见区域的最大值与最小值，确保波动细节清晰放大
const visiblePriceRange = computed(() => {
  const bars = visibleBars.value
  if (!bars.length) return { min: 0, max: 100, span: 100 }
  let minP = Math.min(...bars.map((b) => b.low))
  let maxP = Math.max(...bars.map((b) => b.high))
  const pad = (maxP - minP) * 0.06 || 1
  minP -= pad
  maxP += pad
  return { min: minP, max: maxP, span: maxP - minP }
})

function getY(price: number): number {
  const { min, span } = visiblePriceRange.value
  return mainBottom - ((price - min) / span) * mainHeight
}

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

const ma5Polyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getY(b.ma5).toFixed(1)}`).join(' ')
})

const ma10Polyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getY(b.ma10).toFixed(1)}`).join(' ')
})

const ma20Polyline = computed(() => {
  return visibleBars.value.map((b) => `${b.x.toFixed(1)},${getY(b.ma20).toFixed(1)}`).join(' ')
})

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
    max = Math.max(max, Math.abs(b.changePct))
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
      const x = chartLeft + (i / Math.max(n - 1, 1)) * chartWidth
      const y = sliderBottom - 4 - ((b.price - minP) / spanP) * (sliderHeight - 8)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

// 视窗在小地图滑块中的高亮框位置
const sliderWindowRect = computed(() => {
  const total = totalBarsCount.value
  if (!total) return { x: chartLeft, width: chartWidth }
  const x = chartLeft + (rangeStart.value / total) * chartWidth
  const w = ((rangeEnd.value - rangeStart.value) / total) * chartWidth
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
  const mouseX = ((e.clientX - rect.left) / rect.width) * width
  const focal = Math.max(0, Math.min(1, (mouseX - chartLeft) / chartWidth))

  if (e.deltaY < 0) {
    // 滚轮向上：放大 (看清细节)
    zoom(0.82, focal)
  } else {
    // 滚轮向下：缩小 (看更多周期)
    zoom(1.22, focal)
  }
}

function handleMouseDown(e: MouseEvent) {
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
  const barStep = chartWidth / visibleN
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
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const mouseX = ((e.clientX - rect.left) / rect.width) * width

  const bars = visibleBars.value
  if (!bars.length) return

  const n = bars.length
  const dx = chartWidth / n
  const idx = Math.floor((mouseX - chartLeft) / dx)
  if (idx >= 0 && idx < n) {
    hoverIndex.value = idx
  }
}

function handleMouseLeave() {
  hoverIndex.value = null
}

// 小地图滑块点击跳转
function handleSliderClick(e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const clickX = ((e.clientX - rect.left) / rect.width) * width
  const total = totalBarsCount.value
  if (!total) return

  const targetRatio = Math.max(0, Math.min(1, (clickX - chartLeft) / chartWidth))
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
  if (hoverIndex.value !== null && bars[hoverIndex.value]) {
    return bars[hoverIndex.value]
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
    aria-label="通达信交互式行情图表"
    @wheel.prevent="handleWheel"
  >
    <!-- 1. 顶部通达信 HUD 动态读数栏 -->
    <header class="tdx-hud-bar">
      <div class="hud-main-info">
        <strong class="symbol-badge">{{ symbol || 'MAIN' }}</strong>
        <span class="display-name">{{ displayName }}</span>

        <template v-if="activeBar">
          <span class="hud-item hud-time">{{ activeBar.fullDate }}</span>
          <span
            class="hud-item hud-price"
            :class="activeBar.isUp ? 'txt-bullish' : 'txt-bearish'"
          >
            收盘: {{ formatNumber(activeBar.price) }}
          </span>
          <span
            class="hud-item hud-chg"
            :class="activeBar.isUp ? 'txt-bullish' : 'txt-bearish'"
          >
            {{ activeBar.changePct >= 0 ? '+' : '' }}{{ formatPct(activeBar.changePct) }}
          </span>
          <span class="hud-item hud-ma ma5">MA5: {{ formatNumber(activeBar.ma5) }}</span>
          <span class="hud-item hud-ma ma10">MA10: {{ formatNumber(activeBar.ma10) }}</span>
          <span class="hud-item hud-ma ma20">MA20: {{ formatNumber(activeBar.ma20) }}</span>
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
            <span>分时线</span>
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
            title="回到最新实时点"
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
            幅度: {{ activeBar.changePct >= 0 ? '+' : '' }}{{ formatPct(activeBar.changePct) }}
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

    <!-- 3. 通达信主舞台 SVG (主图 K线/折线 + 副图 柱状图 + 十字光标 + 时间轴小地图) -->
    <div
      class="tdx-canvas-wrapper"
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

          <!-- 叠加均线系统 (MA5, MA10, MA20) -->
          <polyline :points="ma5Polyline" class="ma-line ma5-line" />
          <polyline :points="ma10Polyline" class="ma-line ma10-line" />
          <polyline :points="ma20Polyline" class="ma-line ma20-line" />

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
                v-if="bar.changePct >= 0"
                :x="bar.x - barWidth / 2"
                :y="getChgY(bar.changePct)"
                :width="barWidth"
                :height="Math.max(2, macdZeroY - getChgY(bar.changePct))"
                fill="var(--color-bullish)"
              />
              <rect
                v-else
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
              v-if="idx % Math.ceil(visibleBars.length / 6) === 0"
              :x="b.x"
              :y="dateY"
              class="axis-txt date-txt"
              text-anchor="middle"
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
        <g v-if="activeBar && hoverIndex !== null && !isDragging" class="crosshair-layer">
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
      </svg>
    </div>
  </div>
</template>

<style scoped>
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
  font-size: 9.5px;
}

.zero-txt {
  fill: #eab308 !important;
}

.date-txt {
  font-size: 9px;
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
