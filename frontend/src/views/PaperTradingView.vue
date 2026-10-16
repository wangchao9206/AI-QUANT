<script setup lang="ts">
import {
  Activity, AlertTriangle, ArrowDown, ArrowUp, CirclePause, Clock3, Database,
  FastForward, Gauge, History, LoaderCircle, Pause, Play, Plus, RefreshCw,
  RotateCcw, ShieldCheck, StepForward, Trash2, WalletCards, X,
} from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  api,
  type BacktestPresets,
  type CreatePaperSessionRequest,
  type HistoryStatusResponse,
  type MarketMicrostructure,
  type PaperSession,
  type PaperSessionSummary,
  type PlacePaperOrderRequest,
} from '../services/api'
import { formatNumber, formatTime } from '../utils/format'

const sessions = ref<PaperSessionSummary[]>([])
const current = ref<PaperSession | null>(null)
const presets = ref<BacktestPresets | null>(null)
const history = ref<HistoryStatusResponse | null>(null)
const loading = ref(true)
const working = ref(false)
const error = ref('')
const showCreate = ref(false)
const autoplay = ref(false)
let autoplayTimer: number | undefined
const microstructure = ref<MarketMicrostructure | null>(null)
const microError = ref('')
const microLoading = ref(false)
const showDeleteConfirm = ref(false)
let microTimer: number | undefined
let microGeneration = 0

const createForm = ref<CreatePaperSessionRequest>({
  name: '策略验证 01', mode: 'HISTORICAL', symbol: 'CJ0', initialCash: 1_000_000,
  marginRate: 0.12, feeRate: 0.0001, slippageTicks: 1,
  maxParticipationRate: 0.1, autoRoll: true,
})
const order = ref<PlacePaperOrderRequest>({
  clientOrderId: '', side: 'BUY', offset: 'OPEN', orderType: 'MARKET', quantity: 1,
})

const isHistorical = computed(() => current.value?.mode === 'HISTORICAL')
const availableCash = computed(() => current.value
  ? current.value.equity - current.value.position.marginOccupied : 0)
const returnPct = computed(() => current.value
  ? (current.value.equity / current.value.initialCash - 1) * 100 : 0)
const progressPct = computed(() => {
  if (!current.value?.totalBars) return 0
  return Math.min(100, current.value.currentBarIndex / Math.max(1, current.value.totalBars - 1) * 100)
})
const selectedHistory = computed(() => history.value?.symbols.find(item => item.symbol === createForm.value.symbol))
const activeOrders = computed(() => current.value?.orders.filter(item => ['PENDING', 'PARTIAL'].includes(item.status)) ?? [])
const asksDescending = computed(() => [...(microstructure.value?.asks ?? [])].sort((a, b) => b.level - a.level))
const depthMaxVolume = computed(() => Math.max(1, ...[
  ...(microstructure.value?.bids ?? []), ...(microstructure.value?.asks ?? []),
].map(item => item.volume)))

function money(value?: number) {
  return `¥${formatNumber(value, 2)}`
}
function signedMoney(value?: number) {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : '−'}¥${formatNumber(Math.abs(value), 2)}`
}
function setError(cause: unknown, fallback: string) {
  error.value = cause instanceof Error ? cause.message : fallback
}
function updateSession(session: PaperSession) {
  current.value = session
  const index = sessions.value.findIndex(item => item.id === session.id)
  if (index >= 0) sessions.value[index] = session
  else sessions.value.unshift(session)
}

async function selectSession(id: string) {
  working.value = true
  error.value = ''
  try { current.value = await api.paperSession(id) }
  catch (cause) { setError(cause, '读取模拟账户失败') }
  finally { working.value = false }
}

function applyHistoryRange() {
  const range = selectedHistory.value
  if (!range) return
  createForm.value.startDate = range.startDate
  createForm.value.endDate = range.endDate
}

async function createSession() {
  working.value = true
  error.value = ''
  try {
    const body = { ...createForm.value }
    if (body.mode === 'LIVE') {
      delete body.startDate
      delete body.endDate
    }
    const created = await api.createPaperSession(body)
    updateSession(created)
    showCreate.value = false
  } catch (cause) { setError(cause, '创建模拟账户失败') }
  finally { working.value = false }
}

async function placeOrder() {
  if (!current.value) return
  working.value = true
  error.value = ''
  try {
    const payload: PlacePaperOrderRequest = {
      ...order.value,
      clientOrderId: crypto.randomUUID(),
      quantity: Math.max(1, Math.trunc(order.value.quantity)),
    }
    if (payload.orderType !== 'LIMIT') delete payload.limitPrice
    if (payload.orderType !== 'STOP') delete payload.stopPrice
    updateSession(await api.placePaperOrder(current.value.id, payload))
  } catch (cause) { setError(cause, '委托提交失败') }
  finally { working.value = false }
}

async function advance(steps = 1) {
  if (!current.value || working.value) return
  working.value = true
  error.value = ''
  try {
    const updated = await api.advancePaperSession(current.value.id, steps)
    updateSession(updated)
    if (updated.status !== 'ACTIVE') stopAutoplay()
  } catch (cause) {
    stopAutoplay()
    setError(cause, '推进模拟时间失败')
  } finally { working.value = false }
}

function startAutoplay() {
  if (!current.value || current.value.status !== 'ACTIVE') return
  autoplay.value = true
  window.clearInterval(autoplayTimer)
  autoplayTimer = window.setInterval(() => void advance(1), 900)
}
function stopAutoplay() {
  autoplay.value = false
  window.clearInterval(autoplayTimer)
  autoplayTimer = undefined
}
async function togglePaused() {
  if (!current.value) return
  working.value = true
  error.value = ''
  try {
    const updated = current.value.status === 'PAUSED'
      ? await api.resumePaperSession(current.value.id)
      : await api.pausePaperSession(current.value.id)
    updateSession(updated)
    if (updated.status !== 'ACTIVE') stopAutoplay()
  } catch (cause) { setError(cause, '状态切换失败') }
  finally { working.value = false }
}
async function cancelOrder(orderId: string) {
  if (!current.value) return
  working.value = true
  try { updateSession(await api.cancelPaperOrder(current.value.id, orderId)) }
  catch (cause) { setError(cause, '撤单失败') }
  finally { working.value = false }
}

function stopMicrostructure() {
  microGeneration += 1
  window.clearTimeout(microTimer)
  microTimer = undefined
  microLoading.value = false
}

async function refreshMicrostructure(generation: number, contract: string) {
  if (generation !== microGeneration) return
  microLoading.value = !microstructure.value
  try {
    const snapshot = await api.microstructure(contract)
    if (generation === microGeneration) {
      microstructure.value = snapshot
      microError.value = ''
    }
  } catch (cause) {
    if (generation === microGeneration) {
      microError.value = cause instanceof Error ? cause.message : '实时盘口暂不可用'
    }
  } finally {
    if (generation === microGeneration) {
      microLoading.value = false
      microTimer = window.setTimeout(() => void refreshMicrostructure(generation, contract), 1000)
    }
  }
}

function restartMicrostructure() {
  stopMicrostructure()
  microstructure.value = null
  microError.value = ''
  if (current.value?.mode !== 'LIVE') return
  const generation = microGeneration
  void refreshMicrostructure(generation, current.value.currentContract)
}

async function deleteSession() {
  if (!current.value) return
  const deletedId = current.value.id
  working.value = true
  error.value = ''
  stopAutoplay()
  stopMicrostructure()
  try {
    await api.deletePaperSession(deletedId)
    sessions.value = sessions.value.filter(item => item.id !== deletedId)
    showDeleteConfirm.value = false
    current.value = sessions.value.length ? await api.paperSession(sessions.value[0].id) : null
    if (!current.value) showCreate.value = true
  } catch (cause) { setError(cause, '删除试验失败') }
  finally { working.value = false }
}

watch(() => createForm.value.symbol, applyHistoryRange)
watch(current, (value) => {
  if (!value) return
  order.value.limitPrice = value.currentPrice
  order.value.stopPrice = value.currentPrice
})
watch(() => [current.value?.id, current.value?.mode, current.value?.currentContract], restartMicrostructure)

onMounted(async () => {
  try {
    const [loadedSessions, loadedPresets, loadedHistory] = await Promise.all([
      api.paperSessions(), api.backtestPresets(), api.historyStatus(),
    ])
    sessions.value = loadedSessions
    presets.value = loadedPresets
    history.value = loadedHistory
    applyHistoryRange()
    if (loadedSessions.length) current.value = await api.paperSession(loadedSessions[0].id)
    else showCreate.value = true
  } catch (cause) { setError(cause, '模拟交易台初始化失败') }
  finally { loading.value = false }
})
onUnmounted(() => {
  stopAutoplay()
  stopMicrostructure()
})
</script>

<template>
  <div class="paper-page">
    <section class="trust-strip">
      <div><ShieldCheck :size="17" /><strong>仅模拟，不连接实盘交易账户</strong></div>
      <span>行情与历史路径来自 TqSdk；成交、手续费、滑点、保证金和换月独立记账。</span>
    </section>

    <div v-if="error" class="error-banner" role="alert">
      <AlertTriangle :size="17" /><span>{{ error }}</span>
      <button type="button" aria-label="关闭错误提示" @click="error = ''"><X :size="15" /></button>
    </div>

    <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="24" />载入模拟账本…</div>

    <template v-else>
      <section class="session-rail">
        <div class="session-tabs" role="tablist" aria-label="模拟账户">
          <button
            v-for="item in sessions" :key="item.id" type="button" role="tab"
            :aria-selected="current?.id === item.id" :class="{ active: current?.id === item.id }"
            @click="selectSession(item.id)"
          >
            <span class="status-dot" :class="item.status.toLowerCase()" />
            <span><strong>{{ item.name }}</strong><small>{{ item.symbol }} · {{ item.mode === 'LIVE' ? '实时' : '历史' }}</small></span>
          </button>
        </div>
        <button class="new-session" type="button" @click="showCreate = !showCreate"><Plus :size="16" />新建试验</button>
      </section>

      <form v-if="showCreate" class="create-panel" @submit.prevent="createSession">
        <div class="panel-heading"><div><span>NEW EXPERIMENT</span><h2>建立独立模拟账户</h2></div><button type="button" @click="showCreate = false"><X :size="17" /></button></div>
        <div class="form-grid">
          <label><span>试验名称</span><input v-model.trim="createForm.name" maxlength="80" required /></label>
          <label><span>时间模式</span><select v-model="createForm.mode"><option value="HISTORICAL">历史时点回放</option><option value="LIVE">实时仿真</option></select></label>
          <label><span>期货品种</span><select v-model="createForm.symbol"><option v-for="item in presets?.symbols" :key="item.symbol" :value="item.symbol">{{ item.symbol }} · {{ item.name }}</option></select></label>
          <label><span>初始资金</span><input v-model.number="createForm.initialCash" type="number" min="1000" step="1000" required /></label>
          <label v-if="createForm.mode === 'HISTORICAL'"><span>开始日期</span><input v-model="createForm.startDate" type="date" :min="selectedHistory?.startDate" :max="selectedHistory?.endDate" required /></label>
          <label v-if="createForm.mode === 'HISTORICAL'"><span>结束日期</span><input v-model="createForm.endDate" type="date" :min="selectedHistory?.startDate" :max="selectedHistory?.endDate" required /></label>
          <label><span>保证金率</span><input v-model.number="createForm.marginRate" type="number" min="0.01" max="1" step="0.01" /></label>
          <label><span>滑点（tick）</span><input v-model.number="createForm.slippageTicks" type="number" min="0" max="100" step="0.5" /></label>
        </div>
        <label class="check"><input v-model="createForm.autoRoll" type="checkbox" /><span><strong>主力切换时自动移仓</strong><small>使用新旧合约真实价格分别平仓、开仓，并计入双边成本</small></span></label>
        <div class="create-actions"><span v-if="selectedHistory">可用真实数据：{{ selectedHistory.startDate }} — {{ selectedHistory.endDate }} · {{ selectedHistory.totalBars }} 条</span><button class="primary" :disabled="working"><LoaderCircle v-if="working" class="spin" :size="15" />创建账户</button></div>
      </form>

      <div v-if="current" class="terminal-grid">
        <main class="ledger">
          <header class="market-header">
            <div>
              <div class="market-title"><span class="mode-badge">{{ current.mode === 'LIVE' ? 'LIVE PAPER' : 'HISTORICAL' }}</span><span class="state-badge" :class="current.status.toLowerCase()">{{ current.status }}</span></div>
              <h2>{{ current.currentContract }} <strong>{{ formatNumber(current.currentPrice, 2) }}</strong></h2>
              <p><Database :size="14" />{{ current.dataSource }} · {{ formatTime(current.currentMarketTime) }}</p>
            </div>
            <div class="playback">
              <button v-if="isHistorical" type="button" title="推进一根K线" :disabled="working || current.status !== 'ACTIVE'" @click="advance(1)"><StepForward :size="17" />单步</button>
              <button v-if="isHistorical" type="button" title="推进五根K线" :disabled="working || current.status !== 'ACTIVE'" @click="advance(5)"><FastForward :size="17" />5步</button>
              <button v-if="isHistorical" type="button" :disabled="current.status !== 'ACTIVE'" @click="autoplay ? stopAutoplay() : startAutoplay()"><Pause v-if="autoplay" :size="17" /><Play v-else :size="17" />{{ autoplay ? '停止' : '播放' }}</button>
              <button v-else type="button" :disabled="working" @click="advance(1)"><RefreshCw :class="{ spin: working }" :size="17" />刷新实盘行情</button>
              <button v-if="['ACTIVE', 'PAUSED'].includes(current.status)" type="button" @click="togglePaused"><Play v-if="current.status === 'PAUSED'" :size="17" /><CirclePause v-else :size="17" />{{ current.status === 'PAUSED' ? '恢复' : '暂停' }}</button>
              <button class="delete-trigger" type="button" title="删除当前试验" @click="showDeleteConfirm = true"><Trash2 :size="16" />删除</button>
            </div>
          </header>

          <div v-if="isHistorical" class="timeline"><span :style="{ width: `${progressPct}%` }" /><div><small>{{ current.currentBarIndex + 1 }} / {{ current.totalBars }}</small><small>{{ progressPct.toFixed(1) }}%</small></div></div>

          <section class="metrics">
            <article><span><WalletCards :size="15" />账户权益</span><strong>{{ money(current.equity) }}</strong><small :class="returnPct >= 0 ? 'up' : 'down'">{{ returnPct >= 0 ? '+' : '' }}{{ returnPct.toFixed(2) }}%</small></article>
            <article><span><Gauge :size="15" />可用资金</span><strong>{{ money(availableCash) }}</strong><small>占用 {{ money(current.position.marginOccupied) }}</small></article>
            <article><span><Activity :size="15" />浮动盈亏</span><strong :class="current.position.unrealizedPnl >= 0 ? 'up' : 'down'">{{ signedMoney(current.position.unrealizedPnl) }}</strong><small>已实现 {{ signedMoney(current.realizedPnl) }}</small></article>
            <article><span><RotateCcw :size="15" />交易成本</span><strong>{{ money(current.commissionPaid + current.slippagePaid) }}</strong><small>手续费 + 滑点</small></article>
          </section>

          <section v-if="current.mode === 'LIVE'" class="microstructure-section">
            <div class="section-title micro-title">
              <div><span>LIVE MICROSTRUCTURE</span><h3>五档盘口与成交明细</h3></div>
              <small v-if="microstructure"><i :class="microstructure.dataStatus.toLowerCase()" />{{ microstructure.source }} · {{ formatTime(microstructure.dataTimestamp) }}</small>
              <small v-else><LoaderCircle v-if="microLoading" class="spin" :size="13" />{{ microError || '正在订阅天勤实时盘口…' }}</small>
            </div>
            <div class="micro-grid">
              <article class="depth-panel">
                <header><span>档位</span><span>价格</span><span>挂单量</span></header>
                <div v-for="level in asksDescending" :key="`ask-${level.level}`" class="depth-row ask">
                  <i :style="{ width: `${level.volume / depthMaxVolume * 100}%` }" />
                  <span>卖{{ level.level }}</span><strong>{{ level.price == null ? '—' : formatNumber(level.price, 2) }}</strong><b>{{ level.volume || '—' }}</b>
                </div>
                <div class="last-price"><span>最新</span><strong>{{ formatNumber(microstructure?.lastPrice, 2) }}</strong><small>{{ current.currentContract }}</small></div>
                <div v-for="level in microstructure?.bids ?? []" :key="`bid-${level.level}`" class="depth-row bid">
                  <i :style="{ width: `${level.volume / depthMaxVolume * 100}%` }" />
                  <span>买{{ level.level }}</span><strong>{{ level.price == null ? '—' : formatNumber(level.price, 2) }}</strong><b>{{ level.volume || '—' }}</b>
                </div>
                <div v-if="!microstructure" class="micro-placeholder">{{ microError || '等待第一帧真实盘口' }}</div>
              </article>
              <article class="tape-panel">
                <header><span>时间</span><span>价格</span><span>成交量</span><span>增仓</span></header>
                <div class="tape-scroll">
                  <div v-for="trade in microstructure?.trades ?? []" :key="`${trade.id}-${trade.timestamp}`" class="tape-row" :class="trade.side.toLowerCase()">
                    <time>{{ new Date(trade.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) }}</time>
                    <strong>{{ formatNumber(trade.price, 2) }}</strong>
                    <b>{{ trade.volume }}</b>
                    <span :class="trade.openInterestChange >= 0 ? 'up' : 'down'">{{ trade.openInterestChange > 0 ? '+' : '' }}{{ trade.openInterestChange }}</span>
                  </div>
                  <div v-if="microstructure && !microstructure.trades.length" class="micro-placeholder">当前时段尚无新增成交</div>
                  <div v-else-if="!microstructure" class="micro-placeholder">逐笔成交将在订阅完成后出现</div>
                </div>
              </article>
            </div>
            <p class="micro-footnote">成交方向依据该 Tick 成交价相对当时买一/卖一推断；无法可靠判断时显示为中性。所有空档均保持为空，不补造价格。</p>
          </section>

          <section v-else class="historical-depth-note">
            <Database :size="16" /><div><strong>历史模式不伪造五档盘口</strong><span>历史交易继续使用真实日线与换月双腿；实时五档和逐笔仅在实时仿真账户中提供。</span></div>
          </section>

          <section class="position-card">
            <div class="section-title"><div><span>POSITION</span><h3>当前持仓</h3></div><small>合约乘数 {{ current.volumeMultiple }} · 最小变动 {{ current.priceTick }}</small></div>
            <div v-if="current.position.lots" class="position-row">
              <span class="direction" :class="current.position.direction > 0 ? 'long' : 'short'">{{ current.position.direction > 0 ? '多' : '空' }}</span>
              <strong>{{ current.position.contract }}</strong><span>{{ current.position.lots }} 手</span><span>均价 {{ formatNumber(current.position.averagePrice, 2) }}</span><span>市价 {{ formatNumber(current.currentPrice, 2) }}</span><b :class="current.position.unrealizedPnl >= 0 ? 'up' : 'down'">{{ signedMoney(current.position.unrealizedPnl) }}</b>
            </div>
            <div v-else class="empty-line">当前无持仓。委托在真实行情路径上按撮合规则执行。</div>
          </section>

          <section class="records">
            <div class="section-title"><div><span>EXECUTIONS</span><h3>成交与换月流水</h3></div><small>最近 200 条</small></div>
            <div class="table-wrap"><table><thead><tr><th>时间</th><th>事件</th><th>合约</th><th>方向</th><th>手数</th><th>行情价</th><th>成交价</th><th>费用</th><th>已实现盈亏</th></tr></thead>
              <tbody><tr v-for="fill in current.fills" :key="fill.id"><td>{{ formatTime(fill.marketTime) }}</td><td><span class="event-tag" :class="{ roll: fill.eventType === 'ROLL' }">{{ fill.eventType === 'ROLL' ? '换月' : '成交' }}</span></td><td>{{ fill.contract }}</td><td :class="fill.side === 'BUY' ? 'up' : 'down'">{{ fill.side === 'BUY' ? '买' : '卖' }} / {{ fill.offset === 'OPEN' ? '开' : '平' }}</td><td>{{ fill.quantity }}</td><td>{{ formatNumber(fill.marketPrice, 2) }}</td><td>{{ formatNumber(fill.fillPrice, 2) }}</td><td>{{ money(fill.fee + fill.slippageCost) }}</td><td :class="fill.realizedPnl >= 0 ? 'up' : 'down'">{{ signedMoney(fill.realizedPnl) }}</td></tr>
              <tr v-if="!current.fills.length"><td colspan="9" class="empty-cell">尚无成交记录</td></tr></tbody></table></div>
          </section>
        </main>

        <aside class="order-ticket">
          <div class="ticket-head"><div><span>ORDER TICKET</span><h3>模拟下单</h3></div><Clock3 :size="18" /></div>
          <div class="segmented"><button type="button" :class="{ selected: order.side === 'BUY' }" @click="order.side = 'BUY'"><ArrowUp :size="15" />买入</button><button type="button" :class="{ selected: order.side === 'SELL' }" @click="order.side = 'SELL'"><ArrowDown :size="15" />卖出</button></div>
          <div class="segmented subtle"><button type="button" :class="{ selected: order.offset === 'OPEN' }" @click="order.offset = 'OPEN'">开仓</button><button type="button" :class="{ selected: order.offset === 'CLOSE' }" @click="order.offset = 'CLOSE'">平仓</button></div>
          <label><span>委托类型</span><select v-model="order.orderType"><option value="MARKET">市价单</option><option value="LIMIT">限价单</option><option value="STOP">止损触发单</option></select></label>
          <label><span>手数</span><input v-model.number="order.quantity" type="number" min="1" max="1000000" /></label>
          <label v-if="order.orderType === 'LIMIT'"><span>限价</span><input v-model.number="order.limitPrice" type="number" min="0" :step="current.priceTick" /></label>
          <label v-if="order.orderType === 'STOP'"><span>触发价</span><input v-model.number="order.stopPrice" type="number" min="0" :step="current.priceTick" /></label>
          <div class="estimate"><span>当前合约</span><strong>{{ current.currentContract }}</strong><span>参考价</span><strong>{{ formatNumber(current.currentPrice, 2) }}</strong><span>每手保证金参考</span><strong>{{ money(Math.max(current.marginPerLot, current.currentPrice * current.volumeMultiple * current.marginRate)) }}</strong></div>
          <button class="submit-order" :class="order.side.toLowerCase()" type="button" :disabled="working || current.status !== 'ACTIVE'" @click="placeOrder"><LoaderCircle v-if="working" class="spin" :size="16" />{{ order.side === 'BUY' ? '提交买入' : '提交卖出' }}{{ order.offset === 'OPEN' ? '开仓' : '平仓' }}</button>
          <p class="execution-note">{{ isHistorical ? '历史模式下，委托最早从下一根 K 线撮合，避免使用下单时不可知的未来价格。' : '实时模式使用天勤当前行情模拟成交，始终不会向真实经纪账户发送委托。' }}</p>

          <div class="pending"><div class="pending-title"><span>待成交委托</span><b>{{ activeOrders.length }}</b></div><article v-for="item in activeOrders" :key="item.id"><div><strong>{{ item.side === 'BUY' ? '买' : '卖' }}{{ item.offset === 'OPEN' ? '开' : '平' }} · {{ item.orderType }}</strong><small>{{ item.remainingQuantity }}/{{ item.quantity }} 手</small></div><button type="button" @click="cancelOrder(item.id)">撤单</button></article><p v-if="!activeOrders.length">暂无活动委托</p></div>
        </aside>
      </div>

      <section v-else-if="!showCreate" class="empty-state"><History :size="28" /><h2>还没有模拟账户</h2><p>创建一个实时仿真或指定历史时点的独立试验。</p><button class="primary" type="button" @click="showCreate = true"><Plus :size="16" />新建试验</button></section>
    </template>

    <div v-if="showDeleteConfirm && current" class="modal-backdrop" role="presentation" @click.self="showDeleteConfirm = false">
      <section class="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title">
        <div class="delete-icon"><Trash2 :size="20" /></div>
        <div><span>IRREVERSIBLE ACTION</span><h2 id="delete-title">删除“{{ current.name }}”？</h2></div>
        <p>此操作会永久删除该试验的行情路径、委托、持仓、成交与换月流水，无法恢复。</p>
        <div class="dialog-actions"><button type="button" @click="showDeleteConfirm = false">取消</button><button class="confirm-delete" type="button" :disabled="working" @click="deleteSession"><LoaderCircle v-if="working" class="spin" :size="15" />永久删除</button></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.paper-page { display: grid; gap: 1rem; }
.trust-strip { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .75rem 1rem; color: #405259; border: 1px solid #cfdcdf; border-radius: .8rem; background: #edf4f4; font-size: .75rem; }
.trust-strip div { display: flex; align-items: center; gap: .45rem; color: #183a45; }
.error-banner { display: flex; align-items: center; gap: .6rem; padding: .8rem 1rem; color: #7b2f28; border: 1px solid #e8c1bb; border-radius: .8rem; background: #fff0ed; font-size: .78rem; }
.error-banner span { flex: 1; }.error-banner button,.panel-heading button { display: grid; place-items: center; padding: .3rem; border: 0; background: transparent; cursor: pointer; }
.loading-state,.empty-state { display: grid; min-height: 20rem; place-items: center; align-content: center; gap: .8rem; color: var(--color-ink-secondary); }
.session-rail { display: flex; align-items: stretch; gap: .8rem; min-width: 0; }
.session-tabs { display: flex; flex: 1; gap: .45rem; min-width: 0; overflow-x: auto; scrollbar-width: thin; }
.session-tabs button { display: flex; flex: 0 0 auto; min-width: 11rem; align-items: center; gap: .6rem; padding: .7rem .85rem; color: var(--color-ink-secondary); border: 1px solid var(--color-line); border-radius: .75rem; background: rgb(255 255 255 / 45%); cursor: pointer; text-align: left; }
.session-tabs button.active { color: var(--color-ink); border-color: #aebfc8; background: white; box-shadow: 0 5px 16px rgb(20 35 44 / 7%); }.session-tabs button span:nth-child(2) { display: grid; gap: .12rem; }.session-tabs strong { font-size: .76rem; }.session-tabs small { color: var(--color-ink-tertiary); font-size: .63rem; }
.status-dot { width: .44rem; height: .44rem; border-radius: 50%; background: #8b8d90; }.status-dot.active { background: var(--color-success); box-shadow: 0 0 0 3px var(--color-success-soft); }.status-dot.error { background: #b33d33; }.status-dot.paused { background: #b1842d; }
.new-session,.playback button { display: inline-flex; align-items: center; justify-content: center; gap: .4rem; padding: .7rem .85rem; color: #263239; border: 1px solid var(--color-line); border-radius: .7rem; background: white; cursor: pointer; font-size: .72rem; font-weight: 650; white-space: nowrap; }
.create-panel,.ledger,.order-ticket { border: 1px solid var(--color-line); border-radius: 1rem; background: var(--color-surface-raised); box-shadow: var(--shadow-raised); }
.create-panel { padding: 1.25rem; }.panel-heading,.section-title,.ticket-head { display: flex; align-items: center; justify-content: space-between; }.panel-heading span,.section-title span,.ticket-head span { color: var(--color-ink-tertiary); font: 650 .58rem var(--font-numeric); letter-spacing: .13em; }.panel-heading h2,.section-title h3,.ticket-head h3 { margin: .2rem 0 0; font: 500 1.15rem var(--font-display); }
.form-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .85rem; margin-top: 1rem; }.form-grid label,.order-ticket > label { display: grid; gap: .35rem; color: var(--color-ink-secondary); font-size: .68rem; }
input,select { width: 100%; min-height: 2.45rem; padding: 0 .7rem; color: var(--color-ink); border: 1px solid var(--color-line); border-radius: .55rem; outline: none; background: #fafaf8; font: 500 .75rem var(--font-sans); } input:focus,select:focus { border-color: var(--color-accent); box-shadow: var(--shadow-focus); }
.check { display: flex; align-items: center; gap: .65rem; margin-top: 1rem; }.check input { width: 1rem; min-height: 1rem; }.check span { display: grid; gap: .1rem; }.check strong { font-size: .73rem; }.check small { color: var(--color-ink-tertiary); font-size: .64rem; }.create-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 1rem; color: var(--color-ink-tertiary); font-size: .65rem; }
.primary { display: inline-flex; align-items: center; gap: .4rem; padding: .7rem 1rem; color: white; border: 0; border-radius: .65rem; background: #245b79; cursor: pointer; font-size: .72rem; font-weight: 700; }
.terminal-grid { display: grid; grid-template-columns: minmax(0, 1fr) 18rem; align-items: start; gap: 1rem; }.ledger { min-width: 0; overflow: hidden; }.market-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1.25rem; border-bottom: 1px solid var(--color-line); }.market-title { display: flex; gap: .4rem; }.mode-badge,.state-badge,.event-tag { display: inline-flex; padding: .2rem .42rem; border-radius: .3rem; background: #e8eef1; font: 700 .52rem var(--font-numeric); letter-spacing: .06em; }.state-badge.active { color: #236039; background: #e5f2e8; }.state-badge.paused { color: #75591e; background: #f4eacc; }.state-badge.error { color: #903a32; background: #f7dfdc; }
.market-header h2 { display: flex; align-items: baseline; gap: .7rem; margin: .5rem 0 .2rem; font: 600 1rem var(--font-numeric); }.market-header h2 strong { font-size: 1.85rem; }.market-header p { display: flex; align-items: center; gap: .35rem; margin: 0; color: var(--color-ink-tertiary); font-size: .66rem; }.playback { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .4rem; }.playback button { padding: .52rem .65rem; }.playback button:disabled,.submit-order:disabled,.primary:disabled { opacity: .45; cursor: not-allowed; }
.playback .delete-trigger { color: #8a342d; border-color: #e3c5c1; background: #fff8f6; }
.timeline { height: 2px; background: #e8e7e2; }.timeline > span { display: block; height: 100%; background: var(--color-accent); transition: width .25s; }.timeline div { display: flex; justify-content: space-between; padding: .35rem 1.25rem; color: var(--color-ink-tertiary); font: .56rem var(--font-numeric); }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); padding: 1.5rem 1.25rem 1rem; }.metrics article { display: grid; gap: .32rem; padding: .1rem 1rem; border-right: 1px solid var(--color-line); }.metrics article:first-child { padding-left: 0; }.metrics article:last-child { border: 0; }.metrics span { display: flex; align-items: center; gap: .35rem; color: var(--color-ink-tertiary); font-size: .64rem; }.metrics strong { font: 650 1.1rem var(--font-numeric); }.metrics small { color: var(--color-ink-tertiary); font-size: .6rem; }
.microstructure-section { margin: 1.1rem 1.25rem; padding-top: 1.1rem; border-top: 1px solid var(--color-line); }.micro-title small { display: flex; align-items: center; gap: .35rem; }.micro-title small i { width: .42rem; height: .42rem; border-radius: 50%; background: #96989b; }.micro-title small i.fresh { background: var(--color-success); box-shadow: 0 0 0 3px var(--color-success-soft); }.micro-grid { display: grid; grid-template-columns: minmax(17rem, .9fr) minmax(20rem, 1.35fr); gap: .8rem; margin-top: .8rem; }.depth-panel,.tape-panel { min-width: 0; overflow: hidden; border: 1px solid var(--color-line); border-radius: .72rem; background: #fbfbf9; }.depth-panel header,.tape-panel header { display: grid; padding: .48rem .65rem; color: var(--color-ink-tertiary); border-bottom: 1px solid var(--color-line); background: #f1f1ee; font: 600 .55rem var(--font-numeric); }.depth-panel header { grid-template-columns: 3rem 1fr 4.2rem; text-align: right; }.depth-panel header span:first-child { text-align: left; }.depth-row { position: relative; display: grid; grid-template-columns: 3rem 1fr 4.2rem; min-height: 1.62rem; align-items: center; padding: 0 .65rem; font: .61rem var(--font-numeric); }.depth-row i { position: absolute; z-index: 0; top: 2px; right: 0; bottom: 2px; opacity: .48; }.depth-row.ask i { background: var(--color-negative-soft); }.depth-row.bid i { background: var(--color-positive-soft); }.depth-row span,.depth-row strong,.depth-row b { position: relative; z-index: 1; }.depth-row span { color: var(--color-ink-tertiary); }.depth-row strong,.depth-row b { text-align: right; }.depth-row.ask strong { color: var(--color-negative); }.depth-row.bid strong { color: var(--color-positive); }.last-price { display: grid; grid-template-columns: 3rem 1fr 4.2rem; align-items: baseline; padding: .52rem .65rem; border-block: 1px solid var(--color-line); background: white; }.last-price span,.last-price small { color: var(--color-ink-tertiary); font-size: .57rem; }.last-price strong { text-align: right; font: 700 .86rem var(--font-numeric); }.last-price small { text-align: right; }.tape-panel header { grid-template-columns: 1.4fr 1fr .8fr .8fr; text-align: right; }.tape-panel header span:first-child { text-align: left; }.tape-scroll { max-height: 19rem; overflow-y: auto; }.tape-row { display: grid; grid-template-columns: 1.4fr 1fr .8fr .8fr; align-items: center; min-height: 1.75rem; padding: 0 .65rem; border-bottom: 1px solid #efeee9; font: .59rem var(--font-numeric); text-align: right; }.tape-row time { color: var(--color-ink-tertiary); text-align: left; }.tape-row.buy strong { color: var(--color-positive); }.tape-row.sell strong { color: var(--color-negative); }.tape-row.neutral strong { color: var(--color-ink-secondary); }.micro-placeholder { display: grid; min-height: 5rem; place-items: center; padding: 1rem; color: var(--color-ink-tertiary); font-size: .64rem; text-align: center; }.micro-footnote { margin: .65rem 0 0; color: var(--color-ink-tertiary); font-size: .58rem; line-height: 1.55; }.historical-depth-note { display: flex; align-items: flex-start; gap: .6rem; margin: 1.1rem 1.25rem; padding: .8rem; color: #516168; border: 1px solid #d7e0e1; border-radius: .7rem; background: #f2f6f6; }.historical-depth-note div { display: grid; gap: .18rem; }.historical-depth-note strong { font-size: .68rem; }.historical-depth-note span { color: #748086; font-size: .6rem; line-height: 1.5; }
.position-card,.records { margin: 1.1rem 1.25rem; padding-top: 1.1rem; border-top: 1px solid var(--color-line); }.section-title small { color: var(--color-ink-tertiary); font-size: .61rem; }.position-row { display: grid; grid-template-columns: 2rem 1fr repeat(4, auto); align-items: center; gap: 1rem; margin-top: .85rem; padding: .8rem; border-radius: .7rem; background: #f7f6f2; font: .7rem var(--font-numeric); }.direction { display: grid; width: 1.6rem; height: 1.6rem; place-items: center; color: white; border-radius: .38rem; font: 700 .64rem var(--font-sans); }.direction.long { background: var(--color-positive); }.direction.short { background: var(--color-negative); }.empty-line { margin-top: .8rem; padding: 1rem; color: var(--color-ink-tertiary); border: 1px dashed var(--color-line-strong); border-radius: .7rem; font-size: .7rem; text-align: center; }
.table-wrap { margin-top: .75rem; overflow-x: auto; }table { width: 100%; border-collapse: collapse; white-space: nowrap; }th { padding: .55rem .6rem; color: var(--color-ink-tertiary); border-bottom: 1px solid var(--color-line); font-size: .57rem; font-weight: 650; text-align: right; }th:first-child,th:nth-child(2),th:nth-child(3),td:first-child,td:nth-child(2),td:nth-child(3) { text-align: left; }td { padding: .68rem .6rem; border-bottom: 1px solid #efeee9; font: .61rem var(--font-numeric); text-align: right; }.event-tag.roll { color: #654c20; background: #f3e6c7; }.empty-cell { color: var(--color-ink-tertiary); text-align: center !important; }
.order-ticket { position: sticky; top: 1rem; display: grid; gap: .8rem; padding: 1rem; }.ticket-head { padding-bottom: .25rem; }.segmented { display: grid; grid-template-columns: 1fr 1fr; padding: .2rem; border-radius: .65rem; background: #eff0ef; }.segmented button { display: flex; min-height: 2.25rem; align-items: center; justify-content: center; gap: .35rem; color: var(--color-ink-secondary); border: 0; border-radius: .48rem; background: transparent; cursor: pointer; font-size: .71rem; font-weight: 650; }.segmented button.selected { color: var(--color-ink); background: white; box-shadow: 0 1px 5px rgb(0 0 0 / 9%); }.segmented:not(.subtle) button:first-child.selected { color: var(--color-positive); }.segmented:not(.subtle) button:last-child.selected { color: var(--color-negative); }.estimate { display: grid; grid-template-columns: 1fr auto; gap: .4rem; padding: .75rem; border-radius: .65rem; background: #f6f5f1; font-size: .63rem; }.estimate span { color: var(--color-ink-tertiary); }.estimate strong { font-family: var(--font-numeric); font-size: .64rem; }.submit-order { display: flex; min-height: 2.7rem; align-items: center; justify-content: center; gap: .4rem; color: white; border: 0; border-radius: .65rem; cursor: pointer; font-size: .75rem; font-weight: 700; }.submit-order.buy { background: var(--color-positive); }.submit-order.sell { background: var(--color-negative); }.execution-note { margin: 0; color: var(--color-ink-tertiary); font-size: .6rem; line-height: 1.55; }.pending { display: grid; gap: .5rem; padding-top: .8rem; border-top: 1px solid var(--color-line); }.pending-title { display: flex; justify-content: space-between; color: var(--color-ink-secondary); font-size: .68rem; }.pending-title b { font-family: var(--font-numeric); }.pending article { display: flex; align-items: center; justify-content: space-between; padding: .6rem; border: 1px solid var(--color-line); border-radius: .55rem; }.pending article div { display: grid; gap: .15rem; }.pending article strong { font-size: .65rem; }.pending article small,.pending > p { margin: 0; color: var(--color-ink-tertiary); font-size: .58rem; }.pending article button { padding: .25rem .4rem; color: #8a342d; border: 1px solid #e4c4c0; border-radius: .35rem; background: #fff5f3; cursor: pointer; font-size: .58rem; }
.up { color: var(--color-positive) !important; }.down { color: var(--color-negative) !important; }.spin { animation: spin .8s linear infinite; }@keyframes spin { to { transform: rotate(360deg); } }
.modal-backdrop { position: fixed; z-index: 100; inset: 0; display: grid; place-items: center; padding: 1rem; background: rgb(20 22 24 / 48%); backdrop-filter: blur(5px); }.delete-dialog { display: grid; width: min(100%, 27rem); gap: 1rem; padding: 1.4rem; border: 1px solid #d8c5c1; border-radius: 1rem; background: #fffdfa; box-shadow: 0 24px 70px rgb(20 22 24 / 28%); }.delete-icon { display: grid; width: 2.3rem; height: 2.3rem; place-items: center; color: #973d34; border-radius: .65rem; background: #f8e5e1; }.delete-dialog span { color: #a36d65; font: 700 .55rem var(--font-numeric); letter-spacing: .12em; }.delete-dialog h2 { margin: .25rem 0 0; font: 500 1.35rem var(--font-display); }.delete-dialog p { margin: 0; color: var(--color-ink-secondary); font-size: .72rem; line-height: 1.65; }.dialog-actions { display: flex; justify-content: flex-end; gap: .5rem; }.dialog-actions button { display: inline-flex; min-height: 2.35rem; align-items: center; gap: .4rem; padding: 0 .8rem; border: 1px solid var(--color-line); border-radius: .55rem; background: white; cursor: pointer; font-size: .68rem; font-weight: 650; }.dialog-actions .confirm-delete { color: white; border-color: #963e35; background: #963e35; }
@media (max-width: 1100px) { .terminal-grid { grid-template-columns: 1fr; }.order-ticket { position: static; grid-template-columns: repeat(2, 1fr); }.ticket-head,.submit-order,.execution-note,.pending { grid-column: 1 / -1; }.form-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) { .micro-grid { grid-template-columns: 1fr; }.tape-scroll { max-height: 14rem; } }
@media (max-width: 760px) { .trust-strip { align-items: flex-start; flex-direction: column; }.session-rail,.market-header,.create-actions { align-items: stretch; flex-direction: column; }.new-session { min-height: 2.6rem; }.metrics { grid-template-columns: repeat(2, 1fr); gap: 1rem; }.metrics article:nth-child(2) { border: 0; }.position-row { grid-template-columns: 2rem 1fr auto; }.position-row span:nth-of-type(n+3),.position-row b { grid-column: span 1; }.order-ticket { grid-template-columns: 1fr; }.ticket-head,.submit-order,.execution-note,.pending { grid-column: auto; } }
@media (max-width: 520px) { .form-grid,.metrics { grid-template-columns: 1fr; }.metrics article { padding: .6rem 0; border-right: 0; border-bottom: 1px solid var(--color-line); }.market-header h2 strong { font-size: 1.5rem; }.playback { justify-content: flex-start; }.position-row { grid-template-columns: 2rem 1fr; } }
</style>
