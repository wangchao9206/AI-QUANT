<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Play } from 'lucide-vue-next'
import { request } from '../services/api'
import { hasPermission } from '../services/auth'
import { formatNumber, formatPct, formatTradingDateTime } from '../utils/format'
import { currentScope } from '../utils/storageScope'

interface Ma20BacktestResult {
  symbol: string
  scope: { first: string; last: string; scoreDays: number }
  metrics: { netPnl: number; returnPct: number; maxDrawdownPct: number; closedTrades: number; fees: number; slippageCost: number }
  trades: { direction: number; entryAt: string; exitAt: string; entryPrice: number; exitPrice: number; netPnl: number; exitReason: string }[]
}

const archive = { symbol: 'FG701', first: '2026-10-19', last: '2026-11-16' }
const startDate = ref(archive.first)
const endDate = ref(archive.last)
const costMultiplier = ref<1 | 2>(1)
const result = ref<Ma20BacktestResult | null>(null)
const busy = ref(false)
const error = ref('')
const canRun = computed(() => hasPermission('research.write'))
const exitReasons: Record<string, string> = {
  STOP_GAP: '跳空触发止损', STOP: '固定止损', MEAN_REVERSAL: '反向偏离均线', DAY_END: '日内清仓',
}

watch([startDate, endDate, costMultiplier], () => {
  result.value = null
  error.value = ''
})

async function run() {
  if (busy.value || !canRun.value) return
  result.value = null
  error.value = ''
  if (startDate.value < archive.first || endDate.value > archive.last || startDate.value > endDate.value) {
    error.value = '请选择行情档案内有效的起止日期。'
    return
  }
  const scope = currentScope()
  busy.value = true
  try {
    const output = await request<Ma20BacktestResult>('/api/v1/research/ma20-macd/backtest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: archive.symbol, startDate: startDate.value, endDate: endDate.value, costMultiplier: costMultiplier.value }),
    }, 60000)
    if (currentScope() === scope) result.value = output
  } catch (cause) {
    if (currentScope() === scope) error.value = cause instanceof Error ? cause.message : '回测暂时无法完成。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page-stack ma20-page">
    <RouterLink class="ma20-back" to="/strategy"><ArrowLeft :size="15" aria-hidden="true" /> 返回策略中心</RouterLink>
    <section class="ma20-card">
      <h2>1分钟MA20＋日线MACD</h2>
      <p>用玻璃 FG701 的历史分钟线回测。日线 MACD 过滤方向，分钟突破触发入场，以固定一手和日内清仓规则模拟成交。</p>
      <form @submit.prevent="run">
        <fieldset :disabled="busy || !canRun">
          <label>起始日期<input v-model="startDate" type="date" :min="archive.first" :max="endDate" required /></label>
          <label>结束日期<input v-model="endDate" type="date" :min="startDate" :max="archive.last" required /></label>
          <label>交易成本<select v-model.number="costMultiplier"><option :value="1">基准成本</option><option :value="2">双倍成本</option></select></label>
          <button type="submit"><Play :size="15" aria-hidden="true" /> {{busy?'回测中…':'运行历史回测'}}</button>
        </fieldset>
      </form>
      <p v-if="!canRun">当前账号没有运行回测的权限。</p>
      <p v-if="error" class="ma20-error" role="alert">{{error}}</p>
      <RouterLink :to="{path:'/paper',query:{automation:'MA20_MACD'},hash:'#paper-automation'}">配置模拟盘执行</RouterLink>
    </section>

    <section v-if="result" class="ma20-card" aria-label="回测结果">
      <h2>回测结果</h2>
      <p>{{result.symbol}} · {{result.scope.first}} 至 {{result.scope.last}} · {{result.scope.scoreDays}} 个交易日</p>
      <dl>
        <div><dt>净损益</dt><dd>{{formatNumber(result.metrics.netPnl)}} 元</dd></div>
        <div><dt>累计收益率</dt><dd>{{formatPct(result.metrics.returnPct, 3)}}</dd></div>
        <div><dt>最大回撤</dt><dd>{{formatNumber(result.metrics.maxDrawdownPct, 3)}}%</dd></div>
        <div><dt>平仓笔数</dt><dd>{{result.metrics.closedTrades}}</dd></div>
      </dl>
      <div v-if="result.trades.length" class="ma20-trades">
        <table>
          <caption>逐笔成交</caption>
          <thead><tr><th scope="col">方向</th><th scope="col">开仓时间</th><th scope="col">开仓价</th><th scope="col">平仓时间</th><th scope="col">平仓价</th><th scope="col">净损益</th><th scope="col">平仓原因</th></tr></thead>
          <tbody>
            <tr v-for="trade in result.trades" :key="trade.entryAt"><td>{{trade.direction > 0 ? '多头' : '空头'}}</td><td>{{formatTradingDateTime(trade.entryAt)}}</td><td>{{formatNumber(trade.entryPrice)}}</td><td>{{formatTradingDateTime(trade.exitAt)}}</td><td>{{formatNumber(trade.exitPrice)}}</td><td>{{formatNumber(trade.netPnl)}} 元</td><td>{{exitReasons[trade.exitReason]??trade.exitReason}}</td></tr>
          </tbody>
        </table>
      </div>
      <p v-else>本次回测没有成交。</p>
    </section>
  </div>
</template>

<style scoped>
.ma20-page { min-width: 0; }
.ma20-back { display: inline-flex; align-items: center; gap: .4rem; }
a { color: var(--color-accent); font-size: .75rem; }
.ma20-card { min-width: 0; border: 1px solid var(--color-line); border-radius: .8rem; padding: 1.25rem; background: var(--color-surface-raised); }
h2 { margin: 0; font-size: 1rem; }
p, label, dt { color: var(--color-ink-secondary); font-size: .75rem; line-height: 1.75; }
fieldset { display: flex; flex-wrap: wrap; align-items: end; gap: .75rem; border: 0; padding: 0; margin: .9rem 0; }
label { display: grid; gap: .25rem; }
input, select, button { padding: .55rem .65rem; border: 1px solid var(--color-line); border-radius: .4rem; background: var(--color-surface); color: var(--color-ink); font: inherit; font-size: .76rem; }
button { display: inline-flex; align-items: center; gap: .35rem; background: var(--color-accent); color: white; cursor: pointer; }
fieldset:disabled { opacity: .6; }
.ma20-error { color: var(--color-warning); }
dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr)); gap: .8rem; }
dd { margin: .35rem 0 0; font: 600 .95rem var(--font-numeric); }
.ma20-trades { overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: .73rem; white-space: nowrap; }
caption { text-align: left; font-weight: 650; margin-bottom: .4rem; }
th, td { padding: .55rem; text-align: left; border-bottom: 1px solid var(--color-line); }
</style>
