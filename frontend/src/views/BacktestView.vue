<script setup lang="ts">
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  History,
  Layers,
  Percent,
  Play,
  RotateCcw,
  ShieldAlert,
  Sliders,
  TrendingDown,
  TrendingUp,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import {
  api,
  type BacktestPresets,
  type BacktestRequest,
  type BacktestResult,
  type DailyEquityPoint,
  type HistoryStatusResponse,
  type TradeLog,
} from '../services/api'
import { formatNumber, formatPct } from '../utils/format'

// 核心状态
const loadingPresets = ref(true)
const loadingBacktest = ref(false)
const loadingHistory = ref(false)
const presets = ref<BacktestPresets | null>(null)
const historyStatus = ref<HistoryStatusResponse | null>(null)
const result = ref<BacktestResult | null>(null)
const errorMessage = ref<string | null>(null)

// 回测参数表单。默认值仅是计算起点，不代表最优参数。
const symbol = ref('CJ0')
const strategy = ref('BOLLINGER_REVERSAL')
const initialCapital = ref(1000000)
const positionPct = ref(25)
const leverage = ref(1.8)
const marginRate = ref(0.12)
const feeRate = ref(0.0001)
const slippage = ref(1.0)
const stopLossAtr = ref(2.0)
const takeProfitAtr = ref(2.5)
const includeRollCost = ref(true)
const startDate = ref('')
const endDate = ref('')

// 交易日志过滤与分页
const tradeFilter = ref<'ALL' | 'WIN' | 'LOSS' | 'LONG' | 'SHORT'>('ALL')
const currentPage = ref(1)
const pageSize = 15

// 图表交互 Hover 状态
const hoveredPoint = ref<DailyEquityPoint | null>(null)
const hoverX = ref(0)
const showBenchmark = ref(true)

// 当前选中标的元信息
const currentSymbolMeta = computed(() => {
  return presets.value?.symbols.find((s) => s.symbol === symbol.value)
})

// 当前选中策略元信息
const currentStrategyMeta = computed(() => {
  return presets.value?.strategies.find((s) => s.id === strategy.value)
})

// 历史数据覆盖统计
const currentSymbolHistory = computed(() => {
  return historyStatus.value?.symbols.find((s) => s.symbol === symbol.value)
})

// Strategy metadata hint. This is not a performance ranking.
const recommendedStrategyForSymbol = computed(() => {
  const match = presets.value?.strategies.find((item) => item.bestFor?.includes(symbol.value))
  if (!match) return null
  return {
    strategyId: match.id,
    name: match.name,
    reason: '预设适用品种标签匹配，仍需用当前区间与成本独立验证',
  }
})

// 一键应用推荐策略
function applyRecommendedStrategy() {
  const rec = recommendedStrategyForSymbol.value
  if (!rec) return
  strategy.value = rec.strategyId
  onStrategyChange()
}

// 快速日期区间切换
function setDateRangePreset(preset: '1Y' | '3Y' | '5Y' | 'ALL') {
  const availableEnd = currentSymbolHistory.value?.endDate || new Date().toISOString().slice(0, 10)
  const now = new Date(`${availableEnd}T00:00:00`)
  endDate.value = availableEnd
  if (preset === '1Y') {
    const d = new Date(now)
    d.setFullYear(d.getFullYear() - 1)
    startDate.value = d.toISOString().slice(0, 10)
  } else if (preset === '3Y') {
    const d = new Date(now)
    d.setFullYear(d.getFullYear() - 3)
    startDate.value = d.toISOString().slice(0, 10)
  } else if (preset === '5Y') {
    const d = new Date(now)
    d.setFullYear(d.getFullYear() - 5)
    startDate.value = d.toISOString().slice(0, 10)
  } else if (preset === 'ALL') {
    if (currentSymbolHistory.value?.startDate) {
      startDate.value = currentSymbolHistory.value.startDate
    } else {
      startDate.value = '2019-01-01'
    }
  }
}

// 策略切换时自动载入推荐参数
function onStrategyChange() {
  const strat = currentStrategyMeta.value
  if (strat && strat.recommendedParams) {
    positionPct.value = strat.recommendedParams.positionPct
    stopLossAtr.value = strat.recommendedParams.stopLossAtr
    takeProfitAtr.value = strat.recommendedParams.takeProfitAtr
    if (strat.recommendedParams.leverage) {
      leverage.value = strat.recommendedParams.leverage
    }
  }
}

// 标的切换时如果超出历史范围，调整日期
function onSymbolChange() {
  const hist = currentSymbolHistory.value
  if (hist && hist.startDate && startDate.value < hist.startDate) {
    startDate.value = hist.startDate
  }
  // 智能自适应切换为针对该品种推荐的突破或回归策略
  const rec = recommendedStrategyForSymbol.value
  if (rec && strategy.value !== rec.strategyId) {
    strategy.value = rec.strategyId
    onStrategyChange()
  }
}

// 执行量化回测
async function runBacktest() {
  loadingBacktest.value = true
  errorMessage.value = null
  currentPage.value = 1
  try {
    const req: BacktestRequest = {
      symbol: symbol.value,
      strategy: strategy.value,
      initialCapital: initialCapital.value,
      positionPct: positionPct.value,
      feeRate: feeRate.value,
      slippage: slippage.value,
      stopLossAtr: stopLossAtr.value,
      takeProfitAtr: takeProfitAtr.value,
      leverage: leverage.value,
      marginRate: marginRate.value,
      includeRollCost: includeRollCost.value,
      startDate: startDate.value || undefined,
      endDate: endDate.value || undefined,
    }
    const res = await api.runBacktest(req)
    result.value = res
  } catch (err: any) {
    errorMessage.value = err?.message || '回测执行失败，请检查参数与网络连接'
  } finally {
    loadingBacktest.value = false
  }
}

// 初始化加载预设与历史库状态
onMounted(async () => {
  try {
    const [pRes, hRes] = await Promise.all([
      api.backtestPresets(),
      api.historyStatus(),
    ])
    presets.value = pRes
    historyStatus.value = hRes
    const selectedHistory = hRes.symbols.find((item) => item.symbol === symbol.value)
    if (selectedHistory) {
      endDate.value = selectedHistory.endDate
      setDateRangePreset('5Y')
    }
  } catch (err: any) {
    errorMessage.value = err?.message || '初始化回测配置失败'
  } finally {
    loadingPresets.value = false
  }
})

// 交易日志过滤
const filteredTrades = computed(() => {
  if (!result.value) return []
  const trades = result.value.tradeLogs
  if (tradeFilter.value === 'ALL') return trades
  if (tradeFilter.value === 'WIN') return trades.filter((t) => t.pnl > 0)
  if (tradeFilter.value === 'LOSS') return trades.filter((t) => t.pnl < 0)
  if (tradeFilter.value === 'LONG') return trades.filter((t) => t.action.includes('LONG') || t.action === 'OPEN_BUY')
  if (tradeFilter.value === 'SHORT') return trades.filter((t) => t.action.includes('SHORT') || t.action === 'OPEN_SHORT')
  return trades
})

const totalPages = computed(() => {
  return Math.ceil(filteredTrades.value.length / pageSize) || 1
})

const paginatedTrades = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredTrades.value.slice(start, start + pageSize)
})

// SVG 资金曲线渲染计算
const chartWidth = 920
const chartHeight = 320
const chartPadding = { top: 20, right: 24, bottom: 40, left: 70 }

const chartPoints = computed(() => {
  if (!result.value || !result.value.dailyEquity.length) return null
  const series = result.value.dailyEquity
  const n = series.length
  if (n < 2) return null

  const innerW = chartWidth - chartPadding.left - chartPadding.right
  const innerH = chartHeight - chartPadding.top - chartPadding.bottom

  // 权益区间
  let minEq = Math.min(...series.map((p) => p.equity))
  let maxEq = Math.max(...series.map((p) => p.equity))
  if (showBenchmark.value) {
    minEq = Math.min(minEq, ...series.map((p) => p.benchmarkEquity))
    maxEq = Math.max(maxEq, ...series.map((p) => p.benchmarkEquity))
  }
  const range = maxEq - minEq || 1.0
  const pad = range * 0.08
  const yMin = Math.max(0, minEq - pad)
  const yMax = maxEq + pad

  const getX = (i: number) => chartPadding.left + (i / (n - 1)) * innerW
  const getY = (val: number) => chartPadding.top + innerH - ((val - yMin) / (yMax - yMin)) * innerH

  // 生成策略曲线路径与填充路径
  let equityPath = ''
  let fillPath = ''
  let benchmarkPath = ''

  series.forEach((pt, i) => {
    const x = getX(i)
    const y = getY(pt.equity)
    const yBench = getY(pt.benchmarkEquity)
    const cmd = i === 0 ? 'M' : 'L'
    equityPath += `${cmd} ${x.toFixed(1)} ${y.toFixed(1)} `
    benchmarkPath += `${cmd} ${x.toFixed(1)} ${yBench.toFixed(1)} `
  })

  // 面积填充闭合路径
  const firstX = getX(0).toFixed(1)
  const lastX = getX(n - 1).toFixed(1)
  const bottomY = (chartPadding.top + innerH).toFixed(1)
  fillPath = `${equityPath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`

  // 基线：初始本金线
  const baselineY = getY(result.value.initialCapital)

  // 时间轴刻度 (5个等距标签)
  const xTicks = [0, 0.25, 0.5, 0.75, 1.0].map((frac) => {
    const idx = Math.min(n - 1, Math.round(frac * (n - 1)))
    return {
      x: getX(idx),
      date: series[idx].date,
    }
  })

  // 价值 Y 轴刻度 (4个分度)
  const yTicks = [0, 0.33, 0.66, 1.0].map((frac) => {
    const val = yMin + frac * (yMax - yMin)
    return {
      y: getY(val),
      val: formatNumber(val, 0),
    }
  })

  return {
    series,
    equityPath,
    fillPath,
    benchmarkPath,
    baselineY,
    xTicks,
    yTicks,
    innerW,
    innerH,
    getX,
    getY,
    yMin,
    yMax,
  }
})

// 回撤子图 SVG 渲染计算
const ddSubHeight = 80
const ddPadding = { top: 8, right: 24, bottom: 20, left: 70 }

const ddPoints = computed(() => {
  if (!result.value || !result.value.dailyEquity.length) return null
  const series = result.value.dailyEquity
  const n = series.length
  if (n < 2) return null

  const innerW = chartWidth - ddPadding.left - ddPadding.right
  const innerH = ddSubHeight - ddPadding.top - ddPadding.bottom
  const maxDD = Math.max(1.0, ...series.map((p) => p.drawdownPct))

  const getX = (i: number) => ddPadding.left + (i / (n - 1)) * innerW
  const getY = (dd: number) => ddPadding.top + (dd / maxDD) * innerH

  let path = ''
  series.forEach((pt, i) => {
    const x = getX(i)
    const y = getY(pt.drawdownPct)
    path += `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)} `
  })

  const firstX = getX(0).toFixed(1)
  const lastX = getX(n - 1).toFixed(1)
  const topY = ddPadding.top.toFixed(1)
  const fill = `${path} L ${lastX} ${topY} L ${firstX} ${topY} Z`

  return {
    fill,
    path,
    maxDD: maxDD.toFixed(1),
    innerW,
    innerH,
  }
})

// 图表鼠标移动检测
function handleChartMouseMove(event: MouseEvent) {
  if (!chartPoints.value) return
  const svgRect = (event.currentTarget as SVGElement).getBoundingClientRect()
  const mouseX = event.clientX - svgRect.left
  const { series, innerW, getX } = chartPoints.value

  const relX = Math.max(0, Math.min(innerW, mouseX - chartPadding.left))
  const idx = Math.round((relX / innerW) * (series.length - 1))
  if (series[idx]) {
    hoveredPoint.value = series[idx]
    hoverX.value = getX(idx)
  }
}

function handleChartMouseLeave() {
  hoveredPoint.value = null
}
</script>

<template>
  <div class="backtest-view">
    <!-- 顶部状态栏与核心信息 -->
    <header class="backtest-header">
      <div class="header-left">
        <div class="tag-row">
          <span class="badge badge--brand">
            <History :size="13" /> 量化回测与模拟交易引擎
          </span>
          <span v-if="historyStatus" class="badge badge--success">
            <Database :size="13" /> 离线数据已就绪：{{ historyStatus.totalSymbols }} 核心品种 / {{ historyStatus.totalBars.toLocaleString() }} 根日K
          </span>
          <span v-if="currentSymbolHistory" class="badge badge--muted">
            {{ currentSymbolHistory.displayName }} 跨度: {{ currentSymbolHistory.startDate }} ~ {{ currentSymbolHistory.endDate }} ({{ currentSymbolHistory.totalBars }}根)
          </span>
        </div>
        <h2>真实主力合约日线回测</h2>
        <p class="header-desc">
          信号于收盘确认、下一交易日开盘成交；主力切换日按旧合约平仓和新合约开仓分别结算。手续费、最小价位滑点、保证金与整数手数均进入执行账本。结果不代表实盘收益。
        </p>
      </div>

      <div class="header-right">
        <button
          type="button"
          class="btn-run"
          :disabled="loadingBacktest"
          @click="runBacktest"
        >
          <Play v-if="!loadingBacktest" :size="16" />
          <RotateCcw v-else class="spin-icon" :size="16" />
          <span>{{ loadingBacktest ? '策略仿真回测中...' : '启动量化仿真回测' }}</span>
        </button>
      </div>
    </header>

    <!-- 错误警告提示 -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      <ShieldAlert :size="18" />
      <span>{{ errorMessage }}</span>
    </div>

    <div v-if="result" class="smart-rec-banner">
      <div class="srb-left">
        <span class="srb-tag">数据审计</span>
        <span class="srb-text">
          <strong>{{ result.dataSource }}</strong> · {{ result.providerSymbol }} ·
          获取于 {{ new Date(result.dataTimestamp).toLocaleString('zh-CN') }}。
          换月价差只用于成本基准重置，不直接计入收益。
        </span>
      </div>
    </div>

    <!-- 品种与策略的元数据匹配提示，不构成绩效排名。 -->
    <div v-if="recommendedStrategyForSymbol" class="smart-rec-banner">
      <div class="srb-left">
        <span class="srb-tag">策略适配提示</span>
        <span class="srb-text">
          <strong>{{ currentSymbolMeta?.name || symbol }}</strong> 在预设元数据中关联到 <strong>{{ recommendedStrategyForSymbol.name }}</strong>。
          {{ recommendedStrategyForSymbol.reason }}。
        </span>
      </div>
      <button
        type="button"
        class="btn-apply-rec"
        :disabled="strategy === recommendedStrategyForSymbol.strategyId"
        @click="applyRecommendedStrategy"
      >
        {{ strategy === recommendedStrategyForSymbol.strategyId ? '已选择该策略' : '应用参数' }}
      </button>
    </div>

    <!-- 参数控制控制台 (Control Deck) -->
    <section class="control-deck">
      <div class="deck-row">
        <!-- 标的选择 -->
        <div class="form-group form-group--symbol">
          <label>回测标的</label>
          <select v-model="symbol" class="form-select" @change="onSymbolChange">
            <optgroup label="农产品与软商品">
              <option value="CJ0">CJ0 - 红枣主连 (CZCE)</option>
              <option value="AP0">AP0 - 苹果主连 (CZCE)</option>
              <option value="CF0">CF0 - 棉花主连 (CZCE)</option>
              <option value="SR0">SR0 - 白糖主连 (CZCE)</option>
              <option value="M0">M0 - 豆粕主连 (DCE)</option>
              <option value="C0">C0 - 玉米主连 (DCE)</option>
              <option value="OI0">OI0 - 菜油主连 (CZCE)</option>
              <option value="P0">P0 - 棕榈油主连 (DCE)</option>
              <option value="Y0">Y0 - 豆油主连 (DCE)</option>
            </optgroup>
            <optgroup label="黑色金属与建材">
              <option value="RB0">RB0 - 螺纹钢主连 (SHFE)</option>
              <option value="HC0">HC0 - 热卷主连 (SHFE)</option>
              <option value="I0">I0 - 铁矿石主连 (DCE)</option>
              <option value="J0">J0 - 焦炭主连 (DCE)</option>
              <option value="JM0">JM0 - 焦煤主连 (DCE)</option>
              <option value="FG0">FG0 - 玻璃主连 (CZCE)</option>
              <option value="SA0">SA0 - 纯碱主连 (CZCE)</option>
            </optgroup>
            <optgroup label="有色金属与新能源">
              <option value="CU0">CU0 - 沪铜主连 (SHFE)</option>
              <option value="AL0">AL0 - 沪铝主连 (SHFE)</option>
              <option value="ZN0">ZN0 - 沪锌主连 (SHFE)</option>
              <option value="NI0">NI0 - 沪镍主连 (SHFE)</option>
              <option value="LC0">LC0 - 碳酸锂主连 (GFEX)</option>
              <option value="SI0">SI0 - 工业硅主连 (GFEX)</option>
            </optgroup>
            <optgroup label="贵金属">
              <option value="AU0">AU0 - 黄金主连 (SHFE)</option>
              <option value="AG0">AG0 - 白银主连 (SHFE)</option>
            </optgroup>
            <optgroup label="能源化工">
              <option value="TA0">TA0 - PTA主连 (CZCE)</option>
              <option value="MA0">MA0 - 甲醇主连 (CZCE)</option>
              <option value="PP0">PP0 - 聚丙烯主连 (DCE)</option>
              <option value="EG0">EG0 - 乙二醇主连 (DCE)</option>
              <option value="SC0">SC0 - 原油主连 (INE)</option>
            </optgroup>
            <optgroup label="金融期货">
              <option value="IF0">IF0 - 沪深300主连 (CFFEX)</option>
              <option value="IC0">IC0 - 中证500主连 (CFFEX)</option>
              <option value="IM0">IM0 - 中证1000主连 (CFFEX)</option>
              <option value="IH0">IH0 - 上证50主连 (CFFEX)</option>
              <option value="T0">T0 - 10年期国债主连 (CFFEX)</option>
            </optgroup>
          </select>
        </div>

        <!-- 策略选择 -->
        <div class="form-group form-group--strat">
          <label>量化算法策略</label>
          <select v-model="strategy" class="form-select" @change="onStrategyChange">
            <option v-for="item in presets?.strategies || []" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select>
        </div>

        <!-- 时间区间选择 -->
        <div class="form-group form-group--dates">
          <div class="date-header">
            <label>历史回测区间</label>
            <div class="quick-presets">
              <button type="button" @click="setDateRangePreset('1Y')">近1年</button>
              <button type="button" @click="setDateRangePreset('3Y')">近3年</button>
              <button type="button" @click="setDateRangePreset('5Y')">近5年</button>
              <button type="button" @click="setDateRangePreset('ALL')">全历史</button>
            </div>
          </div>
          <div class="date-inputs">
            <input v-model="startDate" type="date" class="form-input" />
            <span class="date-sep">至</span>
            <input v-model="endDate" type="date" class="form-input" />
          </div>
        </div>
      </div>

      <!-- 参数微调网格 -->
      <div class="deck-params">
        <div class="param-cell">
          <span class="p-label">初始资金 (¥)</span>
          <input v-model.number="initialCapital" type="number" step="100000" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">仓位资金 (%)</span>
          <input v-model.number="positionPct" type="number" min="5" max="100" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">期货有效杠杆 (倍)</span>
          <input v-model.number="leverage" type="number" step="0.1" min="1.0" max="5.0" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">手续费率</span>
          <input v-model.number="feeRate" type="number" step="0.0001" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">交易滑点 (最小价位跳数)</span>
          <input v-model.number="slippage" type="number" step="0.5" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">ATR 跟踪止损倍数</span>
          <input v-model.number="stopLossAtr" type="number" step="0.1" class="param-input" />
        </div>
        <div class="param-cell">
          <span class="p-label">ATR 目标止盈倍数</span>
          <input v-model.number="takeProfitAtr" type="number" step="0.1" class="param-input" />
        </div>
        <div class="param-cell param-cell--toggle">
          <span class="p-label">真实换月数据</span>
          <label class="toggle-control" title="回测强制使用天勤真实主力映射和新旧合约成交价">
            <input v-model="includeRollCost" type="checkbox" disabled />
            <span class="toggle-text">天勤真实换月（强制）</span>
          </label>
        </div>
      </div>
    </section>

    <!-- 策略简介卡片 -->
    <div v-if="currentStrategyMeta" class="strategy-summary-card">
      <div class="sc-header">
        <Sliders :size="15" />
        <strong>{{ currentStrategyMeta.name }}</strong>
      </div>
      <p>{{ currentStrategyMeta.description }}</p>
    </div>

    <!-- 核心业绩指标概览网格 (12 Key Institutional Indicators) -->
    <section v-if="result" class="metrics-dashboard">
      <div class="metric-card" :class="{ 'metric--up': result.totalReturnPct > 0, 'metric--down': result.totalReturnPct < 0 }">
        <span class="m-title">策略总收益率</span>
        <div class="m-val">
          <strong>{{ result.totalReturnPct > 0 ? '+' : '' }}{{ result.totalReturnPct }}%</strong>
          <ArrowUpRight v-if="result.totalReturnPct > 0" :size="18" />
          <ArrowDownRight v-else-if="result.totalReturnPct < 0" :size="18" />
        </div>
        <span class="m-sub">期末资产: ¥{{ result.finalEquity.toLocaleString() }}</span>
      </div>

      <div class="metric-card" :class="{ 'metric--up': result.annualizedReturnPct > 0, 'metric--down': result.annualizedReturnPct < 0 }">
        <span class="m-title">年化复合收益 (CAGR)</span>
        <div class="m-val">
          <strong>{{ result.annualizedReturnPct > 0 ? '+' : '' }}{{ result.annualizedReturnPct }}%</strong>
        </div>
        <span class="m-sub">折合年化复利收益</span>
      </div>

      <div class="metric-card" :class="{ 'metric--up': result.benchmarkReturnPct > 0, 'metric--down': result.benchmarkReturnPct < 0 }">
        <span class="m-title">标的基准收益 (Buy&Hold)</span>
        <div class="m-val">
          <strong>{{ result.benchmarkReturnPct > 0 ? '+' : '' }}{{ result.benchmarkReturnPct }}%</strong>
        </div>
        <span class="m-sub">标的同周期纯持有</span>
      </div>

      <div class="metric-card" :class="{ 'metric--up': result.alphaPct > 0, 'metric--down': result.alphaPct < 0 }">
        <span class="m-title">超额收益 (Alpha)</span>
        <div class="m-val">
          <strong>{{ result.alphaPct > 0 ? '+' : '' }}{{ result.alphaPct }}%</strong>
        </div>
        <span class="m-sub">超越标的基准差值</span>
      </div>

      <div class="metric-card metric--drawdown">
        <span class="m-title">最大动态回撤</span>
        <div class="m-val">
          <strong>-{{ result.maxDrawdownPct }}%</strong>
        </div>
        <span class="m-sub">最长回撤周期: {{ result.maxDrawdownDays }} 交易日</span>
      </div>

      <div class="metric-card">
        <span class="m-title">夏普比率 (Sharpe)</span>
        <div class="m-val">
          <strong>{{ result.sharpeRatio }}</strong>
        </div>
        <span class="m-sub">风险调整后年化回报</span>
      </div>

      <div class="metric-card">
        <span class="m-title">索提诺比率 (Sortino)</span>
        <div class="m-val">
          <strong>{{ result.sortinoRatio }}</strong>
        </div>
        <span class="m-sub">仅惩罚下行波动风险</span>
      </div>

      <div class="metric-card">
        <span class="m-title">卡尔玛比率 (Calmar)</span>
        <div class="m-val">
          <strong>{{ result.calmarRatio }}</strong>
        </div>
        <span class="m-sub">收益与最大回撤比率</span>
      </div>

      <div class="metric-card">
        <span class="m-title">策略交易胜率</span>
        <div class="m-val">
          <strong>{{ result.winRate }}%</strong>
        </div>
        <span class="m-sub">盈利交易占比</span>
      </div>

      <div class="metric-card">
        <span class="m-title">单笔盈亏比</span>
        <div class="m-val">
          <strong>{{ result.profitLossRatio }}</strong>
        </div>
        <span class="m-sub">平均盈利 / 平均亏损</span>
      </div>

      <div class="metric-card">
        <span class="m-title">仿真交易笔数</span>
        <div class="m-val">
          <strong>{{ result.totalTrades }} 笔</strong>
        </div>
        <span class="m-sub">胜 {{ result.winningTrades }} 笔 / 负 {{ result.losingTrades }} 笔</span>
      </div>

      <div class="metric-card">
        <span class="m-title">平均持仓周期</span>
        <div class="m-val">
          <strong>{{ result.avgHoldBars }} 根K线</strong>
        </div>
        <span class="m-sub">单笔平均盈利: ¥{{ result.avgTradePnl }}</span>
      </div>

      <div class="metric-card">
        <span class="m-title">期货有效杠杆 (Leverage)</span>
        <div class="m-val">
          <strong>{{ result.effectiveLeverage || leverage }}x</strong>
        </div>
        <span class="m-sub">仿真假设：资金占用 {{ Math.round(positionPct) }}%，保证金率 {{ (marginRate * 100).toFixed(1) }}%</span>
      </div>

      <div class="metric-card">
        <span class="m-title">换月执行成本</span>
        <div class="m-val">
          <strong>¥{{ (result.rollCostTotal ?? 0).toLocaleString() }}</strong>
        </div>
        <span class="m-sub">{{ result.rollTrades ?? 0 }} 次换月 · 手续费与滑点</span>
      </div>

      <div class="metric-card">
        <span class="m-title">换月价差（信息项）</span>
        <div class="m-val">
          <strong>{{ (result.rollPriceGapTotal ?? 0) >= 0 ? '+' : '' }}¥{{ (result.rollPriceGapTotal ?? 0).toLocaleString() }}</strong>
        </div>
        <span class="m-sub">不直接计入权益 · {{ result.rollModelStatus || '无可审计换月事件' }}</span>
      </div>
    </section>

    <!-- 交互式资产净值曲线与动态回撤图表 -->
    <section v-if="result && chartPoints" class="chart-section">
      <div class="chart-header">
        <div class="ch-title">
          <TrendingUp :size="18" />
          <h3>资产净值走势与标的对比 (Equity Curve vs Benchmark)</h3>
        </div>
        <div class="ch-legend">
          <label class="legend-item">
            <span class="dot dot--strategy"></span>
            <span>策略净值 ({{ result.strategyName }})</span>
          </label>
          <label class="legend-item">
            <input v-model="showBenchmark" type="checkbox" />
            <span class="dot dot--bench"></span>
            <span>基准持有 (Buy & Hold)</span>
          </label>
        </div>
      </div>

      <!-- SVG 资金曲线主图 -->
      <div class="chart-wrapper">
        <svg
          class="equity-svg"
          role="img"
          aria-label="策略净值与基准净值历史回测曲线"
          tabindex="0"
          :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
          preserveAspectRatio="none"
          @mousemove="handleChartMouseMove"
          @mouseleave="handleChartMouseLeave"
        >
          <defs>
            <linearGradient id="eqGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.35" />
              <stop offset="100%" stop-color="#06b6d4" stop-opacity="0.0" />
            </linearGradient>
            <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#ef4444" stop-opacity="0.0" />
              <stop offset="100%" stop-color="#ef4444" stop-opacity="0.3" />
            </linearGradient>
          </defs>

          <!-- 背景网格横线与 Y 轴刻度 -->
          <g class="grid-lines">
            <template v-for="tick in chartPoints.yTicks" :key="tick.y">
              <line
                :x1="chartPadding.left"
                :y1="tick.y"
                :x2="chartWidth - chartPadding.right"
                :y2="tick.y"
                stroke="var(--color-border, #2d3748)"
                stroke-dasharray="3,3"
                stroke-opacity="0.6"
              />
              <text
                :x="chartPadding.left - 10"
                :y="tick.y + 4"
                text-anchor="end"
                class="tick-label"
              >
                ¥{{ tick.val }}
              </text>
            </template>
          </g>

          <!-- 本金初始基线 -->
          <line
            :x1="chartPadding.left"
            :y1="chartPoints.baselineY"
            :x2="chartWidth - chartPadding.right"
            :y2="chartPoints.baselineY"
            stroke="#94a3b8"
            stroke-dasharray="2,4"
            stroke-opacity="0.4"
          />

          <!-- 策略净值填充区域 -->
          <path :d="chartPoints.fillPath" fill="url(#eqGradient)" />

          <!-- 基准曲线 (虚线) -->
          <path
            v-if="showBenchmark"
            :d="chartPoints.benchmarkPath"
            fill="none"
            stroke="#f59e0b"
            stroke-width="1.8"
            stroke-dasharray="5,4"
          />

          <!-- 策略净值曲线 -->
          <path
            :d="chartPoints.equityPath"
            fill="none"
            stroke="#06b6d4"
            stroke-width="2.5"
            stroke-linejoin="round"
            stroke-linecap="round"
          />

          <!-- X 轴刻度标签 -->
          <g class="x-axis-ticks">
            <template v-for="tick in chartPoints.xTicks" :key="tick.date">
              <line
                :x1="tick.x"
                :y1="chartHeight - chartPadding.bottom"
                :x2="tick.x"
                :y2="chartHeight - chartPadding.bottom + 5"
                stroke="var(--color-border, #4a5568)"
              />
              <text
                :x="tick.x"
                :y="chartHeight - 12"
                text-anchor="middle"
                class="tick-label"
              >
                {{ tick.date }}
              </text>
            </template>
          </g>

          <!-- 鼠标悬停交叉垂直十字线与提示点 -->
          <g v-if="hoveredPoint" class="hover-group">
            <line
              :x1="hoverX"
              :y1="chartPadding.top"
              :x2="hoverX"
              :y2="chartHeight - chartPadding.bottom"
              stroke="#e2e8f0"
              stroke-width="1"
              stroke-dasharray="2,2"
            />
            <circle
              :cx="hoverX"
              :cy="chartPoints.getY(hoveredPoint.equity)"
              r="4.5"
              fill="#06b6d4"
              stroke="#ffffff"
              stroke-width="2"
            />
          </g>
        </svg>

        <!-- 悬停信息浮动指示卡片 -->
        <div
          v-if="hoveredPoint"
          class="chart-tooltip"
          :style="{ left: `${Math.min(hoverX + 16, chartWidth - 200)}px` }"
        >
          <div class="tt-header">{{ hoveredPoint.date }}</div>
          <div class="tt-row">
            <span>策略净值:</span>
            <strong class="tt-cyan">¥{{ hoveredPoint.equity.toLocaleString() }}</strong>
          </div>
          <div class="tt-row">
            <span>单日收益:</span>
            <span :class="hoveredPoint.dailyReturnPct >= 0 ? 'text-red' : 'text-green'">
              {{ hoveredPoint.dailyReturnPct >= 0 ? '+' : '' }}{{ hoveredPoint.dailyReturnPct }}%
            </span>
          </div>
          <div class="tt-row">
            <span>基准净值:</span>
            <strong class="tt-amber">¥{{ hoveredPoint.benchmarkEquity.toLocaleString() }}</strong>
          </div>
          <div class="tt-row">
            <span>动态回撤:</span>
            <span class="text-red">-{{ hoveredPoint.drawdownPct }}%</span>
          </div>
          <div class="tt-row">
            <span>持仓比例:</span>
            <span>{{ hoveredPoint.positionPct }}%</span>
          </div>
        </div>
      </div>

      <!-- 下方动态回撤子图 (Underwater Chart) -->
      <div v-if="ddPoints" class="drawdown-subchart">
        <div class="dd-title">
          <span>动态回撤深度 (Underwater Drawdown %)</span>
          <small>峰值回撤: -{{ result.maxDrawdownPct }}%</small>
        </div>
        <svg
          class="dd-svg"
          :viewBox="`0 0 ${chartWidth} ${ddSubHeight}`"
          preserveAspectRatio="none"
        >
          <path :d="ddPoints.fill" fill="url(#ddGradient)" />
          <path :d="ddPoints.path" fill="none" stroke="#ef4444" stroke-width="1.2" />
          <line
            :x1="ddPadding.left"
            :y1="ddPadding.top"
            :x2="chartWidth - ddPadding.right"
            :y2="ddPadding.top"
            stroke="#475569"
            stroke-dasharray="2,2"
          />
        </svg>
      </div>
    </section>

    <!-- 仿真成交明细与回溯归因日志 (Trade Execution Logs) -->
    <section v-if="result" class="trades-section">
      <div class="trades-header">
        <div class="th-left">
          <Layers :size="18" />
          <h3>仿真成交逐笔回溯与信号归因明细 ({{ filteredTrades.length }} 笔记录)</h3>
        </div>

        <!-- 过滤标签 -->
        <div class="th-filters">
          <button
            type="button"
            :class="{ active: tradeFilter === 'ALL' }"
            @click="tradeFilter = 'ALL'; currentPage = 1"
          >
            全部交易 ({{ result.tradeLogs.length }})
          </button>
          <button
            type="button"
            :class="{ active: tradeFilter === 'WIN' }"
            @click="tradeFilter = 'WIN'; currentPage = 1"
          >
            盈利平仓 ({{ result.winningTrades }})
          </button>
          <button
            type="button"
            :class="{ active: tradeFilter === 'LOSS' }"
            @click="tradeFilter = 'LOSS'; currentPage = 1"
          >
            亏损平仓 ({{ result.losingTrades }})
          </button>
          <button
            type="button"
            :class="{ active: tradeFilter === 'LONG' }"
            @click="tradeFilter = 'LONG'; currentPage = 1"
          >
            多头头寸
          </button>
          <button
            type="button"
            :class="{ active: tradeFilter === 'SHORT' }"
            @click="tradeFilter = 'SHORT'; currentPage = 1"
          >
            空头头寸
          </button>
        </div>
      </div>

      <!-- 交易表格 -->
      <div class="table-container">
        <table class="trades-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>方向/操作</th>
              <th>合约 / 手数</th>
              <th>成交价</th>
              <th>仓位比例</th>
              <th>账本现金变动 (¥)</th>
              <th>收益率</th>
              <th>持仓天数</th>
              <th>费用 / 滑点</th>
              <th>策略触发归因与风控指令</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(trade, idx) in paginatedTrades" :key="idx" class="trade-row">
              <td class="td-time">{{ trade.timestamp.slice(0, 10) }}</td>
              <td>
                <span
                  class="action-badge"
                  :class="{
                    'badge--buy': trade.action === 'OPEN_BUY',
                    'badge--short': trade.action === 'OPEN_SHORT',
                    'badge--close-long': trade.action === 'FLATTEN_LONG',
                    'badge--close-short': trade.action === 'FLATTEN_SHORT',
                    'badge--close-final': trade.action === 'FINAL_FLATTEN',
                  }"
                >
                  <template v-if="trade.action === 'OPEN_BUY'">做多开仓</template>
                  <template v-else-if="trade.action === 'OPEN_SHORT'">做空开仓</template>
                  <template v-else-if="trade.action === 'FLATTEN_LONG'">多头平仓</template>
                  <template v-else-if="trade.action === 'FLATTEN_SHORT'">空头平仓</template>
                  <template v-else-if="trade.action === 'FINAL_FLATTEN'">期末结算平仓</template>
                  <template v-else-if="trade.action === 'ROLL_LONG'">多头移仓</template>
                  <template v-else-if="trade.action === 'ROLL_SHORT'">空头移仓</template>
                  <template v-else>{{ trade.action }}</template>
                </span>
              </td>
              <td class="td-num">
                <span v-if="trade.fromContract && trade.toContract">
                  {{ trade.fromContract }} → {{ trade.toContract }} / {{ trade.lots ?? 0 }}手
                </span>
                <span v-else>{{ trade.contract || '-' }} / {{ trade.lots ?? 0 }}手</span>
              </td>
              <td class="td-num">{{ trade.price.toFixed(1) }}</td>
              <td class="td-num">{{ trade.positionPct.toFixed(1) }}%</td>
              <td class="td-num">
                <span
                  v-if="trade.pnl !== 0"
                  :class="trade.pnl > 0 ? 'text-red' : 'text-green'"
                  class="font-mono"
                >
                  {{ trade.pnl > 0 ? '+' : '' }}¥{{ trade.pnl.toLocaleString() }}
                </span>
                <span v-else class="text-muted">-</span>
              </td>
              <td class="td-num">
                <span
                  v-if="trade.returnPct !== 0"
                  :class="trade.returnPct > 0 ? 'text-red' : 'text-green'"
                  class="font-mono"
                >
                  {{ trade.returnPct > 0 ? '+' : '' }}{{ trade.returnPct }}%
                </span>
                <span v-else class="text-muted">-</span>
              </td>
              <td class="td-num">
                <span v-if="trade.holdBars > 0">{{ trade.holdBars }} 根</span>
                <span v-else class="text-muted">-</span>
              </td>
              <td class="td-num">
                ¥{{ (trade.fee ?? 0).toFixed(2) }} / ¥{{ (trade.slippageCost ?? 0).toFixed(2) }}
              </td>
              <td class="td-reason">
                <span class="reason-tag">{{ trade.reason }}</span>
              </td>
            </tr>
            <tr v-if="paginatedTrades.length === 0">
              <td colspan="10" class="empty-trades">
                暂无符合筛选条件的仿真交易记录
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页栏 -->
      <div v-if="totalPages > 1" class="pagination-bar">
        <button
          type="button"
          class="page-btn"
          :disabled="currentPage <= 1"
          @click="currentPage--"
        >
          <ChevronLeft :size="16" /> 上一页
        </button>
        <span class="page-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button
          type="button"
          class="page-btn"
          :disabled="currentPage >= totalPages"
          @click="currentPage++"
        >
          下一页 <ChevronRight :size="16" />
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.backtest-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 4px 48px;
  max-width: 1400px;
  margin: 0 auto;
}

/* 顶部 Header */
.backtest-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  background: var(--color-bg-card, #131722);
  border: 1px solid var(--color-border, #1e2638);
  border-radius: 12px;
  padding: 24px;
}

/* 智能品种适配策略推荐条 */
.smart-rec-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background: linear-gradient(90deg, rgba(6, 182, 212, 0.12), rgba(16, 185, 129, 0.12));
  border: 1px solid rgba(6, 182, 212, 0.35);
  border-radius: 10px;
  padding: 14px 20px;
}

.srb-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.srb-tag {
  background: rgba(6, 182, 212, 0.2);
  color: #38bdf8;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid rgba(56, 189, 248, 0.4);
  white-space: nowrap;
}

.srb-text {
  font-size: 13px;
  color: var(--color-text, #f1f5f9);
  line-height: 1.5;
}

.srb-text strong {
  color: #38bdf8;
}

.btn-apply-rec {
  background: linear-gradient(135deg, #10b981, #059669);
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  transition: all 0.2s ease;
}

.btn-apply-rec:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-apply-rec:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
}

.badge--brand {
  background: rgba(6, 182, 212, 0.12);
  color: #06b6d4;
  border: 1px solid rgba(6, 182, 212, 0.3);
}

.badge--success {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge--muted {
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.backtest-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text, #f1f5f9);
  margin: 4px 0 0;
}

.header-desc {
  font-size: 13px;
  color: var(--color-text-muted, #94a3b8);
  line-height: 1.6;
  max-width: 900px;
  margin: 0;
}

.btn-run {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #06b6d4, #0284c7);
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(6, 182, 212, 0.35);
  transition: all 0.2s ease;
  white-space: nowrap;
}

.btn-run:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
}

.btn-run:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 错误横幅 */
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
  padding: 12px 18px;
  border-radius: 8px;
  font-size: 14px;
}

/* 控制台表单 (Control Deck) */
.control-deck {
  background: var(--color-bg-card, #131722);
  border: 1px solid var(--color-border, #1e2638);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.deck-row {
  display: grid;
  grid-template-columns: 1.2fr 1.6fr 1.6fr;
  gap: 20px;
}

@media (max-width: 1024px) {
  .deck-row {
    grid-template-columns: 1fr;
  }
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.form-select,
.form-input {
  background: var(--color-bg-input, #0d111a);
  border: 1px solid var(--color-border, #242e42);
  color: var(--color-text, #f1f5f9);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.form-select:focus,
.form-input:focus {
  border-color: #06b6d4;
}

.date-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.quick-presets {
  display: flex;
  gap: 4px;
}

.quick-presets button {
  background: transparent;
  border: 1px solid var(--color-border, #242e42);
  color: var(--color-text-muted, #94a3b8);
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.quick-presets button:hover {
  background: rgba(6, 182, 212, 0.15);
  color: #06b6d4;
  border-color: #06b6d4;
}

.date-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-sep {
  color: var(--color-text-muted, #94a3b8);
  font-size: 12px;
}

/* 参数微调网格 */
.deck-params {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border, #1a2232);
}

@media (max-width: 900px) {
  .deck-params {
    grid-template-columns: repeat(2, 1fr);
  }
}

.param-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.param-cell--toggle {
  justify-content: space-between;
}

.toggle-control {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  height: 32px;
  background: rgba(6, 182, 212, 0.08);
  border: 1px solid rgba(6, 182, 212, 0.25);
  border-radius: 6px;
  padding: 0 10px;
}

.toggle-control input[type="checkbox"] {
  accent-color: #06b6d4;
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.toggle-text {
  font-size: 11px;
  color: #22d3ee;
  font-weight: 600;
  white-space: nowrap;
}

.p-label {
  font-size: 11px;
  color: var(--color-text-muted, #94a3b8);
}

.param-input {
  background: var(--color-bg-input, #0d111a);
  border: 1px solid var(--color-border, #242e42);
  color: var(--color-text, #f1f5f9);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-family: monospace;
}

/* 策略简介卡片 */
.strategy-summary-card {
  background: rgba(6, 182, 212, 0.05);
  border: 1px dashed rgba(6, 182, 212, 0.25);
  border-radius: 8px;
  padding: 12px 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #06b6d4;
}

.strategy-summary-card p {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
  line-height: 1.5;
  margin: 0;
}

/* 核心业绩指标概览网格 */
.metrics-dashboard {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

@media (max-width: 1200px) {
  .metrics-dashboard {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics-dashboard {
    grid-template-columns: repeat(2, 1fr);
  }
}

.metric-card {
  background: var(--color-bg-card, #131722);
  border: 1px solid var(--color-border, #1e2638);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
  overflow: hidden;
}

.m-title {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}

.m-val {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text, #f1f5f9);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
}

.m-sub {
  font-size: 11px;
  color: var(--color-text-muted, #64748b);
  margin-top: 2px;
}

/* 颜色编码：中国股市与期货红涨绿跌 */
.metric--up .m-val {
  color: #ef4444; /* 红色代表收益/上涨 */
}

.metric--down .m-val {
  color: #10b981; /* 绿色代表亏损/下跌 */
}

.metric--drawdown .m-val {
  color: #ef4444; /* 回撤警示 */
}

/* 资产净值图表 */
.chart-section {
  background: var(--color-bg-card, #131722);
  border: 1px solid var(--color-border, #1e2638);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ch-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #06b6d4;
}

.ch-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text, #f1f5f9);
  margin: 0;
}

.ch-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-muted, #94a3b8);
  cursor: pointer;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.dot--strategy {
  background: #06b6d4;
}

.dot--bench {
  background: #f59e0b;
}

.chart-wrapper {
  position: relative;
  width: 100%;
}

.equity-svg {
  width: 100%;
  height: 320px;
  overflow: visible;
}

.tick-label {
  fill: #64748b;
  font-size: 10px;
  font-family: monospace;
}

.chart-tooltip {
  position: absolute;
  top: 20px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(6, 182, 212, 0.4);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
  min-width: 170px;
  pointer-events: none;
  z-index: 10;
  backdrop-filter: blur(8px);
}

.tt-header {
  font-weight: 700;
  color: #f8fafc;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 4px;
  margin-bottom: 6px;
}

.tt-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 3px;
  color: #94a3b8;
}

.tt-cyan {
  color: #06b6d4;
}

.tt-amber {
  color: #f59e0b;
}

.text-red {
  color: #ef4444;
}

.text-green {
  color: #10b981;
}

/* 回撤子图 */
.drawdown-subchart {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px solid var(--color-border, #1a2232);
  padding-top: 10px;
}

.dd-title {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #94a3b8;
}

.dd-svg {
  width: 100%;
  height: 80px;
  overflow: visible;
}

/* 交易记录表格 */
.trades-section {
  background: var(--color-bg-card, #131722);
  border: 1px solid var(--color-border, #1e2638);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.trades-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.th-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #06b6d4;
}

.th-left h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text, #f1f5f9);
  margin: 0;
}

.th-filters {
  display: flex;
  gap: 6px;
}

.th-filters button {
  background: var(--color-bg-input, #0d111a);
  border: 1px solid var(--color-border, #242e42);
  color: var(--color-text-muted, #94a3b8);
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.th-filters button.active {
  background: rgba(6, 182, 212, 0.15);
  border-color: #06b6d4;
  color: #06b6d4;
  font-weight: 600;
}

.table-container {
  overflow-x: auto;
}

.trades-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.trades-table th {
  background: rgba(255, 255, 255, 0.02);
  color: var(--color-text-muted, #94a3b8);
  font-weight: 600;
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border, #242e42);
}

.trades-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border, #1a2232);
  color: var(--color-text, #e2e8f0);
}

.trade-row:hover {
  background: rgba(255, 255, 255, 0.02);
}

.td-time {
  font-family: monospace;
  color: #94a3b8;
}

.td-num {
  font-family: monospace;
}

.font-mono {
  font-family: monospace;
  font-weight: 600;
}

.action-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.badge--buy {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.badge--short {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.4);
}

.badge--close-long {
  background: rgba(239, 68, 68, 0.08);
  color: #f87171;
  border: 1px dashed rgba(239, 68, 68, 0.3);
}

.badge--close-short {
  background: rgba(16, 185, 129, 0.08);
  color: #34d399;
  border: 1px dashed rgba(16, 185, 129, 0.3);
}

.badge--close-final {
  background: rgba(148, 163, 184, 0.12);
  color: #cbd5e1;
}

.reason-tag {
  color: var(--color-text-muted, #94a3b8);
  font-size: 12px;
}

.empty-trades {
  text-align: center;
  padding: 32px;
  color: #64748b;
}

/* 分页 */
.pagination-bar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding-top: 12px;
}

.page-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--color-bg-input, #0d111a);
  border: 1px solid var(--color-border, #242e42);
  color: var(--color-text, #f1f5f9);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-btn:hover:not(:disabled) {
  border-color: #06b6d4;
  color: #06b6d4;
}

.page-info {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}
</style>
