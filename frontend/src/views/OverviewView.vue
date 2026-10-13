<script setup lang="ts">
import { ArrowDownRight, ArrowUpRight, Gauge, ShieldCheck, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { computed } from 'vue'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import DimensionBars from '../components/DimensionBars.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import LineChart from '../components/LineChart.vue'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatPct, formatTime } from '../utils/format'

const { store, state, quote, history, prediction, sourceMode, resourceErrors } = useDashboard()
const values = computed(() => history.value?.points.map((point) => point.price) ?? [])
const changePositive = computed(() => (quote.value?.change ?? 0) >= 0)
</script>

<template>
  <div class="page-stack">
    <div v-if="sourceMode === 'demo' && state === 'ready'" class="demo-notice" role="status">
      <TriangleAlert :size="17" aria-hidden="true" />
      实时服务未连接。当前展示开发环境演示快照，不用于交易决策。
    </div>

        <section class="hero">
          <div class="hero__copy">
            <AsyncState :state="store.panelState('quote')" :error-message="resourceErrors.quote" empty-message="行情采集中，尚无可信报价。" @retry="store.load()">
            <template v-if="quote">
            <div class="instrument-line">
              <span>{{ quote.symbol }}</span>
              <FreshnessBadge :status="quote.dataStatus" :timestamp="quote.dataTimestamp" />
            </div>
            <p class="hero__name">{{ quote.displayName }}</p>
            <div class="price-line">
              <strong>{{ formatNumber(quote.price) }}</strong>
              <span :class="changePositive ? 'positive' : 'negative'">
                <component :is="changePositive ? ArrowUpRight : ArrowDownRight" :size="19" aria-hidden="true" />
                {{ formatPct(quote.changePct) }}
              </span>
            </div>
            <p class="source-note">{{ quote.source }} · 数据时间 {{ formatTime(quote.dataTimestamp) }}</p>
            </template>
            </AsyncState>
          </div>

          <div class="decision">
            <AsyncState :state="store.panelState('prediction')" :error-message="resourceErrors.prediction" @retry="store.load()">
            <template v-if="prediction">
            <span>综合决策</span>
            <strong>{{ prediction.signal }}</strong>
            <p>{{ prediction.actionDirective }}</p>
            <div class="decision__score">
              <b>{{ Math.round(prediction.compositeScore) }}</b><span>/ 100</span>
            </div>
            </template>
            </AsyncState>
          </div>
        </section>

        <div class="page-grid">
          <DataPanel class="span-8" title="价格轨迹" eyebrow="历史日 K">
            <template #actions><span class="source-note">{{ values.length }} 个观测点</span></template>
            <AsyncState :state="store.panelState('history')" :error-message="resourceErrors.history" empty-message="历史行情采集中，尚无可信观测点。" @retry="store.load()">
            <LineChart :values="values" :label="`${store.symbol}价格走势`" :height="210" />
            </AsyncState>
          </DataPanel>

          <DataPanel class="span-4" title="执行边界" eyebrow="风险优先">
            <AsyncState :state="store.panelState('prediction')" :error-message="resourceErrors.prediction" @retry="store.load()">
            <template v-if="prediction">
            <div class="risk-list">
              <div><span><Sparkles :size="16" />目标价格</span><strong>{{ formatNumber(prediction.targetPrice) }}</strong></div>
              <div><span><ShieldCheck :size="16" />止损价格</span><strong>{{ formatNumber(prediction.stopLossPrice) }}</strong></div>
              <div><span><Gauge :size="16" />建议仓位</span><strong>{{ formatNumber(prediction.recommendedPositionPct * 100, 0) }}%</strong></div>
            </div>
            <p class="risk-note">边界随新数据重新计算；降级状态下仅作历史参考。</p>
            </template>
            </AsyncState>
          </DataPanel>

          <DataPanel class="span-7" title="核心维度" eyebrow="证据摘要">
            <template #actions><RouterLink to="/strategy" class="text-link">查看全部十一维</RouterLink></template>
            <AsyncState :state="store.panelState('prediction')" :error-message="resourceErrors.prediction" @retry="store.load()">
            <DimensionBars v-if="prediction" :dimensions="prediction.dimensions" :limit="5" />
            </AsyncState>
          </DataPanel>

          <DataPanel class="span-5" title="模型确信程度" eyebrow="共振评估">
            <AsyncState :state="store.panelState('prediction')" :error-message="resourceErrors.prediction" @retry="store.load()">
            <template v-if="prediction">
            <div class="confidence">
              <div class="confidence__value"><strong>{{ Math.round(prediction.confidence * 100) }}</strong><span>%</span></div>
              <div class="confidence__detail">
                <span>综合置信度</span>
                <div class="confidence__track"><i :style="{ width: `${prediction.confidence * 100}%` }" /></div>
              </div>
            </div>
            <div class="resonance"><span>方向共振</span><strong>{{ Math.round(prediction.resonance * 100) }}%</strong></div>
            <p class="model-meta">模型 {{ prediction.modelVersion }} · Trace {{ prediction.traceId.slice(0, 12) }}</p>
            </template>
            </AsyncState>
          </DataPanel>
        </div>
  </div>
</template>

<style scoped>
.hero { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(16rem, .7fr); min-height: 20rem; overflow: hidden; color: white; border-radius: 1.6rem; background: #1b1d20; box-shadow: 0 24px 60px rgb(24 25 27 / 16%); }
.hero__copy { align-self: end; padding: clamp(1.5rem, 5vw, 3.5rem); }
.instrument-line { display: flex; align-items: center; gap: var(--space-3); color: #aeb3b8; font: 700 .7rem var(--font-numeric); letter-spacing: .12em; }
.hero__name { margin: 1rem 0 .2rem; color: #d0d2d4; font-size: .82rem; }
.price-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 1rem; }
.price-line > strong { font: 500 clamp(3rem, 8vw, 6.6rem) var(--font-display); letter-spacing: -.07em; line-height: 1; }
.price-line > span { display: inline-flex; align-items: center; font: 650 .86rem var(--font-numeric); }
.hero .source-note { margin-top: 1.15rem; color: #8f949a; }
.decision { display: flex; flex-direction: column; justify-content: center; padding: clamp(1.5rem, 4vw, 3rem); border-left: 1px solid #34373b; background: #222428; }
.decision > span { color: #91969b; font-size: .66rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
.decision > strong { margin-top: .65rem; font-family: var(--font-display); font-size: clamp(1.7rem, 3vw, 2.5rem); font-weight: 500; }
.decision > p { margin: .7rem 0 1.8rem; color: #bec1c4; font-size: .78rem; line-height: 1.7; }
.decision__score b { font: 500 2.5rem var(--font-numeric); }
.decision__score span { margin-left: .3rem; color: #7f8489; font-size: .7rem; }
.hero :deep(.message strong) { color: #eceeef; }
.hero :deep(.message p) { color: #bec1c4; }
.risk-list { display: grid; gap: .25rem; }
.risk-list > div { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .85rem 0; border-bottom: 1px solid var(--color-line); }
.risk-list span { display: inline-flex; align-items: center; gap: .55rem; color: var(--color-ink-secondary); font-size: .74rem; }
.risk-list strong { font: 600 .9rem var(--font-numeric); }
.risk-note, .model-meta { margin: 1rem 0 0; color: var(--color-ink-tertiary); font-size: .67rem; line-height: 1.55; }
.text-link { color: var(--color-accent); font-size: .7rem; font-weight: 650; text-decoration: none; }
.confidence { display: flex; align-items: center; gap: 1.25rem; padding: 1rem 0 1.5rem; }
.confidence__value strong { font: 500 3rem var(--font-display); letter-spacing: -.06em; }
.confidence__value span { color: var(--color-ink-tertiary); }
.confidence__detail { flex: 1; color: var(--color-ink-secondary); font-size: .69rem; }
.confidence__track { height: 5px; margin-top: .55rem; overflow: hidden; border-radius: var(--radius-pill); background: #e5e2dc; }
.confidence__track i { display: block; height: 100%; background: var(--color-positive); }
.resonance { display: flex; justify-content: space-between; padding: .9rem 0; border-top: 1px solid var(--color-line); border-bottom: 1px solid var(--color-line); font-size: .76rem; }
.resonance strong { font-family: var(--font-numeric); }
@media (max-width: 720px) { .hero { grid-template-columns: 1fr; }.decision { border-top: 1px solid #34373b; border-left: 0; }.price-line > strong { font-size: 3.8rem; } }
</style>
