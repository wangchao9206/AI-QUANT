<script setup lang="ts">
import { Search, TriangleAlert } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import AsyncState from '../components/AsyncState.vue'
import DataPanel from '../components/DataPanel.vue'
import FreshnessBadge from '../components/FreshnessBadge.vue'
import LineChart from '../components/LineChart.vue'
import { useDashboard } from '../composables/useDashboard'
import { formatNumber, formatPct, formatTime } from '../utils/format'

const { store, state, quote, history, termStructure, sourceMode, error } = useDashboard()
const query = ref(store.symbol)
const asyncState = computed(() => state.value === 'idle' ? 'loading' : state.value)
const values = computed(() => history.value?.points.map((point) => point.price) ?? [])
const termValues = computed(() => termStructure.value?.contracts.map((item) => item.price) ?? [])
function submit() { if (/^[A-Za-z]{1,4}[A-Za-z0-9]{0,8}$/.test(query.value.trim())) void store.load(query.value) }
</script>

<template>
  <div class="page-stack">
    <div class="section-intro">
      <p>从价格、历史轨迹和期限结构三个角度观察市场。所有数值都带有采集时间与可信状态。</p>
      <form class="symbol-search" role="search" @submit.prevent="submit">
        <label class="sr-only" for="symbol">合约代码</label>
        <Search :size="16" aria-hidden="true" />
        <input id="symbol" v-model="query" maxlength="12" pattern="[A-Za-z]{1,4}[A-Za-z0-9]{0,8}" placeholder="输入合约，如 RB2505" />
        <button type="submit">查询</button>
      </form>
    </div>
    <div v-if="sourceMode === 'demo' && state === 'ready'" class="demo-notice"><TriangleAlert :size="17" />演示快照，不代表当前市场。</div>

    <AsyncState :state="asyncState" :error-message="error" @retry="store.load()">
      <div v-if="quote && history && termStructure" class="page-grid">
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

        <DataPanel class="span-7" title="期限结构" eyebrow="Forward curve">
          <template #actions><FreshnessBadge :status="termStructure.dataStatus" :timestamp="termStructure.dataTimestamp" /></template>
          <LineChart :values="termValues" :height="180" :label="`${termStructure.rootSymbol}期限结构`" />
        </DataPanel>

        <DataPanel class="span-5" title="合约梯度" eyebrow="Contract ladder">
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>合约</th><th>到期日</th><th class="numeric">价格</th></tr></thead>
              <tbody><tr v-for="item in termStructure.contracts" :key="item.contract"><td><strong>{{ item.contract }}</strong></td><td>{{ item.maturityDate }}</td><td class="numeric">{{ formatNumber(item.price) }}</td></tr></tbody>
            </table>
          </div>
        </DataPanel>
      </div>
    </AsyncState>
  </div>
</template>

<style scoped>
.symbol-search { display: flex; min-width: min(100%, 21rem); align-items: center; gap: .55rem; padding: .35rem .4rem .35rem .75rem; border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); background: white; }
.symbol-search svg { color: var(--color-ink-tertiary); }
.symbol-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: .76rem; text-transform: uppercase; }
.symbol-search button { padding: .48rem .68rem; color: white; border: 0; border-radius: .45rem; background: var(--color-ink); font-size: .7rem; cursor: pointer; }
.quote-main { display: flex; align-items: baseline; gap: 1rem; margin-top: .6rem; }
.quote-main > strong { font: 500 clamp(2.6rem, 6vw, 4.2rem) var(--font-display); letter-spacing: -.07em; }
.quote-main > span { font: 650 .8rem var(--font-numeric); }
.instrument { margin: .1rem 0 1.4rem; color: var(--color-ink-secondary); font-size: .74rem; }
.quote-metrics { grid-template-columns: 1fr 1fr; margin-bottom: 1rem; }
.source-value { display: block; overflow: hidden; font-family: var(--font-sans) !important; font-size: .72rem !important; text-overflow: ellipsis; white-space: nowrap; }
</style>
