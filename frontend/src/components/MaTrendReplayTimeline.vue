<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { FastForward, Pause, Play, StepBack, StepForward } from 'lucide-vue-next'
import ReplayReviewPanel from './ReplayReviewPanel.vue'
import TongdaxinChart from './TongdaxinChart.vue'
import type { HistoryPoint } from '../services/api'
import type { ReplayReviewContext, ReplayReviewTarget } from '../services/replayReviews'
import type { MaTrendReplay, WorkflowVersion } from '../services/workflows'
import { formatTradingDateTime } from '../utils/format'

const props = defineProps<{ replay: MaTrendReplay; version: WorkflowVersion; symbol: string; disabled?: boolean }>()
const emit = defineEmits<{ 'end-state': [finished: boolean] }>()

const frameIndex = ref(0)
const farthestIndex = ref(0)
const playing = ref(false)
const reviewEditing = ref(false)
const delay = ref(450)
let timer: number | undefined

const frames = computed(() => props.replay.reviewTimeline ?? [])
const frame = computed(() => frames.value[frameIndex.value])
const finished = computed(() => frames.value.length > 0 && frameIndex.value === frames.value.length - 1)
const controlsDisabled = computed(() => props.disabled || reviewEditing.value)
const historyPoints = computed<HistoryPoint[]>(() => frames.value.slice(Math.max(0, frameIndex.value - 74), frameIndex.value + 1)
  .map(bar => ({ timestamp: bar.at, price: bar.close, open: bar.open, high: bar.high, low: bar.low,
    volume: bar.volume, contract: props.symbol, changePct: 0, changePctKnown: false })))
const fills = computed(() => (frame.value?.executionIndexes ?? []).flatMap(index => {
  const row = props.replay.executions[index]
  return row ? [{ ...row, index }] : []
}))
const reviewContext = computed<ReplayReviewContext|undefined>(() => props.replay.reviewRunId
  ? { kind:'workflow', id:props.version.id, reviewRunId:props.replay.reviewRunId } : undefined)
const reviewTargets = computed<ReplayReviewTarget[]>(() => {
  const at = frame.value?.at
  return at ? fills.value.map(fill => ({ id:String(fill.index), at,
    label:`${actionLabel(fill.action)} · ${directionLabel(fill.direction)} ${fill.lots} 手 @ ${number.format(fill.price)}` })) : []
})

const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits:2 })
const actionLabels: Record<string,string> = {
  HOLD:'维持', WAIT:'等待确认', OPEN:'开仓', ADD:'加仓', TAKE_PROFIT:'减半止盈', REVERSAL_CLOSE:'反手平仓', TERMINAL_CLOSE:'期末平仓',
}
const triggerLabels: Record<string,string> = { LONG_CROSS:'MA5 上穿 MA20', SHORT_CROSS:'MA5 下穿 MA20', LONG_REENTRY:'收敛后 MA5 上穿 MA10' }
const actionLabel = (value: string) => actionLabels[value] ?? value
const directionLabel = (value: number) => value > 0 ? '多头' : value < 0 ? '空头' : '空仓'
const trendLabel = (value: number) => value > 0 ? '偏多' : value < 0 ? '偏空' : '中性'
const macdLabel = (value?: string|null) => value === 'GOLD' ? '金叉' : value === 'DEATH' ? '死叉' : '无交叉'

function stopTimer() {
  if (timer !== undefined) window.clearInterval(timer)
  timer = undefined
}

function pause() { playing.value = false; stopTimer() }

function moveTo(index: number) {
  if (!frames.value.length || controlsDisabled.value) return
  frameIndex.value = Math.min(Math.max(index, 0), frames.value.length - 1)
  farthestIndex.value = Math.max(farthestIndex.value, frameIndex.value)
  if (finished.value) pause()
}

function step(delta: number) { pause(); moveTo(frameIndex.value + delta) }

function seek(event: Event) {
  const input = event.target as HTMLInputElement
  if (!Number.isInteger(input.valueAsNumber)) return
  pause()
  moveTo(Math.min(farthestIndex.value, input.valueAsNumber))
}

function jump() {
  pause()
  const events = new Set(['OPEN', 'ADD', 'REVERSAL_CLOSE', 'TAKE_PROFIT'])
  const next = frames.value.findIndex((bar, index) => index > frameIndex.value
    && (bar.executionIndexes.length > 0 || events.has(bar.signal)))
  moveTo(next >= 0 ? next : frames.value.length - 1)
}

watch([playing, delay], () => {
  stopTimer()
  if (playing.value && !finished.value && !controlsDisabled.value) {
    timer = window.setInterval(() => {
      if (!document.hidden) moveTo(frameIndex.value + 1)
    }, delay.value)
  }
})
watch(controlsDisabled, disabled => { if (disabled) pause() })
watch(() => props.replay, () => { pause(); frameIndex.value = 0; farthestIndex.value = 0; reviewEditing.value = false })
watch(finished, value => emit('end-state', value), { immediate:true })
onUnmounted(stopTimer)
</script>

<template>
  <section v-if="frame" class="timeline" aria-label="逐根回放">
    <div class="timeline-top">
      <div class="timeline-clock">
        <span>15 分钟收盘 · {{ frame.tradingDate }} 交易日</span>
        <strong data-test="replay-cursor">{{ formatTradingDateTime(frame.at) }}</strong>
      </div>
      <span class="timeline-progress">{{ finished ? '回放结束' : playing ? '自动播放中' : '已暂停' }} · {{ frameIndex + 1 }} / {{ frames.length }} 根</span>
    </div>

    <div class="timeline-controls" aria-label="回放控制">
      <button class="primary" type="button" :disabled="controlsDisabled||finished" @click="playing ? pause() : playing=true">
        <Pause v-if="playing" :size="15" aria-hidden="true" /><Play v-else :size="15" aria-hidden="true" />
        {{ playing ? '暂停' : '自动播放' }}
      </button>
      <button type="button" :disabled="controlsDisabled||frameIndex===0" @click="step(-1)"><StepBack :size="15" aria-hidden="true" />前一根</button>
      <button type="button" :disabled="controlsDisabled||finished" @click="step(1)"><StepForward :size="15" aria-hidden="true" />后一根</button>
      <button type="button" :disabled="controlsDisabled||finished" @click="jump"><FastForward :size="15" aria-hidden="true" />下一信号或成交</button>
      <label class="timeline-speed">速度<select v-model.number="delay" :disabled="controlsDisabled"><option :value="900">慢</option><option :value="450">标准</option><option :value="120">快</option></select></label>
    </div>
    <label v-if="farthestIndex>0" class="timeline-seek">
      <span>已回放区间</span><input type="range" :max="farthestIndex" :value="frameIndex" min="0" step="1" :aria-valuetext="formatTradingDateTime(frame.at)" :disabled="controlsDisabled" @input="seek" />
    </label>

    <TongdaxinChart :points="historyPoints" :symbol="symbol" :display-name="`${symbol} · 15 分钟`" :height="245" :show-sub-chart="false" :initial-visible-bars="45" default-theme="light" time-label-mode="datetime" />

    <div class="timeline-state">
      <div class="strategy-action">
        <div class="status-label">策略在本根的判断</div>
        <strong data-test="replay-signal">{{ actionLabel(frame.signal) }}</strong>
        <p>{{ frame.signalReason }}</p>
        <p v-if="frame.dailyTrigger">日线 {{ frame.dailySignalDate }} · {{ triggerLabels[frame.dailyTrigger] ?? frame.dailyTrigger }}</p>
        <p v-if="frame.pendingAction">待撮合 · {{ actionLabel(frame.pendingAction) }}</p>
        <p v-if="frame.minuteDkx!=null&&frame.minuteMadkx!=null">MACD {{ macdLabel(frame.minuteMacdCross) }} · DKX {{ number.format(frame.minuteDkx) }} / {{ number.format(frame.minuteMadkx) }}</p>
      </div>
      <dl class="frame-values">
        <div><dt>收盘 / MA20</dt><dd>{{ number.format(frame.close) }} / {{ frame.minuteMa20==null ? '—' : number.format(frame.minuteMa20) }}</dd></div>
        <div><dt>15 分钟方向</dt><dd>{{ trendLabel(frame.minuteTrend) }}</dd></div>
        <div><dt>持仓</dt><dd>{{ directionLabel(frame.direction) }}<template v-if="frame.lots"> {{ frame.lots }} 手<template v-if="frame.averagePrice!=null"> · 均价 {{ number.format(frame.averagePrice) }}</template></template></dd></div>
        <div><dt>当时权益</dt><dd>{{ number.format(frame.equity) }} 元</dd></div>
      </dl>
    </div>

    <div v-if="fills.length" class="current-fills" aria-label="本根模拟成交">
      <h5>本根成交</h5>
      <ul><li v-for="fill in fills" :key="fill.index">{{ actionLabel(fill.action) }} · {{ directionLabel(fill.direction) }} {{ fill.lots }} 手 · {{ number.format(fill.price) }} · {{ formatTradingDateTime(fill.at) }}</li></ul>
    </div>
    <ReplayReviewPanel v-if="reviewContext" :key="replay.reviewRunId"
      :context="reviewContext" :at="frame.at" :fills="reviewTargets" :busy="disabled" :workflow-id="version.workflowId"
      @pause="pause" @editing="reviewEditing=$event" />
    <p v-else class="timeline-missing">本次回放未返回可保存复盘的记录。可重新开始回放。</p>
  </section>
</template>

<style scoped>
.timeline { margin-block: .95rem; min-width: 0; }
.timeline-top,.timeline-controls { display: flex; align-items: center; flex-wrap: wrap; gap: .6rem; }
.timeline-top { justify-content: space-between; border-top: 2px solid var(--color-accent); padding: .8rem .2rem; }
.timeline-clock { display: grid; gap: .28rem; }
.timeline-clock span,.timeline-progress,.timeline-speed,.timeline-seek,.status-label,.frame-values dt { font-size: .72rem; color: var(--color-ink-secondary); }
.timeline-clock strong { font-size: 1.05rem; font-family: var(--font-numeric); }
.timeline-controls { margin-block: .4rem .75rem; }
.timeline-controls button { gap: .35rem; display: inline-flex; align-items: center; }
.timeline-controls button svg { flex: none; }
.timeline-speed { display: inline-flex; align-items: center; gap: .35rem; }
.timeline-seek { display: flex; align-items: center; gap: .55rem; margin-block: .5rem .75rem; }
.timeline-seek span { flex: none; }
.timeline-seek input { flex: 1; min-width: 3rem; accent-color: var(--color-accent); }
.timeline-state { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); margin-block: .8rem; border-block: 1px solid var(--color-line); }
.strategy-action { padding: .75rem .7rem .75rem .1rem; }
.strategy-action > strong { display: block; margin-top: .3rem; }
.strategy-action > p,.timeline-missing { font-size: .76rem; margin: .35rem 0; line-height: 1.6; color: var(--color-ink-secondary); }
.frame-values { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin: 0; padding: .75rem .2rem .75rem .7rem; border-left: 1px solid var(--color-line); }
.frame-values dd { margin: .22rem 0 0; font-size: .8rem; font-weight: 650; }
.current-fills { margin-block: .7rem; }
.current-fills h5 { margin: 0 0 .4rem; font-size: .8rem; }
.current-fills ul { margin: 0; padding-left: 1.15rem; font-size: .77rem; line-height: 1.8; }
@media (max-width: 620px) {
  .timeline-state { grid-template-columns: minmax(0,1fr); }
  .frame-values { border-left: 0; border-top: 1px solid var(--color-line); padding-left: .1rem; }
}
</style>
