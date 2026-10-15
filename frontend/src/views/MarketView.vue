<script setup lang="ts">
import { computed } from 'vue'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import LineChart from '../components/LineChart.vue'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatPct, formatTime } from '../utils/format'

const { store, state, quote, history, termStructure, catalog, error } = useDashboard()
const asyncState = computed(() => state.value === 'idle' ? 'loading' : state.value)
const values = computed(() => history.value?.points.map((point) => point.price) ?? [])
const termValues = computed(() => termStructure.value?.contracts.map((item) => item.price) ?? [])
const instrumentCount = computed(() => catalog.value?.exchanges.reduce((sum, group) => sum + group.instruments.length, 0) ?? 0)
const contractCount = computed(() => catalog.value?.exchanges.reduce((sum, group) => sum + group.instruments.reduce((count, item) => count + item.contracts.length, 0), 0) ?? 0)
</script>

<template>
  <div class="page-stack">
    <div class="section-intro">
      <p>从价格、历史轨迹和期限结构三个角度观察市场。使用页面顶部或左侧关注市场切换品种，所有数值都带有采集时间与可信状态。</p>
    </div>
    <div v-if="catalog" class="coverage-strip" aria-label="国内期货覆盖范围">
      <div><strong>{{ catalog.exchanges.length }}</strong><span>交易所</span></div>
      <div><strong>{{ instrumentCount }}</strong><span>期货品种</span></div>
      <div><strong>{{ contractCount }}</strong><span>当前挂牌合约</span></div>
      <div class="coverage-exchanges"><span v-for="group in catalog.exchanges" :key="group.code">{{ group.code }}</span></div>
      <FreshnessBadge :status="catalog.dataStatus" :timestamp="catalog.dataTimestamp" />
    </div>
    <AsyncState :state="asyncState" :error-message="error" @retry="store.load()">
      <div v-if="quote && history" class="page-grid">
        <DataPanel class="span-4" title="当前报价" eyebrow="Market snapshot">
          <template #actions><FreshnessBadge :status="quote.dataStatus" :timestamp="quote.dataTimestamp" /></template>
          <div class="quote-main"><strong>{{ formatNumber(quote.price) }}</strong><span :class="quote.change >= 0 ? 'positive' : 'negative'">{{ formatPct(quote.changePct) }}</span></div>
          <p class="instrument">{{ quote.displayName }} · {{ quote.symbol }}</p>
          <div class="metric-grid quote-metrics">
            <div class="metric"><span>涨跌</span><strong>{{ formatNumber(quote.change) }}</strong></div>
            <div class="metric"><span>来源</span><strong class="source-value">{{ quote.source }}</strong></div>
          </div>
          <p class="source-note">更新于 {{ formatTime(quote.dataTimestamp) }}</p>
        </DataPanel>

        <DataPanel class="span-8" title="历史价格" eyebrow="Observed series">
          <template #actions><FreshnessBadge :status="history.dataStatus" :timestamp="history.dataTimestamp" /></template>
          <LineChart :values="values" :height="220" :label="`${history.symbol}历史价格`" />
        </DataPanel>

        <DataPanel v-if="termStructure" class="span-7" title="期限结构" eyebrow="Forward curve">
          <template #actions><FreshnessBadge :status="termStructure.dataStatus" :timestamp="termStructure.dataTimestamp" /></template>
          <LineChart :values="termValues" :height="180" :label="`${termStructure.rootSymbol}期限结构`" />
        </DataPanel>

        <DataPanel v-if="termStructure" class="span-5" title="合约梯度" eyebrow="Contract ladder">
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>合约</th><th>交割月</th><th class="numeric">价格</th></tr></thead>
              <tbody><tr v-for="item in termStructure.contracts" :key="item.contract"><td><strong>{{ item.contract }}</strong></td><td>{{ item.maturityDate }}</td><td class="numeric">{{ formatNumber(item.price) }}</td></tr></tbody>
            </table>
          </div>
        </DataPanel>
        <DataPanel v-else class="span-12" title="期限结构" eyebrow="Forward curve unavailable">
          <p class="empty-curve">当前品种没有足够的已观测挂牌合约形成期限曲线；报价与十一维分析仍使用真实行情独立计算。</p>
        </DataPanel>
      </div>
    </AsyncState>
  </div>
</template>

<style scoped>
.coverage-strip { display: flex; align-items: center; gap: 1.5rem; padding: .8rem 1rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: rgb(255 255 255 / 55%); }
.coverage-strip > div:not(.coverage-exchanges) { display: grid; gap: .08rem; }
.coverage-strip strong { font: 600 .9rem var(--font-numeric); }
.coverage-strip div > span { color: var(--color-ink-tertiary); font-size: .6rem; }
.coverage-exchanges { display: flex; flex: 1; flex-wrap: wrap; gap: .35rem; }
.coverage-exchanges span { padding: .25rem .42rem; border-radius: var(--radius-pill); background: #ece9e2; font: 650 .58rem var(--font-numeric); }
.empty-curve { margin: 0; color: var(--color-ink-secondary); font-size: .74rem; line-height: 1.7; }
.quote-main { display: flex; align-items: baseline; gap: 1rem; margin-top: .6rem; }
.quote-main > strong { font: 500 clamp(2.6rem, 6vw, 4.2rem) var(--font-display); letter-spacing: -.07em; }
.quote-main > span { font: 650 .8rem var(--font-numeric); }
.instrument { margin: .1rem 0 1.4rem; color: var(--color-ink-secondary); font-size: .74rem; }
.quote-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 1rem; }
.source-value { display: block; overflow: hidden; font-family: var(--font-sans) !important; font-size: .72rem !important; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 700px) { .coverage-strip { align-items: flex-start; flex-wrap: wrap; }.coverage-exchanges { order: 5; flex-basis: 100%; } }
</style>
